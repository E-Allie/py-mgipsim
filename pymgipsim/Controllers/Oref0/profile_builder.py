"""Maps py-mgipsim demographic_info to oref0 profile format."""


class ProfileBuilder:
    """Builds oref0-compatible profile dict from demographic_info."""

    @staticmethod
    def build_profile(demographic_info, patient_idx: int, *, enable_smb: bool = False, enable_uam: bool = False,
                      overrides: dict | None = None) -> dict:
        basal = demographic_info.basal[patient_idx]
        carb_ratio = demographic_info.carb_insulin_ratio[patient_idx]
        sens = demographic_info.correction_bolus[patient_idx]
        total_daily_basal = demographic_info.total_daily_basal[patient_idx]

        basalprofile = [{"minutes": 0, "rate": basal, "start": "00:00:00", "i": 0}]

        isfProfile = {
            "sensitivities": [
                {"offset": 0, "sensitivity": sens, "endOffset": 1440, "start": "00:00:00", "i": 0, "x": 0}
            ]
        }

        carb_ratios = {
            "schedule": [
                {"offset": 0, "ratio": carb_ratio, "start": "00:00:00", "i": 0, "x": 0}
            ]
        }

        bg_targets = {
            "targets": [
                {"offset": 0, "high": 120, "low": 100, "start": "00:00:00", "i": 0, "x": 0}
            ]
        }

        profile = {
            "sens": sens,
            "carb_ratio": carb_ratio,
            "current_basal": basal,
            "max_daily_basal": basal,
            "max_basal": basal * 4,
            "max_iob": total_daily_basal * 0.3,
            "dia": 5,
            "curve": "rapid-acting",
            "type": "current",
            "out_units": "mg/dL",
            "min_bg": 100,
            "max_bg": 120,
            "target_bg": 110,
            "basalprofile": basalprofile,
            "isfProfile": isfProfile,
            "carb_ratios": carb_ratios,
            "bg_targets": bg_targets,
            "pump_settings": {"insulin_action_curve": 5},
            "max_daily_safety_multiplier": 3,
            "current_basal_safety_multiplier": 4,
            "autosens_max": 1.2,
            "autosens_min": 0.7,
            "skip_neutral_temps": False,
            "enableUAM": enable_uam,
            "enableSMB_with_COB": False,
            "enableSMB_always": enable_smb,
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
            "suspend_zeros_iob": True,
            "bolussnooze_dia_divisor": 2,
        }

        if overrides:
            profile.update(overrides)
            if any(k in overrides for k in ("min_bg", "max_bg")):
                profile["bg_targets"]["targets"][0]["low"] = profile["min_bg"]
                profile["bg_targets"]["targets"][0]["high"] = profile["max_bg"]
            if "sens" in overrides:
                profile["isfProfile"]["sensitivities"][0]["sensitivity"] = profile["sens"]
            if "carb_ratio" in overrides:
                profile["carb_ratios"]["schedule"][0]["ratio"] = profile["carb_ratio"]
            if "dia" in overrides:
                profile["pump_settings"]["insulin_action_curve"] = profile["dia"]

        return profile