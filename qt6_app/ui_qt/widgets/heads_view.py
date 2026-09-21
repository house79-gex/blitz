from PySide6.QtWidgets import QFrame
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QPolygonF
from PySide6.QtCore import Qt, QPointF, QRectF, QTimer, QElapsedTimer
import math

from ui_qt.logic.angles import normalize_cut_tilt_deg

# ~6 s da 0° a 45° (più lenta per i test; in macchina conta l'encoder)
HEAD_TILT_DEG_PER_S = 7.5
# Corsa lineare simulata in vista (~8 s su 4000 mm)
HEAD_TRAVEL_MM_PER_S = 500.0


def normalize_head_tilt_deg(raw) -> float:
    """
    Converte un angolo testa in inclinazione 0–45° per il disegno.

    Convenzione UI Semi-auto: 0 = taglio quadro, 45 = 45°.
    Valori ~90 (convenzione lama perpendicolare) diventano 0°.
    """
    return normalize_cut_tilt_deg(raw)


def step_tilt_animation(
    current: float,
    target: float,
    dt_s: float,
    speed_deg_s: float = HEAD_TILT_DEG_PER_S,
) -> float:
    """Avvicina l'angolo disegnato al target con velocità costante (gradi/s)."""
    try:
        cur = float(current)
        tgt = float(target)
        dt = max(0.0, float(dt_s))
        spd = max(0.1, float(speed_deg_s))
    except (TypeError, ValueError):
        return 0.0
    delta = tgt - cur
    max_step = spd * dt
    if abs(delta) <= max_step:
        return tgt
    return cur + (max_step if delta > 0 else -max_step)


def step_travel_animation(
    current: float,
    target: float,
    dt_s: float,
    speed_mm_s: float = HEAD_TRAVEL_MM_PER_S,
) -> float:
    """Avvicina la quota disegnata al target con velocità costante (mm/s)."""
    try:
        cur = float(current)
        tgt = float(target)
        dt = max(0.0, float(dt_s))
        spd = max(1.0, float(speed_mm_s))
    except (TypeError, ValueError):
        return float(target) if target is not None else 0.0
    delta = tgt - cur
    max_step = spd * dt
    if abs(delta) <= max_step:
        return tgt
    return cur + (max_step if delta > 0 else -max_step)


class HeadsView(QFrame):
    """
    Vista grafica teste:
    - Compatibile con MachineAdapter (get_position / get_state).
    - Fallback su attributi legacy (position_current / encoder_position).
    - Preferisce l'angolo misurato dagli encoder di inclinazione se online.
    - Rotazione e corsa lineare animate (solo UI/test; in campo contano gli encoder).
    - Riquadro angolo sempre orizzontale (non ruota con la testa).
    """

    def __init__(self, machine, parent=None):
        super().__init__(parent)
        self.machine = machine
        self.setMinimumHeight(360)
        self.setMinimumWidth(560)
        self.setFrameShape(QFrame.StyledPanel)
        self.setFrameShadow(QFrame.Raised)
        self._last_sx = 0.0
        self._last_dx = 0.0
        self._sx_measured = False
        self._dx_measured = False
        self._draw_sx = None
        self._draw_dx = None
        self._draw_pos = None
        self._anim_clock = QElapsedTimer()
        self._anim_clock.start()
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(16)
        self._anim_timer.timeout.connect(self.update)

    def refresh(self):
        self.update()

    def _get_position_mm(self):
        if hasattr(self.machine, "get_position") and callable(getattr(self.machine, "get_position")):
            try:
                v = self.machine.get_position()
                if v is not None:
                    return float(v)
            except Exception:
                pass
        for name in ("encoder_position", "position_current"):
            if hasattr(self.machine, name):
                try:
                    return float(getattr(self.machine, name))
                except Exception:
                    pass
        return float(getattr(self.machine, "min_distance", 250.0))

    def _state_dict(self):
        if hasattr(self.machine, "get_state") and callable(getattr(self.machine, "get_state")):
            try:
                st = self.machine.get_state()
                if isinstance(st, dict):
                    return st
            except Exception:
                pass
        return {}

    def _get_angle(self, left=True):
        """Restituisce (angolo_tilt_deg, da_encoder)."""
        st = self._state_dict()
        side = "sx" if left else "dx"
        measured_key = "measured_left_head_angle" if left else "measured_right_head_angle"
        cmd_key = "left_head_angle" if left else "right_head_angle"
        online_key = "head_encoder_online_sx" if left else "head_encoder_online_dx"
        online = bool(st.get(online_key) or st.get("head_encoder_online"))

        cmd = None
        ha = st.get("head_angles") if isinstance(st.get("head_angles"), dict) else {}
        if ha and ha.get(side) is not None:
            cmd = ha.get(side)
        elif cmd_key in st and st.get(cmd_key) is not None:
            cmd = st.get(cmd_key)
        else:
            attr = "left_head_angle" if left else "right_head_angle"
            try:
                cmd = getattr(self.machine, attr, 0.0)
            except Exception:
                cmd = 0.0

        measured = st.get(measured_key) if online else None
        return normalize_head_tilt_deg(cmd), bool(online and measured is not None)

    def _badge_angle(self, left: bool, display_deg: float) -> float:
        """Angolo nel riquadro: misura encoder se online, altrimenti animato."""
        st = self._state_dict()
        online_key = "head_encoder_online_sx" if left else "head_encoder_online_dx"
        mk = "measured_left_head_angle" if left else "measured_right_head_angle"
        online = bool(st.get(online_key) or st.get("head_encoder_online"))
        if online and st.get(mk) is not None:
            return normalize_head_tilt_deg(st.get(mk))
        return float(display_deg)

    def _sync_draw(self, ang_sx: float, ang_dx: float, pos_mm: float):
        dt_s = self._anim_clock.restart() / 1000.0
        if dt_s > 0.12:
            dt_s = 0.032
        if self._draw_sx is None:
            self._draw_sx = float(ang_sx)
        else:
            self._draw_sx = step_tilt_animation(self._draw_sx, ang_sx, dt_s)
        if self._draw_dx is None:
            self._draw_dx = float(ang_dx)
        else:
            self._draw_dx = step_tilt_animation(self._draw_dx, ang_dx, dt_s)
        if self._draw_pos is None:
            self._draw_pos = float(pos_mm)
        else:
            self._draw_pos = step_travel_animation(self._draw_pos, pos_mm, dt_s)
        moving = (
            abs(self._draw_sx - ang_sx) > 0.05
            or abs(self._draw_dx - ang_dx) > 0.05
            or abs(self._draw_pos - pos_mm) > 0.5
        )
        if moving and not self._anim_timer.isActive():
            self._anim_timer.start()
        elif not moving and self._anim_timer.isActive():
            self._anim_timer.stop()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w = self.width()
        h = self.height()

        seg_len = 120
        seg_thick = 6
        pivot_r = 7
        body_w = 54
        body_h = 129
        bevel = 15

        min_mm = float(getattr(self.machine, "min_distance", 250.0))
        max_mm = float(getattr(self.machine, "max_cut_length", 4000.0))
        pos_mm = self._get_position_mm()
        pos_mm = max(min_mm, min(max_mm, pos_mm))
        ang_sx, sx_meas = self._get_angle(left=True)
        ang_dx, dx_meas = self._get_angle(left=False)
        self._sync_draw(ang_sx, ang_dx, pos_mm)
        draw_sx = float(self._draw_sx if self._draw_sx is not None else ang_sx)
        draw_dx = float(self._draw_dx if self._draw_dx is not None else ang_dx)
        draw_pos = float(self._draw_pos if self._draw_pos is not None else pos_mm)
        draw_pos = max(min_mm, min(max_mm, draw_pos))
        self._last_sx, self._sx_measured = draw_sx, sx_meas
        self._last_dx, self._dx_measured = draw_dx, dx_meas

        max_theta = math.radians(45.0)
        pad_x = int(body_w * math.cos(max_theta) + body_h * math.sin(max_theta)) + pivot_r + 8
        edge_pad = 16
        left_margin = edge_pad + pad_x
        right_margin = edge_pad + pad_x

        heads_to_scale_gap = 76
        block_h = body_h + heads_to_scale_gap
        center_y = h / 2.0
        heads_y = int(center_y - (block_h / 2.0) + body_h)
        base_y = heads_y + heads_to_scale_gap

        usable_w = max(50, w - left_margin - right_margin)
        scale_min, scale_max = 0.0, max_mm

        def x_at(mm: float) -> float:
            if scale_max <= scale_min:
                return left_margin
            f = (mm - scale_min) / (scale_max - scale_min)
            return left_margin + f * usable_w

        p.setPen(QPen(QColor("#3b4b5a"), 2))
        p.drawLine(int(left_margin), int(base_y), int(left_margin + usable_w), int(base_y))

        p.setPen(QPen(QColor("#5c738a"), 1))
        font = QFont()
        font.setPointSizeF(max(8.0, self.font().pointSizeF() - 1))
        p.setFont(font)
        for t in (0, 1000, 2000, 3000, int(max_mm)):
            x = x_at(t)
            p.drawLine(int(x), int(base_y), int(x), int(base_y - 12))
            label = f"{int(t)}"
            tw = p.fontMetrics().horizontalAdvance(label)
            p.drawText(int(x - tw / 2), int(base_y - 16), label)

        p.setPen(QPen(QColor("#4a6076"), 1))
        p.drawLine(int(left_margin), int(heads_y), int(left_margin + usable_w), int(heads_y))

        x_sx = x_at(0.0)
        x_dx = x_at(draw_pos)

        def draw_head(x: float, angle_deg: float, outward_left: bool, color: str):
            p.setBrush(QBrush(QColor(color)))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(x, heads_y), pivot_r, pivot_r)

            p.save()
            p.translate(x, heads_y)
            p.rotate(-angle_deg if outward_left else +angle_deg)

            if outward_left:
                pts = [
                    QPointF(0, 0),
                    QPointF(-(body_w - bevel), 0),
                    QPointF(-body_w, -bevel),
                    QPointF(-body_w, -(body_h - bevel)),
                    QPointF(-(body_w - bevel), -body_h),
                    QPointF(0, -body_h),
                ]
            else:
                pts = [
                    QPointF(0, 0),
                    QPointF(body_w - bevel, 0),
                    QPointF(body_w, -bevel),
                    QPointF(body_w, -(body_h - bevel)),
                    QPointF(body_w - bevel, -body_h),
                    QPointF(0, -body_h),
                ]
            poly = QPolygonF(pts)
            p.setBrush(QBrush(QColor("#34495e")))
            p.setPen(QPen(QColor("#95a5a6"), 1))
            p.drawPolygon(poly)

            pen = QPen(QColor(color))
            pen.setWidth(seg_thick)
            p.setPen(pen)
            p.drawLine(0, 0, 0, -seg_len)
            p.restore()

        def draw_angle_badge(x: float, display_deg: float, left: bool, color: str):
            badge_deg = self._badge_angle(left, display_deg)
            text = f"{badge_deg:.1f}°"
            font_b = QFont()
            font_b.setPointSizeF(max(10.0, self.font().pointSizeF() + 1))
            font_b.setBold(True)
            p.setFont(font_b)
            fm = p.fontMetrics()
            tw = fm.horizontalAdvance(text)
            th = fm.height()
            pad_x, pad_y = 10, 5
            box_w = tw + pad_x * 2
            box_h = th + pad_y * 2
            if left:
                rx = x - box_w - 10
            else:
                rx = x + 10
            ry = heads_y - body_h - 8
            rect = QRectF(rx, ry, box_w, box_h)
            p.setBrush(QBrush(QColor("#1b2838")))
            p.setPen(QPen(QColor(color), 2))
            p.drawRoundedRect(rect, 6, 6)
            p.setPen(QPen(QColor("#ecf0f1")))
            p.drawText(rect, Qt.AlignCenter, text)

        draw_head(x_sx, draw_sx, outward_left=True, color="#2980b9")
        draw_head(x_dx, draw_dx, outward_left=False, color="#9b59b6")
        draw_angle_badge(x_sx, draw_sx, left=True, color="#2980b9")
        draw_angle_badge(x_dx, draw_dx, left=False, color="#9b59b6")

        hint = (
            "Encoder inclinazione online"
            if (sx_meas or dx_meas)
            else "Angolo comandato (encoder non in lettura)"
        )
        st_all = self._state_dict()
        if st_all.get("head_fc_zero_sx") or st_all.get("head_fc_zero_dx"):
            hint += " — FC 0° attivo"
        p.setPen(QPen(QColor("#7f8c8d")))
        p.drawText(int(left_margin), int(min(h - 8, base_y + 22)), hint)
