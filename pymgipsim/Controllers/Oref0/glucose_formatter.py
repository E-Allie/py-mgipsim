from pymgipsim.Controllers.Oref0.unit_bridge import UnitBridge
from pymgipsim.Controllers.Oref0.state_tracker import _ms_to_iso


def _classify_direction(delta_mgdl_per_min: float) -> str:
    """Classify glucose trend direction from 5-minute delta (mg/dL).

    Thresholds (standard CGM conventions):
    - DoubleUp:      delta >= 3.0 mg/dL/min  (>= 15 mg/dL per 5 min)
    - SingleUp:      delta >= 2.0             (>= 10 mg/dL per 5 min)
    - FortyFiveUp:   delta >= 1.0             (>= 5 mg/dL per 5 min)
    - Flat:          -1.0 < delta < 1.0       (-5 to +5 mg/dL per 5 min)
    - FortyFiveDown: delta <= -1.0            (<= -5 mg/dL per 5 min)
    - SingleDown:    delta <= -2.0            (<= -10 mg/dL per 5 min)
    - DoubleDown:    delta <= -3.0            (<= -15 mg/dL per 5 min)
    """
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
    """Formats StateTracker glucose history into oref0 glucose.json format."""

    @staticmethod
    def format(glucose_history_tuples: list) -> list:
        """Format glucose history as oref0-compatible JSON array (newest first).

        Args:
            glucose_history_tuples: list of (epoch_ms: int, sgv_mgdl: float)
                                    in OLDEST-FIRST order (as stored in StateTracker.glucose_history)

        Returns:
            list of dicts, newest first, each with:
            {"date": epoch_ms, "dateString": iso_str, "sgv": mg_dl,
             "glucose": mg_dl, "direction": str, "type": "sgv", "device": "fakecgm"}
        """
        if not glucose_history_tuples:
            return []

        result = []
        history = list(glucose_history_tuples)  # oldest first

        for i, (ms, mgdl) in enumerate(history):
            # Compute direction from delta to previous reading
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
