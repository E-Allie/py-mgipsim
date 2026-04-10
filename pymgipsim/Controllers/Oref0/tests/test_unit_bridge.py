import pytest

from pymgipsim.Controllers.Oref0.unit_bridge import UnitBridge


class TestUnitBridgeGlucose:
    def test_mmol_to_mgdl(self):
        assert UnitBridge.mmol_to_mgdl(5.5) == pytest.approx(99.0)

    def test_mgdl_to_mmol(self):
        assert UnitBridge.mgdl_to_mmol(99.0) == pytest.approx(5.5)

    def test_glucose_roundtrip_3_0(self):
        x = 3.0
        assert UnitBridge.mgdl_to_mmol(UnitBridge.mmol_to_mgdl(x)) == pytest.approx(x, abs=1e-10)

    def test_glucose_roundtrip_5_5(self):
        x = 5.5
        assert UnitBridge.mgdl_to_mmol(UnitBridge.mmol_to_mgdl(x)) == pytest.approx(x, abs=1e-10)

    def test_glucose_roundtrip_10_0(self):
        x = 10.0
        assert UnitBridge.mgdl_to_mmol(UnitBridge.mmol_to_mgdl(x)) == pytest.approx(x, abs=1e-10)

    def test_glucose_roundtrip_20_0(self):
        x = 20.0
        assert UnitBridge.mgdl_to_mmol(UnitBridge.mmol_to_mgdl(x)) == pytest.approx(x, abs=1e-10)


class TestUnitBridgeInsulin:
    def test_Uhr_to_mUmin(self):
        assert UnitBridge.Uhr_to_mUmin(1.0) == pytest.approx(1000.0 / 60.0)

    def test_mUmin_to_Uhr(self):
        assert UnitBridge.mUmin_to_Uhr(1000.0 / 60.0) == pytest.approx(1.0)

    def test_insulin_roundtrip_0_5(self):
        x = 0.5
        assert UnitBridge.mUmin_to_Uhr(UnitBridge.Uhr_to_mUmin(x)) == pytest.approx(x, abs=1e-10)

    def test_insulin_roundtrip_1_0(self):
        x = 1.0
        assert UnitBridge.mUmin_to_Uhr(UnitBridge.Uhr_to_mUmin(x)) == pytest.approx(x, abs=1e-10)

    def test_insulin_roundtrip_2_5(self):
        x = 2.5
        assert UnitBridge.mUmin_to_Uhr(UnitBridge.Uhr_to_mUmin(x)) == pytest.approx(x, abs=1e-10)


class TestUnitBridgeCarbs:
    def test_g_to_mmol(self):
        assert UnitBridge.g_to_mmol(18.0156) == pytest.approx(100.0, abs=1e-6)

    def test_mmol_to_g(self):
        assert UnitBridge.mmol_to_g(100.0) == pytest.approx(18.0156, abs=1e-3)