"""La pagina Tipologie si apre con Header e stato vuoto."""
from qt6_app.ui_qt.pages.tipologie_page import TipologiePage


class _App:
    def show_page(self, key):
        self.last = key


def test_tipologie_page_constructs(qtbot, tmp_path):
    page = TipologiePage(_App(), db_path=str(tmp_path / "typologies.db"))
    qtbot.addWidget(page)
    assert page.tree is not None
    assert page.btn_new is not None
    assert page.lbl_empty.isVisible()
