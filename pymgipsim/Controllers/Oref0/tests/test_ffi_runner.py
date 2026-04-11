import datetime
import time
import pytest

from pymgipsim.Controllers.Oref0.subprocess_runner import SubprocessRunner


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

IOB_DATA = [{"iob": 0, "activity": 0, "bolussnooze": 0}]
CURRENTTEMP = {"duration": 30, "rate": 1.5, "temp": "absolute"}
CLOCK = "2026-01-01T00:05:00Z"

GLUCOSE = [
    {
        "date": 1767225600000,
        "dateString": "2026-01-01T00:00:00Z",
        "sgv": 115,
        "glucose": 115,
        "direction": "Flat",
        "type": "sgv",
        "device": "test",
    }
]

PUMP_HISTORY = [
    {"_type": "Bolus", "amount": 1, "duration": 0, "timestamp": "2026-03-25T11:00:00.000Z"},
    {"_type": "TempBasalDuration", "duration (min)": 30, "timestamp": "2026-03-25T10:00:00.000Z"},
    {"_type": "TempBasal", "temp": "absolute", "rate": 1.5, "timestamp": "2026-03-25T10:00:00.000Z"},
]

IOB_PROFILE = {
    "dia": 3,
    "current_basal": 0.9,
    "basalprofile": [{"minutes": 0, "rate": 0.9, "start": "00:00:00"}],
}

IOB_CLOCK = "2026-03-25T12:00:00.000Z"


def _make_glucose_history(n=72):
    now_ms = int(time.time() * 1000)
    entries = []
    for i in range(n):
        ms = now_ms - (n - 1 - i) * 5 * 60 * 1000
        dt = datetime.datetime.fromtimestamp(ms / 1000, tz=datetime.timezone.utc)
        entries.append({
            "date": ms,
            "dateString": dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "sgv": 110,
            "glucose": 110,
            "direction": "Flat",
            "type": "sgv",
            "device": "fakecgm",
        })
    entries.reverse()
    return entries


def _normalize(v):
    import math
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    return v


def _dicts_equal(a: dict, b: dict, keys) -> list[str]:
    mismatches = []
    for k in keys:
        av = _normalize(a.get(k))
        bv = _normalize(b.get(k))
        if av != bv:
            mismatches.append(f"{k}: ffi={av!r} subprocess={bv!r}")
    return mismatches


@skip_no_wheel
def test_ffi_runner_initializes():
    from pymgipsim.Controllers.Oref0.ffi_runner import FfiRunner
    runner = FfiRunner()
    assert runner is not None


@skip_no_wheel
def test_ffi_runner_calculate_iob_returns_list():
    from pymgipsim.Controllers.Oref0.ffi_runner import FfiRunner
    runner = FfiRunner()
    result = runner.calculate_iob(PUMP_HISTORY, IOB_PROFILE, IOB_CLOCK)
    assert isinstance(result, list)
    assert len(result) > 0
    assert "iob" in result[0]
    assert "activity" in result[0]


@skip_no_wheel
def test_ffi_runner_determine_basal_returns_dict():
    from pymgipsim.Controllers.Oref0.ffi_runner import FfiRunner
    runner = FfiRunner()
    result = runner.determine_basal(IOB_DATA, CURRENTTEMP, GLUCOSE, PROFILE, CLOCK)
    assert isinstance(result, dict)
    assert "rate" in result
    assert "reason" in result


@skip_no_wheel
def test_calculate_iob_parity_with_subprocess():
    from pymgipsim.Controllers.Oref0.ffi_runner import FfiRunner
    ffi_runner = FfiRunner()
    sub_runner = SubprocessRunner(backend="rust")
    try:
        ffi_result = ffi_runner.calculate_iob(PUMP_HISTORY, IOB_PROFILE, IOB_CLOCK)
        sub_result = sub_runner.calculate_iob(PUMP_HISTORY, IOB_PROFILE, IOB_CLOCK)
        assert ffi_result is not None
        assert sub_result is not None
        mismatches = _dicts_equal(ffi_result[0], sub_result[0], ["iob", "activity", "basaliob", "bolusiob"])
        assert mismatches == [], "IOB parity failed:\n" + "\n".join(mismatches)
    finally:
        sub_runner.cleanup()


@skip_no_wheel
def test_determine_basal_parity_with_subprocess():
    from pymgipsim.Controllers.Oref0.ffi_runner import FfiRunner
    ffi_runner = FfiRunner()
    sub_runner = SubprocessRunner(backend="rust")
    try:
        glucose = _make_glucose_history(12)
        now_ms = glucose[0]["date"]
        dt = datetime.datetime.fromtimestamp(now_ms / 1000, tz=datetime.timezone.utc)
        clock = dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        iob_ffi = ffi_runner.calculate_iob([], IOB_PROFILE, clock)
        iob_sub = sub_runner.calculate_iob([], IOB_PROFILE, clock)
        if iob_ffi is None:
            iob_ffi = [{"iob": 0.0, "activity": 0.0}]
        if iob_sub is None:
            iob_sub = [{"iob": 0.0, "activity": 0.0}]

        ffi_result = ffi_runner.determine_basal(
            iob_ffi, CURRENTTEMP, glucose, PROFILE, clock
        )
        sub_result = sub_runner.determine_basal(
            iob_sub, CURRENTTEMP, glucose, PROFILE, clock
        )
        assert ffi_result is not None
        assert sub_result is not None
        mismatches = _dicts_equal(ffi_result, sub_result, ["rate", "duration", "reason"])
        assert mismatches == [], "determine_basal parity failed:\n" + "\n".join(mismatches)
    finally:
        sub_runner.cleanup()


@skip_no_wheel
def test_ffi_runner_empty_glucose_returns_none():
    from pymgipsim.Controllers.Oref0.ffi_runner import FfiRunner
    runner = FfiRunner()
    result = runner.determine_basal(IOB_DATA, CURRENTTEMP, [], PROFILE, CLOCK)
    assert result is None


@skip_no_wheel
def test_ffi_runner_cleanup_is_noop():
    from pymgipsim.Controllers.Oref0.ffi_runner import FfiRunner
    runner = FfiRunner()
    runner.cleanup()
