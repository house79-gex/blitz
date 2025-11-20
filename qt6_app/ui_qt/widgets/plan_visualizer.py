"""
PlanVisualizerWidget compatibile con OptimizationRunDialog
Fornisce:
- set_data(bars, stock_mm, kerf_base, ripasso_mm, reversible, thickness_mm, angle_tol, max_angle, max_factor, warn_threshold_mm)
- set_done_by_index(done_map)
- mark_done_by_signature(len_mm, ax, ad)
- set_active_signature(len_mm, ax, ad) (alias highlight)
- highlight_active_signature(...)
- mark_active_by_signature(...)
- set_active_piece_by_signature(...)

Il widget disegna barre verticalmente, ogni pezzo rettangolo proporzionale alla lunghezza efficace.
Colori:
  completato: verde
  attivo: arancione
  pendente: grigio
Mostra sfrido (residuo) come segmento finale rosso chiaro se > warn_threshold_mm.
"""

from __future__ import annotations
from typing import List, Dict, Any, Tuple, Optional
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QRectF, QSize
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont

import math
import logging

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# Utility calcoli (replicati leggeri)
# ----------------------------------------------------------------------
def _effective_length(piece: Dict[str, Any], thickness_mm: float) -> float:
    L = float(piece.get("len", piece.get("length_mm", piece.get("length", 0.0))))
    if thickness_mm <= 0: return max(0.0, L)
    ax = abs(float(piece.get("ax", piece.get("ang_sx", 0.0))))
    ad = abs(float(piece.get("ad", piece.get("ang_dx", 0.0))))
    try: c_sx = thickness_mm * math.tan(math.radians(ax))
    except Exception: c_sx = 0.0
    try: c_dx = thickness_mm * math.tan(math.radians(ad))
    except Exception: c_dx = 0.0
    return max(0.0, L - max(0.0,c_sx) - max(0.0,c_dx))

def _sig(piece: Dict[str, Any]) -> Tuple[float,float,float]:
    L = float(piece.get("len", piece.get("length_mm", piece.get("length", 0.0))))
    ax = float(piece.get("ax", piece.get("ang_sx", 0.0)))
    ad = float(piece.get("ad", piece.get("ang_dx", 0.0)))
    return (round(L,2), round(ax,1), round(ad,1))

# ----------------------------------------------------------------------
class PlanVisualizerWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._bars: List[List[Dict[str, Any]]] = []
        self._stock_mm: float = 0.0
        self._kerf_base: float = 0.0
        self._ripasso_mm: float = 0.0
        self._reversible: bool = False
        self._thickness_mm: float = 0.0
        self._angle_tol: float = 0.0
        self._max_angle: float = 0.0
        self._max_factor: float = 0.0
        self._warn_thr: float = 0.0

        # done_by_index: {bar_index: [bool,...]}
        self._done_map: Dict[int,List[bool]] = {}

        # active piece signature
        self._active_sig: Optional[Tuple[float,float,float]] = None

        # completati per signature (fallback se done_map non trova)
        self._done_signatures: set[Tuple[float,float,float]] = set()

        self._bar_v_space = 14
        self._bar_height = 46
        self._piece_min_w_px = 16
        self.setMinimumHeight(140)
        self.setMouseTracking(True)

    # ---------------- API richiesti ----------------
    def set_data(self,
                 bars: List[List[Dict[str,Any]]],
                 stock_mm: float,
                 kerf_base: float,
                 ripasso_mm: float,
                 reversible: bool,
                 thickness_mm: float,
                 angle_tol: float,
                 max_angle: float,
                 max_factor: float,
                 warn_threshold_mm: float):
        self._bars = bars or []
        self._stock_mm = float(stock_mm or 0.0)
        self._kerf_base = float(kerf_base or 0.0)
        self._ripasso_mm = float(ripasso_mm or 0.0)
        self._reversible = bool(reversible)
        self._thickness_mm = float(thickness_mm or 0.0)
        self._angle_tol = float(angle_tol or 0.0)
        self._max_angle = float(max_angle or 0.0)
        self._max_factor = float(max_factor or 0.0)
        self._warn_thr = float(warn_threshold_mm or 0.0)
        # Allinea done_map se dimensioni cambiano
        for i,b in enumerate(self._bars):
            lst=self._done_map.get(i)
            if lst is None or len(lst)!=len(b):
                self._done_map[i]=[False]*len(b)
        self._recalc_min_height()
        self.update()

    def set_done_by_index(self, done_map: Dict[int,List[bool]]):
        # Normalizza rispetto a bars
        for i,b in enumerate(self._bars):
            arr=done_map.get(i)
            if arr is None or len(arr)!=len(b):
                continue
            self._done_map[i]=[bool(x) for x in arr]
            # aggiorna signatures
            for j,p in enumerate(b):
                if self._done_map[i][j]:
                    self._done_signatures.add(_sig(p))
        self.update()

    def mark_done_by_signature(self, length_mm: float, ax: float, ad: float):
        sig=(round(float(length_mm),2),round(float(ax),1),round(float(ad),1))
        self._done_signatures.add(sig)
        # Prova anche su done_map
        for bi,bar in enumerate(self._bars):
            for pi,p in enumerate(bar):
                if _sig(p)==sig:
                    if bi not in self._done_map:
                        self._done_map[bi]=[False]*len(bar)
                    self._done_map[bi][pi]=True
        self.update()

    # alias varie
    def set_active_signature(self, length_mm: float, ax: float, ad: float):
        self._active_sig=(round(float(length_mm),2),round(float(ax),1),round(float(ad),1))
        self.update()
    highlight_active_signature = set_active_signature
    mark_active_by_signature   = set_active_signature
    set_active_piece_by_signature = set_active_signature

    # ---------------- Dimensionamento ----------------
    def _recalc_min_height(self):
        h = len(self._bars)* (self._bar_height + self._bar_v_space) + 40
        self.setMinimumHeight(max(140,h))

    def sizeHint(self) -> QSize:
        return QSize(max(780,self.width()), self.minimumHeight())

    # ---------------- Disegno ----------------
    def paintEvent(self, ev):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        W = self.width()
        y = 8
        font = QFont()
        font.setPointSize(8)
        painter.setFont(font)

        if not self._bars:
            painter.setPen(QPen(QColor("#444"),1))
            painter.drawText(self.rect(), Qt.AlignCenter, "Nessun piano")
            return

        # scala base: larghezza disponibile per pezzi (lascia margine sinistro per testo)
        left_margin = 140
        usable_w = max(100, W - left_margin - 20)

        for bi, bar in enumerate(self._bars):
            # Footer info barra
            bar_rect = QRectF(10, y, W-20, self._bar_height)
            # background
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#fdfdfd"))
            painter.drawRoundedRect(bar_rect, 6, 6)
            painter.setPen(QPen(QColor("#ccc"),1))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(bar_rect, 6, 6)

            # calcolo lunghezze efficaci
            effs=[_effective_length(p,self._thickness_mm) for p in bar]
            total_eff = sum(effs)
            # consumo giunzioni (approx kerf+ripasso ad ogni giunzione)
            joints = 0.0
            if len(bar)>1:
                joints = (self._kerf_base + max(0.0,self._ripasso_mm))*(len(bar)-1)
            used_len = total_eff + joints
            residual = max(0.0, self._stock_mm - used_len)

            # header / descrizione
            painter.setPen(QPen(QColor("#333"),1))
            title = f"Barra {bi+1}  Usato: {used_len:.1f} mm  Residuo: {residual:.1f} mm"
            if residual <= self._warn_thr + 1e-6:
                title += "  [WARN]"
            painter.drawText(QRectF(14,y+4,left_margin-10,12), Qt.AlignLeft|Qt.AlignVCenter, title)

            # disegno pezzi su fascia
            x_piece = left_margin
            h_piece = self._bar_height - 20
            top_piece = y + 16

            # scala orizzontale
            scale = 0.0
            if used_len>0:
                scale = usable_w / max(used_len, self._stock_mm)  # mostra anche residuo proporzionale se c'è spazio

            for pi,p in enumerate(bar):
                eff=effs[pi]
                piece_w = eff*scale
                # aggiungi lo spazio giunzione dopo (non per ultimo)
                joint_w = 0.0
                if pi < len(bar)-1:
                    joint_w = (self._kerf_base + max(0.0,self._ripasso_mm))*scale
                piece_w = max(self._piece_min_w_px, piece_w)

                # Stato
                sig=_sig(p)
                done = (bi in self._done_map and pi < len(self._done_map[bi]) and self._done_map[bi][pi]) or sig in self._done_signatures
                active = (self._active_sig == sig)

                if done:
                    col1,col2 = QColor(110,210,110), QColor(70,170,70)
                elif active:
                    col1,col2 = QColor(255,200,120), QColor(255,140,0)
                else:
                    col1,col2 = QColor(200,200,200), QColor(150,150,150)

                # rettangolo pezzo
                r_piece = QRectF(x_piece, top_piece, piece_w, h_piece)
                painter.setPen(Qt.NoPen)
                # gradiente semplificato
                painter.setBrush(col1)
                painter.drawRoundedRect(r_piece, 4,4)
                painter.setPen(QPen(col2,1))
                painter.drawRoundedRect(r_piece,4,4)

                # testo
                txt_len = f"{sig[0]:.0f}"
                ang_sx = sig[1]; ang_dx = sig[2]
                angle_part=""
                if ang_sx!=0.0 or ang_dx!=0.0:
                    if piece_w > 42:
                        angle_part = f"{ang_sx:.0f}/{ang_dx:.0f}"
                show_text = txt_len if not angle_part else f"{txt_len}\n{angle_part}"
                painter.setPen(QPen(Qt.black if not done and not active else Qt.white,1))
                painter.drawText(r_piece, Qt.AlignCenter, show_text)

                # evidenzia bordo attivo
                if active:
                    painter.setPen(QPen(QColor(255,100,0),2))
                    painter.setBrush(Qt.NoBrush)
                    painter.drawRoundedRect(r_piece.adjusted(-2,-2,2,2),5,5)

                x_piece += piece_w

                # giunzione (kerf+ripasso) come separatore
                if joint_w > 0:
                    r_joint = QRectF(x_piece, top_piece + h_piece*0.15, joint_w, h_piece*0.70)
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(QColor(240,240,240))
                    painter.drawRect(r_joint)
                    painter.setPen(QPen(QColor(180,180,180),1,Qt.DashLine))
                    painter.drawRect(r_joint)
                    x_piece += joint_w

            # residuo
            if residual>0:
                res_w = residual*scale
                if res_w > 4:
                    r_res = QRectF(x_piece, top_piece, max(4,res_w), h_piece)
                    painter.setPen(Qt.NoPen)
                    warn = residual <= self._warn_thr + 1e-6
                    painter.setBrush(QColor(255,210,210) if warn else QColor(255,230,230))
                    painter.drawRoundedRect(r_res,4,4)
                    painter.setPen(QPen(QColor(200,80,80 if warn else 110),1))
                    painter.drawRoundedRect(r_res,4,4)
                    painter.setPen(QPen(Qt.black,1))
                    painter.drawText(r_res, Qt.AlignCenter, f"{residual:.0f}")

            y += self._bar_height + self._bar_v_space

    # ---------------- Interazione semplice ----------------
    def mousePressEvent(self, ev):
        # Non implementiamo selezione pezzo avanzata ora
        super().mousePressEvent(ev)

    # Compat: alcune chiamate nel codice possono usare highlight_* senza parametri addizionali
    # già mappate agli alias definendo la stessa logica

# Backwards compatibility alias
PlanVisualizer = PlanVisualizerWidget
