"""
PlanVisualizerWidget compatibile con OptimizationRunDialog
Rappresentazione grafica barre e pezzi:
- Ogni pezzo come trapezio (base superiore più larga, base inferiore più stretta)
  con i lati inclinati proporzionalmente agli angoli ax/ad.
- Solo il pezzo attivo viene evidenziato (arancione); pezzi completati in verde; pendenti grigi.
- Residuo visualizzato a fine barra (rosso chiaro, warning se sotto soglia).
Metodi richiesti dal dialog:
  set_data(...)
  set_done_by_index(...)
  mark_done_by_signature(...)
  set_active_signature(...)/alias highlight/mark_active/set_active_piece_by_signature
Internamente se viene chiamato set_active_signature cerca il primo pezzo non completato con quella firma.
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
# Utility
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

def _sig(piece: Dict[str, Any]) -> Tuple[float,float,float,str]:
    L = float(piece.get("len", piece.get("length_mm", piece.get("length", 0.0))))
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

        # Active piece position (preferred)
        self._active_pos: Optional[Tuple[int,int]] = None
        # Fallback signature search (if only signature passed)
        self._active_sig: Optional[Tuple[float,float,float,str]] = None

        self._bar_v_space = 14
        self._bar_height = 52
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
        # normalize done map
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
                # update signatures
                for pi,p in enumerate(self._bars[bi]):
                    if self._done_map[bi][pi]:
                        self._done_signatures.add(_sig(p))
        self.update()

    def mark_done_by_signature(self, length_mm: float, ax: float, ad: float):
        sig=(round(float(length_mm),2),round(float(ax),1),round(float(ad),1),"")
        # match ignoring profile for marking (profile optional)
        # Add all matches as done
        for bi,bar in enumerate(self._bars):
            for pi,p in enumerate(bar):
                psig=_sig(p)
                if psig[:3]==sig[:3]:
                    self._done_signatures.add(psig)
                    if bi not in self._done_map:
                        self._done_map[bi]=[False]*len(bar)
                    self._done_map[bi][pi]=True
                    # se era l'attivo, rimuovi highlight
                    if self._active_pos == (bi,pi):
                        self._active_pos=None
        self.update()

    # Attivo per firma (usato dal dialog)
    def set_active_signature(self, length_mm: float, ax: float, ad: float,
                             profile: str = ""):
        target_sig=(round(float(length_mm),2),round(float(ax),1),round(float(ad),1),str(profile or "").strip())
        self._active_sig=target_sig
        # trova primo pezzo non completato con quella firma
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
        # se non trovato, highlight nulla
        self.update()

    # Alias richiesti
    highlight_active_signature = set_active_signature
    mark_active_by_signature = set_active_signature
    set_active_piece_by_signature = set_active_signature

    # Possibile API aggiuntiva (se in futuro si usa direttamente bar,idx)
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

        left_margin = 150
        usable_w = max(100, W - left_margin - 28)

        for bi, bar in enumerate(self._bars):
            bar_rect = QRectF(10, y, W-20, self._bar_height)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#fcfcfc"))
            painter.drawRoundedRect(bar_rect, 6, 6)
            painter.setPen(QPen(QColor("#c5c5c5"),1))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(bar_rect, 6, 6)

            effs=[_effective_length(p,self._thickness_mm) for p in bar]
            total_eff = sum(effs)
            joints = 0.0
            if len(bar)>1:
                joints = (self._kerf_base + max(0.0,self._ripasso_mm))*(len(bar)-1)
            used_len = total_eff + joints
            residual = max(0.0, self._stock_mm - used_len)

            painter.setPen(QPen(QColor("#333"),1))
            title = f"Barra {bi+1}  Usato: {used_len:.1f} mm  Residuo: {residual:.1f} mm"
            if residual <= self._warn_thr + 1e-6:
                title += "  [WARN]"
            painter.drawText(QRectF(14,y+4,left_margin-6,12), Qt.AlignLeft|Qt.AlignVCenter, title)

            x_piece = left_margin
            h_piece = self._bar_height - 22
            top_piece = y + 18

            scale = (usable_w / max(used_len, self._stock_mm)) if used_len>0 else 0.0

            for pi,p in enumerate(bar):
                eff=effs[pi]
                piece_w = max(self._piece_min_w_px, eff*scale)
                joint_w = 0.0
                if pi < len(bar)-1:
                    joint_w = (self._kerf_base + max(0.0,self._ripasso_mm))*scale

                sig=_sig(p)
                done = (bi in self._done_map and pi < len(self._done_map[bi]) and self._done_map[bi][pi]) or sig in self._done_signatures
                active = (self._active_pos == (bi,pi))

                if done:
                    col1,col2 = QColor(115,215,115), QColor(75,165,75)
                    txt_color = Qt.white
                elif active:
                    col1,col2 = QColor(255,195,110), QColor(255,140,0)
                    txt_color = Qt.black
                else:
                    col1,col2 = QColor(205,205,205), QColor(150,150,150)
                    txt_color = Qt.black

                # Trapezio: base superiore = piece_w, base inferiore = piece_w - taper_left - taper_right
                # Taper proporzionale agli angoli (limite 35% larghezza totale).
                ax = abs(sig[1])
                ad = abs(sig[2])
                max_taper_ratio = 0.35
                taper_left = piece_w * max_taper_ratio * min(ax/90.0,1.0)
                taper_right = piece_w * max_taper_ratio * min(ad/90.0,1.0)
                # Evita che la base inferiore risulti negativa
                total_taper = min(taper_left + taper_right, piece_w * 0.6)
                if taper_left + taper_right > total_taper:
                    # ridistribuisce proporzionalmente
                    ratio = total_taper / (taper_left + taper_right + 1e-9)
                    taper_left *= ratio
                    taper_right *= ratio

                top_left_x = x_piece
                top_right_x = x_piece + piece_w
                bottom_left_x = x_piece + taper_left
                bottom_right_x = x_piece + piece_w - taper_right

                poly = QPolygonF([
                    QRectF(top_left_x, top_piece, 0,0).topLeft(),
                    QRectF(top_right_x, top_piece,0,0).topLeft(),
                    QRectF(bottom_right_x, top_piece + h_piece,0,0).bottomLeft(),
                    QRectF(bottom_left_x, top_piece + h_piece,0,0).bottomLeft()
                ])

                painter.setPen(Qt.NoPen)
                painter.setBrush(col1)
                painter.drawPolygon(poly)
                painter.setPen(QPen(col2,1))
                painter.drawPolygon(poly)

                # Testo
                painter.setPen(QPen(txt_color,1))
                piece_text = f"{sig[0]:.0f}"
                if (ax!=0.0 or ad!=0.0) and piece_w > 55:
                    piece_text += f"\n{int(sig[1])}/{int(sig[2])}"
                # area disponibile: bounding box del trapezio
                text_rect = QRectF(x_piece, top_piece, piece_w, h_piece)
                painter.drawText(text_rect, Qt.AlignCenter, piece_text)

                # Evidenzia attivo
                if active:
                    painter.setPen(QPen(QColor(255,100,0),2))
                    painter.setBrush(Qt.NoBrush)
                    painter.drawPolygon(poly)

                x_piece += piece_w

                # Giunzione
                if joint_w > 0:
                    r_joint = QRectF(x_piece, top_piece + h_piece*0.25, joint_w, h_piece*0.50)
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(QColor(235,235,235))
                    painter.drawRect(r_joint)
                    painter.setPen(QPen(QColor(180,180,180),1,Qt.DashLine))
                    painter.drawRect(r_joint)
                    x_piece += joint_w

            # Residuo
            if residual>0:
                res_w = residual*scale
                if res_w > 4:
                    r_res = QRectF(x_piece, top_piece, max(4,res_w), h_piece)
                    warn = residual <= self._warn_thr + 1e-6
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(QColor(255,210,210) if warn else QColor(255,230,230))
                    painter.drawRoundedRect(r_res,4,4)
                    painter.setPen(QPen(QColor(200,90 if warn else 120,90),1))
                    painter.drawRoundedRect(r_res,4,4)
                    painter.setPen(QPen(Qt.black,1))
                    painter.drawText(r_res, Qt.AlignCenter, f"{residual:.0f}")

            y += self._bar_height + self._bar_v_space

    # ---------------- Interazione futura ----------------
    def mousePressEvent(self, ev):
        # Potremmo in futuro tradurre click in selezione pezzo
        super().mousePressEvent(ev)

# Compat alias
PlanVisualizer = PlanVisualizerWidget
