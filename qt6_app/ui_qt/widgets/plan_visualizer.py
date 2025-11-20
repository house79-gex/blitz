"""
PlanVisualizerWidget (full-width, corrected overflow, adjustable vertical space)

Correzioni richieste:
1. La barra ora occupa il 100% (meno i margini) della larghezza disponibile dell'area grafica.
2. Eliminato il problema dell’ultimo elemento che “esce” dalla barra:
   - Calcoliamo prima tutte le larghezze (pezzi + kerf) in pixel.
   - Se la somma eccede lo spazio disponibile (per arrotondamenti), applichiamo un fattore di riduzione uniforme.
   - Se la somma è più corta (scenario raro), possiamo opzionalmente espandere.
3. Mostra trapezi realistici: angolo grafico derivato da tan(angolo) con altezza costante ROW_HEIGHT_PX.
4. Scala orizzontale basata SOLO sulla somma (lunghezze esterne + kerf*(n-1)) per sfruttare tutta la larghezza.
5. Più altezza totale per visualizzare più barre (AUTO_HEIGHT = True). Calcola min height dinamica.
6. Parametri configurabili in alto (ROW_HEIGHT_PX, BAR_VERTICAL_GAP, MIN_PIECE_WIDTH_PX).
7. Nessun pezzo oltre i margini: correzione post-scaling e clamp finale dell’ultimo pixel.
8. Evidenziazione singolo pezzo attivo (arancione) e solo il tagliato (verde).
9. Possibilità di modalità compatta (COMPACT_MODE) che riduce l’altezza barra se vuoi farne stare di più a schermo.

Se desideri comprimere ulteriormente (più barre visibili con minore altezza), imposta:
  ROW_HEIGHT_PX = 22
  BAR_VERTICAL_GAP = 6

API invariata per il dialogo:
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

NOTA: thickness_mm non influenza la geometria (rappresentazione idealizzata 2D dei soli angoli).
"""

from __future__ import annotations
from typing import List, Dict, Any, Tuple, Optional

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QRectF, QSize, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QPolygonF

import math
import logging

logger = logging.getLogger(__name__)

# ---------------- Parametri configurabili ----------------
ROW_HEIGHT_PX       = 30      # altezza di ogni barra (aumenta per trapezi più evidenti)
BAR_VERTICAL_GAP    = 10      # spazio verticale tra barre
LEFT_MARGIN_PX      = 12
RIGHT_MARGIN_PX     = 12
TOP_MARGIN_PX       = 12

MIN_PIECE_WIDTH_PX  = 24      # larghezza minima visiva pezzo
MIN_KERF_WIDTH_PX   = 3.5     # kerf minimo visivo
MAX_TAPER_RATIO     = 0.70    # somma offset <= MAX_TAPER_RATIO * top_width
ANGLE_CLAMP_VERTICAL= 89.0    # oltre questo consideriamo il taglio come verticale
EXPAND_IF_SHORT     = True    # se la somma pixel < area disponibile, espandi per riempire
COMPACT_MODE        = False   # se True riduce l’altezza totale calcolata
AUTO_HEIGHT         = True    # se True la height si adatta al numero di barre

# ---------------- Utility ----------------
def _ext_len(p: Dict[str, Any]) -> float:
    return float(p.get("len", p.get("length_mm", p.get("length", 0.0))))

def _get_angles(p: Dict[str, Any]) -> Tuple[float,float]:
    ax = float(p.get("ax", p.get("ang_sx", 0.0)))
    ad = float(p.get("ad", p.get("ang_dx", 0.0)))
    return ax, ad

def _signature(p: Dict[str, Any]) -> Tuple[float,float,float,str]:
    L = _ext_len(p)
    ax, ad = _get_angles(p)
    prof = str(p.get("profile","")).strip()
    return (round(L,2), round(ax,1), round(ad,1), prof)

def _offset_px_for_angle(angle_deg: float, height_px: float) -> float:
    a = abs(angle_deg)
    if a <= 0.01: return 0.0
    if a >= ANGLE_CLAMP_VERTICAL: return 0.0
    return height_px * math.tan(math.radians(a))


class PlanVisualizerWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._bars: List[List[Dict[str, Any]]] = []
        self._kerf_mm: float = 0.0
        self._ripasso_mm: float = 0.0
        self._stock_mm: float = 0.0
        self._thickness_mm: float = 0.0  # non usato per disegno
        self._warn_thr: float = 0.0

        self._done_map: Dict[int,List[bool]] = {}
        self._active_pos: Optional[Tuple[int,int]] = None
        self._active_sig: Optional[Tuple[float,float,float,str]] = None

        self.setMouseTracking(True)
        self._recalc_min_height()

    # ------------- API -------------
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
        # Normalizza done map misura per misura
        new_map={}
        for i,b in enumerate(self._bars):
            arr=self._done_map.get(i)
            new_map[i] = arr if (arr and len(arr)==len(b)) else [False]*len(b)
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

    def mark_done_at(self, bar_idx:int, piece_idx:int):
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
        for bi,bar in enumerate(self._bars):
            for pi,p in enumerate(bar):
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

    # ------------- Layout dinamico -------------
    def _recalc_min_height(self):
        rows = len(self._bars)
        if AUTO_HEIGHT:
            h = TOP_MARGIN_PX + rows*(ROW_HEIGHT_PX+BAR_VERTICAL_GAP) + 20
        else:
            # Fisso: mostra almeno 8 barre
            show_rows = max(rows, 8)
            h = TOP_MARGIN_PX + show_rows*(ROW_HEIGHT_PX+BAR_VERTICAL_GAP) + 20
        if COMPACT_MODE:
            h = int(h*0.88)
        self.setMinimumHeight(max(160,h))

    def sizeHint(self)->QSize:
        # Larghezza minima generosa
        return QSize(max(1100,self.width()), self.minimumHeight())

    # ------------- Disegno -------------
    def paintEvent(self, ev):
        painter=QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        try:
            W=self.width()
            inner_left=LEFT_MARGIN_PX
            inner_right=W-RIGHT_MARGIN_PX
            inner_width=max(100, inner_right-inner_left)

            y=TOP_MARGIN_PX

            font=QFont()
            font.setPointSize(8)
            painter.setFont(font)

            if not self._bars:
                painter.setPen(QPen(QColor("#666"),1))
                painter.drawText(self.rect(), Qt.AlignCenter, "Nessun piano")
                return

            for bi, bar in enumerate(self._bars):
                # Lunghezza totale mm per scala
                total_mm = sum(_ext_len(p) for p in bar)
                if len(bar)>1:
                    total_mm += self._kerf_mm*(len(bar)-1)
                total_mm = max(1.0,total_mm)
                scale = inner_width / total_mm

                # Pre-calcolo larghezze pezzi + kerf (float)
                piece_widths = []
                kerf_widths = []
                for pi,p in enumerate(bar):
                    w = _ext_len(p) * scale
                    if w < MIN_PIECE_WIDTH_PX:
                        w = MIN_PIECE_WIDTH_PX
                    piece_widths.append(w)
                    if pi < len(bar)-1:
                        kw = self._kerf_mm * scale
                        if kw < MIN_KERF_WIDTH_PX:
                            kw = MIN_KERF_WIDTH_PX
                        kerf_widths.append(kw)

                total_pixels = sum(piece_widths) + sum(kerf_widths)
                # Riduzione o espansione per usare TUTTA la larghezza
                if total_pixels > inner_width + 0.5:
                    factor = inner_width / total_pixels
                    piece_widths = [w*factor for w in piece_widths]
                    kerf_widths = [k*factor for k in kerf_widths]
                    total_pixels = inner_width
                elif EXPAND_IF_SHORT and total_pixels < inner_width - 0.5:
                    factor = inner_width / total_pixels
                    piece_widths = [w*factor for w in piece_widths]
                    kerf_widths = [k*factor for k in kerf_widths]
                    total_pixels = inner_width

                # sfondo barra
                bar_rect = QRectF(inner_left-6, y-5, inner_width+12, ROW_HEIGHT_PX+10)
                painter.setPen(QPen(QColor("#d0d0d0"),1))
                painter.setBrush(QColor("#fdfdfd"))
                painter.drawRoundedRect(bar_rect,6,6)

                # etichetta barra
                painter.setPen(QPen(QColor("#222"),1))
                painter.drawText(QRectF(inner_left-2, y-2, 50, ROW_HEIGHT_PX+4),
                                 Qt.AlignLeft | Qt.AlignVCenter, f"B{bi+1}")

                x_cursor=inner_left

                for pi,p in enumerate(bar):
                    piece_w = piece_widths[pi]
                    ax, ad = _get_angles(p)
                    off_sx_px = _offset_px_for_angle(ax, ROW_HEIGHT_PX)
                    off_dx_px = _offset_px_for_angle(ad, ROW_HEIGHT_PX)

                    taper_sum = off_sx_px + off_dx_px
                    max_taper = piece_w * MAX_TAPER_RATIO
                    if taper_sum > max_taper:
                        ratio = max_taper/(taper_sum+1e-9)
                        off_sx_px *= ratio
                        off_dx_px *= ratio
                        taper_sum = off_sx_px + off_dx_px
                    bottom_w = max(4.0, piece_w - taper_sum)

                    # Correzione finale anti-overflow ultima cella
                    projected_end = x_cursor + piece_w
                    if pi == len(bar)-1 and projected_end > inner_left + inner_width:
                        excess = projected_end - (inner_left + inner_width)
                        piece_w -= excess
                        if piece_w < 4: piece_w = 4
                        # ricalcola taper abbassando se serve
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
                    bottom_right= QPointF(x_cursor + off_sx_px + bottom_w, y + ROW_HEIGHT_PX)
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
                    if (axi!=0 or adi!=0) and piece_w > 62:
                        txt += f"\n{axi}/{adi}"
                    painter.setPen(QPen(txt_col,1))
                    painter.drawText(QRectF(x_cursor, y, piece_w, ROW_HEIGHT_PX),
                                     Qt.AlignCenter, txt)

                    if active:
                        painter.setPen(QPen(QColor(255,100,0),2))
                        painter.drawPolygon(poly)

                    x_cursor += piece_w

                    if pi < len(bar)-1:
                        gap_w = kerf_widths[pi]
                        # correzione anti-overflow anche sul gap (se necessario)
                        projected_gap_end = x_cursor + gap_w
                        if projected_gap_end > inner_left + inner_width:
                            gap_w = (inner_left + inner_width) - x_cursor
                            if gap_w < 2: gap_w = 2
                        gap_rect = QRectF(x_cursor, y, gap_w, ROW_HEIGHT_PX)
                        painter.setPen(Qt.NoPen)
                        painter.setBrush(QColor(232,232,232))
                        painter.drawRect(gap_rect)
                        painter.setPen(QPen(QColor(180,180,180),1, Qt.DashLine))
                        painter.drawRect(gap_rect)
                        x_cursor += gap_w

                y += ROW_HEIGHT_PX + BAR_VERTICAL_GAP

        except Exception as e:
            logger.error(f"Errore paintEvent PlanVisualizer: {e}", exc_info=True)

    def mousePressEvent(self, ev):
        super().mousePressEvent(ev)


# Alias compatibilità
PlanVisualizer = PlanVisualizerWidget
