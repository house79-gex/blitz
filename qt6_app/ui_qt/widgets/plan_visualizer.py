"""
PlanVisualizerWidget (rev)
Obiettivi:
- Ogni barra occupa praticamente tutta la larghezza disponibile del widget.
- Ogni pezzo con almeno un angolo != 0° è disegnato come trapezio (anche se thickness_mm=0).
- I pezzi sono separati da un gap visivo kerf (>= KERF_MIN_PX).
- top width = lunghezza esterna (len)
- bottom width = top width - (offset_sx_px + offset_dx_px)
  offset calcolato da thickness_mm * tan(angle) oppure (se thickness=0) da un modello sintetico.
- Forza offset minimo se angolo > 0° (OFFSET_MIN_PX).
- Evidenziazione singolo pezzo attivo; completati verdi; pendenti grigi.

API:
  set_data(bars, stock_mm, kerf_base, ripasso_mm, reversible, thickness_mm, angle_tol, max_angle, max_factor, warn_threshold_mm)
  set_done_by_index(done_map)
  mark_done_by_signature(length_mm, ax, ad)
  set_active_signature(length_mm, ax, ad, profile="")
  set_active_position(bar_idx, piece_idx)
  mark_done_at(bar_idx, piece_idx)
  (alias: highlight_active_signature, mark_active_by_signature, set_active_piece_by_signature, set_active_piece_by_indices)

NOTA: Non disegniamo residuo; stock_mm è ignorato ai fini della scala. L’ordine dei pezzi è quello passato.

Per debug: impostare self._debug = True per vedere il testo di scala e dimensioni.
"""

from __future__ import annotations
from typing import List, Dict, Any, Tuple, Optional

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QRectF, QSize, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QPolygonF

import math
import logging

logger = logging.getLogger(__name__)

# Layout
ROW_HEIGHT_PX = 26            # altezza per riga (bar)
BAR_VERTICAL_GAP = 12         # spazio verticale tra barre
LEFT_MARGIN_PX = 12
RIGHT_MARGIN_PX = 12
TOP_MARGIN_PX = 14

FILL_RATIO = 0.97             # percentuale di larghezza interna da occupare dai pezzi
MIN_PIECE_WIDTH_PX = 24       # larghezza minima di un pezzo
KERF_MIN_PX = 4.0             # gap minimo visivo (kerf)
OFFSET_MIN_PX = 3.0           # offset minimo se angolo > 0°
OFFSET_SYNTH_FACTOR = 0.25    # fattore sintetico per offset se thickness=0 (proporzionale a angolo)
OFFSET_SCALE_BOOST = 1.0      # moltiplicatore ulteriore sugli offset (per renderli più evidenti)
MAX_TAPER_RATIO = 0.75        # somma offset max = piece_w * MAX_TAPER_RATIO

def _angle_value(p: Dict[str, Any], key_a: str, key_b: str) -> float:
    # Recupera valore angolo da possibili chiavi alternative
    return float(p.get(key_a, p.get(key_b, 0.0)))

def _get_angles(p: Dict[str, Any]) -> Tuple[float,float]:
    ax = _angle_value(p, "ax", "ang_sx")
    ad = _angle_value(p, "ad", "ang_dx")
    return ax, ad

def _ext_len(p: Dict[str, Any]) -> float:
    return float(p.get("len", p.get("length_mm", p.get("length", 0.0))))

def _signature(p: Dict[str, Any]) -> Tuple[float,float,float,str]:
    L = _ext_len(p)
    ax, ad = _get_angles(p)
    prof = str(p.get("profile", "")).strip()
    return (round(L,2), round(ax,1), round(ad,1), prof)

def _offsets_mm(p: Dict[str, Any], thickness_mm: float) -> Tuple[float,float]:
    ax, ad = _get_angles(p)
    if thickness_mm > 0:
        try:
            sx = thickness_mm * math.tan(math.radians(abs(ax)))
        except Exception:
            sx = 0.0
        try:
            dx = thickness_mm * math.tan(math.radians(abs(ad)))
        except Exception:
            dx = 0.0
    else:
        # thickness assente: offset sintetico proporzionale all'angolo
        sx = abs(ax) * OFFSET_SYNTH_FACTOR
        dx = abs(ad) * OFFSET_SYNTH_FACTOR
    return max(0.0, sx), max(0.0, dx)


class PlanVisualizerWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._bars: List[List[Dict[str, Any]]] = []
        self._kerf_base: float = 0.0
        self._thickness_mm: float = 0.0
        self._ripasso_mm: float = 0.0
        self._warn_thr: float = 0.0
        self._done_map: Dict[int,List[bool]] = {}
        self._active_pos: Optional[Tuple[int,int]] = None
        self._active_sig: Optional[Tuple[float,float,float,str]] = None
        self._debug: bool = False

        self.setMouseTracking(True)
        self._recalc_min_height()

    # -------------------- API --------------------
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
        # Alcuni parametri non influenzano la grafica (reversible, angle_tol, max_angle, max_factor, stock_mm)
        self._bars = bars or []
        self._kerf_base = float(kerf_base or 0.0)
        self._ripasso_mm = float(ripasso_mm or 0.0)
        self._thickness_mm = float(thickness_mm or 0.0)
        self._warn_thr = float(warn_threshold_mm or 0.0)

        # Normalizza done_map
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
        target=(round(float(length_mm),2), round(float(ax),1), round(float(ad),1))
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

    # -------------------- Layout --------------------
    def _recalc_min_height(self):
        h = TOP_MARGIN_PX + len(self._bars)*(ROW_HEIGHT_PX + BAR_VERTICAL_GAP) + 10
        self.setMinimumHeight(max(120,h))

    def sizeHint(self)->QSize:
        return QSize(max(900,self.width()), self.minimumHeight())

    # -------------------- Paint --------------------
    def paintEvent(self, ev):
        painter=QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        try:
            W=self.width()
            usable_left=LEFT_MARGIN_PX
            usable_right=W-RIGHT_MARGIN_PX
            inner_width=max(100, usable_right-usable_left)  # spazio orizzontale totale

            y=TOP_MARGIN_PX

            font=QFont()
            font.setPointSize(8)
            painter.setFont(font)

            if not self._bars:
                painter.setPen(QPen(QColor("#666"),1))
                painter.drawText(self.rect(), Qt.AlignCenter, "Nessun piano")
                return

            for bi, bar in enumerate(self._bars):
                total_ext = sum(_ext_len(p) for p in bar)
                total_kerf_mm = (len(bar)-1)*self._kerf_base if len(bar)>1 else 0.0
                total_for_scale_mm = max(1.0, total_ext + total_kerf_mm)

                # Scala per occupare FILL_RATIO dell'inner_width
                scale = (inner_width * FILL_RATIO) / total_for_scale_mm
                # x iniziale (centrato orizzontalmente)
                x_cursor = usable_left + (inner_width*(1-FILL_RATIO))/2.0

                # Barra sfondo
                bar_rect = QRectF(usable_left-4, y-3, inner_width+8, ROW_HEIGHT_PX+6)
                painter.setPen(QPen(QColor("#d0d0d0"),1))
                painter.setBrush(QColor("#fdfdfd"))
                painter.drawRoundedRect(bar_rect,5,5)

                # Etichetta barra
                painter.setPen(QPen(QColor("#222"),1))
                painter.drawText(QRectF(usable_left-2, y-2, 60, ROW_HEIGHT_PX+4),
                                 Qt.AlignLeft | Qt.AlignVCenter,
                                 f"B{bi+1}")

                # Disegno pezzi
                for pi, p in enumerate(bar):
                    ext_mm = _ext_len(p)
                    piece_w = ext_mm * scale
                    if piece_w < MIN_PIECE_WIDTH_PX:
                        piece_w = MIN_PIECE_WIDTH_PX

                    # offset mm → px (o sintetici)
                    off_sx_mm, off_dx_mm = _offsets_mm(p, self._thickness_mm)
                    off_sx_mm *= OFFSET_SCALE_BOOST
                    off_dx_mm *= OFFSET_SCALE_BOOST

                    off_sx_px = off_sx_mm * scale if off_sx_mm>0 else 0.0
                    off_dx_px = off_dx_mm * scale if off_dx_mm>0 else 0.0

                    ax, ad = _get_angles(p)
                    if abs(ax)>0.01 and off_sx_px < OFFSET_MIN_PX:
                        off_sx_px = OFFSET_MIN_PX
                    if abs(ad)>0.01 and off_dx_px < OFFSET_MIN_PX:
                        off_dx_px = OFFSET_MIN_PX

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
                        fill_col = QColor(115,215,115)
                        edge_col = QColor(70,160,70)
                        txt_col = QColor(255,255,255)
                    elif active:
                        fill_col = QColor(255,195,110)
                        edge_col = QColor(255,140,0)
                        txt_col = QColor(0,0,0)
                    else:
                        fill_col = QColor(205,205,205)
                        edge_col = QColor(150,150,150)
                        txt_col = QColor(0,0,0)

                    painter.setPen(Qt.NoPen)
                    painter.setBrush(fill_col)
                    painter.drawPolygon(poly)
                    painter.setPen(QPen(edge_col,1))
                    painter.drawPolygon(poly)

                    sig=_signature(p)
                    txt=f"{sig[0]:.0f}"
                    axi=int(round(sig[1])); adi=int(round(sig[2]))
                    if (axi!=0 or adi!=0) and piece_w > 60:
                        txt += f"\n{axi}/{adi}"
                    painter.setPen(QPen(txt_col,1))
                    painter.drawText(QRectF(x_cursor, y, piece_w, ROW_HEIGHT_PX),
                                     Qt.AlignCenter, txt)

                    if active:
                        painter.setPen(QPen(QColor(255,100,0),2))
                        painter.drawPolygon(poly)

                    x_cursor += piece_w

                    # Gap kerf
                    if pi < len(bar)-1:
                        gap_mm = self._kerf_base
                        gap_w = gap_mm * scale
                        if gap_w < KERF_MIN_PX:
                            gap_w = KERF_MIN_PX
                        gap_rect = QRectF(x_cursor, y, gap_w, ROW_HEIGHT_PX)
                        painter.setPen(Qt.NoPen)
                        painter.setBrush(QColor(235,235,235))
                        painter.drawRect(gap_rect)
                        painter.setPen(QPen(QColor(180,180,180),1, Qt.DashLine))
                        painter.drawRect(gap_rect)
                        x_cursor += gap_w

                # Debug info
                if self._debug:
                    painter.setPen(QPen(QColor("#000"),1))
                    painter.drawText(QRectF(usable_left + 120, y - 10, inner_width - 140, 12),
                                     Qt.AlignLeft,
                                     f"[DEBUG] scale={scale:.4f} total_mm={total_for_scale_mm:.1f}")

                y += ROW_HEIGHT_PX + BAR_VERTICAL_GAP

        except Exception as e:
            logger.error(f"Errore paintEvent: {e}", exc_info=True)

    def mousePressEvent(self, ev):
        super().mousePressEvent(ev)


# Alias per compatibilità
PlanVisualizer = PlanVisualizerWidget
