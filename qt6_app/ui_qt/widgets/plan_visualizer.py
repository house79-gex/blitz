"""
PlanVisualizerWidget compatibile con OptimizationRunDialog
Rappresentazione grafica barre e pezzi:
- Ogni pezzo come trapezio realistico: base superiore = lunghezza esterna (len),
  base inferiore = len - (offset_sx_mm + offset_dx_mm) dove offset = thickness_mm * tan(angolo).
- Taper (offsets) convertiti in pixel con la stessa scala usata per la lunghezza.
- Limite per evitare base inferiore negativa o trapezi eccessivi.
Colori:
  completato: verde
  attivo: arancione (SOLO il pezzo attivo)
  pendente: grigio
Residuo: rettangolo alla fine barra (rosso chiaro, warn se sotto soglia).
Metodi supportati:
  set_data(...)
  set_done_by_index(...)
  mark_done_by_signature(...)
  set_active_signature(...), highlight_active_signature, mark_active_by_signature,
  set_active_piece_by_signature, set_active_position
"""

from __future__ import annotations
from typing import List, Dict, Any, Tuple, Optional
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QRectF, QSize
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QPolygonF

import math
import logging

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# Utility calcoli
# ----------------------------------------------------------------------
def _external_length(piece: Dict[str, Any]) -> float:
    return float(piece.get("len", piece.get("length_mm", piece.get("length", 0.0))))

def _effective_length(piece: Dict[str, Any], thickness_mm: float) -> float:
    L = _external_length(piece)
    if thickness_mm <= 0: return max(0.0, L)
    ax = abs(float(piece.get("ax", piece.get("ang_sx", 0.0))))
    ad = abs(float(piece.get("ad", piece.get("ang_dx", 0.0))))
    try: c_sx = thickness_mm * math.tan(math.radians(ax))
    except Exception: c_sx = 0.0
    try: c_dx = thickness_mm * math.tan(math.radians(ad))
    except Exception: c_dx = 0.0
    return max(0.0, L - max(0.0,c_sx) - max(0.0,c_dx))

def _angle_offsets_mm(piece: Dict[str, Any], thickness_mm: float) -> Tuple[float,float]:
    """Offset (mm) dovuti agli angoli sinistro e destro per rappresentazione grafica."""
    if thickness_mm <= 0:
        return 0.0, 0.0
    ax = abs(float(piece.get("ax", piece.get("ang_sx", 0.0))))
    ad = abs(float(piece.get("ad", piece.get("ang_dx", 0.0))))
    try: off_sx = thickness_mm * math.tan(math.radians(ax))
    except Exception: off_sx = 0.0
    try: off_dx = thickness_mm * math.tan(math.radians(ad))
    except Exception: off_dx = 0.0
    return max(0.0, off_sx), max(0.0, off_dx)

def _sig(piece: Dict[str, Any]) -> Tuple[float,float,float,str]:
    L = _external_length(piece)
    ax = float(piece.get("ax", piece.get("ang_sx", 0.0)))
    ad = float(piece.get("ad", piece.get("ang_dx", 0.0)))
    prof = str(piece.get("profile","")).strip()
    return (round(L,2), round(ax,1), round(ad,1), prof)

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

        self._done_map: Dict[int,List[bool]] = {}
        self._done_signatures: set[Tuple[float,float,float,str]] = set()

        self._active_pos: Optional[Tuple[int,int]] = None
        self._active_sig: Optional[Tuple[float,float,float,str]] = None

        self._bar_v_space = 14
        self._bar_height = 60
        self._piece_min_w_px = 18
        self.setMinimumHeight(140)
        self.setMouseTracking(True)

    # ---------------- API ----------------
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
        for i,b in enumerate(self._bars):
            dm = self._done_map.get(i)
            if dm is None or len(dm)!=len(b):
                self._done_map[i]=[False]*len(b)
        self._recalc_min_height()
        self.update()

    def set_done_by_index(self, done_map: Dict[int,List[bool]]):
        for bi, arr in done_map.items():
            if bi < len(self._bars) and len(arr)==len(self._bars[bi]):
                self._done_map[bi]=[bool(x) for x in arr]
                for pi,p in enumerate(self._bars[bi]):
                    if self._done_map[bi][pi]:
                        self._done_signatures.add(_sig(p))
        self.update()

    def mark_done_by_signature(self, length_mm: float, ax: float, ad: float):
        sig=(round(float(length_mm),2),round(float(ax),1),round(float(ad),1),"")
        for bi,bar in enumerate(self._bars):
            for pi,p in enumerate(bar):
                psig=_sig(p)
                if psig[:3]==sig[:3]:
                    self._done_signatures.add(psig)
                    if bi not in self._done_map:
                        self._done_map[bi]=[False]*len(bar)
                    self._done_map[bi][pi]=True
                    if self._active_pos == (bi,pi):
                        self._active_pos=None
        self.update()

    def set_active_signature(self, length_mm: float, ax: float, ad: float, profile: str=""):
        target_sig=(round(float(length_mm),2),round(float(ax),1),round(float(ad),1),str(profile or "").strip())
        self._active_sig=target_sig
        self._active_pos=None
        for bi,bar in enumerate(self._bars):
            for pi,p in enumerate(bar):
                psig=_sig(p)
                if psig[:3]==target_sig[:3] and not (
                    (bi in self._done_map and self._done_map[bi][pi]) or (psig in self._done_signatures)
                ):
                    self._active_pos=(bi,pi)
                    self.update()
                    return
        self.update()

    highlight_active_signature = set_active_signature
    mark_active_by_signature = set_active_signature
    set_active_piece_by_signature = set_active_signature

    def set_active_position(self, bar_idx:int, piece_idx:int):
        if 0<=bar_idx<len(self._bars) and 0<=piece_idx<len(self._bars[bar_idx]):
            self._active_pos=(bar_idx,piece_idx)
            self._active_sig=None
            self.update()

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

        left_margin = 160
        usable_w = max(120, W - left_margin - 32)

        for bi, bar in enumerate(self._bars):
            bar_rect = QRectF(10, y, W-20, self._bar_height)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#fcfcfd"))
            painter.drawRoundedRect(bar_rect, 6, 6)
            painter.setPen(QPen(QColor("#bbbbbb"),1))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(bar_rect, 6, 6)

            effs=[_effective_length(p,self._thickness_mm) for p in bar]
            total_eff = sum(effs)
            joints = 0.0
            if len(bar)>1:
                joints = (self._kerf_base + max(0.0,self._ripasso_mm))*(len(bar)-1)
            used_len = total_eff + joints
            residual = max(0.0, self._stock_mm - used_len)

            painter.setPen(QPen(QColor("#222"),1))
            title = f"Barra {bi+1}  Usato eff.: {used_len:.1f} mm  Residuo: {residual:.1f} mm"
            if residual <= self._warn_thr + 1e-6:
                title += " [WARN]"
            painter.drawText(QRectF(14,y+4,left_margin-8,14), Qt.AlignLeft|Qt.AlignVCenter, title)

            x_piece = left_margin
            top_piece = y + 18
            h_piece = self._bar_height - 26

            # Scala basata su lunghezza effettiva totale (visual comparabile a consumo)
            scale = (usable_w / max(used_len, self._stock_mm)) if used_len>0 else 0.0

            for pi,p in enumerate(bar):
                eff=_effective_length(p,self._thickness_mm)
                ext=_external_length(p)
                # width basata sull'effettivo consumo (eff)
                piece_w = max(self._piece_min_w_px, eff*scale)
                joint_w = 0.0
                if pi < len(bar)-1:
                    joint_w = (self._kerf_base + max(0.0,self._ripasso_mm))*scale

                sig=_sig(p)
                done = (bi in self._done_map and pi < len(self._done_map[bi]) and self._done_map[bi][pi]) or sig in self._done_signatures
                active = (self._active_pos == (bi,pi))

                if done:
                    col_fill = QColor(115,215,115)
                    col_edge = QColor(75,165,75)
                    txt_color = Qt.white
                elif active:
                    col_fill = QColor(255,195,110)
                    col_edge = QColor(255,140,0)
                    txt_color = Qt.black
                else:
                    col_fill = QColor(205,205,205)
                    col_edge = QColor(150,150,150)
                    txt_color = Qt.black

                # Calcolo offset angoli realistici (mm → px)
                off_sx_mm, off_dx_mm = _angle_offsets_mm(p, self._thickness_mm)
                off_total_mm = off_sx_mm + off_dx_mm
                # Larghezza superiore (rappresenta ext) scalata a piece_w * (ext/eff) se eff>0
                top_w = piece_w
                if eff > 0 and ext >= eff:
                    top_w = piece_w * (ext / eff)
                # pixel offset
                off_sx_px = off_sx_mm * scale
                off_dx_px = off_dx_mm * scale

                # Limiti: non più del 65% della larghezza superiore
                max_taper_px = top_w * 0.65
                if off_sx_px + off_dx_px > max_taper_px:
                    ratio = max_taper_px / (off_sx_px + off_dx_px + 1e-9)
                    off_sx_px *= ratio
                    off_dx_px *= ratio

                # base inferiore width
                bottom_w = max(4.0, top_w - (off_sx_px + off_dx_px))

                # coordinate trapezio
                top_left_x = x_piece
                top_right_x = x_piece + top_w
                bottom_left_x = x_piece + off_sx_px
                bottom_right_x = bottom_left_x + bottom_w

                poly = QPolygonF([
                    QPointF(top_left_x, top_piece),
                    QPointF(top_right_x, top_piece),
                    QPointF(bottom_right_x, top_piece + h_piece),
                    QPointF(bottom_left_x, top_piece + h_piece)
                ])

                painter.setPen(Qt.NoPen)
                painter.setBrush(col_fill)
                painter.drawPolygon(poly)
                painter.setPen(QPen(col_edge,1))
                painter.drawPolygon(poly)

                # testo
                painter.setPen(QPen(txt_color,1))
                length_text = f"{sig[0]:.0f}"
                ax_val = int(round(sig[1]))
                ad_val = int(round(sig[2]))
                if (ax_val!=0 or ad_val!=0) and top_w > 55:
                    length_text += f"\n{ax_val}/{ad_val}"
                text_rect = QRectF(top_left_x, top_piece, top_w, h_piece)
                painter.drawText(text_rect, Qt.AlignCenter, length_text)

                # evidenzia attivo
                if active:
                    painter.setPen(QPen(QColor(255,100,0),2))
                    painter.setBrush(Qt.NoBrush)
                    painter.drawPolygon(poly)

                # avanza x usando consumo effettivo (piece_w) + giunzione (joint_w)
                x_piece += piece_w
                if joint_w > 0:
                    r_joint = QRectF(x_piece, top_piece + h_piece*0.25, joint_w, h_piece*0.50)
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(QColor(235,235,235))
                    painter.drawRect(r_joint)
                    painter.setPen(QPen(QColor(180,180,180),1,Qt.DashLine))
                    painter.drawRect(r_joint)
                    x_piece += joint_w

            # residuo
            if residual>0:
                res_w = residual*scale
                if res_w > 4:
                    r_res = QRectF(x_piece, top_piece, max(4,res_w), h_piece)
                    warn = residual <= self._warn_thr + 1e-6
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(QColor(255,210,210) if warn else QColor(255,232,232))
                    painter.drawRoundedRect(r_res,4,4)
                    painter.setPen(QPen(QColor(200,90 if warn else 120,90),1))
                    painter.drawRoundedRect(r_res,4,4)
                    painter.setPen(QPen(Qt.black,1))
                    painter.drawText(r_res, Qt.AlignCenter, f"{residual:.0f}")

            y += self._bar_height + self._bar_v_space

    def mousePressEvent(self, ev):
        super().mousePressEvent(ev)

# Alias compatibilità
PlanVisualizer = PlanVisualizerWidget
