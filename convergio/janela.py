"""Janela principal do Convergio."""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

from PySide6.QtCore import QSettings, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QActionGroup, QColor, QDesktopServices, QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QDialog, QFileDialog, QFormLayout, QFrame, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox, QProgressBar, QPushButton, QSpinBox,
    QSystemTrayIcon, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from . import APP_NAME, AUTHOR, COPYRIGHT, EMAIL, __version__, resource, tema
from .atualizador import Atualizador, avisar_falha, resultado_da_ultima_atualizacao
from .integracao import Servidor
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


def nome_do_link(url: str) -> str:
    nome = unquote(os.path.basename(urlparse(url).path))
    return re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "_", nome).strip(" .")


class DialogoNovoDownload(QDialog):
    """Janela que aparece quando o navegador envia um download (como a "Informações do arquivo" do IDM)."""

    def __init__(self, janela, info: dict):
        super().__init__(None, Qt.WindowStaysOnTopHint)
        self.janela, self.info = janela, info
        self.setWindowTitle(f"{APP_NAME} — novo download")
        self.setWindowIcon(icone_app())
        self.setMinimumWidth(560)
        self.setAttribute(Qt.WA_DeleteOnClose)
        url = info["url"]
        lay = QVBoxLayout(self)
        topo = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(QPixmap(resource("assets", "convergio.png")).scaled(40, 40, Qt.KeepAspectRatio,
                                                                           Qt.SmoothTransformation))
        topo.addWidget(logo)
        origem = info.get("navegador") or "navegador"
        topo.addWidget(QLabel(f"<b style='font-size:15px'>Download capturado do {origem}</b>"))
        topo.addStretch()
        lay.addLayout(topo)
        form = QFormLayout()
        lb_url = QLabel(url if len(url) < 90 else url[:60] + "…" + url[-25:])
        lb_url.setToolTip(url)
        lb_url.setObjectName("Muted")
        lb_url.setTextInteractionFlags(Qt.TextSelectableByMouse)
        form.addRow("Link:", lb_url)
        self.ed_nome = QLineEdit(info.get("nome") or nome_do_link(url))
        self.ed_nome.setPlaceholderText("definido pelo servidor ao iniciar")
        form.addRow("Arquivo:", self.ed_nome)
        tam = info.get("tamanho")
        form.addRow("Tamanho:", QLabel(fmt_bytes(tam) if tam else "será obtido ao iniciar"))
        lp = QHBoxLayout()
        self.ed_pasta = QLineEdit(janela.ed_pasta.text())
        bt = QPushButton("Escolher…")
        bt.clicked.connect(self._pasta)
        lp.addWidget(self.ed_pasta, 1)
        lp.addWidget(bt)
        form.addRow("Salvar em:", lp)
        lay.addLayout(form)
        self.ck = QCheckBox("Não perguntar de novo (baixar direto)")
        lay.addWidget(self.ck)
        botoes = QHBoxLayout()
        botoes.addStretch()
        cancelar = QPushButton("Cancelar")
        baixar = QPushButton("Baixar agora")
        baixar.setObjectName("Primary")
        baixar.setDefault(True)
        cancelar.clicked.connect(self.reject)
        baixar.clicked.connect(self._baixar)
        botoes.addWidget(cancelar)
        botoes.addWidget(baixar)
        lay.addLayout(botoes)

    def _pasta(self):
        p = QFileDialog.getExistingDirectory(self, "Pasta de destino", self.ed_pasta.text())
        if p:
            self.ed_pasta.setText(p)

    def _baixar(self):
        if self.ck.isChecked():
            self.janela.settings.setValue("perguntar_navegador", "false")
            self.janela.act_perguntar.setChecked(False)
        nome = self.ed_nome.text().strip() or None
        self.janela.adicionar(self.info["url"], nome=nome, headers=headers_do_pedido(self.info),
                              pasta=self.ed_pasta.text().strip(), avisar_duplicado=False)
        self.accept()

    def mostrar(self):
        self.show()
        self.raise_()
        self.activateWindow()


def headers_do_pedido(info: dict) -> dict:
    h = {}
    if info.get("cookies"):
        h["Cookie"] = info["cookies"]
    if info.get("referrer"):
        h["Referer"] = info["referrer"]
    if info.get("userAgent"):
        h["User-Agent"] = info["userAgent"]
    return h


def pasta_extensao() -> str:
    """Pasta da extensão: ao lado do executável (instalado) ou na raiz do projeto (código-fonte)."""
    if getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(sys.executable), "extensao")
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "extensao")


class DialogoIntegracao(QDialog):
    def __init__(self, janela):
        super().__init__(janela)
        self.janela = janela
        self.setWindowTitle("Integração com navegadores")
        self.setMinimumWidth(600)
        lay = QVBoxLayout(self)
        self.lb_status = QLabel()
        lay.addWidget(self.lb_status)
        pasta = pasta_extensao()
        texto = QLabel(
            "<p>Com a extensão instalada, os downloads do <b>Chrome, Edge, Brave e Opera</b> vão direto para o "
            f"{APP_NAME}. Se o programa estiver fechado, o navegador baixa normalmente.</p>"
            "<p><b>Para instalar (uma vez só):</b></p><ol>"
            "<li>No navegador, abra <code>chrome://extensions</code> (no Edge: <code>edge://extensions</code>).</li>"
            "<li>Ative o <b>Modo do desenvolvedor</b>, no canto da página.</li>"
            "<li>Clique em <b>Carregar sem compactação</b> e escolha a pasta abaixo.</li></ol>"
            "<p>Também dá para clicar com o botão direito num link e escolher <b>Baixar com o Convergio</b>.</p>")
        texto.setWordWrap(True)
        texto.setTextFormat(Qt.RichText)
        lay.addWidget(texto)
        lp = QHBoxLayout()
        ed = QLineEdit(pasta)
        ed.setReadOnly(True)
        copiar = QPushButton("Copiar caminho")
        copiar.clicked.connect(lambda: (QGuiApplication.clipboard().setText(pasta), copiar.setText("Copiado ✓")))
        abrir = QPushButton("Abrir pasta")
        abrir.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(pasta)))
        lp.addWidget(ed, 1)
        lp.addWidget(copiar)
        lp.addWidget(abrir)
        lay.addLayout(lp)
        fechar = QPushButton("Fechar")
        fechar.setObjectName("Primary")
        fechar.clicked.connect(self.accept)
        lb = QHBoxLayout()
        lb.addStretch()
        lb.addWidget(fechar)
        lay.addLayout(lb)
        lay.addStretch(1)
        self.lb_status.setSizePolicy(self.lb_status.sizePolicy().horizontalPolicy(),
                                     self.lb_status.sizePolicy().Policy.Fixed)
        self._timer = QTimer(self, interval=1000, timeout=self._status)
        self._timer.start()
        self._status()

    def _status(self):
        srv = self.janela.servidor
        c = tema.atual
        if not self.janela.servidor_ativo:
            msg, cor = "A porta de integração está ocupada por outro programa.", c["danger"]
        elif srv.extensao_conectada:
            nav = f" ({srv.navegador})" if srv.navegador else ""
            msg, cor = f"✓ Extensão conectada{nav}", c["ok"]
        else:
            msg, cor = "Extensão ainda não conectada", c["muted"]
        self.lb_status.setText(f"<b style='color:{cor}; font-size:14px'>{msg}</b>")


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

        self._saindo = False
        self._encerrado = False
        self.servidor = Servidor()
        self.servidor.pedido.connect(self.receber_pedido)
        self.servidor.abrir.connect(self.receber_abrir)
        self.servidor.capturar = self.settings.value("capturar_navegador", "true") != "false"
        self.servidor_ativo = self.servidor.iniciar()
        self._menus()
        self._bandeja()
        self._configurar_inicio_automatico()
        QGuiApplication.clipboard().dataChanged.connect(self.clipboard_mudou)
        QApplication.instance().aboutToQuit.connect(self._encerrar)
        self.timer = QTimer(self, interval=400, timeout=self.atualizar)
        self.timer.start()
        self.carregar_lista()
        self.atualizador = Atualizador(self)
        QTimer.singleShot(1500, self._apresentar_integracao)
        QTimer.singleShot(800, self._conferir_atualizacao_anterior)
        QTimer.singleShot(3000, self.atualizador.verificar_auto)

    # ------------------------------------------------------------ menus
    def _menus(self):
        mb = self.menuBar()
        m = mb.addMenu("&Arquivo")
        a = m.addAction("Colar link e baixar", self.colar_e_baixar)
        a.setShortcut("Ctrl+V")
        m.addAction("Escolher pasta de destino…", self.escolher_pasta)
        m.addSeparator()
        m.addAction("Sair", self.sair).setShortcut("Ctrl+Q")

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

        m = mb.addMenu("&Navegadores")
        m.addAction("Instalar a extensão / ver conexão…", self.mostrar_integracao)
        self.act_capturar = QAction("Capturar downloads dos navegadores", self, checkable=True,
                                    checked=self.settings.value("capturar_navegador", "true") != "false")
        self.act_capturar.toggled.connect(self._alternar_captura)
        m.addAction(self.act_capturar)
        self.act_perguntar = QAction("Perguntar antes de baixar", self, checkable=True,
                                     checked=self.settings.value("perguntar_navegador", "true") != "false")
        self.act_perguntar.toggled.connect(
            lambda v: self.settings.setValue("perguntar_navegador", "true" if v else "false"))
        m.addAction(self.act_perguntar)

        m = mb.addMenu("&Opções")
        self.act_iniciar = QAction("Iniciar com o Windows (em segundo plano)", self, checkable=True,
                                   checked=self.settings.value("iniciar_windows", "") == "true")
        self.act_iniciar.toggled.connect(self._alternar_inicio)
        m.addAction(self.act_iniciar)
        sub = m.addMenu("Ao clicar em fechar (X)")
        grupo_f = QActionGroup(self)
        self.acts_fechar = {}
        for chave, nome in (("bandeja", "Continuar em segundo plano (perto do relógio)"),
                            ("sair", "Fechar o programa")):
            act = QAction(nome, self, checkable=True, checked=(chave == self.acao_fechar))
            act.triggered.connect(lambda _=False, k=chave: self.settings.setValue("acao_fechar", k))
            grupo_f.addAction(act)
            sub.addAction(act)
            self.acts_fechar[chave] = act

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

    def adicionar(self, url: str | None = None, nome: str | None = None, headers: dict | None = None,
                  pasta: str | None = None, avisar_duplicado: bool = True):
        url = (url or self.ed_url.text()).strip()
        if not RE_URL.match(url):
            QMessageBox.warning(self, "Link inválido", "Informe um link começando com http:// ou https://")
            return
        if any(d.url == url and d.status != CONCLUIDO for d in self.downloads):
            if avisar_duplicado:
                QMessageBox.information(self, "Já na lista", "Esse link já está na lista de downloads.")
            return
        pasta = pasta or self.ed_pasta.text().strip() or PASTA_PADRAO
        d = Download(url, pasta, self.sp_con.value(), nome=nome, headers=headers)
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
        if getattr(self, "tray", None):
            self._atualizar_dica_bandeja()
        self.setWindowTitle(f"{APP_NAME} — ↓ {fmt_bytes(total)}/s" if total else APP_NAME)

    # ------------------------------------------------------------ persistência
    def salvar_lista(self):
        dados = [{"url": d.url, "pasta": d.pasta, "conexoes": d.conexoes, "nome": d.nome, "headers": d.headers_extra}
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
            d = Download(x["url"], x["pasta"], x.get("conexoes", 16), nome=x.get("nome"), headers=x.get("headers"))
            d.status = PAUSADO
            self._inserir(d)

    def _salvar_opcoes(self):
        s = self.settings
        s.setValue("pasta", self.ed_pasta.text())
        s.setValue("conexoes", self.sp_con.value())
        s.setValue("simultaneos", self.sp_sim.value())
        s.setValue("clipboard", "true" if self.ck_clip.isChecked() else "false")

    def fechar_para_atualizar(self):
        self._saindo = True
        self._encerrar()

    def _encerrar(self):
        if self._encerrado:
            return
        self._encerrado = True
        self.servidor.parar()
        if getattr(self, "tray", None):
            self.tray.hide()
        self.timer.stop()
        for d in self.downloads:
            d.pausar()
        for d in self.downloads:
            d.aguardar(5)
        self.salvar_lista()
        self._salvar_opcoes()

    def closeEvent(self, ev):
        acao = "sair" if self._saindo or not QSystemTrayIcon.isSystemTrayAvailable() else self.acao_fechar
        if acao == "bandeja":
            self._salvar_opcoes()
            self.salvar_lista()
            self.hide()
            if self.settings.value("aviso_bandeja", "") != "1":
                self.settings.setValue("aviso_bandeja", "1")
                self.tray.showMessage(APP_NAME, "O Convergio continua em segundo plano, perto do relógio, pronto para "
                                                "receber os downloads do navegador. Para fechar de vez, clique no ícone "
                                                "e escolha Sair.", icone_app(), 7000)
            ev.ignore()
            return
        ativos = [d for d in self.downloads if d.rodando]
        if ativos and QMessageBox.question(
                self, APP_NAME, f"Há {len(ativos)} download(s) em andamento. Eles serão pausados e "
                                "continuam quando você abrir o programa de novo. Fechar?") != QMessageBox.Yes:
            self._saindo = False
            ev.ignore()
            return
        self._encerrar()
        ev.accept()

    # ------------------------------------------------------------ navegador e bandeja
    def receber_pedido(self, info: dict):
        url = info.get("url", "")
        if any(d.url == url and d.status != CONCLUIDO for d in self.downloads):
            self.mostrar_janela()
            return
        if self.settings.value("perguntar_navegador", "true") == "false":
            self.adicionar(url, nome=info.get("nome") or None, headers=headers_do_pedido(info), avisar_duplicado=False)
            self.tray.showMessage(APP_NAME, f"Baixando {info.get('nome') or nome_do_link(url) or url}",
                                  icone_app(), 3000)
            return
        dlg = DialogoNovoDownload(self, info)
        self._dialogos = [x for x in getattr(self, "_dialogos", []) if x.isVisible()] + [dlg]
        dlg.mostrar()

    def receber_abrir(self, links: list):
        self.mostrar_janela()
        for u in links:
            if RE_URL.match(u):
                self.adicionar(u, avisar_duplicado=False)

    def mostrar_janela(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def mostrar_integracao(self):
        self.mostrar_janela()
        DialogoIntegracao(self).exec()

    def sair(self):
        self._saindo = True
        if not self.close():
            self._saindo = False
            return
        QApplication.instance().quit()

    def _bandeja(self):
        self.tray = QSystemTrayIcon(icone_app(), self)
        self.tray.setToolTip(APP_NAME)
        menu = QMenu(self)
        abrir = menu.addAction(f"Abrir o {APP_NAME}", self.mostrar_janela)
        f = abrir.font()
        f.setBold(True)
        abrir.setFont(f)
        menu.addAction("Baixar o link copiado", self.colar_da_area_de_transferencia)
        menu.addSeparator()
        menu.addAction("Pausar todos", self.pausar_todos)
        menu.addAction("Retomar todos", self.retomar_todos)
        menu.addAction("Abrir pasta de downloads", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(self.ed_pasta.text())))
        menu.addSeparator()
        self.act_tray_capturar = QAction("Capturar downloads dos navegadores", self, checkable=True,
                                         checked=self.act_capturar.isChecked())
        self.act_tray_capturar.toggled.connect(self._alternar_captura)
        menu.addAction(self.act_tray_capturar)
        menu.addAction(self.act_iniciar)
        menu.addAction("Verificar atualizações…", lambda: (self.mostrar_janela(), self.atualizador.verificar(False)))
        menu.addSeparator()
        menu.addAction(f"Sair do {APP_NAME}", self.sair)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda motivo: self.mostrar_janela() if motivo in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick) else None)
        self.tray.show()

    # ------------------------------------------------------------ iniciar com o Windows
    CHAVE_RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"

    def _configurar_inicio_automatico(self):
        # reaplica a escolha (atualiza o caminho do programa); na primeira vez, pergunta depois de abrir
        if self.settings.value("iniciar_windows", "") in ("true", "false"):
            self._alternar_inicio(self.act_iniciar.isChecked())

    def _perguntar_inicio_windows(self):
        if self.settings.value("iniciar_windows", "") in ("true", "false"):
            return
        caixa = QMessageBox(self)
        caixa.setWindowTitle(APP_NAME)
        caixa.setIconPixmap(QPixmap(resource("assets", "convergio.png")).scaled(48, 48, Qt.KeepAspectRatio,
                                                                                Qt.SmoothTransformation))
        caixa.setText("<b>Iniciar o Convergio junto com o Windows?</b>")
        caixa.setInformativeText("Ele abre em silêncio, só em segundo plano perto do relógio, pronto para "
                                 "receber os downloads do navegador. Dá para mudar depois em Opções ou no ícone "
                                 "perto do relógio.")
        sim = caixa.addButton("Sim, iniciar com o Windows", QMessageBox.YesRole)
        caixa.addButton("Agora não", QMessageBox.NoRole)
        sim.setObjectName("Primary")
        sim.style().unpolish(sim)
        sim.style().polish(sim)
        caixa.setDefaultButton(sim)
        caixa.exec()
        self.act_iniciar.setChecked(caixa.clickedButton() is sim)
        self._alternar_inicio(caixa.clickedButton() is sim)

    def _alternar_inicio(self, ligado: bool):
        self.settings.setValue("iniciar_windows", "true" if ligado else "false")
        if sys.platform != "win32" or not getattr(sys, "frozen", False):
            return
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.CHAVE_RUN, 0, winreg.KEY_SET_VALUE) as k:
                if ligado:
                    winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, f'"{sys.executable}" --minimizado')
                else:
                    try:
                        winreg.DeleteValue(k, APP_NAME)
                    except FileNotFoundError:
                        pass
        except OSError:
            pass

    @property
    def acao_fechar(self) -> str:
        acao = self.settings.value("acao_fechar", "bandeja")
        return acao if acao in ("bandeja", "sair") else "bandeja"

    def _alternar_captura(self, ligado: bool):
        self.settings.setValue("capturar_navegador", "true" if ligado else "false")
        self.servidor.capturar = ligado
        if getattr(self, "act_tray_capturar", None) and self.act_tray_capturar.isChecked() != ligado:
            self.act_tray_capturar.setChecked(ligado)
        if self.act_capturar.isChecked() != ligado:
            self.act_capturar.setChecked(ligado)

    def colar_da_area_de_transferencia(self):
        t = QGuiApplication.clipboard().text().strip()
        self.mostrar_janela()
        if RE_URL.match(t):
            self.adicionar(t)
        else:
            self.ed_url.setFocus()

    def _atualizar_dica_bandeja(self):
        ativos = [d for d in self.downloads if d.status == BAIXANDO]
        if ativos:
            vel = sum(d.velocidade for d in ativos)
            self.tray.setToolTip(f"{APP_NAME} — {len(ativos)} baixando, {fmt_bytes(vel)}/s")
        else:
            self.tray.setToolTip(f"{APP_NAME} — nenhum download em andamento")

    def _apresentar_integracao(self):
        """Na primeira vez que a janela abre: pergunta sobre iniciar com o Windows e mostra a extensão."""
        if not self.isVisible():
            return
        self._perguntar_inicio_windows()
        if self.settings.value("integracao_apresentada", "") != "1":
            self.settings.setValue("integracao_apresentada", "1")
            DialogoIntegracao(self).exec()

    def _conferir_atualizacao_anterior(self):
        info = resultado_da_ultima_atualizacao()
        if info:
            self.mostrar_janela()
            avisar_falha(self, info)
