import threading
import time


def start_homing(machine, callback=None):
    """
    Simulazione HOMING con logica sensore/backoff e stop a '0 macchina' (quota minima):
    - Avvicinamento lento verso min_distance (es. 250 mm).
    - Trigger sensore a (min_distance + 5 mm).
    - Backoff (inversione) di 10 mm.
    - Movimento preciso fino a min_distance (0 macchina).
    Durante il movimento aggiorna position_current e, se presente, encoder_position.
    """
    try:
        if getattr(machine, "emergency_active", False):
            if callback:
                callback(success=False, msg="EMERGENZA")
            return
    except Exception:
        pass

    try:
        if getattr(machine, "machine_homed", False):
            if callback:
                callback(success=True, msg="GIÀ HOMED")
            return
    except Exception:
        pass

    def _run():
        try:
            min_pos = float(getattr(machine, "min_distance", 250.0))
            pos = float(getattr(machine, "position_current", min_pos))

            # Condizioni di homing: freno sbloccato, frizione inserita
            try:
                setattr(machine, "brake_active", False)
                setattr(machine, "clutch_active", True)
            except Exception:
                pass

            # 1) Avvicinamento verso sensore (min + 5 mm)
            sensor_th = min_pos + 5.0
            while pos > sensor_th:
                if getattr(machine, "emergency_active", False):
                    if callback:
                        callback(success=False, msg="EMERGENZA")
                    return
                pos = max(sensor_th, pos - 5.0)  # passi lenti
                try:
                    setattr(machine, "position_current", pos)
                    setattr(machine, "encoder_position", pos)
                except Exception:
                    pass
                time.sleep(0.02)

            # 2) Backoff (inversione) di 10 mm
            pos = min(pos + 10.0, float(getattr(machine, "max_cut_length", pos + 10.0)))
            try:
                setattr(machine, "position_current", pos)
                setattr(machine, "encoder_position", pos)
            except Exception:
                pass
            time.sleep(0.15)

            # 3) Rientro preciso a min_distance
            while pos > min_pos:
                if getattr(machine, "emergency_active", False):
                    if callback:
                        callback(success=False, msg="EMERGENZA")
                    return
                pos = max(min_pos, pos - 2.0)
                try:
                    setattr(machine, "position_current", pos)
                    setattr(machine, "encoder_position", pos)
                except Exception:
                    pass
                time.sleep(0.02)

            # 4) Fine homing allo 0 macchina
            try:
                setattr(machine, "position_current", min_pos)
                setattr(machine, "position_target", min_pos)
                setattr(machine, "machine_homed", True)
                # Freno sbloccato, frizione inserita
                setattr(machine, "brake_active", False)
                setattr(machine, "clutch_active", True)
                if hasattr(machine, "_update_cut_enable_output"):
                    machine._update_cut_enable_output()
            except Exception:
                pass

            if callback:
                callback(success=True, msg="HOMING COMPLETATO")
        except Exception:
            if callback:
                callback(success=False, msg="ERRORE HOMING"))

    threading.Thread(target=_run, daemon=True).start()
