"""Tema visual do Convergio (claro e escuro) — mesma identidade violeta + dourado do Dispersio PDF."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

CLARO = dict(
    bg="#f6f5fb", panel="#ffffff", border="#e6e3f0", text="#1f1d2b", muted="#6c6880", hover="#f2effa",
    accent="#6d3cf0", accent_2="#9b5cff", accent_text="#ffffff", selected="#ece6fe", input="#ffffff",
    danger="#e5484d", ok="#1f9d55", gold="#f59e0b", track="#ecebf3",
    hero_1="#2a1b6e", hero_2="#6d3cf0", hero_3="#c0479b",
)
ESCURO = dict(
    bg="#14121c", panel="#1c1a26", border="#2c2939", text="#ecebf4", muted="#a19db6", hover="#262335",
    accent="#8b5cff", accent_2="#b48cff", accent_text="#ffffff", selected="#2e2554", input="#232030",
    danger="#ff6369", ok="#3ecf7a", gold="#ffb547", track="#0f0d16",
    hero_1="#1d1450", hero_2="#4b27b8", hero_3="#9a3a85",
)

atual = dict(CLARO)


def sistema_escuro() -> bool:
    try:
        return QApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except AttributeError:
        return False


def qss(c):
    return f"""
* {{ font-family: 'Segoe UI Variable Text', 'Segoe UI', 'Inter', 'Noto Sans', sans-serif; font-size: 13px;
     color: {c['text']}; }}
QMainWindow, QDialog {{ background: {c['bg']}; }}
QFrame#Hero {{ border-radius: 16px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {c['hero_1']}, stop:0.65 {c['hero_2']}, stop:1 {c['hero_3']}); }}
QFrame#Hero QLabel {{ color: #ffffff; background: transparent; }}
QLabel#HeroTitle {{ font-size: 20px; font-weight: 700; }}
QLabel#HeroSub {{ color: rgba(255,255,255,0.80); }}
QFrame#Hero QLineEdit {{ background: rgba(255,255,255,0.96); color: #1f1d2b; border: none; border-radius: 10px;
    padding: 9px 12px; font-size: 14px; }}
QPushButton#HeroPrimary {{ background: #ffffff; color: {c['hero_2']}; border: none; border-radius: 10px;
    padding: 9px 22px; font-weight: 700; font-size: 14px; }}
QPushButton#HeroPrimary:hover {{ background: #f3eeff; }}
QFrame#Card {{ background: {c['panel']}; border: 1px solid {c['border']}; border-radius: 14px; }}
QLabel#Muted {{ color: {c['muted']}; }}
QLabel#Total {{ color: {c['accent']}; font-weight: 700; }}
QPushButton {{ background: {c['panel']}; border: 1px solid {c['border']}; border-radius: 9px; padding: 6px 14px; }}
QPushButton:hover {{ background: {c['hover']}; border-color: {c['accent']}; }}
QPushButton:disabled {{ color: {c['muted']}; }}
QPushButton#Primary {{ background: {c['accent']}; color: {c['accent_text']}; border: none; font-weight: 600; }}
QPushButton#Primary:hover {{ background: {c['accent_2']}; }}
QSpinBox {{ padding-right: 22px; }}
QSpinBox::up-button, QSpinBox::down-button {{ subcontrol-origin: border; width: 20px; border: none;
    background: transparent; }}
QSpinBox::up-button {{ subcontrol-position: top right; }}
QSpinBox::down-button {{ subcontrol-position: bottom right; }}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {{ background: {c['hover']}; border-radius: 4px; }}
QSpinBox::up-arrow {{ image: url({c['seta_cima']}); width: 10px; height: 8px; }}
QSpinBox::down-arrow {{ image: url({c['seta_baixo']}); width: 10px; height: 8px; }}
QLineEdit, QSpinBox {{ background: {c['input']}; border: 1px solid {c['border']}; border-radius: 8px; padding: 5px 8px; }}
QLineEdit:focus, QSpinBox:focus {{ border-color: {c['accent']}; }}
QTableWidget {{ background: {c['panel']}; border: none; gridline-color: transparent;
    selection-background-color: {c['selected']}; selection-color: {c['text']}; alternate-background-color: {c['bg']}; }}
QTableWidget::item {{ padding: 4px 6px; border-bottom: 1px solid {c['border']}; }}
QHeaderView::section {{ background: {c['panel']}; color: {c['muted']}; border: none;
    border-bottom: 1px solid {c['border']}; padding: 8px 6px; font-weight: 600; }}
QProgressBar {{ background: {c['track']}; border: none; border-radius: 6px; text-align: center; height: 14px;
    color: {c['text']}; font-size: 11px; font-weight: 600; margin: 6px 4px; }}
QProgressBar::chunk {{ border-radius: 6px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {c['accent']}, stop:1 {c['accent_2']}); }}
QCheckBox::indicator:checked {{ background: {c['accent']}; border: 1px solid {c['accent']}; border-radius: 4px; }}
QCheckBox::indicator {{ width: 14px; height: 14px; border: 1px solid {c['border']}; border-radius: 4px; background: {c['input']}; }}
QMenuBar {{ background: {c['bg']}; }}
QMenuBar::item:selected, QMenu::item:selected {{ background: {c['selected']}; }}
QMenu {{ background: {c['panel']}; border: 1px solid {c['border']}; padding: 4px; }}
QMenu::item {{ padding: 6px 22px; border-radius: 6px; }}
QTextBrowser {{ background: {c['panel']}; border: 1px solid {c['border']}; border-radius: 8px; }}
QStatusBar {{ color: {c['muted']}; }}
QToolTip {{ background: {c['panel']}; color: {c['text']}; border: 1px solid {c['border']}; }}
"""


def aplicar(app: QApplication, escuro: bool):
    from . import resource
    atual.clear()
    atual.update(ESCURO if escuro else CLARO)
    sufixo = "escuro" if escuro else "claro"
    for d in ("cima", "baixo"):
        atual[f"seta_{d}"] = resource("assets", f"seta_{d}_{sufixo}.svg").replace("\\", "/")
    app.setStyle("Fusion")
    pal = QPalette()
    for papel, chave in ((QPalette.Window, "bg"), (QPalette.Base, "panel"), (QPalette.AlternateBase, "bg"),
                         (QPalette.Text, "text"), (QPalette.WindowText, "text"), (QPalette.Button, "panel"),
                         (QPalette.ButtonText, "text"), (QPalette.Highlight, "accent"),
                         (QPalette.HighlightedText, "accent_text"), (QPalette.ToolTipBase, "panel"),
                         (QPalette.ToolTipText, "text"), (QPalette.PlaceholderText, "muted")):
        pal.setColor(papel, QColor(atual[chave]))
    app.setPalette(pal)
    app.setStyleSheet(qss(atual))
