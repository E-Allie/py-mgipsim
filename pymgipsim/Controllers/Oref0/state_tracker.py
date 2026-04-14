"""Per-patient glucose/insulin/carb history for oref0."""

from __future__ import annotations

import datetime
import time
from collections import deque

from pymgipsim.Controllers.Oref0.unit_bridge import UnitBridge


def _ms_to_iso(ms: int) -> str:
    dt = datetime.datetime.fromtimestamp(ms / 1000.0, tz=datetime.timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


class StateTracker:

    def __init__(self, sampling_time: float, glucose_maxlen: int = 48):
        """sampling_time: simulation step size in minutes (e.g. 1.0).
        glucose_maxlen: max glucose readings to retain (48=4h, 288=24h).
        """
        self.sampling_time = sampling_time
        # Fixed epoch so timestamps are deterministic across runs.
        # oref0 rejects glucose it considers stale (vs wall clock), so this
        # must not fall too far behind real time.
        self.epoch_ms: int = 1775952000000  # 2026-04-12T00:00:00Z
        # deque of (epoch_ms: int, sgv_mgdl: float) - newest appended last
        self.glucose_history: deque = deque(maxlen=glucose_maxlen)
        # list of dicts: {timestamp_str, rate_Uhr, duration_min}
        self.insulin_deliveries: list = []
        # list of dicts: {timestamp_str, amount_g}
        self.carb_events: list = []
        # current temp basal: {rate_Uhr, duration_min, timestamp_str} or None
        self.current_temp: dict | None = None

    def _sample_to_ms(self, sample: int) -> int:
        return self.epoch_ms + int(sample * self.sampling_time * 60 * 1000)

    def _sample_to_iso(self, sample: int) -> str:
        return _ms_to_iso(self._sample_to_ms(sample))

    def record_glucose(self, sample: int, glucose_mmol: float) -> None:
        ms = self._sample_to_ms(sample)
        mgdl = UnitBridge.mmol_to_mgdl(glucose_mmol)
        self.glucose_history.append((ms, mgdl))

    def record_insulin(
        self, sample: int, rate_mUmin: float, duration_min: float = 5.0
    ) -> None:
        rate_Uhr = UnitBridge.mUmin_to_Uhr(rate_mUmin)
        ts = self._sample_to_iso(sample)
        self.insulin_deliveries.append(
            {
                "timestamp_str": ts,
                "rate_Uhr": rate_Uhr,
                "duration_min": duration_min,
            }
        )
        self.current_temp = {
            "rate_Uhr": rate_Uhr,
            "duration_min": duration_min,
            "timestamp_str": ts,
        }

    def record_carbs(self, sample: int, carbs_g: float) -> None:
        ts = self._sample_to_iso(sample)
        self.carb_events.append({"timestamp_str": ts, "amount_g": carbs_g})

    def get_glucose_json(self) -> list:
        """Glucose history as oref0 JSON (newest first), direction always "Flat"."""
        result = []
        history = list(self.glucose_history)  # oldest first
        for ms, mgdl in history:
            result.append(
                {
                    "date": ms,
                    "dateString": _ms_to_iso(ms),
                    "sgv": round(mgdl, 1),
                    "glucose": round(mgdl, 1),
                    "direction": "Flat",
                    "type": "sgv",
                    "device": "fakecgm",
                }
            )
        result.reverse()  # newest first
        return result

    def get_pump_history_json(self) -> list:
        """Pump history as oref0 JSON, newest-first."""
        result = []
        for delivery in self.insulin_deliveries:
            if delivery.get("_type") == "Bolus":
                result.append({
                    "_type": "Bolus",
                    "amount": delivery["amount_Uhr"],
                    "timestamp": delivery["timestamp_str"],
                })
                continue
            result.append({
                "_type": "TempBasal",
                "temp": "absolute",
                "rate": delivery["rate_Uhr"],
                "timestamp": delivery["timestamp_str"],
            })
            result.append({
                "_type": "TempBasalDuration",
                "duration (min)": delivery["duration_min"],
                "timestamp": delivery["timestamp_str"],
            })
        result.reverse()
        return result

    def get_current_temp_json(self) -> dict:
        if self.current_temp is None:
            return {"duration": 0, "rate": 0, "temp": "absolute"}
        return {
            "duration": self.current_temp["duration_min"],
            "rate": self.current_temp["rate_Uhr"],
            "temp": "absolute",
        }

    def get_clock_json(self, sample: int) -> str:
        return self._sample_to_iso(sample)

    @staticmethod
    def integrate_carbs(inputs_row, sample: int, control_sampling: int, sampling_time: float) -> float:
        """Sum fast+slow carb channels over one control window, return grams."""
        end = sample + control_sampling
        fast = inputs_row[0, sample:end]
        slow = inputs_row[1, sample:end]
        total_mmol_per_min = float(fast.sum() + slow.sum())
        total_mmol = total_mmol_per_min * sampling_time
        grams = UnitBridge.mmol_to_g(total_mmol)
        return max(0.0, grams)
