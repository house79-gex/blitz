"""
PlanVisualizerWidget (rappresentazione realistica angoli)
- Barra occupa tutta la larghezza disponibile.
- Pezzi disegnati come trapezi se angoli != 0°:
    offset_px = ROW_HEIGHT_PX * tan(angle_rad)
    (angolo 45° produce offset ~= altezza, quindi lato a 45° reale)
- Kerf tra i pezzi proporzionale (kerf_mm * scale) con min visivo.
- Solo il pezzo attivo evidenziato (arancione), tagliati verdi, pendenti grigi.
- Mark singolo pezzo come completato: mark_done_at / mark_done_by_signature.

API mantenute per compatibilità:
  set_data(...)
  set_done_by_index(...)
  mark_done_by_signature(...)
  set_active_signature(...)
  highlight_active_signature(...)
  mark_active_by_signature(...)
  set_active_piece_by_signature(...)
  set_active_position(...)
  set_active_piece_by_indices(...)
  mark_done_at(...)

Nota: thickness_mm non influisce sulla grafica (è geometria 2D stilizzata).
Residuo non disegnato in questa versione (si può aggiungere).
"""

from __future__ import annotations
from typing import List, Dict, Any, Tuple, Optional

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QRectF, QSize, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QPolygonF

import math
import logging

logger = logging.getLogger(__name__)

# Layout costanti
ROW_HEIGHT_PX = 30            # altezza di ogni barra
BAR_VERTICAL_GAP = 12         # spazio tra barre
LEFT_MARGIN_PX = 16
RIGHT_MARGIN_PX = 16
TOP_MARGIN_PX = 16

MIN_PIECE_WIDTH_PX = 28       # larghezza minima visiva pezzo
MIN_KERF_WIDTH_PX = 4         # kerf minimo visuale
MAX_TAPER_RATIO = 0.65        # somma degli offset max = 65% top width
ANGLE_CLAMP_DEG = 89.0        # se angolo >= 89 → considerato verticale

# Firma
def _signature(p: Dict[str, Any]) -> Tuple[float,float,float,str]:
    L = float(p.get("len", p.get("length_mm", p.get("length", 0.0))))
    ax = float(p.get("ax", p.get("ang_sx", 0.0)))
    ad = float(p.get("ad", p.get("ang_dx", 0.0)))
    prof = str(p.get("profile","")).strip()
    return (round(L,2), round(ax,1), round(ad,1), prof)

def _ext_len(p: Dict[str, Any]) -> float:
    return float(p.get("len", p.get("length_mm", p.get("length", 0.0))))

def _get_angles(p: Dict[str, Any]) -> Tuple[float,float]:
    ax = float(p.get("ax", p.get("ang_sx", 0.0)))
    ad = float(p.get("ad", p.get("ang_dx", 0.0)))
    return ax, ad

def _offset_px_for_angle(angle_deg: float, height_px: float) -> float:
    # Angolo >0 produce offset = height * tan(angle)
    a = abs(angle_deg)
    if a <= 0.01:
        return 0.0
    if a >= ANGLE_CLAMP_DEG:
        return 0.0  # taglio quasi verticale -> nessun offset orizzontale
    rad = math.radians(a)
    return height_px * math.tan(rad)


class PlanVisualizerWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._bars: List[List[Dict[str, Any]]] = []

        self._stock_mm: float = 0.0
        self._kerf_mm: float = 0.0
        self._ripasso_mm: float = 0.0
        self._thickness_mm: float = 0.0
        self._warn_thr: float = 0.0

        self._done_map: Dict[int,List[bool]] = {}
        self._active_pos: Optional[Tuple[int,int]] = None
        self._active_sig: Optional[Tuple[float,float,float,str]] = None

        self.setMouseTracking(True)
        self._recalc_min_height()

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
        self._kerf_mm = float(kerf_base or 0.0)
        self._ripasso_mm = float(ripasso_mm or 0.0)
        self._thickness_mm = float(thickness_mm or 0.0)
        self._warn_thr = float(warn_threshold_mm or 0.0)

        # normalizza done map
        new_map={}
        for i,b in enumerate(self._bars):
            arr=self._done_map.get(i)
            if arr is None or len(arr)!=len(b):
                new_map[i]=[False]*len(b)
            else:
                new_map[i]=arr
        self._done_map=new_map
        self._active_pos=None
        self._active_sig=None
        self._recalc_min_height()
        self.update()

    def set_done_by_index(self, done_map: Dict[int,List[bool]]):
        for bi, arr in done_map.items():
            if bi < len(self._bars) and len(arr)==len(self._bars[bi]):
                self._done_map[bi] = [bool(x) for x in arr]
        self.update()

    def mark_done_at(self, bar_idx:int, piece_idx:int):
        if 0<=bar_idx<len(self._bars) and 0<=piece_idx<len(self._bars[bar_idx]):
            self._done_map.setdefault(bar_idx,[False]*len(self._bars[bar_idx]))
            self._done_map[bar_idx][piece_idx]=True
            if self._active_pos == (bar_idx,piece_idx):
                self._active_pos=None
            self.update()

    def mark_done_by_signature(self, length_mm: float, ax: float, ad: float):
        target = (round(float(length_mm),2), round(float(ax),1), round(float(ad),1))
        for bi,bar in enumerate(self._bars):
            for pi,p in enumerate(bar):
                if self._done_map.get(bi,[False]*len(bar))[pi]:
                    continue
                sig=_signature(p)
                if sig[0]==target[0] and sig[1]==target[1] and sig[2]==target[2]:
                    self.mark_done_at(bi,pi)
                    return

    def set_active_signature(self, length_mm: float, ax: float, ad: float, profile: str=""):
        target=(round(float(length_mm),2), round(float(ax),1), round(float(ad),1), profile.strip())
        self._active_sig=target
        self._active_pos=None
        for bi, bar in enumerate(self._bars):
            for pi, p in enumerate(bar):
                if self._done_map.get(bi,[False]*len(bar))[pi]:
                    continue
                sig=_signature(p)
                if sig[:3]==target[:3]:
                    self._active_pos=(bi,pi)
                    self.update()
                    return
        self.update()

    highlight_active_signature = set_active_signature
    mark_active_by_signature = set_active_signature
    set_active_piece_by_signature = set_active_signature

    def set_active_position(self, bar_idx:int, piece_idx:int):
        if 0<=bar_idx<len(self._bars) and 0<=piece_idx<len(self._bars[bar_idx]):
            if not self._done_map.get(bar_idx,[False]*len(self._bars[bar_idx]))[piece_idx]:
                self._active_pos=(bar_idx,piece_idx)
                self._active_sig=None
                self.update()

    set_active_piece_by_indices = set_active_position

    # ---------------- Layout ----------------
    def _recalc_min_height(self):
        h = TOP_MARGIN_PX + len(self._bars)*(ROW_HEIGHT_PX + BAR_VERTICAL_GAP) + 20
        self.setMinimumHeight(max(140,h))

    def sizeHint(self) -> QSize:
        return QSize(max(900,self.width()), self.minimumHeight())

    # ---------------- Paint ----------------
    def paintEvent(self, ev):
        painter=QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        try:
            W=self.width()
            usable_left=LEFT_MARGIN_PX
            usable_right=W-RIGHT_MARGIN_PX
            inner_width=max(100, usable_right-usable_left)

            y=TOP_MARGIN_PX

            font=QFont()
            font.setPointSize(8)
            painter.setFont(font)

            if not self._bars:
                painter.setPen(QPen(QColor("#555"),1))
                painter.drawText(self.rect(), Qt.AlignCenter, "Nessun piano")
                return

            for bi, bar in enumerate(self._bars):
                # lunghezza totale per scala = somma pezzi + kerf*(n-1)
                total_mm = sum(_ext_len(p) for p in bar) + (len(bar)-1)*self._kerf_mm if len(bar)>1 else sum(_ext_len(p) for p in bar)
                total_mm = max(1.0,total_mm)
                scale = inner_width / total_mm

                # sfondo barra
                bar_rect = QRectF(usable_left-6, y-4, inner_width+12, ROW_HEIGHT_PX+8)
                painter.setPen(QPen(QColor("#d0d0d0"),1))
                painter.setBrush(QColor("#fafafa"))
                painter.drawRoundedRect(bar_rect,6,6)

                # etichetta barra
                painter.setPen(QPen(QColor("#222"),1))
                painter.drawText(QRectF(usable_left-2, y-2, 50, ROW_HEIGHT_PX+4),
                                 Qt.AlignLeft | Qt.AlignVCenter,
                                 f"B{bi+1}")

                x_cursor = usable_left

                for pi, p in enumerate(bar):
                    L_mm = _ext_len(p)
                    piece_w = L_mm * scale
                    if piece_w < MIN_PIECE_WIDTH_PX:
                        piece_w = MIN_PIECE_WIDTH_PX  # minima visiva

                    ax, ad = _get_angles(p)
                    off_sx_px = _offset_px_for_angle(ax, ROW_HEIGHT_PX)
                    off_dx_px = _offset_px_for_angle(ad, ROW_HEIGHT_PX)

                    # Limita offset e somma per evitare inversioni
                    taper_sum = off_sx_px + off_dx_px
                    max_taper = piece_w * MAX_TAPER_RATIO
                    if taper_sum > max_taper:
                        ratio = max_taper/(taper_sum+1e-9)
                        off_sx_px *= ratio
                        off_dx_px *= ratio
                        taper_sum = off_sx_px + off_dx_px

                    bottom_w = max(4.0, piece_w - taper_sum)

                    top_left = QPointF(x_cursor, y)
                    top_right = QPointF(x_cursor + piece_w, y)
                    bottom_left = QPointF(x_cursor + off_sx_px, y + ROW_HEIGHT_PX)
                    bottom_right = QPointF(x_cursor + off_sx_px + bottom_w, y + ROW_HEIGHT_PX)

                    poly = QPolygonF([top_left, top_right, bottom_right, bottom_left])

                    done = self._done_map.get(bi,[False]*len(bar))[pi]
                    active = (self._active_pos == (bi,pi))

                    if done:
                        fill_col=QColor(115,215,115)
                        edge_col=QColor(70,160,70)
                        txt_col=QColor(255,255,255)
                    elif active:
                        fill_col=QColor(255,195,110)
                        edge_col=QColor(255,140,0)
                        txt_col=QColor(0,0,0)
                    else:
                        fill_col=QColor(205,205,205)
                        edge_col=QColor(150,150,150)
                        txt_col=QColor(0,0,0)

                    painter.setPen(Qt.NoPen)
                    painter.setBrush(fill_col)
                    painter.drawPolygon(poly)
                    painter.setPen(QPen(edge_col,1))
                    painter.drawPolygon(poly)

                    sig=_signature(p)
                    txt=f"{sig[0]:.0f}"
                    axi=int(round(sig[1])); adi=int(round(sig[2]))
                    if (axi!=0 or adi!=0) and piece_w > 70:
                        txt+=f"\n{axi}/{adi}"
                    painter.setPen(QPen(txt_col,1))
                    painter.drawText(QRectF(x_cursor, y, piece_w, ROW_HEIGHT_PX),
                                     Qt.AlignCenter, txt)

                    if active:
                        painter.setPen(QPen(QColor(255,100,0),2))
                        painter.drawPolygon(poly)

                    x_cursor += piece_w

                    # gap kerf
                    if pi < len(bar)-1:
                        gap_w = self._kerf_mm * scale
                        if gap_w < MIN_KERF_WIDTH_PX:
                            gap_w = MIN_KERF_WIDTH_PX
                        gap_rect = QRectF(x_cursor, y, gap_w, ROW_HEIGHT_PX)
                        painter.setPen(Qt.NoPen)
                        painter.setBrush(QColor(230,230,230))
                        painter.drawRect(gap_rect)
                        painter.setPen(QPen(QColor(180,180,180),1, Qt.DashLine))
                        painter.drawRect(gap_rect)
                        x_cursor += gap_w

                y += ROW_HEIGHT_PX + BAR_VERTICAL_GAP

        except Exception as e:
            logger.error(f"Errore paintEvent PlanVisualizer: {e}", exc_info=True)

    def mousePressEvent(self, ev):
        super().mousePressEvent(ev)


PlanVisualizer = PlanVisualizerWidget
