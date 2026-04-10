import types
import pytest
from pymgipsim.Controllers.Oref0.profile_builder import ProfileBuilder


def make_demo():
    return types.SimpleNamespace(
        basal=[1.1361426567898003],
        carb_insulin_ratio=[17.5],
        correction_bolus=[27.75762064628288],
        total_daily_basal=[16.893508304187925],
    )


REQUIRED_FIELDS = [
    "sens",
    "carb_ratio",
    "current_basal",
    "dia",
    "max_iob",
    "min_bg",
    "max_bg",
    "target_bg",
    "basalprofile",
    "isfProfile",
    "curve",
    "max_basal",
    "out_units",
    "type",
]


def test_profile_has_required_fields():
    demo = make_demo()
    profile = ProfileBuilder.build_profile(demo, 0)
    for field in REQUIRED_FIELDS:
        assert field in profile, f"Missing required field: {field}"


def test_sens_mapping():
    demo = make_demo()
    profile = ProfileBuilder.build_profile(demo, 0)
    assert profile["sens"] == pytest.approx(27.75762064628288)


def test_carb_ratio_mapping():
    demo = make_demo()
    profile = ProfileBuilder.build_profile(demo, 0)
    assert profile["carb_ratio"] == pytest.approx(17.5)


def test_current_basal_mapping():
    demo = make_demo()
    profile = ProfileBuilder.build_profile(demo, 0)
    assert profile["current_basal"] == pytest.approx(1.1361426567898003)


def test_max_iob():
    demo = make_demo()
    profile = ProfileBuilder.build_profile(demo, 0)
    assert profile["max_iob"] == pytest.approx(16.893508304187925 * 0.3)


def test_max_basal():
    demo = make_demo()
    profile = ProfileBuilder.build_profile(demo, 0)
    assert profile["max_basal"] == pytest.approx(1.1361426567898003 * 4)


def test_dia_fixed():
    demo = make_demo()
    profile = ProfileBuilder.build_profile(demo, 0)
    assert profile["dia"] == 5


def test_curve_fixed():
    demo = make_demo()
    profile = ProfileBuilder.build_profile(demo, 0)
    assert profile["curve"] == "rapid-acting"


def test_basalprofile_structure():
    demo = make_demo()
    profile = ProfileBuilder.build_profile(demo, 0)
    basalprofile = profile["basalprofile"]
    assert isinstance(basalprofile, list)
    assert len(basalprofile) == 1
    entry = basalprofile[0]
    assert "minutes" in entry
    assert "rate" in entry
    assert "start" in entry


def test_basalprofile_rate():
    demo = make_demo()
    profile = ProfileBuilder.build_profile(demo, 0)
    assert profile["basalprofile"][0]["rate"] == pytest.approx(1.1361426567898003)


def test_smb_disabled():
    demo = make_demo()
    profile = ProfileBuilder.build_profile(demo, 0)
    assert profile["enableSMB_always"] is False
    assert profile["enableSMB_with_COB"] is False


def test_target_bg():
    demo = make_demo()
    profile = ProfileBuilder.build_profile(demo, 0)
    assert profile["target_bg"] == 110


class TestFeatureFlags:
    def test_default_smb_disabled(self):
        profile = ProfileBuilder.build_profile(make_demo(), 0)
        assert profile["enableSMB_always"] == False

    def test_default_uam_disabled(self):
        profile = ProfileBuilder.build_profile(make_demo(), 0)
        assert profile["enableUAM"] == False

    def test_enable_smb_sets_smb_always(self):
        profile = ProfileBuilder.build_profile(make_demo(), 0, enable_smb=True)
        assert profile["enableSMB_always"] == True

    def test_enable_smb_does_not_set_other_smb_fields(self):
        profile = ProfileBuilder.build_profile(make_demo(), 0, enable_smb=True)
        assert profile["enableSMB_with_COB"] == False
        assert profile["enableSMB_after_carbs"] == False
        assert profile["enableSMB_with_temptarget"] == False

    def test_enable_uam_sets_uam(self):
        profile = ProfileBuilder.build_profile(make_demo(), 0, enable_uam=True)
        assert profile["enableUAM"] == True

    def test_both_flags_together(self):
        profile = ProfileBuilder.build_profile(make_demo(), 0, enable_smb=True, enable_uam=True)
        assert profile["enableSMB_always"] == True
        assert profile["enableUAM"] == True
