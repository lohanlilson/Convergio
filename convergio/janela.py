"""Janela principal do Convergio."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QActionGroup, QColor, QDesktopServices, QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QFileDialog, QFrame, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMainWindow, QMessageBox, QProgressBar, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from . import APP_NAME, AUTHOR, COPYRIGHT, EMAIL, __version__, resource, tema
from .atualizador import Atualizador
from .motor import BAIXANDO, CONCLUIDO, CONECTANDO, ERRO, NA_FILA, PAUSADO, Download, fmt_bytes, fmt_tempo

LISTA = Path(os.environ.get("APPDATA") or Path.home()) / "Convergio" / "downloads.json"
PASTA_PADRAO = str(Path.home() / "Downloads")
RE_URL = re.compile(r"^https?://\S+$", re.I)
EXT_MONITORADAS = re.compile(
    r"\.(zip|rar|7z|tar|gz|iso|exe|msi|apk|pdf|mp4|mkv|avi|mov|mp3|flac|bin|img|dmg|deb|rpm|torrent)(\?|$)", re.I)

COL_ARQ, COL_TAM, COL_PROG, COL_VEL, COL_ETA, COL_CON, COL_STATUS = range(7)


def icone_app() -> QIcon:
    return QIcon(resource("assets", "convergio.ico"))


class BarraSegmentos(QWidget):
    """Mostra os trechos do arquivo e as conexões ativas (cada uma com um brilho dourado na ponta)."""

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(22)
        self.download: Download | None = None

    def paintEvent(self, _):
        c = tema.atual
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.rect().adjusted(1, 1, -1, -1)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(c["track"]))
        p.drawRoundedRect(r, 6, 6)
        d = self.download
        p.setClipRect(r)
        if d and d.status == CONCLUIDO:
            p.setBrush(QColor(c["accent"]))
            p.drawRoundedRect(r, 6, 6)
        elif d and d.tamanho:
            w = r.width() / d.tamanho
            for start, end, pos, ativo in d.mapa():
                x = r.x() + start * w
                feito = max(0, min(pos, end + 1) - start) * w
                p.fillRect(int(x), r.y(), max(1, int(feito + 0.5)), r.height(),
                           QColor(c["accent_2"] if ativo else c["accent"]))
                if ativo and pos <= end:
                    p.fillRect(int(x + feito), r.y(), 3, r.height(), QColor(c["gold"]))


class Janela(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("Convergio", "Convergio")
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(icone_app())
        self.resize(1060, 640)
        self.downloads: list[Download] = []
        self._ultimo_clip = ""

        # --- topo (mesmo estilo do "Hero" do Dispersio)
        hero = QFrame(objectName="Hero")
        hl = QVBoxLayout(hero)
        hl.setContentsMargins(20, 16, 20, 18)
        topo = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(QPixmap(resource("assets", "convergio.png")).scaled(
            44, 44, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        titulo = QVBoxLayout()
        titulo.setSpacing(0)
        titulo.addWidget(QLabel(APP_NAME, objectName="HeroTitle"))
        titulo.addWidget(QLabel("Acelerador de downloads — várias conexões, um arquivo", objectName="HeroSub"))
        topo.addWidget(logo)
        topo.addSpacing(6)
        topo.addLayout(titulo)
        topo.addStretch()
        hl.addLayout(topo)
        hl.addSpacing(8)
        lu = QHBoxLayout()
        self.ed_url = QLineEdit(placeholderText="Cole o link do download (http/https)…")
        self.ed_url.returnPressed.connect(self.adicionar)
        bt_add = QPushButton("Baixar", objectName="HeroPrimary")
        bt_add.setCursor(Qt.PointingHandCursor)
        bt_add.clicked.connect(lambda: self.adicionar())
        lu.addWidget(self.ed_url, 1)
        lu.addWidget(bt_add)
        hl.addLayout(lu)

        # --- opções
        s = self.settings
        self.ed_pasta = QLineEdit(s.value("pasta", PASTA_PADRAO))
        bt_pasta = QPushButton("Escolher…")
        bt_pasta.clicked.connect(self.escolher_pasta)
        self.sp_con = QSpinBox(minimum=1, maximum=32, value=int(s.value("conexoes", 16)))
        self.sp_sim = QSpinBox(minimum=1, maximum=10, value=int(s.value("simultaneos", 3)))
        self.ck_clip = QCheckBox("Capturar links copiados")
        self.ck_clip.setChecked(s.value("clipboard", "true") == "true")
        lo = QHBoxLayout()
        lo.addWidget(QLabel("Salvar em:"))
        lo.addWidget(self.ed_pasta, 1)
        lo.addWidget(bt_pasta)
        lo.addSpacing(10)
        lo.addWidget(QLabel("Conexões por arquivo:"))
        lo.addWidget(self.sp_con)
        lo.addWidget(QLabel("Simultâneos:"))
        lo.addWidget(self.sp_sim)
        lo.addSpacing(10)
        lo.addWidget(self.ck_clip)

        # --- tabela
        self.tab = QTableWidget(0, 7)
        self.tab.setHorizontalHeaderLabels(
            ["Arquivo", "Tamanho", "Progresso", "Velocidade", "Restante", "Conexões", "Status"])
        h = self.tab.horizontalHeader()
        h.setSectionResizeMode(COL_ARQ, QHeaderView.Stretch)
        h.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        for col, w in ((COL_TAM, 90), (COL_PROG, 170), (COL_VEL, 100), (COL_ETA, 80), (COL_CON, 76), (COL_STATUS, 170)):
            self.tab.setColumnWidth(col, w)
        self.tab.verticalHeader().hide()
        self.tab.verticalHeader().setDefaultSectionSize(34)
        self.tab.setShowGrid(False)
        self.tab.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tab.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tab.setFocusPolicy(Qt.NoFocus)
        self.tab.doubleClicked.connect(self.abrir_arquivo)

        self.barra = BarraSegmentos()
        card = QFrame(objectName="Card")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(10, 8, 10, 10)
        cl.addWidget(self.tab, 1)
        self.lb_seg = QLabel("Selecione um download para ver as conexões", objectName="Muted")
        cl.addWidget(self.lb_seg)
        cl.addWidget(self.barra)

        # --- botões
        lb = QHBoxLayout()
        for txt, fn, primario in (("Retomar", self.retomar, True), ("Pausar", self.pausar, False),
                                  ("Remover", self.remover, False), ("Pausar todos", self.pausar_todos, False),
                                  ("Abrir pasta", self.abrir_pasta, False)):
            b = QPushButton(txt)
            if primario:
                b.setObjectName("Primary")
            b.clicked.connect(fn)
            lb.addWidget(b)
        lb.addStretch()
        self.lb_total = QLabel(objectName="Total")
        lb.addWidget(self.lb_total)

        lay = QVBoxLayout()
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(10)
        lay.addWidget(hero)
        lay.addLayout(lo)
        lay.addWidget(card, 1)
        lay.addLayout(lb)
        w = QWidget()
        w.setLayout(lay)
        self.setCentralWidget(w)
        self.statusBar()

        self._menus()
        QGuiApplication.clipboard().dataChanged.connect(self.clipboard_mudou)
        self.timer = QTimer(self, interval=400, timeout=self.atualizar)
        self.timer.start()
        self.carregar_lista()
        self.atualizador = Atualizador(self)
        QTimer.singleShot(3000, self.atualizador.verificar_auto)

    # ------------------------------------------------------------ menus
    def _menus(self):
        mb = self.menuBar()
        m = mb.addMenu("&Arquivo")
        a = m.addAction("Colar link e baixar", self.colar_e_baixar)
        a.setShortcut("Ctrl+V")
        m.addAction("Escolher pasta de destino…", self.escolher_pasta)
        m.addSeparator()
        m.addAction("Sair", self.close).setShortcut("Ctrl+Q")

        m = mb.addMenu("&Downloads")
        m.addAction("Retomar", self.retomar)
        m.addAction("Pausar", self.pausar)
        m.addAction("Remover", self.remover).setShortcut("Del")
        m.addSeparator()
        m.addAction("Retomar todos", self.retomar_todos)
        m.addAction("Pausar todos", self.pausar_todos)
        m.addAction("Limpar concluídos", self.limpar_concluidos)
        m.addSeparator()
        m.addAction("Abrir pasta", self.abrir_pasta)

        m = mb.addMenu("&Exibir")
        grupo = QActionGroup(self)
        atual = self.settings.value("tema", "auto")
        for chave, nome in (("auto", "Tema do Windows"), ("claro", "Tema claro"), ("escuro", "Tema escuro")):
            act = QAction(nome, self, checkable=True, checked=(chave == atual))
            act.triggered.connect(lambda _=False, k=chave: self.trocar_tema(k))
            grupo.addAction(act)
            m.addAction(act)

        m = mb.addMenu("A&juda")
        m.addAction("Verificar atualizações…", lambda: self.atualizador.verificar(False))
        auto = QAction("Verificar atualizações automaticamente", self, checkable=True,
                       checked=self.settings.value("auto_atualizar", "true") != "false")
        auto.toggled.connect(lambda v: self.settings.setValue("auto_atualizar", "true" if v else "false"))
        m.addAction(auto)
        m.addSeparator()
        m.addAction(f"Sobre o {APP_NAME}", self.sobre)

    def trocar_tema(self, chave):
        self.settings.setValue("tema", chave)
        escuro = tema.sistema_escuro() if chave == "auto" else chave == "escuro"
        tema.aplicar(QApplication.instance(), escuro)
        self.barra.update()

    def sobre(self):
        QMessageBox.about(self, f"Sobre o {APP_NAME}",
                          f"<h3>{APP_NAME} {__version__}</h3>"
                          "<p>Acelerador de downloads com segmentação dinâmica: várias conexões baixam partes "
                          "do mesmo arquivo e se redistribuem até o fim.</p>"
                          f"<p>{COPYRIGHT}<br>{AUTHOR} — <a href='mailto:{EMAIL}'>{EMAIL}</a></p>")

    # ------------------------------------------------------------ ações
    def escolher_pasta(self):
        p = QFileDialog.getExistingDirectory(self, "Pasta de destino", self.ed_pasta.text())
        if p:
            self.ed_pasta.setText(p)

    def colar_e_baixar(self):
        t = QGuiApplication.clipboard().text().strip()
        if self.ed_url.hasFocus() or self.ed_pasta.hasFocus():
            (self.ed_url if self.ed_url.hasFocus() else self.ed_pasta).paste()
        elif RE_URL.match(t):
            self.adicionar(t)

    def adicionar(self, url: str | None = None):
        url = (url or self.ed_url.text()).strip()
        if not RE_URL.match(url):
            QMessageBox.warning(self, "Link inválido", "Informe um link começando com http:// ou https://")
            return
        if any(d.url == url and d.status != CONCLUIDO for d in self.downloads):
            QMessageBox.information(self, "Já na lista", "Esse link já está na lista de downloads.")
            return
        d = Download(url, self.ed_pasta.text().strip() or PASTA_PADRAO, self.sp_con.value())
        self._inserir(d)
        self.ed_url.clear()
        self.tab.selectRow(len(self.downloads) - 1)
        self.salvar_lista()

    def _inserir(self, d: Download):
        self.downloads.append(d)
        r = self.tab.rowCount()
        self.tab.insertRow(r)
        for col in range(7):
            self.tab.setItem(r, col, QTableWidgetItem(""))
        pb = QProgressBar(minimum=0, maximum=1000)
        self.tab.setCellWidget(r, COL_PROG, pb)

    def _selecionados(self) -> list[int]:
        return sorted({i.row() for i in self.tab.selectedIndexes()})

    def retomar(self):
        for r in self._selecionados():
            self._retomar(self.downloads[r])

    def retomar_todos(self):
        for d in self.downloads:
            self._retomar(d)

    @staticmethod
    def _retomar(d):
        if d.status in (PAUSADO, ERRO) and not d.rodando:
            d.status = NA_FILA

    def pausar(self):
        for r in self._selecionados():
            self.downloads[r].pausar()

    def pausar_todos(self):
        for d in self.downloads:
            d.pausar()

    def limpar_concluidos(self):
        for r in reversed(range(len(self.downloads))):
            if self.downloads[r].status == CONCLUIDO:
                self.downloads.pop(r)
                self.tab.removeRow(r)
        self.salvar_lista()

    def remover(self):
        linhas = self._selecionados()
        if not linhas:
            return
        apagar = False
        if any(self.downloads[r].status != CONCLUIDO for r in linhas):
            resp = QMessageBox.question(
                self, "Remover", "Apagar também os arquivos parciais dos downloads não concluídos?",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
            if resp == QMessageBox.Cancel:
                return
            apagar = resp == QMessageBox.Yes
        for r in reversed(linhas):
            d = self.downloads.pop(r)
            d.pausar()
            d.aguardar(5)
            if apagar and d.status != CONCLUIDO and d.caminho:
                for f in (d.caminho + ".part", d.caminho + ".part.json"):
                    try:
                        os.remove(f)
                    except OSError:
                        pass
            self.tab.removeRow(r)
        self.salvar_lista()

    def abrir_pasta(self):
        linhas = self._selecionados()
        pasta = self.downloads[linhas[0]].pasta if linhas else self.ed_pasta.text()
        QDesktopServices.openUrl(QUrl.fromLocalFile(pasta))

    def abrir_arquivo(self, idx):
        d = self.downloads[idx.row()]
        if d.status == CONCLUIDO and d.caminho:
            QDesktopServices.openUrl(QUrl.fromLocalFile(d.caminho))

    def clipboard_mudou(self):
        if not self.ck_clip.isChecked():
            return
        t = QGuiApplication.clipboard().text().strip()
        if t != self._ultimo_clip and RE_URL.match(t) and EXT_MONITORADAS.search(t):
            self._ultimo_clip = t
            self.ed_url.setText(t)
            self.showNormal()
            self.activateWindow()
            self.ed_url.setFocus()

    # ------------------------------------------------------------ ciclo
    def atualizar(self):
        rodando = sum(1 for d in self.downloads if d.rodando)
        for d in self.downloads:
            if rodando >= self.sp_sim.value():
                break
            if d.status == NA_FILA and not d.rodando:
                d.iniciar()
                rodando += 1

        c = tema.atual
        cores = {CONCLUIDO: c["ok"], ERRO: c["danger"], BAIXANDO: c["accent"], CONECTANDO: c["accent"]}
        total = 0.0
        for r, d in enumerate(self.downloads):
            total += d.velocidade
            it = self.tab.item(r, COL_ARQ)
            it.setText(d.nome or d.url)
            it.setToolTip(d.url)
            self.tab.item(r, COL_TAM).setText(fmt_bytes(d.tamanho) if d.tamanho else "?")
            pb: QProgressBar = self.tab.cellWidget(r, COL_PROG)
            pr = d.progresso
            if pr < 0:
                pb.setFormat(fmt_bytes(d.baixado) if d.baixado else "")
                pb.setValue(0)
            else:
                pb.setFormat("%p%")
                pb.setValue(int(pr * 1000))
            em_curso = d.status == BAIXANDO
            self.tab.item(r, COL_VEL).setText(f"{fmt_bytes(d.velocidade)}/s" if em_curso else "")
            self.tab.item(r, COL_ETA).setText(fmt_tempo(d.tempo_restante) if em_curso else "")
            self.tab.item(r, COL_CON).setText(str(d.conexoes_ativas) if em_curso else "")
            st = d.status + (f": {d.erro}" if d.status == ERRO and d.erro else "")
            it = self.tab.item(r, COL_STATUS)
            it.setText(st)
            it.setToolTip(st)
            it.setForeground(QColor(cores.get(d.status, c["muted"])))

        sel = self._selecionados()
        d = self.downloads[sel[0]] if sel else None
        self.barra.download = d
        self.barra.update()
        if d and d.status == BAIXANDO:
            self.lb_seg.setText(f"{d.nome} — {d.conexoes_ativas} conexões ativas, {len(d.segmentos)} trechos")
        elif d:
            self.lb_seg.setText(d.nome or d.url)
        else:
            self.lb_seg.setText("Selecione um download para ver as conexões")
        self.lb_total.setText(f"↓ {fmt_bytes(total)}/s" if total else "")
        self.setWindowTitle(f"{APP_NAME} — ↓ {fmt_bytes(total)}/s" if total else APP_NAME)

    # ------------------------------------------------------------ persistência
    def salvar_lista(self):
        dados = [{"url": d.url, "pasta": d.pasta, "conexoes": d.conexoes, "nome": d.nome}
                 for d in self.downloads if d.status != CONCLUIDO]
        try:
            LISTA.parent.mkdir(parents=True, exist_ok=True)
            LISTA.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            pass

    def carregar_lista(self):
        try:
            dados = json.loads(LISTA.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        for x in dados:
            d = Download(x["url"], x["pasta"], x.get("conexoes", 16), nome=x.get("nome"))
            d.status = PAUSADO
            self._inserir(d)

    def _salvar_opcoes(self):
        s = self.settings
        s.setValue("pasta", self.ed_pasta.text())
        s.setValue("conexoes", self.sp_con.value())
        s.setValue("simultaneos", self.sp_sim.value())
        s.setValue("clipboard", "true" if self.ck_clip.isChecked() else "false")

    def fechar_para_atualizar(self):
        self._encerrar()

    def _encerrar(self):
        self.timer.stop()
        for d in self.downloads:
            d.pausar()
        for d in self.downloads:
            d.aguardar(5)
        self.salvar_lista()
        self._salvar_opcoes()

    def closeEvent(self, ev):
        ativos = [d for d in self.downloads if d.rodando]
        if ativos and QMessageBox.question(
                self, APP_NAME, f"Há {len(ativos)} download(s) em andamento. Eles serão pausados e "
                                "continuam quando você abrir o programa de novo. Fechar?") != QMessageBox.Yes:
            ev.ignore()
            return
        self._encerrar()
        ev.accept()
