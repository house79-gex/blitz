"""
PlanVisualizerWidget (full width absolute)
- Saturazione reale larghezza: calcola la larghezza massima disponibile risalendo la catena dei parent.
- Barra riempie al 100% (meno margini minimi LEFT/RIGHT).
- Trapezi realistici (offset = altezza * tan(angolo)).
- Kerf proporzionale.
- Debug mode (self._debug=True) mostra le larghezze usate.

API invariata (come versioni precedenti).
"""

from __future__ import annotations
from typing import List, Dict, Any, Tuple, Optional

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QRectF, QSize, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QPolygonF

import math
import logging

logger = logging.getLogger(__name__)

# Parametri
ROW_HEIGHT_PX        = 30
BAR_VERTICAL_GAP     = 22
LEFT_MARGIN_PX       = 4     # ridotti al minimo
RIGHT_MARGIN_PX      = 4
TOP_MARGIN_PX        = 12
MIN_PIECE_WIDTH_PX   = 20
MIN_KERF_WIDTH_PX    = 3.0
MAX_TAPER_RATIO      = 0.70
ANGLE_CLAMP_VERTICAL = 89.0
FORCE_FULL_WIDTH     = True   # sempre saturare
REDISTRIBUTE_PIXELS  = True   # redistribuisce differenze di arrotondamento
DEBUG_SHOW           = False  # puoi cambiare a True per vedere overlay debug

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
        self._stock_mm: float = 0.0
        self._ripasso_mm: float = 0.0
        self._thickness_mm: float = 0.0
        self._warn_thr: float = 0.0

        self._done_map: Dict[int,List[bool]] = {}
        self._active_pos: Optional[Tuple[int,int]] = None
        self._active_sig: Optional[Tuple[float,float,float,str]] = None

        self._debug = DEBUG_SHOW

        self.setSizePolicy(QWidget.SizePolicy.Expanding, QWidget.SizePolicy.Preferred)
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
        self._thickness_mm = float(thickness_mm or 0.0)  # non usato qui
        self._warn_thr = float(warn_threshold_mm or 0.0)

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
                    self.mark_done_at(bi,pi); return

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
                    self._active_pos=(bi,pi); self.update(); return
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
        rows=len(self._bars)
        h=TOP_MARGIN_PX + rows*(ROW_HEIGHT_PX+BAR_VERTICAL_GAP) + 24
        self.setMinimumHeight(max(180,h))

    def sizeHint(self)->QSize:
        return QSize(max(1200,self.width()), self.minimumHeight())

    # ------------- Supporto larghezza effettiva -------------
    def _effective_inner_width(self) -> int:
        w_self = self.width()
        # prova parent diretto
        parent = self.parent()
        w_parent = parent.width() if parent else w_self
        # se dentro un contenitore superiore (scroll viewport o dialog)
        try:
            if parent and hasattr(parent, "parent") and parent.parent():
                w_top = parent.parent().width()
            else:
                w_top = w_parent
        except Exception:
            w_top = w_parent
        # scegli il massimo sensato
        candidates = [w_self, w_parent, w_top]
        eff = max(candidates)
        # evita numeri assurdi < 200
        if eff < 200:
            eff = w_self
        return eff

    # ------------- Disegno -------------
    def paintEvent(self, ev):
        painter=QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        try:
            total_available = self._effective_inner_width()
            inner_left = LEFT_MARGIN_PX
            inner_right = total_available - RIGHT_MARGIN_PX
            inner_width = max(50, inner_right - inner_left)

            y = TOP_MARGIN_PX

            font=QFont(); font.setPointSize(8)
            painter.setFont(font)

            if not self._bars:
                painter.setPen(QPen(QColor("#666"),1))
                painter.drawText(self.rect(), Qt.AlignCenter, "Nessun piano")
                return

            debug_lines=[]

            for bi, bar in enumerate(self._bars):
                # totale mm = somma pezzi + kerf tra i pezzi
                total_mm = sum(_ext_len(p) for p in bar)
                if len(bar)>1:
                    total_mm += self._kerf_mm*(len(bar)-1)
                total_mm = max(1.0,total_mm)
                scale = inner_width / total_mm

                raw_piece=[]
                raw_kerf=[]
                for pi,p in enumerate(bar):
                    w=_ext_len(p)*scale
                    if w < MIN_PIECE_WIDTH_PX: w=MIN_PIECE_WIDTH_PX
                    raw_piece.append(w)
                    if pi < len(bar)-1:
                        kw = self._kerf_mm*scale
                        if kw < MIN_KERF_WIDTH_PX: kw = MIN_KERF_WIDTH_PX
                        raw_kerf.append(kw)

                total_pixels = sum(raw_piece)+sum(raw_kerf)

                if FORCE_FULL_WIDTH and abs(total_pixels - inner_width) > 0.5:
                    factor = inner_width / total_pixels
                    raw_piece=[w*factor for w in raw_piece]
                    raw_kerf=[k*factor for k in raw_kerf]
                    total_pixels = inner_width

                # Arrotondamenti
                piece_w = [int(round(w)) for w in raw_piece]
                kerf_w  = [int(round(k)) for k in raw_kerf]
                used = sum(piece_w)+sum(kerf_w)
                diff = inner_width - used

                if REDISTRIBUTE_PIXELS and diff != 0:
                    order = sorted(range(len(piece_w)), key=lambda i: piece_w[i], reverse=True)
                    sign = 1 if diff>0 else -1
                    idx=0
                    attempts=0
                    while diff != 0 and attempts < len(order)*6:
                        i=order[idx % len(order)]
                        new_val = piece_w[i] + sign
                        if new_val >= MIN_PIECE_WIDTH_PX:
                            piece_w[i]=new_val
                            diff -= sign
                        idx+=1
                        attempts+=1

                # Ultimo controllo overflow
                final_used = sum(piece_w)+sum(kerf_w)
                if final_used > inner_width:
                    overflow = final_used - inner_width
                    order = sorted(range(len(piece_w)), key=lambda i: piece_w[i], reverse=True)
                    for i in order:
                        if overflow<=0: break
                        if piece_w[i] > MIN_PIECE_WIDTH_PX:
                            take = min(overflow, piece_w[i]-MIN_PIECE_WIDTH_PX)
                            piece_w[i] -= take
                            overflow -= take

                # Sfondo barra
                bar_rect=QRectF(inner_left-3, y-4, inner_width+6, ROW_HEIGHT_PX+8)
                painter.setPen(QPen(QColor("#d0d0d0"),1))
                painter.setBrush(QColor("#fdfdfd"))
                painter.drawRoundedRect(bar_rect,5,5)

                # Etichetta
                painter.setPen(QPen(QColor("#222"),1))
                painter.drawText(QRectF(inner_left, y-2, 46, ROW_HEIGHT_PX+4),
                                 Qt.AlignLeft | Qt.AlignVCenter, f"B{bi+1}")

                x_cursor=inner_left

                for pi,p in enumerate(bar):
                    w_piece = piece_w[pi]
                    ax, ad = _get_angles(p)
                    off_sx = _offset_px_for_angle(ax, ROW_HEIGHT_PX)
                    off_dx = _offset_px_for_angle(ad, ROW_HEIGHT_PX)

                    taper_sum = off_sx + off_dx
                    max_taper = w_piece * MAX_TAPER_RATIO
                    if taper_sum > max_taper:
                        ratio = max_taper/(taper_sum+1e-9)
                        off_sx *= ratio
                        off_dx *= ratio
                        taper_sum = off_sx + off_dx
                    bottom_w = max(4.0, w_piece - taper_sum)

                    # clamp ultimo pezzo
                    end_proj = x_cursor + w_piece
                    limit = inner_left + inner_width
                    if pi==len(bar)-1 and end_proj > limit:
                        excess=end_proj-limit
                        w_piece -= excess
                        if w_piece < 4: w_piece=4
                        max_taper = w_piece*MAX_TAPER_RATIO
                        if taper_sum > max_taper:
                            ratio = max_taper/(taper_sum+1e-9)
                            off_sx*=ratio; off_dx*=ratio
                            taper_sum=off_sx+off_dx
                        bottom_w = max(4.0, w_piece - taper_sum)

                    top_left = QPointF(x_cursor, y)
                    top_right= QPointF(x_cursor + w_piece, y)
                    bottom_left= QPointF(x_cursor + off_sx, y + ROW_HEIGHT_PX)
                    bottom_right=QPointF(x_cursor + off_sx + bottom_w, y + ROW_HEIGHT_PX)
                    poly = QPolygonF([top_left, top_right, bottom_right, bottom_left])

                    done = self._done_map.get(bi,[False]*len(bar))[pi]
                    active = (self._active_pos == (bi,pi))

                    if done:
                        fcol=QColor(115,215,115); ecol=QColor(70,160,70); tcol=QColor(255,255,255)
                    elif active:
                        fcol=QColor(255,195,110); ecol=QColor(255,140,0); tcol=QColor(0,0,0)
                    else:
                        fcol=QColor(205,205,205); ecol=QColor(150,150,150); tcol=QColor(0,0,0)

                    painter.setPen(Qt.NoPen); painter.setBrush(fcol); painter.drawPolygon(poly)
                    painter.setPen(QPen(ecol,1)); painter.drawPolygon(poly)

                    sig=_signature(p)
                    txt=f"{sig[0]:.0f}"
                    axi=int(round(sig[1])); adi=int(round(sig[2]))
                    if (axi!=0 or adi!=0) and w_piece>58:
                        txt+=f"\n{axi}/{adi}"
                    painter.setPen(QPen(tcol,1))
                    painter.drawText(QRectF(x_cursor, y, w_piece, ROW_HEIGHT_PX),
                                     Qt.AlignCenter, txt)

                    if active:
                        painter.setPen(QPen(QColor(255,100,0),2))
                        painter.drawPolygon(poly)

                    x_cursor += w_piece

                    if pi < len(bar)-1:
                        g = kerf_w[pi] if pi < len(kerf_w) else 0
                        gap_end = x_cursor + g
                        if gap_end > limit:
                            g = limit - x_cursor
                            if g < 2: g=2
                        gap_rect=QRectF(x_cursor, y, g, ROW_HEIGHT_PX)
                        painter.setPen(Qt.NoPen); painter.setBrush(QColor(232,232,232)); painter.drawRect(gap_rect)
                        painter.setPen(QPen(QColor(180,180,180),1,Qt.DashLine)); painter.drawRect(gap_rect)
                        x_cursor += g

                if self._debug:
                    debug_lines.append(f"Bar {bi+1}: inner_width={inner_width} used={sum(piece_w)+sum(kerf_w)} scale={scale:.4f}")

                y += ROW_HEIGHT_PX + BAR_VERTICAL_GAP

            if self._debug and debug_lines:
                painter.setPen(QPen(QColor("#000"),1))
                ydbg = 4
                for dl in debug_lines:
                    painter.drawText(QRectF(8,ydbg,self.width()-16,12), Qt.AlignLeft, dl)
                    ydbg += 12

        except Exception as e:
            logger.error(f"Errore paintEvent PlanVisualizer: {e}", exc_info=True)

    def mousePressEvent(self, ev):
        super().mousePressEvent(ev)


PlanVisualizer = PlanVisualizerWidget
