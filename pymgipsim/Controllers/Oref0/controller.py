from __future__ import annotations

import json
import os

import numpy as np

from pymgipsim.Controllers.Oref0.unit_bridge import UnitBridge
from pymgipsim.Controllers.Oref0.state_tracker import StateTracker
from pymgipsim.Controllers.Oref0.glucose_formatter import GlucoseFormatter
from pymgipsim.Controllers.Oref0.profile_builder import ProfileBuilder
from pymgipsim.Controllers.Oref0.pump_history import PumpHistoryBuilder
from pymgipsim.Controllers.Oref0.subprocess_runner import SubprocessRunner
from pymgipsim.Utilities.Scenario import scenario


class Controller:
    name = "Oref0"

    def __init__(self, scenario_instance: scenario, backend: str | None = None,
                 forward_carbs: bool | None = None, enable_smb: bool | None = None,
                 enable_uam: bool | None = None, enable_autosens: bool | None = None,
                 enable_autotune: bool | None = None,
                 autotune_interval_hours: float | None = None,
                 use_ffi: bool | None = None):
        if backend is None:
            backend = os.environ.get("OREF0_BACKEND", "rust")
        if use_ffi is None:
            use_ffi = os.environ.get("OREF0_USE_FFI", "").lower() in ("1", "true", "yes")
        if forward_carbs is None:
            forward_carbs = os.environ.get("OREF0_FORWARD_CARBS", "").lower() in ("1", "true", "yes")
        if enable_smb is None:
            enable_smb = os.environ.get("OREF0_ENABLE_SMB", "").lower() in ("1", "true", "yes")
        if enable_uam is None:
            enable_uam = os.environ.get("OREF0_ENABLE_UAM", "").lower() in ("1", "true", "yes")
        if enable_autosens is None:
            enable_autosens = os.environ.get("OREF0_ENABLE_AUTOSENS", "").lower() in ("1", "true", "yes")
        if enable_autotune is None:
            enable_autotune = os.environ.get("OREF0_ENABLE_AUTOTUNE", "").lower() in ("1", "true", "yes")
        if autotune_interval_hours is None:
            autotune_interval_hours = float(os.environ.get("OREF0_AUTOTUNE_INTERVAL", "24"))
        self.forward_carbs = forward_carbs
        self.enable_smb = enable_smb
        self.enable_uam = enable_uam
        self.enable_autosens = enable_autosens
        self.enable_autotune = enable_autotune
        self.sampling_time = scenario_instance.settings.sampling_time
        self.control_sampling = int(5 / self.sampling_time)
        self.warmup_samples = int(45 / self.sampling_time)
        self.autotune_interval_samples = int(autotune_interval_hours * 60 / self.sampling_time)
        self.n_patients = scenario_instance.patient.number_of_subjects
        self.demographic_info = scenario_instance.patient.demographic_info

        glucose_maxlen = 288 if (enable_autosens or enable_autotune) else 48
        self.trackers = [
            StateTracker(self.sampling_time, glucose_maxlen=glucose_maxlen)
            for _ in range(self.n_patients)
        ]

        self.profiles = [
            ProfileBuilder.build_profile(self.demographic_info, i, enable_smb=enable_smb, enable_uam=enable_uam)
            for i in range(self.n_patients)
        ]

        # Immutable pump profiles for autotune (the "ground truth" starting point)
        self.pump_profiles = [dict(p) for p in self.profiles]
        # Previous autotune output per patient (None = first run, use pump profile)
        self.last_autotune: list[dict | None] = [None] * self.n_patients

        self.runners = [
            SubprocessRunner(backend=backend, use_ffi=use_ffi)
            for _ in range(self.n_patients)
        ]

        self.basal_rates_mUmin = [
            UnitBridge.Uhr_to_mUmin(self.demographic_info.basal[i])
            for i in range(self.n_patients)
        ]

        self.debug_log_path = os.environ.get("OREF0_DEBUG_LOG") or None
        self.debug_log_bg_threshold = float(os.environ.get("OREF0_DEBUG_BG", "90"))
        if self.debug_log_path:
            with open(self.debug_log_path, "w") as f:
                f.write("")

    def run(self, measurements, inputs, states, sample: int) -> None:
        # Record glucose at CGM rate (every control_sampling ticks = 5 min).
        # oref0's get_last_glucose averages entries < 2.5 min apart, which
        # drags the "now" timestamp backward when fed 1-min data.
        if sample % self.control_sampling == 0:
            for i in range(self.n_patients):
                self.trackers[i].record_glucose(sample, float(measurements[i]))

        if sample % self.control_sampling != 0:
            return

        if sample < self.warmup_samples:
            for i in range(self.n_patients):
                end = min(sample + self.control_sampling, inputs.shape[2])
                inputs[i, 3, sample:end] = self.basal_rates_mUmin[i]
            return

        if (self.enable_autotune
                and sample >= self.autotune_interval_samples
                and sample % self.autotune_interval_samples == 0):
            for i in range(self.n_patients):
                self._run_autotune(i, sample)

        for i in range(self.n_patients):
            rate_mUmin = self._run_oref0(i, sample, inputs)
            end = min(sample + self.control_sampling, inputs.shape[2])
            inputs[i, 3, sample:end] = rate_mUmin
            self.trackers[i].record_insulin(
                sample, rate_mUmin, duration_min=float(self.control_sampling * self.sampling_time)
            )

    def _run_oref0(self, patient_idx: int, sample: int, inputs) -> float:
        tracker = self.trackers[patient_idx]
        runner = self.runners[patient_idx]
        profile = self.profiles[patient_idx]

        glucose_json = GlucoseFormatter.format(list(tracker.glucose_history))
        if not glucose_json:
            return self.basal_rates_mUmin[patient_idx]

        if self.forward_carbs:
            carbs_g = StateTracker.integrate_carbs(
                inputs[patient_idx], sample, self.control_sampling, self.sampling_time
            )
            if carbs_g > 0:
                tracker.record_carbs(sample, carbs_g)

        pump_history_json = PumpHistoryBuilder.build_pump_history(tracker.insulin_deliveries)
        clock = tracker.get_clock_json(sample)
        # Always report no active temp - we directly control the insulin rate
        # each cycle, so there's no "running temp" to preserve or cancel.
        currenttemp = {"duration": 0, "rate": 0, "temp": "absolute"}

        iob = runner.calculate_iob(pump_history_json, profile, clock)
        if iob is None:
            iob = {"iob": 0.0, "activity": 0.0, "bolussnooze": 0.0}

        # Build carb history once if carb forwarding is active (used by meal + autosens)
        carb_history_json = (
            PumpHistoryBuilder.build_carb_history(tracker.carb_events)
            if self.forward_carbs else []
        )
        basalprofile = profile.get("basalprofile", [])

        meal_data = None
        if self.forward_carbs:
            meal_data = runner.calculate_meal(
                pump_history_json, profile, clock, glucose_json, basalprofile, carb_history_json or None
            )

        autosens_data = None
        if self.enable_autosens:
            isf = dict(profile.get("isfProfile", {}))
            if "units" not in isf:
                isf["units"] = "mg/dL"
            autosens_result = runner.detect_sensitivity(
                glucose_json,
                pump_history_json,
                isf,
                basalprofile,
                profile,
                carb_history_json or None,
            )
            autosens_data = autosens_result if autosens_result is not None else {"ratio": 1.0}

        result = runner.determine_basal(
            iob, currenttemp, glucose_json, profile, clock,
            meal_data=meal_data,
            microbolus=self.enable_smb,
            autosens_data=autosens_data,
        )
        if result is None:
            return self.basal_rates_mUmin[patient_idx]

        if self.debug_log_path:
            current_bg = glucose_json[0]["glucose"] if glucose_json else None
            if current_bg is not None and current_bg <= self.debug_log_bg_threshold:
                entry = {
                    "sample": sample,
                    "patient": patient_idx,
                    "bg": current_bg,
                    "iob": iob.get("iob", 0.0),
                    "rate": result.get("rate"),
                    "duration": result.get("duration"),
                    "units": result.get("units"),
                    "reason": result.get("reason", ""),
                    "smb_enabled": self.enable_smb,
                }
                with open(self.debug_log_path, "a") as f:
                    f.write(json.dumps(entry) + "\n")

        if self.enable_smb:
            smb_units = result.get("units")
            if smb_units and float(smb_units) > 0:
                smb_u = float(smb_units)
                # Record SMB as a Bolus event in pump history for correct IOB accounting
                tracker.insulin_deliveries.append({
                    "timestamp_str": tracker.get_clock_json(sample),
                    "_type": "Bolus",
                    "amount_Uhr": smb_u,
                    "duration_min": 0.0,
                })
                # Add SMB to the basal rate for this window (convert U to mU/min over 5 min)
                smb_mUmin = (smb_u * 1000.0) / (self.control_sampling * self.sampling_time)
                rate_Uhr = result.get("rate")
                if rate_Uhr is None:
                    rate_Uhr = self.demographic_info.basal[patient_idx]
                return UnitBridge.Uhr_to_mUmin(float(rate_Uhr)) + smb_mUmin

        rate_Uhr = result.get("rate")
        if rate_Uhr is None:
            rate_Uhr = self.demographic_info.basal[patient_idx]
        rate_Uhr = float(rate_Uhr)
        return UnitBridge.Uhr_to_mUmin(rate_Uhr)

    def _run_autotune(self, patient_idx: int, sample: int) -> None:
        tracker = self.trackers[patient_idx]
        runner = self.runners[patient_idx]
        profile = self.profiles[patient_idx]
        pump_profile = self.pump_profiles[patient_idx]

        glucose_json = GlucoseFormatter.format(list(tracker.glucose_history))
        if len(glucose_json) < 36:
            return

        pump_history_json = PumpHistoryBuilder.build_pump_history(tracker.insulin_deliveries)
        carb_history_json = (
            PumpHistoryBuilder.build_carb_history(tracker.carb_events)
            if self.forward_carbs else None
        )

        prepped = runner.autotune_prep(
            pump_history_json, profile, glucose_json, pump_profile,
            carb_history=carb_history_json,
        )
        if prepped is None:
            return

        previous = self.last_autotune[patient_idx]
        if previous is None:
            previous = self._profile_to_autotune_shape(pump_profile)

        result = runner.autotune_core(prepped, previous, self._profile_to_autotune_shape(pump_profile))
        if result is None:
            return

        self.last_autotune[patient_idx] = result
        self._merge_autotune(patient_idx, result)

    @staticmethod
    def _profile_to_autotune_shape(profile: dict) -> dict:
        isf_profile = profile.get("isfProfile", {})
        sens_value = profile.get("sens", 50)
        if isinstance(isf_profile, dict) and "sensitivities" in isf_profile:
            sensitivities = isf_profile["sensitivities"]
            if sensitivities:
                sens_value = sensitivities[0].get("sensitivity", sens_value)

        return {
            "dia": profile.get("dia", 3),
            "curve": profile.get("curve", "rapid-acting"),
            "useCustomPeakTime": profile.get("useCustomPeakTime", False),
            "insulinPeakTime": profile.get("insulinPeakTime", 75),
            "carb_ratio": profile.get("carb_ratio", 10),
            "basalprofile": profile.get("basalprofile", []),
            "isfProfile": isf_profile,
            "sens": sens_value,
            "autosens_max": profile.get("autosens_max", 1.2),
            "autosens_min": profile.get("autosens_min", 0.7),
            "min_5m_carbimpact": profile.get("min_5m_carbimpact", 8),
        }

    def _merge_autotune(self, patient_idx: int, autotune_result: dict) -> None:
        profile = self.profiles[patient_idx]

        if "basalprofile" in autotune_result:
            profile["basalprofile"] = autotune_result["basalprofile"]
            if autotune_result["basalprofile"]:
                new_basal = autotune_result["basalprofile"][0].get("rate", profile["current_basal"])
                profile["current_basal"] = new_basal

        if "sens" in autotune_result:
            profile["sens"] = autotune_result["sens"]
            profile["isfProfile"] = {
                "sensitivities": [
                    {"offset": 0, "sensitivity": autotune_result["sens"],
                     "endOffset": 1440, "start": "00:00:00", "i": 0, "x": 0}
                ]
            }

        if "carb_ratio" in autotune_result:
            profile["carb_ratio"] = autotune_result["carb_ratio"]
            profile["carb_ratios"] = {
                "schedule": [
                    {"offset": 0, "ratio": autotune_result["carb_ratio"],
                     "start": "00:00:00", "i": 0, "x": 0}
                ]
            }

    def cleanup(self) -> None:
        for runner in self.runners:
            runner.cleanup()
