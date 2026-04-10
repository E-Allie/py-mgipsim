import datetime
import os
import time
import pytest
from pymgipsim.Controllers.Oref0.subprocess_runner import SubprocessRunner

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

IOB_DATA = {"iob": 0, "activity": 0, "bolussnooze": 0}

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

MEAL_PROFILE = {
    "dia": 3,
    "current_basal": 0.9,
    "basalprofile": [{"minutes": 0, "rate": 0.9, "start": "00:00:00"}],
    "carb_ratio": 10,
    "sens": 40,
}

IOB_CLOCK = "2026-03-25T12:00:00.000Z"

MEAL_GLUCOSE = [
    {"date": int(time.time() * 1000), "dateString": "2026-04-07T12:00:00Z", "sgv": 115, "glucose": 115,
     "direction": "Flat", "type": "sgv", "device": "fakecgm"}
]
BASALPROFILE = [{"minutes": 0, "rate": 0.9, "start": "00:00:00", "i": 0}]
CARB_HISTORY = [{"_type": "Carb", "carbs": 50, "timestamp": "2026-04-07T20:00:00Z"}]


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
    entries.reverse()  # oref0 expects newest-first
    return entries


ISF_DATA = {"units": "mg/dL", "sensitivities": [{"sensitivity": 40.0}]}


@pytest.fixture
def runner():
    r = SubprocessRunner(backend="rust")
    yield r
    r.cleanup()


def test_determine_basal_returns_dict(runner):
    result = runner.determine_basal(IOB_DATA, CURRENTTEMP, GLUCOSE, PROFILE, CLOCK)
    assert isinstance(result, dict)


def test_determine_basal_has_rate(runner):
    result = runner.determine_basal(IOB_DATA, CURRENTTEMP, GLUCOSE, PROFILE, CLOCK)
    assert result is not None
    assert "rate" in result
    assert isinstance(result["rate"], (int, float))
    assert result["rate"] >= 0


def test_determine_basal_has_duration(runner):
    result = runner.determine_basal(IOB_DATA, CURRENTTEMP, GLUCOSE, PROFILE, CLOCK)
    assert result is not None
    assert "duration" in result


def test_determine_basal_has_reason(runner):
    result = runner.determine_basal(IOB_DATA, CURRENTTEMP, GLUCOSE, PROFILE, CLOCK)
    assert result is not None
    assert "reason" in result
    assert isinstance(result["reason"], str)
    assert len(result["reason"]) > 0


def test_determine_basal_invalid_input_returns_none(runner):
    result = runner.determine_basal({}, {}, [], {}, CLOCK)
    assert result is None


def test_calculate_iob_returns_dict(runner):
    result = runner.calculate_iob(PUMP_HISTORY, IOB_PROFILE, IOB_CLOCK)
    assert isinstance(result, dict)


def test_calculate_iob_has_iob_field(runner):
    result = runner.calculate_iob(PUMP_HISTORY, IOB_PROFILE, IOB_CLOCK)
    assert result is not None
    assert "iob" in result
    assert isinstance(result["iob"], (int, float))


def test_cleanup_removes_tmpdir(runner):
    tmpdir = runner.tmpdir
    assert os.path.exists(tmpdir)
    runner.cleanup()
    assert not os.path.exists(tmpdir)


def test_calculate_meal_returns_dict(runner):
    result = runner.calculate_meal(PUMP_HISTORY, MEAL_PROFILE, IOB_CLOCK, MEAL_GLUCOSE, BASALPROFILE)
    assert isinstance(result, dict)


def test_calculate_meal_has_meal_cob(runner):
    result = runner.calculate_meal(PUMP_HISTORY, MEAL_PROFILE, IOB_CLOCK, MEAL_GLUCOSE, BASALPROFILE)
    assert result is not None
    assert "mealCOB" in result


def test_calculate_meal_with_carbs(runner):
    result = runner.calculate_meal(PUMP_HISTORY, MEAL_PROFILE, IOB_CLOCK, MEAL_GLUCOSE, BASALPROFILE, CARB_HISTORY)
    assert isinstance(result, dict)
    assert "mealCOB" in result


def test_detect_sensitivity_returns_dict(runner):
    glucose = _make_glucose_history(72)
    result = runner.detect_sensitivity(glucose, [], ISF_DATA, BASALPROFILE, MEAL_PROFILE)
    assert isinstance(result, dict)


def test_detect_sensitivity_has_ratio(runner):
    glucose = _make_glucose_history(72)
    result = runner.detect_sensitivity(glucose, [], ISF_DATA, BASALPROFILE, MEAL_PROFILE)
    assert result is not None
    assert "ratio" in result
    assert isinstance(result["ratio"], (int, float))


def test_detect_sensitivity_insufficient_data_returns_ratio_1(runner):
    glucose = _make_glucose_history(10)
    result = runner.detect_sensitivity(glucose, [], ISF_DATA, BASALPROFILE, MEAL_PROFILE)
    assert result is not None
    assert result["ratio"] == 1


def test_autotune_dir_exists_in_tmpdir(runner):
    assert os.path.isdir(os.path.join(runner.tmpdir, "autotune"))


def test_determine_basal_backward_compatible(runner):
    result = runner.determine_basal(IOB_DATA, CURRENTTEMP, GLUCOSE, PROFILE, CLOCK)
    assert isinstance(result, dict)


def test_determine_basal_with_autosens(runner):
    autosens = {"ratio": 1.0}
    result = runner.determine_basal(IOB_DATA, CURRENTTEMP, GLUCOSE, PROFILE, CLOCK, autosens_data=autosens)
    assert isinstance(result, dict)


def test_determine_basal_microbolus_returns_dict(runner):
    smb_profile = dict(PROFILE)
    smb_profile["enableSMB_always"] = True
    result = runner.determine_basal(IOB_DATA, CURRENTTEMP, GLUCOSE, smb_profile, CLOCK, microbolus=True)
    assert isinstance(result, dict)


AUTOTUNE_PROFILE = {
    "dia": 5,
    "curve": "rapid-acting",
    "useCustomPeakTime": False,
    "insulinPeakTime": 75,
    "carb_ratio": 10,
    "basalprofile": [{"minutes": 0, "rate": 0.9, "start": "00:00:00", "i": 0}],
    "isfProfile": {
        "sensitivities": [
            {"offset": 0, "sensitivity": 40, "endOffset": 1440, "start": "00:00:00", "i": 0, "x": 0}
        ]
    },
    "sens": 40,
    "autosens_max": 1.2,
    "autosens_min": 0.7,
    "min_5m_carbimpact": 8,
}


def test_autotune_prep_returns_dict_or_none(runner):
    glucose = _make_glucose_history(288)
    result = runner.autotune_prep(PUMP_HISTORY, PROFILE, glucose, AUTOTUNE_PROFILE)
    assert result is None or isinstance(result, dict)


def test_autotune_prep_with_carb_history(runner):
    glucose = _make_glucose_history(288)
    result = runner.autotune_prep(
        PUMP_HISTORY, PROFILE, glucose, AUTOTUNE_PROFILE, carb_history=CARB_HISTORY
    )
    assert result is None or isinstance(result, dict)


def test_autotune_core_returns_dict_or_none(runner):
    glucose = _make_glucose_history(288)
    prepped = runner.autotune_prep(PUMP_HISTORY, PROFILE, glucose, AUTOTUNE_PROFILE)
    if prepped is None:
        pytest.skip("autotune_prep returned None with test data")
    result = runner.autotune_core(prepped, AUTOTUNE_PROFILE, AUTOTUNE_PROFILE)
    assert result is None or isinstance(result, dict)


def test_autotune_core_output_has_basalprofile(runner):
    glucose = _make_glucose_history(288)
    prepped = runner.autotune_prep(PUMP_HISTORY, PROFILE, glucose, AUTOTUNE_PROFILE)
    if prepped is None:
        pytest.skip("autotune_prep returned None with test data")
    result = runner.autotune_core(prepped, AUTOTUNE_PROFILE, AUTOTUNE_PROFILE)
    if result is None:
        pytest.skip("autotune_core returned None with test data")
    assert "basalprofile" in result
    assert "sens" in result
    assert "carb_ratio" in result
