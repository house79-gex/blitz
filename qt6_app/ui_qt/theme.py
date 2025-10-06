from types import SimpleNamespace
from PySide6.QtWidgets import QApplication

# Palette coerente con il THEME Tk (stesse chiavi)
THEME = SimpleNamespace(
    APP_BG="#1c2833",
    SURFACE_BG="#22313f",
    PANEL_BG="#2c3e50",
    CARD_BG="#34495e",
    TILE_BG="#2f4f6a",
    ACCENT="#2980b9",
    ACCENT_2="#9b59b6",
    OK="#27ae60",
    WARN="#e67e22",
    ERR="#e74c3c",
    TEXT="#ecf0f1",
    TEXT_MUTED="#bdc3c7",
    OUTLINE="#2c3e50",
    OUTLINE_SOFT="#3b4b5a",
    HEADER_BG="#2c3e50",
    HEADER_FG="#ecf0f1",
)

def set_palette_from_dict(pal: dict):
    # Aggiorna THEME dalle chiavi presenti nel dizionario (fallback sicuri)
    for k, v in pal.items():
        if hasattr(THEME, k):
            setattr(THEME, k, str(v))


def _base_stylesheet() -> str:
    # Stylesheet coerente con l’app Tk, con ruoli e componenti principali
    return f"""
    QWidget {{
        background: {THEME.APP_BG};
        color: {THEME.TEXT};
        font-family: 'Segoe UI', Arial, sans-serif;
        font-size: 12.5pt;
    }}

    QMainWindow, QDialog {{
        background: {THEME.APP_BG};
    }}

    /* Header (banner titolo + emergenza) */
    QFrame[role="header"] {{
        background: {THEME.HEADER_BG};
        border-bottom: 1px solid {THEME.OUTLINE};
    }}
    QLabel[role="headerTitle"] {{
        color: {THEME.HEADER_FG};
        font-weight: 700;
        font-size: 16pt;
    }}

    /* Pannelli e Card */
    QFrame[role="panel"], QGroupBox, QFrame#StatusPanel {{
        background: {THEME.CARD_BG};
        border: 1px solid {THEME.OUTLINE};
        border-radius: 6px;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 8px;
        padding: 0 4px;
        color: {THEME.TEXT};
        font-weight: 600;
    }}

    /* Pulsanti */
    QPushButton {{
        background: {THEME.SURFACE_BG};
        border: 1px solid {THEME.OUTLINE_SOFT};
        border-radius: 6px;
        padding: 8px 12px;
        color: {THEME.TEXT};
    }}
    QPushButton:hover {{
        border-color: {THEME.ACCENT};
    }}
    QPushButton:pressed {{
        background: {THEME.PANEL_BG};
    }}

    /* Input base */
    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
        background: {THEME.SURFACE_BG};
        color: {THEME.TEXT};
        border: 1px solid {THEME.OUTLINE_SOFT};
        border-radius: 4px;
        padding: 4px 6px;
        selection-background-color: {THEME.ACCENT};
    }}

    /* Tab */
    QTabWidget::pane {{
        border: 1px solid {THEME.OUTLINE};
        background: {THEME.CARD_BG};
    }}
    QTabBar::tab {{
        background: {THEME.SURFACE_BG};
        color: {THEME.TEXT};
        padding: 6px 12px;
        border: 1px solid {THEME.OUTLINE_SOFT};
        border-bottom: none;
        border-top-left-radius: 6px;
        border-top-right-radius: 6px;
        margin-right: 1px;
    }}
    QTabBar::tab:selected {{
        background: {THEME.CARD_BG};
        border-color: {THEME.ACCENT};
        color: {THEME.TEXT};
    }}

    /* Alberi/liste */
    QTreeWidget, QTreeView, QListWidget, QTableView {{
        background: {THEME.SURFACE_BG};
        color: {THEME.TEXT};
        border: 1px solid {THEME.OUTLINE_SOFT};
        selection-background-color: {THEME.ACCENT};
        selection-color: white;
        alternate-background-color: {THEME.PANEL_BG};
    }}
    QHeaderView::section {{
        background: {THEME.PANEL_BG};
        color: {THEME.TEXT};
        border: 1px solid {THEME.OUTLINE_SOFT};
        padding: 4px 6px;
    }}

    /* Scrollbar */
    QScrollBar:vertical {{
        background: {THEME.PANEL_BG};
        width: 12px;
        margin: 0px;
    }}
    QScrollBar::handle:vertical {{
        background: {THEME.OUTLINE_SOFT};
        min-height: 24px;
        border-radius: 6px;
    }}
    QScrollBar:horizontal {{
        background: {THEME.PANEL_BG};
        height: 12px;
        margin: 0px;
    }}
    QScrollBar::handle:horizontal {{
        background: {THEME.OUTLINE_SOFT};
        min-width: 24px;
        border-radius: 6px;
    }}
    """

def apply_global_stylesheet(app: QApplication):
    app.setStyleSheet(_base_stylesheet())

