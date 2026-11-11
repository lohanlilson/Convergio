"""Recursos extras da janela principal: configurações, navegadores, vários links, menu de contexto,
atualizar link, aviso ao terminar, limite de velocidade e agendamento."""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time

from PySide6.QtCore import QDateTime, Qt, QTime, QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QGuiApplication, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QLineEdit, QMenu, QMessageBox, QPlainTextEdit, QPushButton, QSpinBox, QTabWidget, QTimeEdit,
    QVBoxLayout, QWidget,
)

from . import APP_NAME, resource, tema
from .motor import BAIXANDO, CATEGORIAS, CONCLUIDO, ERRO, LIMITADOR, NA_FILA, PAUSADO, fmt_bytes

RE_LINKS = re.compile(r"https?://[^\s<>\"']+", re.I)
AO_TERMINAR = (("nada", "Não fazer nada"), ("fechar", "Fechar o Convergio"),
               ("suspender", "Suspender o computador"), ("desligar", "Desligar o computador"))


def _icone() -> QIcon:
    return QIcon(resource("assets", "convergio.ico"))


def _logo(tamanho: int) -> QPixmap:
    return QPixmap(resource("assets", "convergio.png")).scaled(tamanho, tamanho, Qt.KeepAspectRatio,
                                                               Qt.SmoothTransformation)


def mostrar_na_pasta(caminho: str):
    """Abre a pasta com o arquivo selecionado (no Windows) ou só a pasta."""
    if sys.platform == "win32" and os.path.exists(caminho):
        subprocess.Popen(["explorer", "/select,", os.path.normpath(caminho)])
    else:
        QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(caminho) or caminho))


# ------------------------------------------------------------------ navegadores instalados
NAVEGADORES = (
    # nome (igual ao que a extensão informa), executável, pastas comuns, página de extensões, compatível
    ("Chrome", "chrome.exe", (r"Google\Chrome\Application",), "chrome://extensions", True),
    ("Edge", "msedge.exe", (r"Microsoft\Edge\Application",), "edge://extensions", True),
    ("Brave", "brave.exe", (r"BraveSoftware\Brave-Browser\Application",), "brave://extensions", True),
    ("Opera", "opera.exe", (r"Programs\Opera", "Opera"), "opera://extensions", True),
    ("Vivaldi", "vivaldi.exe", (r"Vivaldi\Application",), "vivaldi://extensions", True),
    ("Firefox", "firefox.exe", ("Mozilla Firefox",), "about:addons", False),
)


def navegadores_instalados() -> list[dict]:
    achados = []
    if sys.platform != "win32":
        return achados
    import winreg
    for nome, exe, pastas, pagina, compativel in NAVEGADORES:
        caminho = ""
        for raiz in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                with winreg.OpenKey(raiz, rf"Software\Microsoft\Windows\CurrentVersion\App Paths\{exe}") as k:
                    caminho = winreg.QueryValue(k, None).strip('"')
                    if os.path.exists(caminho):
                        break
                    caminho = ""
            except OSError:
                pass
        if not caminho:
            for base in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
                for pasta in pastas:
                    c = os.path.join(os.environ.get(base, ""), pasta, exe)
                    if os.path.exists(c):
                        caminho = c
                        break
                if caminho:
                    break
        if caminho:
            achados.append({"nome": nome, "exe": caminho, "pagina": pagina, "compativel": compativel})
    return achados


# ------------------------------------------------------------------ diálogos
class DialogoVariosLinks(QDialog):
    def __init__(self, janela, texto=""):
        super().__init__(janela)
        self.setWindowTitle("Adicionar vários links")
        self.setMinimumSize(620, 380)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Cole os links, um por linha (texto em volta dos links é ignorado):"))
        self.ed = QPlainTextEdit(texto)
        self.ed.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.ed.textChanged.connect(self._contar)
        lay.addWidget(self.ed, 1)
        self.ck_pausado = QCheckBox("Adicionar pausados (para iniciar depois ou pelo agendamento)")
        lay.addWidget(self.ck_pausado)
        linha = QHBoxLayout()
        self.lb = QLabel(objectName="Muted")
        linha.addWidget(self.lb)
        linha.addStretch()
        cancelar = QPushButton("Cancelar")
        cancelar.clicked.connect(self.reject)
        self.bt = QPushButton("Adicionar", objectName="Primary")
        self.bt.clicked.connect(self.accept)
        linha.addWidget(cancelar)
        linha.addWidget(self.bt)
        lay.addLayout(linha)
        self._contar()

    def links(self) -> list[str]:
        vistos, saida = set(), []
        for u in RE_LINKS.findall(self.ed.toPlainText()):
            u = u.rstrip(".,;)")
            if u not in vistos:
                vistos.add(u)
                saida.append(u)
        return saida

    def _contar(self):
        n = len(self.links())
        self.lb.setText(f"{n} link(s) encontrado(s)")
        self.bt.setEnabled(n > 0)


class DialogoAtualizarLink(QDialog):
    """Troca o endereço de um download cujo link expirou, mantendo o que já foi baixado."""

    def __init__(self, janela, download):
        super().__init__(janela)
        self.janela, self.download = janela, download
        self.setWindowTitle("Atualizar link do download")
        self.setMinimumWidth(580)
        self.setAttribute(Qt.WA_DeleteOnClose)
        lay = QVBoxLayout(self)
        feito = f" ({fmt_bytes(download.baixado)} já baixados serão mantidos)" if download.baixado else ""
        texto = QLabel(f"<b>{download.nome or download.url}</b>{feito}"
                       "<p>Alguns sites geram links que valem por pouco tempo. Para continuar de onde parou:</p>"
                       "<p><b>1.</b> Volte à página do download e clique para baixar de novo no navegador. "
                       "O Convergio usa o link novo neste download automaticamente.<br>"
                       "<b>2.</b> Ou cole o link novo abaixo.</p>")
        texto.setWordWrap(True)
        lay.addWidget(texto)
        origem = download.headers_extra.get("Referer", "")
        if origem:
            bt_pagina = QPushButton("Abrir a página do download")
            bt_pagina.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(origem)))
            lay.addWidget(bt_pagina, 0, Qt.AlignLeft)
        self.ed = QLineEdit(placeholderText="Cole aqui o link novo (http/https)…")
        lay.addWidget(self.ed)
        self.lb = QLabel("Aguardando o navegador enviar o link novo…", objectName="Muted")
        lay.addWidget(self.lb)
        linha = QHBoxLayout()
        linha.addStretch()
        cancelar = QPushButton("Cancelar")
        cancelar.clicked.connect(self.reject)
        usar = QPushButton("Usar o link colado", objectName="Primary")
        usar.clicked.connect(self._usar)
        linha.addWidget(cancelar)
        linha.addWidget(usar)
        lay.addLayout(linha)
        janela._aguardando_link = download

    def _usar(self):
        url = self.ed.text().strip()
        if not re.match(r"^https?://\S+$", url, re.I):
            QMessageBox.warning(self, APP_NAME, "Cole um link começando com http:// ou https://")
            return
        self.janela.aplicar_link_novo(self.download, url, {})
        self.accept()

    def done(self, r):
        if self.janela._aguardando_link is self.download:
            self.janela._aguardando_link = None
        super().done(r)


class AvisoConcluido(QFrame):
    """Cartão no canto da tela quando um download termina, com Abrir e Abrir pasta."""
    abertos: list["AvisoConcluido"] = []

    def __init__(self, download):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setObjectName("Aviso")
        c = tema.atual
        self.setStyleSheet(f"QFrame#Aviso {{ background: {c['panel']}; border: 1px solid {c['accent']}; "
                           "border-radius: 12px; }")
        self.setFixedWidth(380)
        lay = QGridLayout(self)
        lay.setContentsMargins(14, 12, 12, 12)
        logo = QLabel()
        logo.setPixmap(_logo(36))
        lay.addWidget(logo, 0, 0, 2, 1, Qt.AlignTop)
        titulo = QLabel("<b>Download concluído</b>")
        lay.addWidget(titulo, 0, 1)
        fechar = QPushButton("✕")
        fechar.setFixedSize(26, 24)
        fechar.setStyleSheet("padding: 0;")
        fechar.clicked.connect(self.close)
        lay.addWidget(fechar, 0, 2, Qt.AlignRight)
        nome = download.nome or ""
        lb = QLabel((nome if len(nome) < 46 else nome[:30] + "…" + nome[-13:]) + f"  ·  {fmt_bytes(download.tamanho)}")
        lb.setObjectName("Muted")
        lb.setToolTip(download.caminho or "")
        lay.addWidget(lb, 1, 1, 1, 2)
        linha = QHBoxLayout()
        abrir = QPushButton("Abrir", objectName="Primary")
        abrir.clicked.connect(lambda: (QDesktopServices.openUrl(QUrl.fromLocalFile(download.caminho)), self.close()))
        pasta = QPushButton("Abrir pasta")
        pasta.clicked.connect(lambda: (mostrar_na_pasta(download.caminho), self.close()))
        linha.addWidget(abrir)
        linha.addWidget(pasta)
        linha.addStretch()
        lay.addLayout(linha, 2, 1, 1, 2)
        lay.setColumnStretch(1, 1)
        QTimer.singleShot(10000, self.close)

    def mostrar(self):
        AvisoConcluido.abertos = [a for a in AvisoConcluido.abertos if a.isVisible()]
        self.adjustSize()
        tela = QGuiApplication.primaryScreen().availableGeometry()
        y = tela.bottom() - 16 - sum(a.height() + 10 for a in AvisoConcluido.abertos) - self.height()
        self.move(tela.right() - self.width() - 16, max(tela.top() + 10, y))
        AvisoConcluido.abertos.append(self)
        self.show()

    def closeEvent(self, ev):
        if self in AvisoConcluido.abertos:
            AvisoConcluido.abertos.remove(self)
        super().closeEvent(ev)


class DialogoContagem(QDialog):
    """Contagem regressiva antes de fechar/suspender/desligar ao terminar os downloads."""

    def __init__(self, janela, acao: str, segundos: int = 30):
        super().__init__(janela, Qt.WindowStaysOnTopHint)
        self.setWindowTitle(APP_NAME)
        self.acao, self.resta = acao, segundos
        self.texto = {"fechar": "O Convergio será fechado", "suspender": "O computador será suspenso",
                      "desligar": "O computador será desligado"}[acao]
        lay = QVBoxLayout(self)
        self.lb = QLabel()
        lay.addWidget(self.lb)
        cancelar = QPushButton("Cancelar", objectName="Primary")
        cancelar.clicked.connect(self.reject)
        lay.addWidget(cancelar, 0, Qt.AlignRight)
        self.timer = QTimer(self, interval=1000, timeout=self._tick)
        self.timer.start()
        self._tick()

    def _tick(self):
        if self.resta <= 0:
            self.timer.stop()
            self.accept()
            return
        self.lb.setText(f"<b>Todos os downloads terminaram.</b><br>{self.texto} em {self.resta} segundos.")
        self.resta -= 1


class DialogoConfiguracoes(QDialog):
    ABA_NAVEGADORES = 2

    def __init__(self, janela, aba: int = 0):
        super().__init__(janela)
        self.j = janela
        s = janela.settings
        self.setWindowTitle("Configurações")
        self.setMinimumSize(640, 470)
        lay = QVBoxLayout(self)
        self.abas = QTabWidget()
        lay.addWidget(self.abas, 1)

        # ---------------- Geral
        g = QWidget()
        f = QFormLayout(g)
        self.ck_iniciar = QCheckBox("Iniciar com o Windows, em segundo plano")
        self.ck_iniciar.setChecked(janela.act_iniciar.isChecked())
        f.addRow(self.ck_iniciar)
        self.cb_fechar = QComboBox()
        self.cb_fechar.addItem("Continuar em segundo plano (perto do relógio)", "bandeja")
        self.cb_fechar.addItem("Fechar o programa", "sair")
        self.cb_fechar.setCurrentIndex(0 if janela.acao_fechar == "bandeja" else 1)
        f.addRow("Ao clicar em fechar (X):", self.cb_fechar)
        self.cb_tema = QComboBox()
        for chave, nome in (("auto", "Igual ao Windows"), ("claro", "Claro"), ("escuro", "Escuro")):
            self.cb_tema.addItem(nome, chave)
        self.cb_tema.setCurrentIndex(max(0, self.cb_tema.findData(s.value("tema", "auto"))))
        f.addRow("Tema:", self.cb_tema)
        self.ck_atualizar = QCheckBox("Verificar atualizações automaticamente")
        self.ck_atualizar.setChecked(s.value("auto_atualizar", "true") != "false")
        f.addRow(self.ck_atualizar)
        self.ck_aviso = QCheckBox("Mostrar um aviso quando um download terminar")
        self.ck_aviso.setChecked(s.value("aviso_concluir", "true") != "false")
        f.addRow(self.ck_aviso)
        self.ck_clip = QCheckBox("Capturar links de arquivos copiados para a área de transferência")
        self.ck_clip.setChecked(janela.ck_clip.isChecked())
        f.addRow(self.ck_clip)
        self.abas.addTab(g, "Geral")

        # ---------------- Downloads
        d = QWidget()
        f = QFormLayout(d)
        lp = QHBoxLayout()
        self.ed_pasta = QLineEdit(janela.ed_pasta.text())
        bt = QPushButton("Escolher…")
        bt.clicked.connect(self._pasta)
        lp.addWidget(self.ed_pasta, 1)
        lp.addWidget(bt)
        f.addRow("Salvar em:", lp)
        self.ck_tipo = QCheckBox("Separar em subpastas por tipo de arquivo")
        self.ck_tipo.setChecked(s.value("por_tipo", "true") != "false")
        f.addRow(self.ck_tipo)
        tipos = QLabel("   " + " · ".join(CATEGORIAS) + " (os outros tipos ficam na pasta principal)", objectName="Muted")
        tipos.setWordWrap(True)
        f.addRow(tipos)
        self.sp_con = QSpinBox(minimum=1, maximum=32, value=janela.sp_con.value())
        self.sp_con.setMaximumWidth(90)
        f.addRow("Conexões por arquivo:", self.sp_con)
        self.sp_sim = QSpinBox(minimum=1, maximum=10, value=janela.sp_sim.value())
        self.sp_sim.setMaximumWidth(90)
        f.addRow("Downloads simultâneos:", self.sp_sim)
        ll = QHBoxLayout()
        self.ck_limite = QCheckBox("Limitar a velocidade total a")
        self.ck_limite.setChecked(s.value("limite_ativo", "false") == "true")
        self.sp_limite = QSpinBox(minimum=50, maximum=1000000, singleStep=100, value=int(s.value("limite_kb", 1024)))
        self.sp_limite.setSuffix(" KB/s")
        ll.addWidget(self.ck_limite)
        ll.addWidget(self.sp_limite)
        ll.addStretch()
        f.addRow(ll)
        self.abas.addTab(d, "Downloads")

        # ---------------- Navegadores
        n = QWidget()
        v = QVBoxLayout(n)
        v.addWidget(QLabel("<b>Navegadores encontrados neste computador</b>"))
        self.grade = QGridLayout()
        v.addLayout(self.grade)
        self.lb_passos = QLabel(objectName="Muted")
        self.lb_passos.setWordWrap(True)
        v.addWidget(self.lb_passos)
        self.bt_caminho = QPushButton("Copiar caminho da extensão")
        self.bt_caminho.clicked.connect(self._copiar_caminho)
        self.bt_caminho.hide()
        v.addWidget(self.bt_caminho, 0, Qt.AlignLeft)
        self.ck_capturar = QCheckBox("Capturar os downloads dos navegadores vinculados")
        self.ck_capturar.setChecked(janela.act_capturar.isChecked())
        v.addWidget(self.ck_capturar)
        self.ck_perguntar = QCheckBox("Perguntar nome e pasta antes de baixar")
        self.ck_perguntar.setChecked(janela.act_perguntar.isChecked())
        v.addWidget(self.ck_perguntar)
        v.addStretch()
        self.abas.addTab(n, "Navegadores")
        self._rotulos = {}
        self._montar_navegadores()
        self._timer = QTimer(self, interval=1500, timeout=self._atualizar_navegadores)
        self._timer.start()

        # ---------------- Agendamento
        a = QWidget()
        f = QFormLayout(a)
        l1 = QHBoxLayout()
        self.ck_inicio = QCheckBox("Iniciar os downloads pausados todos os dias às")
        self.ck_inicio.setChecked(s.value("agenda_inicio_ativa", "false") == "true")
        self.tm_inicio = QTimeEdit(QTime.fromString(s.value("agenda_inicio", "02:00"), "HH:mm"))
        self.tm_inicio.setDisplayFormat("HH:mm")
        l1.addWidget(self.ck_inicio)
        l1.addWidget(self.tm_inicio)
        l1.addStretch()
        f.addRow(l1)
        l2 = QHBoxLayout()
        self.ck_fim = QCheckBox("Pausar todos os downloads todos os dias às")
        self.ck_fim.setChecked(s.value("agenda_fim_ativa", "false") == "true")
        self.tm_fim = QTimeEdit(QTime.fromString(s.value("agenda_fim", "07:00"), "HH:mm"))
        self.tm_fim.setDisplayFormat("HH:mm")
        l2.addWidget(self.ck_fim)
        l2.addWidget(self.tm_fim)
        l2.addStretch()
        f.addRow(l2)
        self.cb_terminar = QComboBox()
        for chave, nome in AO_TERMINAR:
            self.cb_terminar.addItem(nome, chave)
        self.cb_terminar.setCurrentIndex(max(0, self.cb_terminar.findData(janela.ao_terminar)))
        f.addRow("Quando todos os downloads terminarem:", self.cb_terminar)
        f.addRow(QLabel("Essa última opção vale só para a próxima vez; depois volta para \"Não fazer nada\".\n"
                        "O agendamento funciona com o Convergio aberto ou em segundo plano.", objectName="Muted"))
        self.abas.addTab(a, "Agendamento")

        linha = QHBoxLayout()
        linha.addStretch()
        cancelar = QPushButton("Cancelar")
        cancelar.clicked.connect(self.reject)
        ok = QPushButton("Salvar", objectName="Primary")
        ok.setDefault(True)
        ok.clicked.connect(self._salvar)
        linha.addWidget(cancelar)
        linha.addWidget(ok)
        lay.addLayout(linha)
        self.abas.setCurrentIndex(aba)

    # -------- navegadores
    def _montar_navegadores(self):
        lista = navegadores_instalados()
        self._navegadores = lista
        if not lista:
            self.grade.addWidget(QLabel("Nenhum navegador compatível foi encontrado.", objectName="Muted"), 0, 0)
        for i, nav in enumerate(lista):
            self.grade.addWidget(QLabel(f"<b>{nav['nome']}</b>"), i, 0)
            estado = QLabel()
            self._rotulos[nav["nome"]] = estado
            self.grade.addWidget(estado, i, 1)
            if nav["compativel"]:
                bt = QPushButton("Vincular")
                bt.clicked.connect(lambda _=False, x=nav: self._vincular(x))
                self.grade.addWidget(bt, i, 2)
        self.grade.setColumnStretch(1, 1)
        self._atualizar_navegadores()

    def _atualizar_navegadores(self):
        c = tema.atual
        contatos = self.j.servidor.contatos
        for nav in self._navegadores:
            lb = self._rotulos[nav["nome"]]
            if not nav["compativel"]:
                lb.setText(f"<span style='color:{c['muted']}'>ainda não compatível</span>")
                continue
            quando, versao = contatos.get(nav["nome"], (0, ""))
            if time.time() - quando < 150:
                lb.setText(f"<span style='color:{c['ok']}'>✓ vinculado e conectado"
                           f"{' (extensão ' + versao + ')' if versao and versao != 'antiga' else ''}</span>")
            elif nav["nome"] in self.j.navegadores_vinculados():
                lb.setText(f"<span style='color:{c['muted']}'>vinculado (navegador fechado)</span>")
            else:
                lb.setText(f"<span style='color:{c['muted']}'>não vinculado</span>")

    def _vincular(self, nav):
        # os navegadores não deixam abrir a página de extensões por fora; o endereço vai para a área de
        # transferência e a pessoa cola na barra de endereço
        QGuiApplication.clipboard().setText(nav["pagina"])
        try:
            subprocess.Popen([nav["exe"]])
        except OSError as e:
            QMessageBox.warning(self, APP_NAME, f"Não foi possível abrir o {nav['nome']}:\n{e}")
            return
        self.lb_passos.setText(
            f"O {nav['nome']} foi aberto. Faça uma vez só:\n"
            f"1. Na barra de endereço, cole (Ctrl+V) e dê Enter: {nav['pagina']}  (já está copiado)\n"
            "2. Ative o \"Modo do desenvolvedor\", no canto da página, e clique em \"Carregar sem compactação\".\n"
            "3. Clique no botão abaixo para copiar o caminho da extensão, cole na barra de endereço da janela "
            "que abriu, dê Enter e clique em \"Selecionar pasta\".\n"
            "Quando a extensão conectar, o estado acima muda para \"vinculado e conectado\".")
        self.bt_caminho.show()

    def _copiar_caminho(self):
        from .janela import pasta_extensao
        QGuiApplication.clipboard().setText(pasta_extensao())
        self.bt_caminho.setText("Caminho copiado ✓")

    # -------- salvar
    def _pasta(self):
        p = QFileDialog.getExistingDirectory(self, "Pasta de destino", self.ed_pasta.text())
        if p:
            self.ed_pasta.setText(p)

    def _salvar(self):
        j, s = self.j, self.j.settings

        def b(v):
            return "true" if v else "false"
        j.act_iniciar.setChecked(self.ck_iniciar.isChecked())
        j._alternar_inicio(self.ck_iniciar.isChecked())
        acao = self.cb_fechar.currentData()
        s.setValue("acao_fechar", acao)
        j.acts_fechar[acao].setChecked(True)
        if self.cb_tema.currentData() != s.value("tema", "auto"):
            j.trocar_tema(self.cb_tema.currentData())
            j.acts_tema[self.cb_tema.currentData()].setChecked(True)
        j.act_auto_atualizar.setChecked(self.ck_atualizar.isChecked())
        s.setValue("aviso_concluir", b(self.ck_aviso.isChecked()))
        j.ck_clip.setChecked(self.ck_clip.isChecked())
        j.ed_pasta.setText(self.ed_pasta.text().strip() or j.ed_pasta.text())
        s.setValue("por_tipo", b(self.ck_tipo.isChecked()))
        j.sp_con.setValue(self.sp_con.value())
        j.sp_sim.setValue(self.sp_sim.value())
        s.setValue("limite_kb", self.sp_limite.value())
        j.act_limite.setChecked(self.ck_limite.isChecked())
        j.aplicar_limite(self.ck_limite.isChecked())
        j._alternar_captura(self.ck_capturar.isChecked())
        j.act_perguntar.setChecked(self.ck_perguntar.isChecked())
        s.setValue("agenda_inicio_ativa", b(self.ck_inicio.isChecked()))
        s.setValue("agenda_inicio", self.tm_inicio.time().toString("HH:mm"))
        s.setValue("agenda_fim_ativa", b(self.ck_fim.isChecked()))
        s.setValue("agenda_fim", self.tm_fim.time().toString("HH:mm"))
        j.ao_terminar = self.cb_terminar.currentData()
        j._salvar_opcoes()
        self.accept()


# ------------------------------------------------------------------ métodos da janela
class Recursos:
    """Misturado à Janela (janela.py)."""

    def _iniciar_recursos(self):
        self.ao_terminar = "nada"
        self._aguardando_link = None
        self._status_anterior = {id(d): d.status for d in self.downloads}
        self._agenda_disparada = ""
        self.setAcceptDrops(True)
        self.tab.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tab.customContextMenuRequested.connect(self._menu_contexto)
        self.aplicar_limite(self.settings.value("limite_ativo", "false") == "true")

    # -------- configurações / limite
    def abrir_configuracoes(self, aba: int = 0):
        self.mostrar_janela()
        DialogoConfiguracoes(self, aba).exec()

    def aplicar_limite(self, ligado: bool):
        self.settings.setValue("limite_ativo", "true" if ligado else "false")
        kb = int(self.settings.value("limite_kb", 1024))
        LIMITADOR.limite = kb * 1024 if ligado else 0
        self.act_limite.setText(f"Limitar velocidade ({fmt_bytes(kb * 1024)}/s)")
        if self.act_limite.isChecked() != ligado:
            self.act_limite.setChecked(ligado)

    def navegadores_vinculados(self) -> list[str]:
        return [x for x in str(self.settings.value("navegadores_vinculados", "")).split(",") if x]

    def _registrar_navegadores(self):
        """Lembra quais navegadores já conectaram (para mostrar "vinculado" mesmo com o navegador fechado)."""
        ja = self.navegadores_vinculados()
        novos = [n for n in self.servidor.contatos if n and n not in ja]
        if novos:
            self.settings.setValue("navegadores_vinculados", ",".join(ja + novos))

    # -------- vários links / arrastar e soltar
    def adicionar_varios(self, texto: str = ""):
        dlg = DialogoVariosLinks(self, texto)
        if dlg.exec():
            self.adicionar_links(dlg.links(), pausado=dlg.ck_pausado.isChecked())

    def adicionar_links(self, links: list[str], pausado: bool = False):
        antes = len(self.downloads)
        for u in links:
            self.adicionar(u, avisar_duplicado=False, pausado=pausado)
        novos = len(self.downloads) - antes
        self.statusBar().showMessage(f"{novos} download(s) adicionado(s)" +
                                     (f", {len(links) - novos} já estava(m) na lista" if novos < len(links) else ""), 6000)

    def dragEnterEvent(self, ev):
        if ev.mimeData().hasUrls() or ev.mimeData().hasText():
            ev.acceptProposedAction()

    def dropEvent(self, ev):
        md = ev.mimeData()
        texto = "\n".join(u.toString() for u in md.urls()) if md.hasUrls() else md.text()
        links = [u.rstrip(".,;)") for u in RE_LINKS.findall(texto)]
        if links:
            ev.acceptProposedAction()
            self.adicionar_links(list(dict.fromkeys(links)))

    # -------- menu de contexto
    def _menu_contexto(self, pos):
        linha = self.tab.rowAt(pos.y())
        if linha < 0:
            return
        if linha not in self._selecionados():
            self.tab.selectRow(linha)
        d = self.downloads[linha]
        m = QMenu(self)
        if d.status == CONCLUIDO:
            existe = bool(d.caminho) and os.path.exists(d.caminho)
            m.addAction("Abrir", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(d.caminho))).setEnabled(existe)
            m.addAction("Mostrar na pasta", lambda: mostrar_na_pasta(d.caminho)).setEnabled(existe)
            m.addAction("Baixar de novo", lambda: self.adicionar(d.url, headers=d.headers_extra, avisar_duplicado=False))
        else:
            m.addAction("Retomar", self.retomar).setEnabled(d.status in (PAUSADO, ERRO))
            m.addAction("Pausar", self.pausar).setEnabled(d.status in (BAIXANDO, NA_FILA) or d.rodando)
            m.addAction("Atualizar link…", self.atualizar_link)
            m.addAction("Abrir pasta", self.abrir_pasta)
        m.addSeparator()
        m.addAction("Copiar link", lambda: QGuiApplication.clipboard().setText(d.url))
        if d.headers_extra.get("Referer"):
            m.addAction("Abrir a página de origem", lambda: QDesktopServices.openUrl(QUrl(d.headers_extra["Referer"])))
        m.addSeparator()
        m.addAction("Remover da lista", self.remover)
        m.exec(self.tab.viewport().mapToGlobal(pos))

    # -------- atualizar link
    def atualizar_link(self):
        sel = self._selecionados()
        if not sel:
            return
        d = self.downloads[sel[0]]
        if d.status == CONCLUIDO:
            return
        d.pausar()
        dlg = DialogoAtualizarLink(self, d)
        self._dlg_link = dlg
        dlg.show()

    def aplicar_link_novo(self, d, url: str, headers: dict):
        d.pausar()
        d.aguardar(5)
        d.trocar_link(url, headers)
        d.status = NA_FILA
        self._aguardando_link = None
        self.salvar_lista()
        self.statusBar().showMessage(f"Link atualizado — continuando: {d.nome or url}", 8000)

    # -------- ciclo: concluídos, agendamento, ao terminar
    def _tick_recursos(self):
        self._registrar_navegadores()
        terminou_algum = False
        for d in self.downloads:
            antes = self._status_anterior.get(id(d))
            recente = antes is None and time.time() - d.concluido_em < 5      # terminou antes do 1º ciclo
            if d.status == CONCLUIDO and (antes not in (None, CONCLUIDO) or recente):
                terminou_algum = True
                if self.settings.value("aviso_concluir", "true") != "false":
                    AvisoConcluido(d).mostrar()
        self._status_anterior = {id(d): d.status for d in self.downloads}
        if terminou_algum:
            self.salvar_lista()
            ativos = any(d.rodando or d.status == NA_FILA for d in self.downloads)
            if not ativos and self.ao_terminar != "nada":
                acao, self.ao_terminar = self.ao_terminar, "nada"
                if DialogoContagem(self, acao).exec():
                    self.executar_ao_terminar(acao)
        self._tick_agenda()

    def _tick_agenda(self):
        s = self.settings
        agora = QDateTime.currentDateTime()
        marca = agora.toString("yyyy-MM-dd HH:mm")
        if marca == self._agenda_disparada:
            return
        hora = agora.toString("HH:mm")
        if s.value("agenda_inicio_ativa", "false") == "true" and hora == s.value("agenda_inicio", "02:00"):
            self._agenda_disparada = marca
            self.retomar_todos()
            self.tray.showMessage(APP_NAME, "Agendamento: downloads iniciados.", _icone(), 4000)
        elif s.value("agenda_fim_ativa", "false") == "true" and hora == s.value("agenda_fim", "07:00"):
            self._agenda_disparada = marca
            self.pausar_todos()
            self.tray.showMessage(APP_NAME, "Agendamento: downloads pausados.", _icone(), 4000)

    def executar_ao_terminar(self, acao: str):
        if acao == "fechar":
            self.sair()
            return
        self.salvar_lista()
        self._salvar_opcoes()
        if sys.platform != "win32":
            return
        if acao == "desligar":
            subprocess.Popen(["shutdown", "/s", "/t", "5", "/c", "Convergio: downloads concluídos."])
        elif acao == "suspender":
            subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])

    def _acoes_recursos(self):
        """Ações de menu criadas aqui e usadas pelos menus da janela."""
        self.act_limite = QAction("Limitar velocidade", self, checkable=True)
        self.act_limite.toggled.connect(self.aplicar_limite)


__all__ = ["Recursos", "DialogoConfiguracoes", "AvisoConcluido", "mostrar_na_pasta", "QApplication"]
