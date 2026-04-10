import numpy as np
import types
import pytest
from unittest.mock import MagicMock, patch

from pymgipsim.Controllers.Oref0.controller import Controller
from pymgipsim.Controllers.Oref0.unit_bridge import UnitBridge


BASAL_UHR = 1.1361426567898003
BASAL_MUMIN = UnitBridge.Uhr_to_mUmin(BASAL_UHR)


def make_scenario(n_patients=1, sampling_time=1.0, n_samples=120):
    demo = types.SimpleNamespace(
        basal=[BASAL_UHR] * n_patients,
        carb_insulin_ratio=[17.5] * n_patients,
        correction_bolus=[27.75762064628288] * n_patients,
        total_daily_basal=[16.893508304187925] * n_patients,
    )
    settings = types.SimpleNamespace(sampling_time=sampling_time)
    patient = types.SimpleNamespace(
        number_of_subjects=n_patients,
        demographic_info=demo,
    )
    return types.SimpleNamespace(settings=settings, patient=patient)


def make_inputs(n_patients=1, n_channels=10, n_samples=120):
    return np.zeros((n_patients, n_channels, n_samples))


def make_measurements(n_patients=1, glucose_mmol=6.0):
    return np.array([glucose_mmol] * n_patients)


def _patched_controller(scenario_instance, mock_instance=None):
    if mock_instance is None:
        mock_instance = MagicMock()
        mock_instance.calculate_iob.return_value = {"iob": 0.0, "activity": 0.0, "bolussnooze": 0.0}
        mock_instance.determine_basal.return_value = {"rate": 1.0, "duration": 30, "reason": "test"}
    with patch("pymgipsim.Controllers.Oref0.controller.SubprocessRunner") as MockRunner:
        MockRunner.return_value = mock_instance
        ctrl = Controller(scenario_instance)
    return ctrl, mock_instance


def test_controller_name():
    assert Controller.name == "Oref0"


def test_control_sampling():
    sc = make_scenario(sampling_time=1.0)
    with patch("pymgipsim.Controllers.Oref0.controller.SubprocessRunner"):
        ctrl = Controller(sc)
    assert ctrl.control_sampling == 5


def test_warmup_samples():
    sc = make_scenario(sampling_time=1.0)
    with patch("pymgipsim.Controllers.Oref0.controller.SubprocessRunner"):
        ctrl = Controller(sc)
    assert ctrl.warmup_samples == 45


def test_n_trackers():
    sc = make_scenario(n_patients=3)
    with patch("pymgipsim.Controllers.Oref0.controller.SubprocessRunner"):
        ctrl = Controller(sc)
    assert len(ctrl.trackers) == 3


def test_n_profiles():
    sc = make_scenario(n_patients=2)
    with patch("pymgipsim.Controllers.Oref0.controller.SubprocessRunner"):
        ctrl = Controller(sc)
    assert len(ctrl.profiles) == 2


def test_warmup_delivers_basal():
    sc = make_scenario(n_patients=1, sampling_time=1.0)
    inputs = make_inputs(n_patients=1, n_samples=120)
    measurements = make_measurements(n_patients=1)
    ctrl, _ = _patched_controller(sc)

    ctrl.run(measurements, inputs, states=None, sample=0)

    np.testing.assert_array_almost_equal(inputs[0, 3, 0:5], BASAL_MUMIN)


def test_no_action_between_control_samples():
    sc = make_scenario(n_patients=1, sampling_time=1.0)
    inputs = make_inputs(n_patients=1, n_samples=120)
    measurements = make_measurements()
    ctrl, _ = _patched_controller(sc)

    ctrl.run(measurements, inputs, states=None, sample=1)

    assert np.all(inputs[0, 3, :] == 0.0)


def test_oref0_called_after_warmup():
    sc = make_scenario(n_patients=1, sampling_time=1.0)
    inputs = make_inputs(n_patients=1, n_samples=120)
    measurements = make_measurements()

    mock_instance = MagicMock()
    mock_instance.calculate_iob.return_value = {"iob": 0.0, "activity": 0.0, "bolussnooze": 0.0}
    mock_instance.determine_basal.return_value = {"rate": 1.0, "duration": 30, "reason": "test"}

    with patch("pymgipsim.Controllers.Oref0.controller.SubprocessRunner") as MockRunner:
        MockRunner.return_value = mock_instance
        ctrl = Controller(sc)

        for s in range(46):
            ctrl.run(measurements, inputs, states=None, sample=s)

    mock_instance.determine_basal.assert_called()


def test_fallback_on_runner_failure():
    sc = make_scenario(n_patients=1, sampling_time=1.0)
    inputs = make_inputs(n_patients=1, n_samples=120)
    measurements = make_measurements()

    mock_instance = MagicMock()
    mock_instance.calculate_iob.return_value = None
    mock_instance.determine_basal.return_value = None

    with patch("pymgipsim.Controllers.Oref0.controller.SubprocessRunner") as MockRunner:
        MockRunner.return_value = mock_instance
        ctrl = Controller(sc)

        for s in range(46):
            ctrl.run(measurements, inputs, states=None, sample=s)

    assert inputs[0, 3, 45] == pytest.approx(BASAL_MUMIN)


def test_glucose_recorded_every_tick():
    sc = make_scenario(n_patients=1, sampling_time=1.0)
    inputs = make_inputs()
    measurements = make_measurements()
    ctrl, _ = _patched_controller(sc)

    for s in range(10):
        ctrl.run(measurements, inputs, states=None, sample=s)

    assert len(ctrl.trackers[0].glucose_history) == 2  # recorded every 5 ticks: samples 0 and 5


def test_insulin_recorded_after_control():
    sc = make_scenario(n_patients=1, sampling_time=1.0)
    inputs = make_inputs(n_patients=1, n_samples=200)
    measurements = make_measurements()

    mock_instance = MagicMock()
    mock_instance.calculate_iob.return_value = {"iob": 0.0, "activity": 0.0, "bolussnooze": 0.0}
    mock_instance.determine_basal.return_value = {"rate": 1.0, "duration": 30, "reason": "test"}

    with patch("pymgipsim.Controllers.Oref0.controller.SubprocessRunner") as MockRunner:
        MockRunner.return_value = mock_instance
        ctrl = Controller(sc)

        for s in range(46):
            ctrl.run(measurements, inputs, states=None, sample=s)

    assert len(ctrl.trackers[0].insulin_deliveries) >= 1


def test_rate_converted_to_mUmin():
    sc = make_scenario(n_patients=1, sampling_time=1.0)
    inputs = make_inputs(n_patients=1, n_samples=200)
    measurements = make_measurements()

    mock_instance = MagicMock()
    mock_instance.calculate_iob.return_value = {"iob": 0.0, "activity": 0.0, "bolussnooze": 0.0}
    mock_instance.determine_basal.return_value = {"rate": 1.0, "duration": 30, "reason": "test"}

    with patch("pymgipsim.Controllers.Oref0.controller.SubprocessRunner") as MockRunner:
        MockRunner.return_value = mock_instance
        ctrl = Controller(sc)

        for s in range(46):
            ctrl.run(measurements, inputs, states=None, sample=s)

    expected_mUmin = UnitBridge.Uhr_to_mUmin(1.0)
    assert inputs[0, 3, 45] == pytest.approx(expected_mUmin)


def test_forward_carbs_false_no_meal_call():
    sc = make_scenario(n_patients=1, sampling_time=1.0)
    inputs = make_inputs(n_patients=1, n_samples=200)
    measurements = make_measurements()

    mock_instance = MagicMock()
    mock_instance.calculate_iob.return_value = {"iob": 0.0, "activity": 0.0, "bolussnooze": 0.0}
    mock_instance.determine_basal.return_value = {"rate": 1.0, "duration": 30, "reason": "test"}
    mock_instance.calculate_meal.return_value = {"mealCOB": 0, "carbs": 0}

    with patch("pymgipsim.Controllers.Oref0.controller.SubprocessRunner") as MockRunner:
        MockRunner.return_value = mock_instance
        ctrl = Controller(sc, forward_carbs=False)
        for s in range(46):
            ctrl.run(measurements, inputs, states=None, sample=s)

    mock_instance.calculate_meal.assert_not_called()


def test_forward_carbs_true_calls_meal_pipeline():
    sc = make_scenario(n_patients=1, sampling_time=1.0)
    inputs = make_inputs(n_patients=1, n_samples=200)
    inputs[0, 0, 45:50] = 0.1
    measurements = make_measurements()

    mock_instance = MagicMock()
    mock_instance.calculate_iob.return_value = {"iob": 0.0, "activity": 0.0, "bolussnooze": 0.0}
    mock_instance.determine_basal.return_value = {"rate": 1.0, "duration": 30, "reason": "test"}
    mock_instance.calculate_meal.return_value = {"mealCOB": 5.0, "carbs": 10.0}

    with patch("pymgipsim.Controllers.Oref0.controller.SubprocessRunner") as MockRunner:
        MockRunner.return_value = mock_instance
        ctrl = Controller(sc, forward_carbs=True)
        for s in range(46):
            ctrl.run(measurements, inputs, states=None, sample=s)

    mock_instance.calculate_meal.assert_called()


def test_forward_carbs_records_carb_events():
    sc = make_scenario(n_patients=1, sampling_time=1.0)
    inputs = make_inputs(n_patients=1, n_samples=200)
    inputs[0, 0, 45:50] = 0.1
    measurements = make_measurements()

    mock_instance = MagicMock()
    mock_instance.calculate_iob.return_value = {"iob": 0.0, "activity": 0.0, "bolussnooze": 0.0}
    mock_instance.determine_basal.return_value = {"rate": 1.0, "duration": 30, "reason": "test"}
    mock_instance.calculate_meal.return_value = {"mealCOB": 5.0, "carbs": 10.0}

    with patch("pymgipsim.Controllers.Oref0.controller.SubprocessRunner") as MockRunner:
        MockRunner.return_value = mock_instance
        ctrl = Controller(sc, forward_carbs=True)
        for s in range(46):
            ctrl.run(measurements, inputs, states=None, sample=s)

    assert len(ctrl.trackers[0].carb_events) >= 1


def test_forward_carbs_meal_data_passed_to_determine_basal():
    sc = make_scenario(n_patients=1, sampling_time=1.0)
    inputs = make_inputs(n_patients=1, n_samples=200)
    inputs[0, 0, 45:50] = 0.1
    measurements = make_measurements()

    mock_instance = MagicMock()
    mock_instance.calculate_iob.return_value = {"iob": 0.0, "activity": 0.0, "bolussnooze": 0.0}
    mock_instance.determine_basal.return_value = {"rate": 1.0, "duration": 30, "reason": "test"}
    mock_instance.calculate_meal.return_value = {"mealCOB": 5.0, "carbs": 10.0}

    with patch("pymgipsim.Controllers.Oref0.controller.SubprocessRunner") as MockRunner:
        MockRunner.return_value = mock_instance
        ctrl = Controller(sc, forward_carbs=True)
        for s in range(46):
            ctrl.run(measurements, inputs, states=None, sample=s)

    calls = mock_instance.determine_basal.call_args_list
    post_warmup_calls = [c for c in calls if c.kwargs.get("meal_data") is not None]
    assert len(post_warmup_calls) >= 1


def test_enable_smb_false_no_microbolus():
    sc = make_scenario(n_patients=1, sampling_time=1.0)
    inputs = make_inputs(n_patients=1, n_samples=200)
    measurements = make_measurements()

    mock_instance = MagicMock()
    mock_instance.calculate_iob.return_value = {"iob": 0.0, "activity": 0.0, "bolussnooze": 0.0}
    mock_instance.determine_basal.return_value = {"rate": 1.0, "duration": 30, "reason": "test"}

    with patch("pymgipsim.Controllers.Oref0.controller.SubprocessRunner") as MockRunner:
        MockRunner.return_value = mock_instance
        ctrl = Controller(sc, enable_smb=False)
        for s in range(46):
            ctrl.run(measurements, inputs, states=None, sample=s)

    calls = mock_instance.determine_basal.call_args_list
    for call in calls:
        assert call.kwargs.get("microbolus") == False


def test_enable_smb_true_passes_microbolus():
    sc = make_scenario(n_patients=1, sampling_time=1.0)
    inputs = make_inputs(n_patients=1, n_samples=200)
    measurements = make_measurements()

    mock_instance = MagicMock()
    mock_instance.calculate_iob.return_value = {"iob": 0.0, "activity": 0.0, "bolussnooze": 0.0}
    mock_instance.determine_basal.return_value = {"rate": 1.0, "duration": 30, "reason": "test"}

    with patch("pymgipsim.Controllers.Oref0.controller.SubprocessRunner") as MockRunner:
        MockRunner.return_value = mock_instance
        ctrl = Controller(sc, enable_smb=True)
        for s in range(46):
            ctrl.run(measurements, inputs, states=None, sample=s)

    calls = mock_instance.determine_basal.call_args_list
    post_warmup = [c for c in calls if c.kwargs.get("microbolus") == True]
    assert len(post_warmup) >= 1


def test_smb_units_added_to_rate():
    sc = make_scenario(n_patients=1, sampling_time=1.0)
    inputs = make_inputs(n_patients=1, n_samples=200)
    measurements = make_measurements()

    mock_instance = MagicMock()
    mock_instance.calculate_iob.return_value = {"iob": 0.0, "activity": 0.0, "bolussnooze": 0.0}
    mock_instance.determine_basal.return_value = {"rate": 0.5, "duration": 30, "reason": "SMB", "units": 0.1}

    with patch("pymgipsim.Controllers.Oref0.controller.SubprocessRunner") as MockRunner:
        MockRunner.return_value = mock_instance
        ctrl = Controller(sc, enable_smb=True)
        for s in range(46):
            ctrl.run(measurements, inputs, states=None, sample=s)

    expected_basal_mUmin = UnitBridge.Uhr_to_mUmin(0.5)
    expected_smb_mUmin = 0.1 * 1000.0 / 5.0
    expected_total = expected_basal_mUmin + expected_smb_mUmin
    assert inputs[0, 3, 45] == pytest.approx(expected_total, rel=1e-3)


def test_smb_bolus_recorded_in_pump_history():
    sc = make_scenario(n_patients=1, sampling_time=1.0)
    inputs = make_inputs(n_patients=1, n_samples=200)
    measurements = make_measurements()

    mock_instance = MagicMock()
    mock_instance.calculate_iob.return_value = {"iob": 0.0, "activity": 0.0, "bolussnooze": 0.0}
    mock_instance.determine_basal.return_value = {"rate": 0.5, "duration": 30, "reason": "SMB", "units": 0.1}

    with patch("pymgipsim.Controllers.Oref0.controller.SubprocessRunner") as MockRunner:
        MockRunner.return_value = mock_instance
        ctrl = Controller(sc, enable_smb=True)
        for s in range(46):
            ctrl.run(measurements, inputs, states=None, sample=s)

    bolus_entries = [d for d in ctrl.trackers[0].insulin_deliveries if d.get("_type") == "Bolus"]
    assert len(bolus_entries) >= 1


def test_enable_autosens_false_no_detect_sensitivity():
    sc = make_scenario(n_patients=1, sampling_time=1.0)
    inputs = make_inputs(n_patients=1, n_samples=200)
    measurements = make_measurements()

    mock_instance = MagicMock()
    mock_instance.calculate_iob.return_value = {"iob": 0.0, "activity": 0.0, "bolussnooze": 0.0}
    mock_instance.determine_basal.return_value = {"rate": 1.0, "duration": 30, "reason": "test"}

    with patch("pymgipsim.Controllers.Oref0.controller.SubprocessRunner") as MockRunner:
        MockRunner.return_value = mock_instance
        ctrl = Controller(sc, enable_autosens=False)
        for s in range(46):
            ctrl.run(measurements, inputs, states=None, sample=s)

    mock_instance.detect_sensitivity.assert_not_called()


def test_enable_autosens_true_calls_detect_sensitivity():
    sc = make_scenario(n_patients=1, sampling_time=1.0)
    inputs = make_inputs(n_patients=1, n_samples=200)
    measurements = make_measurements()

    mock_instance = MagicMock()
    mock_instance.calculate_iob.return_value = {"iob": 0.0, "activity": 0.0, "bolussnooze": 0.0}
    mock_instance.determine_basal.return_value = {"rate": 1.0, "duration": 30, "reason": "test"}
    mock_instance.detect_sensitivity.return_value = {"ratio": 0.9}

    with patch("pymgipsim.Controllers.Oref0.controller.SubprocessRunner") as MockRunner:
        MockRunner.return_value = mock_instance
        ctrl = Controller(sc, enable_autosens=True)
        for s in range(46):
            ctrl.run(measurements, inputs, states=None, sample=s)

    mock_instance.detect_sensitivity.assert_called()


def test_enable_autosens_uses_288_maxlen():
    sc = make_scenario(n_patients=1, sampling_time=1.0)
    with patch("pymgipsim.Controllers.Oref0.controller.SubprocessRunner"):
        ctrl = Controller(sc, enable_autosens=True)
    assert ctrl.trackers[0].glucose_history.maxlen == 288


def test_enable_autosens_false_uses_48_maxlen():
    sc = make_scenario(n_patients=1, sampling_time=1.0)
    with patch("pymgipsim.Controllers.Oref0.controller.SubprocessRunner"):
        ctrl = Controller(sc, enable_autosens=False)
    assert ctrl.trackers[0].glucose_history.maxlen == 48


def test_autosens_result_passed_to_determine_basal():
    sc = make_scenario(n_patients=1, sampling_time=1.0)
    inputs = make_inputs(n_patients=1, n_samples=200)
    measurements = make_measurements()

    mock_instance = MagicMock()
    mock_instance.calculate_iob.return_value = {"iob": 0.0, "activity": 0.0, "bolussnooze": 0.0}
    mock_instance.determine_basal.return_value = {"rate": 1.0, "duration": 30, "reason": "test"}
    mock_instance.detect_sensitivity.return_value = {"ratio": 0.85}

    with patch("pymgipsim.Controllers.Oref0.controller.SubprocessRunner") as MockRunner:
        MockRunner.return_value = mock_instance
        ctrl = Controller(sc, enable_autosens=True)
        for s in range(46):
            ctrl.run(measurements, inputs, states=None, sample=s)

    calls = mock_instance.determine_basal.call_args_list
    autosens_calls = [c for c in calls if c.kwargs.get("autosens_data") is not None]
    assert len(autosens_calls) >= 1
    assert autosens_calls[0].kwargs["autosens_data"]["ratio"] == 0.85


def test_enable_autotune_false_no_autotune_calls():
    sc = make_scenario(n_patients=1, sampling_time=1.0)
    inputs = make_inputs(n_patients=1, n_samples=2000)
    measurements = make_measurements()

    mock_instance = MagicMock()
    mock_instance.calculate_iob.return_value = {"iob": 0.0, "activity": 0.0, "bolussnooze": 0.0}
    mock_instance.determine_basal.return_value = {"rate": 1.0, "duration": 30, "reason": "test"}

    with patch("pymgipsim.Controllers.Oref0.controller.SubprocessRunner") as MockRunner:
        MockRunner.return_value = mock_instance
        ctrl = Controller(sc, enable_autotune=False)
        for s in range(200):
            ctrl.run(measurements, inputs, states=None, sample=s)

    mock_instance.autotune_prep.assert_not_called()
    mock_instance.autotune_core.assert_not_called()


def test_enable_autotune_true_calls_autotune_at_interval():
    sc = make_scenario(n_patients=1, sampling_time=1.0)
    # 1-hour interval = 60 samples. Autotune needs >= 36 glucose entries (recorded
    # every 5 ticks), so first eligible trigger is sample 180 (= 36 entries).
    n_samples = 500
    inputs = make_inputs(n_patients=1, n_samples=n_samples)
    measurements = make_measurements()

    mock_instance = MagicMock()
    mock_instance.calculate_iob.return_value = {"iob": 0.0, "activity": 0.0, "bolussnooze": 0.0}
    mock_instance.determine_basal.return_value = {"rate": 1.0, "duration": 30, "reason": "test"}
    mock_instance.autotune_prep.return_value = {"basalGlucoseData": [], "ISFGlucoseData": [], "CSFGlucoseData": [], "CRData": []}
    mock_instance.autotune_core.return_value = {
        "basalprofile": [{"minutes": 0, "rate": 0.85, "start": "00:00:00", "i": 0}],
        "sens": 42.0,
        "carb_ratio": 11.0,
    }

    with patch("pymgipsim.Controllers.Oref0.controller.SubprocessRunner") as MockRunner:
        MockRunner.return_value = mock_instance
        ctrl = Controller(sc, enable_autotune=True, autotune_interval_hours=1.0)
        for s in range(181):
            ctrl.run(measurements, inputs, states=None, sample=s)

    mock_instance.autotune_prep.assert_called()


def test_autotune_merges_profile():
    sc = make_scenario(n_patients=1, sampling_time=1.0)
    n_samples = 500
    inputs = make_inputs(n_patients=1, n_samples=n_samples)
    measurements = make_measurements()

    mock_instance = MagicMock()
    mock_instance.calculate_iob.return_value = {"iob": 0.0, "activity": 0.0, "bolussnooze": 0.0}
    mock_instance.determine_basal.return_value = {"rate": 1.0, "duration": 30, "reason": "test"}
    mock_instance.autotune_prep.return_value = {"basalGlucoseData": [], "ISFGlucoseData": [], "CSFGlucoseData": [], "CRData": []}
    mock_instance.autotune_core.return_value = {
        "basalprofile": [{"minutes": 0, "rate": 0.85, "start": "00:00:00", "i": 0}],
        "sens": 42.0,
        "carb_ratio": 11.0,
    }

    with patch("pymgipsim.Controllers.Oref0.controller.SubprocessRunner") as MockRunner:
        MockRunner.return_value = mock_instance
        ctrl = Controller(sc, enable_autotune=True, autotune_interval_hours=1.0)
        for s in range(181):
            ctrl.run(measurements, inputs, states=None, sample=s)

    assert ctrl.profiles[0]["sens"] == 42.0
    assert ctrl.profiles[0]["carb_ratio"] == 11.0
    assert ctrl.profiles[0]["current_basal"] == 0.85


def test_autotune_does_not_fire_before_interval():
    sc = make_scenario(n_patients=1, sampling_time=1.0)
    inputs = make_inputs(n_patients=1, n_samples=200)
    measurements = make_measurements()

    mock_instance = MagicMock()
    mock_instance.calculate_iob.return_value = {"iob": 0.0, "activity": 0.0, "bolussnooze": 0.0}
    mock_instance.determine_basal.return_value = {"rate": 1.0, "duration": 30, "reason": "test"}

    with patch("pymgipsim.Controllers.Oref0.controller.SubprocessRunner") as MockRunner:
        MockRunner.return_value = mock_instance
        ctrl = Controller(sc, enable_autotune=True, autotune_interval_hours=1.0)
        for s in range(59):
            ctrl.run(measurements, inputs, states=None, sample=s)

    mock_instance.autotune_prep.assert_not_called()


def test_autotune_uses_288_maxlen():
    sc = make_scenario(n_patients=1, sampling_time=1.0)
    with patch("pymgipsim.Controllers.Oref0.controller.SubprocessRunner"):
        ctrl = Controller(sc, enable_autotune=True, enable_autosens=False)
    assert ctrl.trackers[0].glucose_history.maxlen == 288


def test_pump_profiles_immutable_after_autotune():
    sc = make_scenario(n_patients=1, sampling_time=1.0)
    n_samples = 500
    inputs = make_inputs(n_patients=1, n_samples=n_samples)
    measurements = make_measurements()

    mock_instance = MagicMock()
    mock_instance.calculate_iob.return_value = {"iob": 0.0, "activity": 0.0, "bolussnooze": 0.0}
    mock_instance.determine_basal.return_value = {"rate": 1.0, "duration": 30, "reason": "test"}
    mock_instance.autotune_prep.return_value = {"basalGlucoseData": []}
    mock_instance.autotune_core.return_value = {
        "basalprofile": [{"minutes": 0, "rate": 0.5, "start": "00:00:00", "i": 0}],
        "sens": 50.0,
        "carb_ratio": 15.0,
    }

    with patch("pymgipsim.Controllers.Oref0.controller.SubprocessRunner") as MockRunner:
        MockRunner.return_value = mock_instance
        ctrl = Controller(sc, enable_autotune=True, autotune_interval_hours=1.0)
        original_pump_sens = ctrl.pump_profiles[0]["sens"]
        for s in range(181):
            ctrl.run(measurements, inputs, states=None, sample=s)

    assert ctrl.pump_profiles[0]["sens"] == original_pump_sens
    assert ctrl.profiles[0]["sens"] == 50.0
