import datetime
import math
import time
import pytest

from pymgipsim.Controllers.Oref0.subprocess_runner import SubprocessRunner
from pymgipsim.Controllers.Oref0.glucose_formatter import GlucoseFormatter
from pymgipsim.Controllers.Oref0.pump_history import PumpHistoryBuilder
from pymgipsim.Controllers.Oref0.state_tracker import StateTracker


def _wheel_available():
    try:
        import oref0_ffi  # noqa: F401
        return True
    except ImportError:
        return False


WHEEL_AVAILABLE = _wheel_available()
skip_no_wheel = pytest.mark.skipif(not WHEEL_AVAILABLE, reason="oref0_ffi wheel not installed")

PROFILE = {
    "max_iob": 2.5,
    "dia": 5,
    "type": "current",
    "current_basal": 0.9,
    "max_daily_basal": 1.3,
    "max_basal": 3.5,
    "max_bg": 120,
    "min_bg": 110,
    "sens": 40,
    "carb_ratio": 10,
    "out_units": "mg/dL",
    "curve": "rapid-acting",
    "max_daily_safety_multiplier": 3,
    "current_basal_safety_multiplier": 4,
    "autosens_max": 1.2,
    "autosens_min": 0.7,
    "skip_neutral_temps": False,
    "enableUAM": True,
    "enableSMB_with_COB": False,
    "enableSMB_always": False,
    "enableSMB_after_carbs": False,
    "enableSMB_with_temptarget": False,
    "allowSMB_with_high_temptarget": False,
    "maxSMBBasalMinutes": 30,
    "maxUAMSMBBasalMinutes": 30,
    "SMBInterval": 3,
    "bolus_increment": 0.1,
    "maxDelta_bg_threshold": 0.2,
    "A52_risk_enable": False,
    "temptargetSet": False,
    "noisyCGMTargetMultiplier": 1.3,
    "useCustomPeakTime": False,
    "insulinPeakTime": 75,
    "remainingCarbsFraction": 1,
    "remainingCarbsCap": 90,
    "carbsReqThreshold": 1,
    "maxCOB": 120,
    "min_5m_carbimpact": 8,
    "sensitivity_raises_target": True,
    "resistance_lowers_target": False,
    "high_temptarget_raises_sensitivity": False,
    "low_temptarget_lowers_sensitivity": False,
    "exercise_mode": False,
    "half_basal_exercise_target": 160,
    "basalprofile": [{"minutes": 0, "rate": 0.9, "start": "00:00:00", "i": 0}],
    "isfProfile": {
        "sensitivities": [
            {"offset": 0, "sensitivity": 40, "endOffset": 1440, "start": "00:00:00", "i": 0, "x": 0}
        ]
    },
    "suspend_zeros_iob": True,
    "bolussnooze_dia_divisor": 2,
}


def _normalize(v):
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    return v


def _run_steps(runner, n_steps=24):
    tracker = StateTracker(sampling_time=1.0, glucose_maxlen=48)
    base_ms = int(datetime.datetime(2026, 1, 1, 0, 0, 0,
                                    tzinfo=datetime.timezone.utc).timestamp() * 1000)
    results = []
    for i in range(n_steps):
        ms = base_ms + i * 5 * 60 * 1000
        dt = datetime.datetime.fromtimestamp(ms / 1000, tz=datetime.timezone.utc)
        tracker.record_glucose(i * 5, 110.0 + i * 0.5)

        glucose_json = GlucoseFormatter.format(list(tracker.glucose_history))
        if not glucose_json:
            continue

        pump_history = PumpHistoryBuilder.build_pump_history(tracker.insulin_deliveries)
        clock = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        currenttemp = {"duration": 0, "rate": 0, "temp": "absolute"}

        iob = runner.calculate_iob(pump_history, PROFILE, clock)
        if iob is None:
            iob = {"iob": 0.0, "activity": 0.0}

        result = runner.determine_basal(
            iob, currenttemp, glucose_json, PROFILE, clock
        )

        rate = _normalize(result.get("rate") if result else None)
        duration = _normalize(result.get("duration") if result else None)
        results.append((rate, duration))

        if result and result.get("rate") is not None:
            tracker.record_insulin(i * 5, float(result["rate"]) * 1000.0 / 60.0, duration_min=5.0)

    return results


@skip_no_wheel
def test_ffi_parity_with_subprocess_24_steps():
    from pymgipsim.Controllers.Oref0.ffi_runner import FfiRunner

    sub_runner = SubprocessRunner(backend="rust")
    ffi_runner = FfiRunner()
    try:
        sub_results = _run_steps(sub_runner, n_steps=24)
        ffi_results = _run_steps(ffi_runner, n_steps=24)

        assert len(sub_results) == len(ffi_results)
        mismatches = []
        for idx, (sub, ffi) in enumerate(zip(sub_results, ffi_results)):
            sub_rate, sub_dur = sub
            ffi_rate, ffi_dur = ffi
            if sub_rate != ffi_rate:
                mismatches.append(f"step {idx} rate: sub={sub_rate} ffi={ffi_rate}")
            if sub_dur != ffi_dur:
                mismatches.append(f"step {idx} duration: sub={sub_dur} ffi={ffi_dur}")
        assert mismatches == [], "E2E parity failed:\n" + "\n".join(mismatches)
    finally:
        sub_runner.cleanup()


@skip_no_wheel
def test_subprocess_runner_use_ffi_delegation():
    sub_ffi = SubprocessRunner(backend="rust", use_ffi=True)
    sub_norm = SubprocessRunner(backend="rust", use_ffi=False)
    try:
        sub_results = _run_steps(sub_norm, n_steps=12)
        ffi_results = _run_steps(sub_ffi, n_steps=12)

        assert len(sub_results) == len(ffi_results)
        mismatches = []
        for idx, (sub, ffi) in enumerate(zip(sub_results, ffi_results)):
            if sub[0] != ffi[0]:
                mismatches.append(f"step {idx} rate: sub={sub[0]} ffi={ffi[0]}")
        assert mismatches == [], "delegation parity failed:\n" + "\n".join(mismatches)
    finally:
        sub_ffi.cleanup()
        sub_norm.cleanup()
