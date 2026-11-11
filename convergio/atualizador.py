"""Atualização automática: consulta o versao.json da última Release no GitHub, baixa o instalador
(com o próprio motor acelerado), confere o SHA-256, instala em modo silencioso e reabre o programa."""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

from PySide6.QtCore import QThread, QTimer, Signal
from PySide6.QtWidgets import (QApplication, QDialog, QHBoxLayout, QLabel, QMessageBox, QProgressBar,
                               QPushButton, QTextBrowser, QVBoxLayout)

from . import APP_NAME, UPDATE_REPO, __version__
from .motor import CONCLUIDO, ERRO, Download, fmt_bytes

URL_VERSAO = f"https://github.com/{UPDATE_REPO}/releases/latest/download/versao.json"
ARGS_INSTALADOR = ["/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"]


def vtuple(v):
    return tuple(int(x) for x in re.findall(r"\d+", v)[:4])


def buscar_info(timeout=10):
    req = urllib.request.Request(URL_VERSAO, headers={"User-Agent": f"{APP_NAME}/{__version__}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


class ThreadVerificar(QThread):
    resultado = Signal(object, str)

    def run(self):
        try:
            self.resultado.emit(buscar_info(), "")
        except Exception as e:  # noqa: BLE001
            self.resultado.emit(None, str(e))


def sha256(caminho):
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def executar_instalador(caminho):
    """Agenda o instalador para depois que o programa fechar (ele reabre o programa ao terminar)."""
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        subprocess.Popen([caminho] + ARGS_INSTALADOR)
        return
    subprocess.Popen([sys.executable, "--run-update", caminho, str(os.getpid())], close_fds=True,
                     creationflags=0x00000008 | 0x00000200)  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP


def ajudante_atualizacao(argv):
    """Convergio.exe --run-update <instalador> <pid>: espera o programa fechar e inicia a instalação."""
    i = argv.index("--run-update")
    caminho = argv[i + 1]
    pid = int(argv[i + 2]) if len(argv) > i + 2 else 0
    if sys.platform == "win32" and pid:
        import ctypes
        h = ctypes.windll.kernel32.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
        if h:
            ctypes.windll.kernel32.WaitForSingleObject(h, 60000)
            ctypes.windll.kernel32.CloseHandle(h)
    time.sleep(0.5)
    subprocess.Popen([caminho] + ARGS_INSTALADOR, close_fds=True)
    return 0


class DialogoAtualizacao(QDialog):
    def __init__(self, janela, info):
        super().__init__(janela)
        self.janela, self.info = janela, info
        self.setWindowTitle(f"Atualização do {APP_NAME}")
        self.setMinimumWidth(500)
        inst = info["instalador"]
        self.url, self.sha = inst["url"], inst["sha256"]
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"<h3 style='margin:0'>Nova versão disponível: {info['versao']}</h3>"
                             f"<p>Você está usando a versão {__version__}.</p>"))
        notas = QTextBrowser()
        notas.setMarkdown(info.get("novidades") or "Melhorias e correções.")
        notas.setMaximumHeight(200)
        lay.addWidget(QLabel("<b>Novidades</b>"))
        lay.addWidget(notas)
        dica = QLabel(f"Será baixado o instalador ({fmt_bytes(inst.get('tamanho'))}). "
                      f"O {APP_NAME} será fechado, atualizado e aberto de novo — downloads em andamento "
                      "são pausados e continuam depois.")
        dica.setWordWrap(True)
        dica.setObjectName("Muted")
        lay.addWidget(dica)
        self.barra = QProgressBar(maximum=1000)
        self.barra.hide()
        lay.addWidget(self.barra)
        linha = QHBoxLayout()
        self.bt_pular = QPushButton("Pular esta versão")
        self.bt_depois = QPushButton("Lembrar depois")
        self.bt_agora = QPushButton("Atualizar agora")
        self.bt_agora.setObjectName("Primary")
        linha.addWidget(self.bt_pular)
        linha.addStretch()
        linha.addWidget(self.bt_depois)
        linha.addWidget(self.bt_agora)
        lay.addLayout(linha)
        self.bt_pular.clicked.connect(self._pular)
        self.bt_depois.clicked.connect(self.reject)
        self.bt_agora.clicked.connect(self._iniciar)
        self.dl: Download | None = None
        self.timer = QTimer(self, interval=300, timeout=self._acompanhar)

    def _pular(self):
        self.janela.settings.setValue("pular_versao", self.info["versao"])
        self.reject()

    def _iniciar(self):
        if sys.platform != "win32" or not getattr(sys, "frozen", False):
            QMessageBox.information(self, APP_NAME, "A atualização automática funciona no programa instalado.\n"
                                                    f"Baixe manualmente em:\n{self.url}")
            return
        for b in (self.bt_pular, self.bt_depois, self.bt_agora):
            b.setEnabled(False)
        self.barra.show()
        pasta = os.path.join(tempfile.gettempdir(), "Convergio-atualizacao")
        shutil.rmtree(pasta, ignore_errors=True)
        self.dl = Download(self.url, pasta, 8)
        self.dl.iniciar()
        self.timer.start()

    def _acompanhar(self):
        d = self.dl
        if d.progresso >= 0:
            self.barra.setValue(int(d.progresso * 1000))
        if d.status == ERRO:
            self.timer.stop()
            self._falhou(d.erro)
        elif d.status == CONCLUIDO:
            self.timer.stop()
            if sha256(d.caminho).lower() != self.sha.lower():
                os.remove(d.caminho)
                self._falhou("O arquivo baixado está corrompido (SHA-256 não confere). Tente novamente.")
                return
            self.accept()
            self.janela.fechar_para_atualizar()
            executar_instalador(d.caminho)
            QApplication.instance().quit()

    def _falhou(self, erro):
        QMessageBox.critical(self, APP_NAME, f"Não foi possível baixar a atualização:\n{erro}")
        for b in (self.bt_pular, self.bt_depois, self.bt_agora):
            b.setEnabled(True)
        self.barra.hide()

    def reject(self):
        if self.dl:
            self.dl.pausar()
        self.timer.stop()
        super().reject()


class Atualizador:
    def __init__(self, janela):
        self.janela = janela
        self.th = None
        self._mostrando = False
        self._timer = None

    def verificar_auto(self):
        """Verifica ao abrir e depois a cada 4 horas enquanto o programa estiver aberto."""
        if self.janela.settings.value("auto_atualizar", "true") == "false":
            return
        self.verificar(silencioso=True)
        if not self._timer:
            self._timer = QTimer(self.janela, interval=4 * 3600 * 1000, timeout=lambda: self.verificar(True))
            self._timer.start()

    def verificar(self, silencioso=False):
        if self.th and self.th.isRunning():
            return
        self.th = ThreadVerificar()
        self.th.resultado.connect(lambda info, err: self._resultado(info, err, silencioso))
        self.th.start()
        if not silencioso:
            self.janela.statusBar().showMessage("Verificando atualizações…", 4000)

    def _resultado(self, info, err, silencioso):
        if err or not info:
            if not silencioso:
                QMessageBox.warning(self.janela, APP_NAME, f"Não foi possível verificar atualizações.\n{err}")
            return
        nova = info.get("versao", "0")
        if vtuple(nova) <= vtuple(__version__):
            if not silencioso:
                QMessageBox.information(self.janela, APP_NAME,
                                        f"Você já está usando a versão mais recente ({__version__}).")
            return
        if silencioso and self.janela.settings.value("pular_versao", "") == nova:
            return
        if self._mostrando:
            return
        self._mostrando = True
        try:
            DialogoAtualizacao(self.janela, info).exec()
        finally:
            self._mostrando = False
