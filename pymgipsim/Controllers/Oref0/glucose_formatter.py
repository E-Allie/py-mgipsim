from pymgipsim.Controllers.Oref0.unit_bridge import UnitBridge
from pymgipsim.Controllers.Oref0.state_tracker import _ms_to_iso


def _classify_direction(delta_mgdl_per_min: float) -> str:
    """CGM trend arrow from mg/dL-per-minute delta."""
    if delta_mgdl_per_min >= 3.0:
        return "DoubleUp"
    elif delta_mgdl_per_min >= 2.0:
        return "SingleUp"
    elif delta_mgdl_per_min >= 1.0:
        return "FortyFiveUp"
    elif delta_mgdl_per_min <= -3.0:
        return "DoubleDown"
    elif delta_mgdl_per_min <= -2.0:
        return "SingleDown"
    elif delta_mgdl_per_min <= -1.0:
        return "FortyFiveDown"
    else:
        return "Flat"


class GlucoseFormatter:

    @staticmethod
    def format(glucose_history_tuples: list) -> list:
        """Convert (epoch_ms, mgdl) tuples (oldest-first) to oref0 glucose JSON (newest-first)."""
        if not glucose_history_tuples:
            return []

        result = []
        history = list(glucose_history_tuples)  # oldest first

        for i, (ms, mgdl) in enumerate(history):
            if i == 0:
                direction = "Flat"
            else:
                prev_ms, prev_mgdl = history[i - 1]
                dt_min = (ms - prev_ms) / (60 * 1000)  # time delta in minutes
                if dt_min > 0:
                    delta_per_min = (mgdl - prev_mgdl) / dt_min
                else:
                    delta_per_min = 0.0
                direction = _classify_direction(delta_per_min)

            result.append({
                "date": ms,
                "dateString": _ms_to_iso(ms),
                "sgv": round(mgdl, 1),
                "glucose": round(mgdl, 1),
                "direction": direction,
                "type": "sgv",
                "device": "fakecgm",
            })

        result.reverse()  # newest first
        return result
