"""
PlanVisualizerWidget
Visualizzazione grafica piano di taglio:
- Altezza barra (tutti i pezzi su una riga) fissa.
- La larghezza totale della riga riempie ~95% dello spazio disponibile interno.
- Ogni pezzo è un trapezio separato dagli altri da un gap kerf.
- Trapezio:
    top width = lunghezza esterna (len)
    bottom width = top width - (offset_sx_px + offset_dx_px)
    offset = thickness_mm * tan(angolo) convertito in pixel; se angolo >0 ma offset in px troppo piccolo, si forza OFFSET_MIN_PX.
- Nessun uso dello stock per la scala (si scala sul totale dei pezzi reali + kerf).
- I gap kerf sono sempre visibili (minimo KERF_MIN_PX).
- Evidenziazione:
    pezzo attivo: arancione
    pezzo completato: verde
    pezzo pendente: grigio

API supportate:
  set_data(bars, stock_mm, kerf_base, ripasso_mm, reversible, thickness_mm, angle_tol, max_angle, max_factor, warn_threshold_mm)
  set_done_by_index(done_map)
  mark_done_by_signature(length_mm, ax, ad)
  set_active_signature(length_mm, ax, ad, profile="")
  highlight_active_signature (alias)
  mark_active_by_signature (alias)
  set_active_piece_by_signature (alias)
  set_active_position(bar_idx, piece_idx)
  set_active_piece_by_indices(bar_idx, piece_idx)
  mark_done_at(bar_idx, piece_idx)

Note:
- Il parametro stock_mm è conservato per compatibilità ma non influenza la scala orizzontale.
- warn_threshold_mm (self._warn_thr) non viene usato finché non reintroduciamo il residuo (qui non mostriamo residuo).
"""

from __future__ import annotations
from typing import List, Dict, Any, Tuple, Optional

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QRectF, QSize, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QPolygonF

import math
import logging

logger = logging.getLogger(__name__)

# Parametri di layout
ROW_HEIGHT_PX = 22          # altezza totale di ogni barra
BAR_VERTICAL_GAP = 10       # spazio verticale tra barre
LEFT_MARGIN_PX = 12         # margine sinistro interno
RIGHT_MARGIN_PX = 12        # margine destro interno
TOP_MARGIN_PX = 10

FILL_RATIO = 0.95           # % della larghezza interna da riempire coi pezzi
MIN_PIECE_WIDTH_PX = 18     # larghezza minima di un pezzo per non sparire
KERF_MIN_PX = 3.0           # larghezza minima visiva del gap kerf
OFFSET_MIN_PX = 2.0         # offset minimo per angoli > 0°
OFFSET_SCALE_BOOST = 1.5    # moltiplicatore sugli offset (aumenta la “inclinazione”)

# Firma (signature) = (lunghezza, angolo sx, angolo dx, profilo)
def _signature(p: Dict[str, Any]) -> Tuple[float,float,float,str]:
    L = float(p.get("len", p.get("length_mm", p.get("length", 0.0))))
    ax = float(p.get("ax", p.get("ang_sx", 0.0)))
    ad = float(p.get("ad", p.get("ang_dx", 0.0)))
    prof = str(p.get("profile", "")).strip()
    return (round(L,2), round(ax,1), round(ad,1), prof)

def _ext_len(p: Dict[str, Any]) -> float:
    return float(p.get("len", p.get("length_mm", p.get("length", 0.0))))

def _offsets_mm(p: Dict[str, Any], thickness_mm: float) -> Tuple[float,float]:
    if thickness_mm <= 0:
        return 0.0, 0.0
    ax = abs(float(p.get("ax", p.get("ang_sx", 0.0))))
    ad = abs(float(p.get("ad", p.get("ang_dx", 0.0))))
    try:
        sx = thickness_mm * math.tan(math.radians(ax))
    except Exception:
        sx = 0.0
    try:
        dx = thickness_mm * math.tan(math.radians(ad))
    except Exception:
        dx = 0.0
    return max(0.0,sx), max(0.0,dx)


class PlanVisualizerWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._bars: List[List[Dict[str, Any]]] = []
        self._stock_mm: float = 0.0
        self._thickness_mm: float = 0.0
        self._kerf_base: float = 0.0
        self._ripasso_mm: float = 0.0
        self._warn_thr: float = 0.0

        self._done_map: Dict[int,List[bool]] = {}
        self._active_pos: Optional[Tuple[int,int]] = None
        self._active_sig: Optional[Tuple[float,float,float,str]] = None  # fallback

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
        # Parametri non usati direttamente nel disegno (reversible, angle_tol, max_angle, max_factor)
        self._bars = bars or []
        self._stock_mm = float(stock_mm or 0.0)
        self._kerf_base = float(kerf_base or 0.0)
        self._ripasso_mm = float(ripasso_mm or 0.0)  # non usato per la grafica
        self._thickness_mm = float(thickness_mm or 0.0)
        self._warn_thr = float(warn_threshold_mm or 0.0)
        # Normalizza done map
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
            if bi < len(self._bars) and len(arr) == len(self._bars[bi]):
                self._done_map[bi]=[bool(x) for x in arr]
        self.update()

    def mark_done_at(self, bar_idx: int, piece_idx: int):
        if 0<=bar_idx<len(self._bars) and 0<=piece_idx<len(self._bars[bar_idx]):
            self._done_map.setdefault(bar_idx,[False]*len(self._bars[bar_idx]))
            self._done_map[bar_idx][piece_idx]=True
            if self._active_pos==(bar_idx,piece_idx):
                self._active_pos=None
            self.update()

    def mark_done_by_signature(self, length_mm: float, ax: float, ad: float):
        target = (round(float(length_mm),2), round(float(ax),1), round(float(ad),1))
        for bi, bar in enumerate(self._bars):
            for pi, p in enumerate(bar):
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
        h = TOP_MARGIN_PX + len(self._bars)*(ROW_HEIGHT_PX+BAR_VERTICAL_GAP) + 10
        self.setMinimumHeight(max(120,h))

    def sizeHint(self)->QSize:
        return QSize(max(640,self.width()), self.minimumHeight())

    # ---------------- Paint ----------------
    def paintEvent(self, ev):
        painter=QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        try:
            W=self.width()
            usable_left=LEFT_MARGIN_PX
            usable_right=W-RIGHT_MARGIN_PX
            usable_width=max(100, usable_right-usable_left)
            y=TOP_MARGIN_PX

            font=QFont()
            font.setPointSize(7)
            painter.setFont(font)

            if not self._bars:
                painter.setPen(QPen(QColor("#555"),1))
                painter.drawText(self.rect(), Qt.AlignCenter, "Nessun piano")
                return

            for bi, bar in enumerate(self._bars):
                # Calcolo lunghezza totale reale per scala (somma lunghezze esterne + kerf tra pezzi)
                total_ext = sum(_ext_len(p) for p in bar)
                total_kerf = (len(bar)-1)*self._kerf_base if len(bar)>1 else 0.0
                total_display_mm = max(1.0, total_ext + total_kerf)

                scale = (usable_width * FILL_RATIO) / total_display_mm

                x_cursor = usable_left + (usable_width * (1 - FILL_RATIO)/2.0)  # centratura orizzontale

                # Bordo barra
                bar_rect = QRectF(usable_left-4, y-2, usable_width+8, ROW_HEIGHT_PX+4)
                painter.setPen(QPen(QColor("#d0d0d0"),1))
                painter.setBrush(QColor("#fefefe"))
                painter.drawRoundedRect(bar_rect,4,4)

                # Titolo a sinistra
                painter.setPen(QPen(QColor("#222"),1))
                painter.drawText(QRectF(4,y-1, usable_left-8, ROW_HEIGHT_PX+2),
                                 Qt.AlignLeft | Qt.AlignVCenter, f"B{bi+1}")

                # Disegno pezzi
                for pi, p in enumerate(bar):
                    ext_len_mm = _ext_len(p)
                    piece_w = ext_len_mm * scale
                    if piece_w < MIN_PIECE_WIDTH_PX:
                        piece_w = MIN_PIECE_WIDTH_PX  # larghezza minima

                    off_sx_mm, off_dx_mm = _offsets_mm(p, self._thickness_mm)
                    off_sx_mm *= OFFSET_SCALE_BOOST
                    off_dx_mm *= OFFSET_SCALE_BOOST

                    # Converti in pixel
                    off_sx_px = off_sx_mm * scale if off_sx_mm>0 else 0.0
                    off_dx_px = off_dx_mm * scale if off_dx_mm>0 else 0.0

                    # Forza offset minimo se angolo > 0
                    if off_sx_mm > 0 and off_sx_px < OFFSET_MIN_PX: off_sx_px = OFFSET_MIN_PX
                    if off_dx_mm > 0 and off_dx_px < OFFSET_MIN_PX: off_dx_px = OFFSET_MIN_PX

                    # Limita somma offset se troppo grande (evita base negativa)
                    max_taper = piece_w*0.75
                    taper_sum = off_sx_px + off_dx_px
                    if taper_sum > max_taper:
                        ratio = max_taper/(taper_sum+1e-9)
                        off_sx_px *= ratio
                        off_dx_px *= ratio
                        taper_sum = off_sx_px + off_dx_px

                    bottom_w = max(4.0, piece_w - taper_sum)

                    top_left  = QPointF(x_cursor, y)
                    top_right = QPointF(x_cursor + piece_w, y)
                    bottom_left  = QPointF(x_cursor + off_sx_px, y + ROW_HEIGHT_PX)
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

                    # Testo
                    sig=_signature(p)
                    text = f"{sig[0]:.0f}"
                    axi=int(round(sig[1])); adi=int(round(sig[2]))
                    if (axi!=0 or adi!=0) and piece_w > 55:
                        text += f"\n{axi}/{adi}"
                    painter.setPen(QPen(txt_col,1))
                    painter.drawText(QRectF(x_cursor, y, piece_w, ROW_HEIGHT_PX), Qt.AlignCenter, text)

                    if active:
                        painter.setPen(QPen(QColor(255,100,0),2))
                        painter.drawPolygon(poly)

                    x_cursor += piece_w

                    # Gap kerf (solo tra pezzi)
                    if pi < len(bar)-1:
                        kerf_mm = self._kerf_base
                        gap_w = kerf_mm * scale
                        if gap_w < KERF_MIN_PX: gap_w = KERF_MIN_PX
                        gap_rect = QRectF(x_cursor, y, gap_w, ROW_HEIGHT_PX)
                        painter.setPen(Qt.NoPen)
                        painter.setBrush(QColor(240,240,240))
                        painter.drawRect(gap_rect)
                        painter.setPen(QPen(QColor(190,190,190),1, Qt.DashLine))
                        painter.drawRect(gap_rect)
                        x_cursor += gap_w

                y += ROW_HEIGHT_PX + BAR_VERTICAL_GAP

        except Exception as e:
            logger.error(f"Errore paintEvent: {e}", exc_info=True)

    def mousePressEvent(self, ev):
        # Non gestiamo selezioni dirette per ora
        super().mousePressEvent(ev)


# Alias compatibilità
PlanVisualizer = PlanVisualizerWidget
