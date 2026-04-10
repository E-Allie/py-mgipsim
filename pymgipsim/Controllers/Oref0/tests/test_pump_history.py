import pytest

from pymgipsim.Controllers.Oref0.pump_history import PumpHistoryBuilder


def make_delivery(rate_Uhr=1.0, duration_min=5, timestamp="2026-01-01T00:05:00Z"):
    return {"timestamp_str": timestamp, "rate_Uhr": rate_Uhr, "duration_min": duration_min}


def make_carb(amount_g=50.0, timestamp="2026-01-01T01:00:00Z"):
    return {"timestamp_str": timestamp, "amount_g": amount_g}


class TestBuildPumpHistory:
    def test_empty_deliveries_returns_empty_list(self):
        assert PumpHistoryBuilder.build_pump_history([]) == []

    def test_single_delivery_produces_two_entries(self):
        result = PumpHistoryBuilder.build_pump_history([make_delivery()])
        assert len(result) == 2

    def test_twelve_deliveries_produce_24_entries(self):
        deliveries = [make_delivery(rate_Uhr=0.1 * i) for i in range(12)]
        result = PumpHistoryBuilder.build_pump_history(deliveries)
        assert len(result) == 24

    def test_temp_basal_type(self):
        result = PumpHistoryBuilder.build_pump_history([make_delivery()])
        types = {e["_type"] for e in result}
        assert "TempBasal" in types

    def test_temp_basal_duration_type(self):
        result = PumpHistoryBuilder.build_pump_history([make_delivery()])
        types = {e["_type"] for e in result}
        assert "TempBasalDuration" in types

    def test_temp_basal_has_temp_absolute(self):
        result = PumpHistoryBuilder.build_pump_history([make_delivery()])
        tb = next(e for e in result if e["_type"] == "TempBasal")
        assert tb["temp"] == "absolute"

    def test_rate_value(self):
        result = PumpHistoryBuilder.build_pump_history([make_delivery(rate_Uhr=2.5)])
        tb = next(e for e in result if e["_type"] == "TempBasal")
        assert tb["rate"] == 2.5

    def test_duration_value(self):
        result = PumpHistoryBuilder.build_pump_history([make_delivery(duration_min=30)])
        tbd = next(e for e in result if e["_type"] == "TempBasalDuration")
        assert tbd["duration (min)"] == 30

    def test_timestamp_matches(self):
        ts = "2026-06-15T08:30:00Z"
        result = PumpHistoryBuilder.build_pump_history([make_delivery(timestamp=ts)])
        for e in result:
            assert e["timestamp"] == ts

    def test_output_is_newest_first(self):
        deliveries = [
            {"timestamp_str": "2026-01-01T00:00:00Z", "rate_Uhr": 1.0, "duration_min": 5},
            {"timestamp_str": "2026-01-01T00:05:00Z", "rate_Uhr": 1.5, "duration_min": 5},
            {"timestamp_str": "2026-01-01T00:10:00Z", "rate_Uhr": 2.0, "duration_min": 5},
        ]
        result = PumpHistoryBuilder.build_pump_history(deliveries)
        timestamps = [e["timestamp"] for e in result]
        assert timestamps == sorted(timestamps, reverse=True), \
            "pump history must be newest-first so oref0 calc_temp_treatments does not drop entries"

    def test_bolus_output_is_newest_first(self):
        deliveries = [
            {"timestamp_str": "2026-01-01T00:00:00Z", "_type": "Bolus", "amount_Uhr": 0.5, "duration_min": 0},
            {"timestamp_str": "2026-01-01T00:05:00Z", "_type": "Bolus", "amount_Uhr": 1.0, "duration_min": 0},
        ]
        result = PumpHistoryBuilder.build_pump_history(deliveries)
        assert result[0]["timestamp"] == "2026-01-01T00:05:00Z"
        assert result[1]["timestamp"] == "2026-01-01T00:00:00Z"


class TestBuildCarbHistory:
    def test_carb_history_empty(self):
        assert PumpHistoryBuilder.build_carb_history([]) == []

    def test_carb_history_single(self):
        result = PumpHistoryBuilder.build_carb_history([make_carb()])
        assert len(result) == 1
        assert result[0]["_type"] == "Carb"
        assert "carbs" in result[0]
        assert "timestamp" in result[0]

    def test_carb_history_amount(self):
        result = PumpHistoryBuilder.build_carb_history([make_carb(amount_g=75.0)])
        assert result[0]["carbs"] == 75.0
