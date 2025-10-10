# ... import esistenti ...
from ui_qt.dialogs.dxf_measure_dialog import DxfMeasureDialog
# ... dentro _build_dxf_tab(), dopo i pulsanti Analizza/Salva aggiungi: ...

        btn_open_cad = QPushButton("Apri CAD di misura…")
        def open_cad():
            path = (getattr(btn_save, "_last_info", {}) or {}).get("path", (edit_path.text() or "").strip())
            if not path:
                QMessageBox.information(self, "DXF", "Seleziona e analizza un DXF prima.")
                return
            try:
                dlg = DxfMeasureDialog(self, path=path)
                if dlg.exec():
                    th = dlg.result_thickness_mm()
                    if th > 0:
                        edit_th.setText(f"{th:.2f}")
                        QMessageBox.information(self, "Misura", f"Spessore misurato: {th:.2f} mm")
            except Exception as e:
                QMessageBox.warning(self, "DXF", f"Errore apertura CAD: {e!s}")
        btn_open_cad.clicked.connect(open_cad)

        row_btns.addWidget(btn_open_cad)
