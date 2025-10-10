from PySide6.QtWidgets import (
QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton, QComboBox, QSpinBox,
    QTabWidget, QLineEdit, QColorDialog, QMessageBox, QGridLayout, QCheckBox, QFileDialog, QListWidget, QListWidgetItem
    QTabWidget, QLineEdit, QColorDialog, QMessageBox, QGridLayout, QCheckBox, QFileDialog,
    QListWidget, QListWidgetItem
)
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtWidgets import QApplication
from ui_qt.widgets.header import Header
from ui_qt.widgets.status_panel import StatusPanel
from ui_qt.theme import THEME, set_palette_from_dict, apply_global_stylesheet
from ui_qt.utils.theme_store import save_theme_combo, read_themes

# Import “tollerante” del theme_store (se manca, fallback no-op)
try:
    from ui_qt.utils.theme_store import save_theme_combo, read_themes
except Exception:
    def save_theme_combo(name, palette, icons):  # fallback
        pass
    def read_themes():
        return {}

from ui_qt.utils.app_settings import get_bool as settings_get_bool, set_bool as settings_set_bool

# Servizi profili / DXF / tastatore (non generano errori a import)
from ui_qt.services.profiles_store import ProfilesStore
from ui_qt.services.dxf_importer import analyze_dxf
from ui_qt.services.probe_service import ProbeService


class UtilityPage(QWidget):
"""
   Utility con StatusPanel e polling diagnostica.
@@ -93,10 +106,10 @@ def _build_backup_tab(self):

def _build_dxf_tab(self):
"""
        Sezione profili:
        Profili:
       - Import DXF con analisi bbox e salvataggio in DB (name/thickness + metadata opzionali).
       - Archivio profili: elenco, modifica spessore, elimina.
        - Tastatore profili: pulsante test visibile solo se abilitato in Configurazione.
        - Tastatore: pulsante test visibile solo se abilitato in Configurazione.
       """
from PySide6.QtWidgets import QVBoxLayout as VB, QHBoxLayout as HB, QGroupBox, QFormLayout
pg = QFrame()
@@ -136,13 +149,10 @@ def analyze_now():
return
try:
info = analyze_dxf(p)
                # aggiorna UI
if not (edit_name.text() or "").strip():
edit_name.setText(info.get("name_suggestion", ""))
lbl_meta.setText(f"Entità: {info['entities']} | BBox: {info['bbox_w']:.1f} x {info['bbox_h']:.1f} mm")
                # abilita salvataggio
btn_save.setEnabled(True)
                # stash info in widget
btn_save._last_info = info  # type: ignore
except ImportError as e:
QMessageBox.warning(self, "DXF", str(e))
@@ -160,9 +170,7 @@ def save_now():
th = 0.0
info = getattr(btn_save, "_last_info", None)
try:
                # salva spessore
self.profiles.upsert_profile(name, th)
                # salva metadata shape (opzionale)
if info:
self.profiles.upsert_profile_shape(
name=name,
@@ -249,7 +257,8 @@ def do_delete():

lay.addWidget(grp_arch)

        # --- Tastatore profili (sperimentale) ---
        # --- Tastatore profili (test, nascosto se disabilitato) ---
        from PySide6.QtWidgets import QGroupBox
grp_probe = QGroupBox("Tastatore profili (test)")
grp_probe.setVisible(settings_get_bool("probe_profiles_enabled", False))
pr_l = QHBoxLayout(grp_probe)
@@ -266,7 +275,6 @@ def done(ok: bool, value: float | None, msg: str):
btn_probe.setEnabled(True)
if ok and value is not None:
lbl_probe.setText(f"Spessore: {value:.1f} mm")
                    # opzionale: applica al campo spessore se selezionato un profilo
cur = self.lst_profiles.currentItem() if self.lst_profiles else None
if cur and self.edit_prof_name:
self.edit_prof_th.setText(f"{value:.1f}")
@@ -290,7 +298,6 @@ def _refresh_profiles_list(self, select: str | None = None):
rows = self.profiles.list_profiles()
for r in rows:
self.lst_profiles.addItem(QListWidgetItem(str(r["name"])))
            # seleziona
if select:
items = self.lst_profiles.findItems(select, Qt.MatchExactly)
if items:
@@ -299,7 +306,6 @@ def _refresh_profiles_list(self, select: str | None = None):
pass

def _build_theme_tab(self):
        # (rimane come da tua versione precedente — palette e icone tema)
pg = QFrame()
lay = QVBoxLayout(pg)
pal_box = QFrame()
@@ -367,3 +373,6 @@ def _tick_diag(self):
self.status.refresh()
except Exception:
pass

    def _do_backup(self): QMessageBox.information(self, "Backup", "Funzione backup: da collegare al backend.")
    def _do_restore(self): QMessageBox.information(self, "Ripristino", "Funzione ripristino: da collegare al backend.")
