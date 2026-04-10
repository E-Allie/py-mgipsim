import time

import pytest

from pymgipsim.Controllers.Oref0.glucose_formatter import GlucoseFormatter

BASE_MS = int(time.time() * 1000)


class TestGlucoseFormatter:
    def test_empty_returns_empty(self):
        result = GlucoseFormatter.format([])
        assert result == []

    def test_single_entry_returns_one(self):
        tuples = [(BASE_MS, 100.0)]
        result = GlucoseFormatter.format(tuples)
        assert len(result) == 1

    def test_newest_first(self):
        t0 = BASE_MS
        t1 = BASE_MS + 300_000
        t2 = BASE_MS + 600_000
        tuples = [(t0, 100.0), (t1, 110.0), (t2, 120.0)]
        result = GlucoseFormatter.format(tuples)
        assert result[0]["date"] == t2
        assert result[1]["date"] == t1
        assert result[2]["date"] == t0

    def test_fields_present(self):
        tuples = [(BASE_MS, 100.0)]
        result = GlucoseFormatter.format(tuples)
        entry = result[0]
        assert "date" in entry
        assert "dateString" in entry
        assert "sgv" in entry
        assert "glucose" in entry
        assert "direction" in entry
        assert "type" in entry
        assert "device" in entry

    def test_sgv_value_mgdl(self):
        tuples = [(BASE_MS, 108.0)]
        result = GlucoseFormatter.format(tuples)
        assert result[0]["sgv"] == 108.0

    def test_direction_flat_no_change(self):
        t0 = BASE_MS
        t1 = BASE_MS + 300_000
        tuples = [(t0, 100.0), (t1, 100.0)]
        result = GlucoseFormatter.format(tuples)
        assert result[0]["direction"] == "Flat"

    def test_direction_forty_five_up(self):
        t0 = BASE_MS
        t1 = BASE_MS + 300_000
        tuples = [(t0, 100.0), (t1, 105.0)]
        result = GlucoseFormatter.format(tuples)
        assert result[0]["direction"] == "FortyFiveUp"

    def test_direction_single_up(self):
        t0 = BASE_MS
        t1 = BASE_MS + 300_000
        tuples = [(t0, 100.0), (t1, 110.0)]
        result = GlucoseFormatter.format(tuples)
        assert result[0]["direction"] == "SingleUp"

    def test_direction_double_up(self):
        t0 = BASE_MS
        t1 = BASE_MS + 300_000
        tuples = [(t0, 100.0), (t1, 115.0)]
        result = GlucoseFormatter.format(tuples)
        assert result[0]["direction"] == "DoubleUp"

    def test_direction_forty_five_down(self):
        t0 = BASE_MS
        t1 = BASE_MS + 300_000
        tuples = [(t0, 100.0), (t1, 95.0)]
        result = GlucoseFormatter.format(tuples)
        assert result[0]["direction"] == "FortyFiveDown"

    def test_direction_single_down(self):
        t0 = BASE_MS
        t1 = BASE_MS + 300_000
        tuples = [(t0, 100.0), (t1, 90.0)]
        result = GlucoseFormatter.format(tuples)
        assert result[0]["direction"] == "SingleDown"

    def test_direction_double_down(self):
        t0 = BASE_MS
        t1 = BASE_MS + 300_000
        tuples = [(t0, 100.0), (t1, 85.0)]
        result = GlucoseFormatter.format(tuples)
        assert result[0]["direction"] == "DoubleDown"

    def test_first_entry_direction_flat(self):
        t0 = BASE_MS
        t1 = BASE_MS + 300_000
        tuples = [(t0, 100.0), (t1, 115.0)]
        result = GlucoseFormatter.format(tuples)
        assert result[1]["direction"] == "Flat"

    def test_type_field(self):
        tuples = [(BASE_MS, 100.0)]
        result = GlucoseFormatter.format(tuples)
        assert result[0]["type"] == "sgv"

    def test_device_field(self):
        tuples = [(BASE_MS, 100.0)]
        result = GlucoseFormatter.format(tuples)
        assert result[0]["device"] == "fakecgm"
