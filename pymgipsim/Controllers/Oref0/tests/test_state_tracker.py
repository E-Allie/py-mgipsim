import datetime

import pytest

from pymgipsim.Controllers.Oref0.state_tracker import StateTracker


@pytest.fixture
def tracker():
    return StateTracker(sampling_time=1.0)


class TestRecordGlucose:
    def test_record_glucose_stores_mgdl(self, tracker):
        tracker.record_glucose(sample=0, glucose_mmol=6.0)
        ms, mgdl = tracker.glucose_history[0]
        assert ms == tracker._sample_to_ms(0)
        assert ms == tracker.epoch_ms
        assert mgdl == pytest.approx(108.0)

    def test_glucose_history_maxlen(self, tracker):
        for i in range(50):
            tracker.record_glucose(sample=i, glucose_mmol=5.0)
        assert len(tracker.glucose_history) == 48


class TestGlucoseJson:
    def test_glucose_json_newest_first(self, tracker):
        tracker.record_glucose(sample=0, glucose_mmol=5.0)
        tracker.record_glucose(sample=1, glucose_mmol=6.0)
        tracker.record_glucose(sample=2, glucose_mmol=7.0)
        result = tracker.get_glucose_json()
        assert result[0]["date"] > result[1]["date"] > result[2]["date"]

    def test_glucose_json_fields(self, tracker):
        tracker.record_glucose(sample=0, glucose_mmol=6.0)
        entry = tracker.get_glucose_json()[0]
        assert "date" in entry
        assert "dateString" in entry
        assert "sgv" in entry
        assert "glucose" in entry
        assert "direction" in entry
        assert "type" in entry
        assert "device" in entry

    def test_glucose_json_sgv_value(self, tracker):
        tracker.record_glucose(sample=0, glucose_mmol=6.0)
        entry = tracker.get_glucose_json()[0]
        assert entry["sgv"] == pytest.approx(108.0)

    def test_glucose_json_direction_flat(self, tracker):
        tracker.record_glucose(sample=0, glucose_mmol=6.0)
        entry = tracker.get_glucose_json()[0]
        assert entry["direction"] == "Flat"


class TestRecordInsulin:
    def test_record_insulin_converts_units(self, tracker):
        tracker.record_insulin(sample=0, rate_mUmin=16.667)
        delivery = tracker.insulin_deliveries[0]
        assert delivery["rate_Uhr"] == pytest.approx(1.0, abs=1e-3)


class TestPumpHistoryJson:
    def test_pump_history_json_structure(self, tracker):
        tracker.record_insulin(sample=0, rate_mUmin=16.667)
        result = tracker.get_pump_history_json()
        assert len(result) == 2

    def test_pump_history_json_types(self, tracker):
        tracker.record_insulin(sample=0, rate_mUmin=16.667)
        result = tracker.get_pump_history_json()
        types = {e["_type"] for e in result}
        assert types == {"TempBasal", "TempBasalDuration"}

    def test_pump_history_json_rate(self, tracker):
        tracker.record_insulin(sample=0, rate_mUmin=16.667)
        result = tracker.get_pump_history_json()
        tb = next(e for e in result if e["_type"] == "TempBasal")
        assert tb["rate"] == pytest.approx(1.0, abs=1e-3)


class TestCurrentTempJson:
    def test_current_temp_json_none(self, tracker):
        result = tracker.get_current_temp_json()
        assert result == {"duration": 0, "rate": 0, "temp": "absolute"}

    def test_current_temp_json_after_delivery(self, tracker):
        tracker.record_insulin(sample=0, rate_mUmin=16.667)
        result = tracker.get_current_temp_json()
        assert result["rate"] == pytest.approx(1.0, abs=1e-3)
        assert result["temp"] == "absolute"


class TestTimestamps:
    def test_timestamps_monotonic(self, tracker):
        for i in range(5):
            tracker.record_glucose(sample=i, glucose_mmol=5.0)
        dates = [ms for ms, _ in tracker.glucose_history]
        assert dates == sorted(dates)
        assert len(set(dates)) == 5

    def test_clock_json_format(self, tracker):
        iso0 = tracker.get_clock_json(0)
        iso60 = tracker.get_clock_json(60)
        dt0 = datetime.datetime.strptime(iso0, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=datetime.timezone.utc
        )
        dt60 = datetime.datetime.strptime(iso60, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=datetime.timezone.utc
        )
        delta_minutes = (dt60 - dt0).total_seconds() / 60
        assert delta_minutes == pytest.approx(60.0)

    def test_epoch_ms_is_wall_clock(self, tracker):
        import time
        now_ms = int(time.time() * 1000)
        assert abs(tracker.epoch_ms - now_ms) < 5000


class TestRecordCarbs:
    def test_record_carbs(self, tracker):
        tracker.record_carbs(sample=10, carbs_g=50.0)
        assert len(tracker.carb_events) == 1
        assert tracker.carb_events[0]["amount_g"] == 50.0


class TestGlucoseMaxlen:
    def test_default_maxlen_is_48(self):
        tracker = StateTracker(1.0)
        assert tracker.glucose_history.maxlen == 48

    def test_custom_maxlen_288(self):
        tracker = StateTracker(1.0, glucose_maxlen=288)
        assert tracker.glucose_history.maxlen == 288

    def test_custom_maxlen_limits_history(self):
        tracker = StateTracker(1.0, glucose_maxlen=10)
        for i in range(15):
            tracker.record_glucose(i, 6.0)
        assert len(tracker.glucose_history) == 10


class TestIntegrateCarbs:
    def test_zero_carbs_returns_zero(self):
        import numpy as np
        inputs = np.zeros((5, 100))
        result = StateTracker.integrate_carbs(inputs, sample=0, control_sampling=5, sampling_time=1.0)
        assert result == 0.0

    def test_fast_carbs_integration(self):
        import numpy as np
        inputs = np.zeros((5, 100))
        rate_mmol_per_min = (2.5 / 180.156) * 1000
        inputs[0, 0:5] = rate_mmol_per_min
        result = StateTracker.integrate_carbs(inputs, sample=0, control_sampling=5, sampling_time=1.0)
        assert abs(result - 12.5) < 0.01

    def test_slow_carbs_integration(self):
        import numpy as np
        inputs = np.zeros((5, 100))
        rate_mmol_per_min = (1.0 / 180.156) * 1000
        inputs[1, 0:5] = rate_mmol_per_min
        result = StateTracker.integrate_carbs(inputs, sample=0, control_sampling=5, sampling_time=1.0)
        assert abs(result - 5.0) < 0.01

    def test_fast_and_slow_carbs_summed(self):
        import numpy as np
        inputs = np.zeros((5, 100))
        rate = (1.0 / 180.156) * 1000
        inputs[0, 0:5] = rate
        inputs[1, 0:5] = rate
        result = StateTracker.integrate_carbs(inputs, sample=0, control_sampling=5, sampling_time=1.0)
        assert abs(result - 10.0) < 0.01

    def test_negative_carbs_clamped_to_zero(self):
        import numpy as np
        inputs = np.zeros((5, 100))
        inputs[0, 0:5] = -1.0
        result = StateTracker.integrate_carbs(inputs, sample=0, control_sampling=5, sampling_time=1.0)
        assert result == 0.0

    def test_sample_offset_respected(self):
        import numpy as np
        inputs = np.zeros((5, 100))
        rate = (1.0 / 180.156) * 1000
        inputs[0, 10:15] = rate
        result_at_0 = StateTracker.integrate_carbs(inputs, sample=0, control_sampling=5, sampling_time=1.0)
        result_at_10 = StateTracker.integrate_carbs(inputs, sample=10, control_sampling=5, sampling_time=1.0)
        assert result_at_0 == 0.0
        assert abs(result_at_10 - 5.0) < 0.01
