"""
PlanVisualizerWidget (full-width scaling + increased vertical spacing)

Modifiche rispetto alla versione precedente:
- Forzata espansione al 100% della larghezza disponibile: tutti i pezzi + kerf vengono riscalati
  con un unico fattore (FULL_WIDTH_FORCE) così da eliminare il ~25% di spazio libero a destra.
- Distribuzione dei pixel di arrotondamento: eventuali differenze tra somma arrotondata e width reale
  vengono ripartite partendo dai pezzi più larghi per saturare inner_right.
- Aumentato lo spazio verticale tra barre: BAR_VERTICAL_GAP portato a 22 (modificabile).
- Margini laterali ridotti (LEFT_MARGIN_PX / RIGHT_MARGIN_PX) per sfruttare maggiormente la larghezza.
- Correzione overflow finale: l’ultimo pezzo viene clampato se ancora eccede, ma prima tentiamo la ridistribuzione.
- Parametri configurabili in testa.

Nota: thickness_mm non influenza la geometria (visualizzazione 2D degli angoli).
Residuo non disegnato. Si può aggiungere successivamente.

API invariata:
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
ROW_HEIGHT_PX        = 30     # altezza barra
BAR_VERTICAL_GAP     = 22     # spazio verticale tra barre (aumentato)
LEFT_MARGIN_PX       = 8
RIGHT_MARGIN_PX      = 8
TOP_MARGIN_PX        = 14

MIN_PIECE_WIDTH_PX   = 22     # minima larghezza visiva pezzo
MIN_KERF_WIDTH_PX    = 3.5    # minima larghezza visiva kerf
MAX_TAPER_RATIO      = 0.70   # somma offset <= 70% top width
ANGLE_CLAMP_VERTICAL = 89.0   # oltre considerato verticale -> offset 0
FULL_WIDTH_FORCE     = True   # forza sempre saturazione larghezza
EXPAND_IF_SHORT      = True   # (ridondante se FULL_WIDTH_FORCE True, lasciato per compatibilità)

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
        self._thickness_mm: float = 0.0
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
        # Normalizza done map
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
        h = TOP_MARGIN_PX + rows*(ROW_HEIGHT_PX+BAR_VERTICAL_GAP) + 24
        self.setMinimumHeight(max(180,h))

    def sizeHint(self)->QSize:
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
                # Lunghezza totale mm per scala: sum pezzi + kerf*(n-1)
                total_mm = sum(_ext_len(p) for p in bar)
                if len(bar)>1:
                    total_mm += self._kerf_mm*(len(bar)-1)
                total_mm = max(1.0,total_mm)

                # Scala "grezza"
                scale = inner_width / total_mm

                # Pre-calcolo dimensioni in pixel (float) prima del fattore globale
                raw_piece_widths=[]
                raw_kerf_widths=[]
                for pi,p in enumerate(bar):
                    w = _ext_len(p)*scale
                    if w < MIN_PIECE_WIDTH_PX:
                        w = MIN_PIECE_WIDTH_PX
                    raw_piece_widths.append(w)
                    if pi < len(bar)-1:
                        kw = self._kerf_mm*scale
                        if kw < MIN_KERF_WIDTH_PX:
                            kw = MIN_KERF_WIDTH_PX
                        raw_kerf_widths.append(kw)

                total_pixels = sum(raw_piece_widths)+sum(raw_kerf_widths)

                # Forza saturazione esatta larghezza (FULL_WIDTH_FORCE)
                if FULL_WIDTH_FORCE and total_pixels != inner_width:
                    factor = inner_width / total_pixels
                    piece_widths = [w*factor for w in raw_piece_widths]
                    kerf_widths  = [k*factor for k in raw_kerf_widths]
                else:
                    # eventuale espansione se corta
                    if EXPAND_IF_SHORT and total_pixels < inner_width - 0.5:
                        factor = inner_width / total_pixels
                        piece_widths = [w*factor for w in raw_piece_widths]
                        kerf_widths  = [k*factor for k in raw_kerf_widths]
                    else:
                        piece_widths = raw_piece_widths
                        kerf_widths  = raw_kerf_widths

                # Arrotonda a pixel interi e redistribuisci differenza
                int_piece = [int(round(w)) for w in piece_widths]
                int_kerf  = [int(round(k)) for k in kerf_widths]
                used = sum(int_piece)+sum(int_kerf)
                diff = inner_width - used

                if diff != 0:
                    # ordina pezzi per ampiezza desc per distribuire (positiva -> aggiungi, negativa -> togli)
                    order = sorted(range(len(int_piece)), key=lambda i: int_piece[i], reverse=True)
                    sign = 1 if diff>0 else -1
                    idx=0
                    while diff != 0 and order:
                        i=order[idx % len(order)]
                        # vincoli minimi
                        new_w = int_piece[i]+sign
                        if new_w >= MIN_PIECE_WIDTH_PX:
                            int_piece[i]=new_w
                            diff -= sign
                        idx+=1
                        if idx>len(order)*3: break  # evita loop infinito

                # Clamp finale (se ancora overflow per arrotondamenti)
                final_used = sum(int_piece)+sum(int_kerf)
                if final_used > inner_width:
                    overflow = final_used - inner_width
                    # togli pixel dai pezzi più larghi
                    order = sorted(range(len(int_piece)), key=lambda i: int_piece[i], reverse=True)
                    for i in order:
                        if overflow<=0: break
                        if int_piece[i] > MIN_PIECE_WIDTH_PX:
                            take = min(overflow, int_piece[i]-MIN_PIECE_WIDTH_PX)
                            int_piece[i] -= take
                            overflow -= take

                # Sfondo barra
                bar_rect = QRectF(inner_left-4, y-4, inner_width+8, ROW_HEIGHT_PX+8)
                painter.setPen(QPen(QColor("#d0d0d0"),1))
                painter.setBrush(QColor("#fdfdfd"))
                painter.drawRoundedRect(bar_rect,6,6)

                # Etichetta
                painter.setPen(QPen(QColor("#222"),1))
                painter.drawText(QRectF(inner_left-2, y-2, 50, ROW_HEIGHT_PX+4),
                                 Qt.AlignLeft | Qt.AlignVCenter, f"B{bi+1}")

                x_cursor=inner_left

                for pi,p in enumerate(bar):
                    piece_w = int_piece[pi]
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

                    # Anti overflow ultimo pezzo
                    projected_end = x_cursor + piece_w
                    limit = inner_left + inner_width
                    if pi == len(bar)-1 and projected_end > limit:
                        excess = projected_end - limit
                        piece_w -= excess
                        if piece_w < 4: piece_w = 4
                        max_taper = piece_w * MAX_TAPER_RATIO
                        if taper_sum > max_taper:
                            ratio = max_taper/(taper_sum+1e-9)
                            off_sx_px *= ratio
                            off_dx_px *= ratio
                            taper_sum = off_sx_px + off_dx_px
                        bottom_w = max(4.0, piece_w - taper_sum)

                    top_left = QPointF(x_cursor, y)
                    top_right= QPointF(x_cursor + piece_w, y)
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
                        gap_w = int_kerf[pi] if pi < len(int_kerf) else 0
                        projected_gap_end = x_cursor + gap_w
                        if projected_gap_end > limit:
                            gap_w = limit - x_cursor
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
