from __future__ import annotations

import logging
import math
import os
from typing import Any

_logger = logging.getLogger(__name__)


_oref0_ffi = None


def _wheel_available() -> bool:
    try:
        import oref0_ffi  # noqa: F401
        return True
    except ImportError:
        return False


def _get_ffi():
    global _oref0_ffi
    if _oref0_ffi is None:
        try:
            import oref0_ffi
            required = [
                "ffi_determine_basal", "ffi_calculate_iob", "ffi_calculate_meal",
                "ffi_detect_sensitivity", "ffi_autotune_prep", "ffi_autotune_core",
            ]
            missing = [f for f in required if not hasattr(oref0_ffi, f)]
            if missing:
                raise RuntimeError(f"oref0_ffi wheel is missing: {missing}")
            _oref0_ffi = oref0_ffi
        except ImportError as e:
            raise RuntimeError("use_ffi=True but oref0_ffi wheel is not installed") from e
        except (OSError, AttributeError) as e:
            raise RuntimeError(f"oref0_ffi wheel is broken: {e}") from e
    return _oref0_ffi


def _opt_float(v: Any) -> float | None:
    if v is None:
        return None
    f = float(v)
    return None if math.isnan(f) else f


def _opt_int(v: Any) -> int | None:
    return None if v is None else int(v)


def _ffi_get_last_glucose(ffi, glucose_list: list) -> dict | None:
    entries = [_build_glucose_entry(ffi, e) for e in glucose_list]
    result = ffi.ffi_get_last_glucose(entries)
    if result is None:
        return None
    d: dict = {
        "glucose": result.glucose,
        "date": result.date,
        "delta": result.delta,
        "short_avgdelta": result.short_avgdelta,
        "long_avgdelta": result.long_avgdelta,
    }
    if result.noise is not None:
        d["noise"] = result.noise
    if result.device is not None:
        d["device"] = result.device
    return d


def _build_glucose_status(ffi, gs: dict):
    return ffi.FfiGlucoseStatus(
        glucose=float(gs.get("glucose", 0)),
        date=_opt_int(gs.get("date")),
        delta=float(gs.get("delta", 0)),
        short_avgdelta=float(gs.get("short_avgdelta", 0)),
        long_avgdelta=float(gs.get("long_avgdelta", 0)),
        noise=_opt_float(gs.get("noise")),
        last_cal=_opt_int(gs.get("last_cal")),
        device=gs.get("device"),
    )


def _build_current_temp(ffi, ct: dict):
    return ffi.FfiCurrentTemp(
        duration=_opt_float(ct.get("duration")),
        rate=_opt_float(ct.get("rate")),
        temp=ct.get("temp"),
    )


def _build_iob_with_zero_temp(ffi, z: dict):
    return ffi.FfiIobWithZeroTemp(
        iob=float(z.get("iob", 0.0)),
        activity=float(z.get("activity", 0.0)),
        basaliob=float(z.get("basaliob", 0.0)),
        bolusiob=float(z.get("bolusiob", 0.0)),
        netbasalinsulin=_opt_float(z.get("netbasalinsulin")),
        bolusinsulin=_opt_float(z.get("bolusinsulin")),
        time=z.get("time"),
    )


def _build_last_temp(ffi, lt: dict):
    return ffi.FfiLastTemp(
        rate=_opt_float(lt.get("rate")),
        timestamp=lt.get("timestamp"),
        started_at=lt.get("started_at"),
        date=_opt_int(lt.get("date")),
        duration=_opt_float(lt.get("duration")),
    )


def _build_iob_data_entry(ffi, iob: dict):
    zwt_raw = iob.get("iobWithZeroTemp")
    zwt = _build_iob_with_zero_temp(ffi, zwt_raw) if zwt_raw is not None else None

    lt_raw = iob.get("lastTemp")
    lt = _build_last_temp(ffi, lt_raw) if lt_raw is not None else None

    return ffi.FfiIobData(
        iob=_opt_float(iob.get("iob")),
        activity=_opt_float(iob.get("activity")),
        bolussnooze=_opt_float(iob.get("bolussnooze")),
        basaliob=_opt_float(iob.get("basaliob")),
        netbasalinsulin=_opt_float(iob.get("netbasalinsulin")),
        bolusinsulin=_opt_float(iob.get("bolusinsulin")),
        iob_with_zero_temp=zwt,
        last_bolus_time=_opt_int(iob.get("lastBolusTime")),
        last_temp=lt,
        time=iob.get("time"),
    )


def _build_iob_data_input(ffi, iob: dict):
    return ffi.FfiIobDataInput.SINGLE(_build_iob_data_entry(ffi, iob))


def _build_iob_data_array(ffi, iob_list: list):
    return ffi.FfiIobDataInput.ARRAY([_build_iob_data_entry(ffi, e) for e in iob_list])


def _build_meal_data(ffi, meal: dict):
    return ffi.FfiMealData(
        carbs=float(meal.get("carbs", 0)),
        ns_carbs=float(meal.get("nsCarbs", 0)),
        bw_carbs=float(meal.get("bwCarbs", 0)),
        journal_carbs=float(meal.get("journalCarbs", 0)),
        meal_cob=float(meal.get("mealCOB", 0)),
        current_deviation=_opt_float(meal.get("currentDeviation")),
        max_deviation=_opt_float(meal.get("maxDeviation")),
        min_deviation=_opt_float(meal.get("minDeviation")),
        slope_from_max_deviation=_opt_float(meal.get("slopeFromMaxDeviation")),
        slope_from_min_deviation=_opt_float(meal.get("slopeFromMinDeviation")),
        all_deviations=meal.get("allDeviations"),
        last_carb_time=_opt_int(meal.get("lastCarbTime")),
        bw_found=bool(meal.get("bwFound", False)),
        reason=meal.get("reason"),
    )


def _build_autosens(ffi, autosens: dict):
    return ffi.FfiAutosensData(
        ratio=float(autosens.get("ratio", 1.0)),
        reason=autosens.get("reason"),
        newisf=_opt_float(autosens.get("newisf")),
        newbg=_opt_float(autosens.get("newbg")),
        tdd_ratio=_opt_float(autosens.get("tdd_ratio")),
    )


def _build_pump_event(ffi, entry: dict):
    t = entry.get("_type", "")
    ts = str(entry.get("timestamp", ""))

    if t == "TempBasal":
        return ffi.FfiPumpEvent.TEMP_BASAL(
            timestamp=ts,
            rate=_opt_float(entry.get("rate")),
            duration=_opt_float(entry.get("duration")),
            temp=entry.get("temp"),
        )
    if t == "TempBasalDuration":
        return ffi.FfiPumpEvent.TEMP_BASAL_DURATION(
            timestamp=ts,
            duration_min=_opt_float(entry.get("duration (min)")),
        )
    if t == "Bolus":
        return ffi.FfiPumpEvent.BOLUS(
            timestamp=ts,
            amount=_opt_float(entry.get("amount")),
            programmed=_opt_float(entry.get("programmed")),
            unabsorbed=_opt_float(entry.get("unabsorbed")),
            duration=_opt_float(entry.get("duration")),
            bolus_type=entry.get("type"),
        )
    if t == "Carb":
        return ffi.FfiPumpEvent.CARB(
            timestamp=ts,
            carbs=_opt_float(entry.get("carbs")),
            created_at=entry.get("created_at"),
        )
    return ffi.FfiPumpEvent.OTHER()


def _build_basal_entries(ffi, entries: list) -> list:
    return [ffi.FfiBasalProfileEntry(
        minutes=int(e.get("minutes", 0)),
        rate=float(e.get("rate", 0.0)),
        start=str(e.get("start", "00:00:00")),
        i=int(e.get("i", 0)),
    ) for e in entries]


def _build_isf_profile(ffi, isf_raw: dict | None):
    if not isf_raw:
        return None
    sensitivities = [ffi.FfiIsfSensitivity(
        end_offset=_opt_int(s.get("endOffset")),
        offset=_opt_int(s.get("offset")),
        x=_opt_int(s.get("x")),
        sensitivity=float(s.get("sensitivity", 0.0)),
        start=str(s.get("start", "00:00:00")),
        i=_opt_int(s.get("i")),
    ) for s in isf_raw.get("sensitivities", [])]
    return ffi.FfiIsfProfile(
        first=_opt_int(isf_raw.get("first")),
        sensitivities=sensitivities,
        user_preferred_units=isf_raw.get("user_preferred_units"),
        units=isf_raw.get("units"),
    )


def _build_profile(ffi, pd: dict):
    basal_entries = _build_basal_entries(ffi, pd.get("basalprofile", []))

    carb_ratios = None
    cr_raw = pd.get("carb_ratios") or pd.get("carbRatios")
    if cr_raw:
        schedule = []
        for entry in cr_raw.get("schedule", []):
            schedule.append(ffi.FfiCarbRatioEntry(
                x=_opt_int(entry.get("x")),
                i=_opt_int(entry.get("i")),
                offset=_opt_int(entry.get("offset")),
                ratio=float(entry.get("ratio", 0.0)),
                r=_opt_float(entry.get("r")),
                start=str(entry.get("start", "00:00:00")),
            ))
        carb_ratios = ffi.FfiCarbRatios(
            schedule=schedule,
            units=cr_raw.get("units"),
        )

    isf_profile = _build_isf_profile(ffi, pd.get("isfProfile"))
    bg_targets = None
    bt_raw = pd.get("bg_targets") or pd.get("bgTargets")
    if bt_raw:
        targets = []
        for entry in bt_raw.get("targets", []):
            targets.append(ffi.FfiBgTarget(
                max_bg=_opt_float(entry.get("max_bg")),
                min_bg=_opt_float(entry.get("min_bg")),
                x=_opt_int(entry.get("x")),
                offset=_opt_int(entry.get("offset")),
                low=_opt_float(entry.get("low")),
                start=str(entry.get("start", "00:00:00")),
                high=_opt_float(entry.get("high")),
                i=_opt_int(entry.get("i")),
                temptarget_set=entry.get("temptarget_set"),
            ))
        bg_targets = ffi.FfiBgTargets(
            first=_opt_int(bt_raw.get("first")),
            targets=targets,
            user_preferred_units=bt_raw.get("user_preferred_units"),
            units=bt_raw.get("units"),
        )

    model_val = pd.get("model")
    if model_val is not None and not isinstance(model_val, str):
        model_val = str(model_val)

    target_bg_val = pd.get("target_bg")
    if target_bg_val is False:
        target_bg_val = None

    return ffi.FfiProfile(
        model=model_val,
        carb_ratios=carb_ratios,
        carb_ratio=float(pd.get("carb_ratio", 10.0)),
        isf_profile=isf_profile,
        sens=float(pd.get("sens", 40.0)),
        bg_targets=bg_targets,
        max_bg=float(pd.get("max_bg", 120.0)),
        min_bg=float(pd.get("min_bg", 110.0)),
        target_bg=_opt_float(target_bg_val),
        out_units=pd.get("out_units"),
        max_basal=float(pd.get("max_basal", 3.5)),
        min_5m_carbimpact=float(pd.get("min_5m_carbimpact", 8.0)),
        max_cob=float(pd.get("maxCOB", pd.get("max_cob", 120.0))),
        max_iob=float(pd.get("max_iob", 2.5)),
        max_daily_safety_multiplier=float(pd.get("max_daily_safety_multiplier", 3.0)),
        current_basal_safety_multiplier=float(pd.get("current_basal_safety_multiplier", 4.0)),
        autosens_max=float(pd.get("autosens_max", 1.2)),
        autosens_min=float(pd.get("autosens_min", 0.7)),
        remaining_carbs_cap=float(pd.get("remainingCarbsCap", pd.get("remaining_carbs_cap", 90.0))),
        enable_uam=bool(pd.get("enableUAM", True)),
        enable_smb_with_bolus=bool(pd.get("enableSMB_with_bolus", False)),
        enable_smb_with_cob=bool(pd.get("enableSMB_with_COB", False)),
        enable_smb_with_temptarget=bool(pd.get("enableSMB_with_temptarget", False)),
        enable_smb_after_carbs=bool(pd.get("enableSMB_after_carbs", False)),
        enable_smb_always=bool(pd.get("enableSMB_always", False)),
        enable_smb_high_bg=bool(pd.get("enableSMB_high_bg", False)),
        enable_smb_high_bg_target=_opt_float(pd.get("enableSMB_high_bg_target")),
        allow_smb_with_high_temptarget=bool(pd.get("allowSMB_with_high_temptarget", False)),
        prime_indicates_pump_site_change=bool(pd.get("prime_indicates_pump_site_change", False)),
        rewind_indicates_cartridge_change=bool(pd.get("rewind_indicates_cartridge_change", False)),
        battery_indicates_battery_change=bool(pd.get("battery_indicates_battery_change", False)),
        max_smb_basal_minutes=float(pd.get("maxSMBBasalMinutes", 30.0)),
        max_uam_smb_basal_minutes=_opt_float(pd.get("maxUAMSMBBasalMinutes")),
        curve=str(pd.get("curve", "")),
        use_custom_peak_time=bool(pd.get("useCustomPeakTime", False)),
        insulin_peak_time=float(pd.get("insulinPeakTime", 75.0)),
        dia=float(pd.get("dia", 3.0)),
        current_basal=float(pd.get("current_basal", 0.9)),
        basalprofile=basal_entries,
        max_daily_basal=float(pd.get("max_daily_basal", 1.3)),
        rewind_resets_autosens=bool(pd.get("rewind_resets_autosens", False)),
        high_temptarget_raises_sensitivity=bool(pd.get("high_temptarget_raises_sensitivity", False)),
        low_temptarget_lowers_sensitivity=bool(pd.get("low_temptarget_lowers_sensitivity", False)),
        sensitivity_raises_target=bool(pd.get("sensitivity_raises_target", True)),
        resistance_lowers_target=bool(pd.get("resistance_lowers_target", False)),
        exercise_mode=bool(pd.get("exercise_mode", False)),
        half_basal_exercise_target=_opt_float(pd.get("half_basal_exercise_target")),
        skip_neutral_temps=bool(pd.get("skip_neutral_temps", False)),
        unsuspend_if_no_temp=bool(pd.get("unsuspend_if_no_temp", False)),
        bolussnooze_dia_divisor=_opt_float(pd.get("bolussnooze_dia_divisor")),
        autotune_isf_adjustment_fraction=_opt_float(pd.get("autotune_isf_adjustmentFraction")),
        remaining_carbs_fraction=_opt_float(pd.get("remainingCarbsFraction")),
        a52_risk_enable=bool(pd.get("A52_risk_enable", False)),
        smb_interval=_opt_float(pd.get("SMBInterval")),
        bolus_increment=_opt_float(pd.get("bolus_increment")),
        max_delta_bg_threshold=_opt_float(pd.get("maxDelta_bg_threshold")),
        carbs_req_threshold=_opt_float(pd.get("carbsReqThreshold")),
        offline_hotspot=bool(pd.get("offline_hotspot", False)),
        noisy_cgm_target_multiplier=_opt_float(pd.get("noisyCGMTargetMultiplier")),
        suspend_zeros_iob=bool(pd.get("suspend_zeros_iob", True)),
        enable_enlite_bgproxy=bool(pd.get("enable_enlite_bgproxy", False)),
        calc_glucose_noise=bool(pd.get("calc_glucose_noise", False)),
        temptarget_set=pd.get("temptargetSet"),
        edison_battery_shutdown_voltage=_opt_int(pd.get("edison_battery_shutdown_voltage")),
        pi_battery_shutdown_percent=_opt_int(pd.get("pi_battery_shutdown_percent")),
    )


def _build_history_inputs(ffi, pump_history: list, profile: dict, clock: str):
    events = [_build_pump_event(ffi, e) for e in pump_history]
    profile_ffi = _build_profile(ffi, profile) if profile else None
    return ffi.FfiHistoryInputs(
        history=events,
        history24=None,
        profile=profile_ffi,
        clock=clock,
        autosens=None,
    )


def _iob_with_zero_temp_to_dict(z) -> dict:
    d: dict = {
        "iob": z.iob,
        "activity": z.activity,
        "basaliob": z.basaliob,
        "bolusiob": z.bolusiob,
    }
    if z.netbasalinsulin is not None:
        d["netbasalinsulin"] = z.netbasalinsulin
    if z.bolusinsulin is not None:
        d["bolusinsulin"] = z.bolusinsulin
    if z.time is not None:
        d["time"] = z.time
    return d


def _last_temp_to_dict(lt) -> dict:
    d: dict = {}
    if lt.rate is not None:
        d["rate"] = lt.rate
    if lt.timestamp is not None:
        d["timestamp"] = lt.timestamp
    if lt.started_at is not None:
        d["started_at"] = lt.started_at
    if lt.date is not None:
        d["date"] = lt.date
    if lt.duration is not None:
        d["duration"] = lt.duration
    return d


def _iob_entry_to_dict(entry) -> dict:
    d: dict = {
        "iob": entry.iob,
        "activity": entry.activity,
        "basaliob": entry.basaliob,
        "bolusiob": entry.bolusiob,
    }
    if entry.netbasalinsulin is not None:
        d["netbasalinsulin"] = entry.netbasalinsulin
    if entry.bolusinsulin is not None:
        d["bolusinsulin"] = entry.bolusinsulin
    if entry.time is not None:
        d["time"] = entry.time
    if entry.last_bolus_time is not None:
        d["lastBolusTime"] = entry.last_bolus_time
    if entry.iob_with_zero_temp is not None:
        d["iobWithZeroTemp"] = _iob_with_zero_temp_to_dict(entry.iob_with_zero_temp)
    if entry.last_temp is not None:
        d["lastTemp"] = _last_temp_to_dict(entry.last_temp)
    return d


_DB_SCALAR_FIELDS = [
    ("temp", "temp"),
    ("bg", "bg"),
    ("tick", "tick"),
    ("eventual_bg", "eventualBG"),
    ("insulin_req", "insulinReq"),
    ("reservoir", "reservoir"),
    ("deliver_at", "deliverAt"),
    ("sensitivity_ratio", "sensitivityRatio"),
    ("cob", "COB"),
    ("iob", "IOB"),
    ("reason", "reason"),
    ("rate", "rate"),
    ("duration", "duration"),
    ("error", "error"),
    ("bgi", "BGI"),
    ("isf", "ISF"),
    ("cr", "CR"),
    ("deviation", "deviation"),
    ("meal_assist", "mealAssist"),
    ("carbs_req", "carbsReq"),
    ("naive_eventual_bg", "naiveEventualBG"),
    ("min_pred_bg", "minPredBG"),
    ("min_guard_bg", "minGuardBG"),
    ("sensitive_slope", "sensitiveSlope"),
    ("snooze_bg", "snoozeBG"),
    ("target", "Target"),
    ("smb_insulin_req", "SMBInsulinReq"),
    ("bolus_insulin_req", "bolusInsulinReq"),
    ("units", "units"),
    ("target_bg", "target_bg"),
]


def _determine_basal_output_to_dict(result) -> dict:
    d: dict = {}
    for attr, key in _DB_SCALAR_FIELDS:
        val = getattr(result, attr, None)
        if val is not None:
            d[key] = val
    if "reason" not in d:
        d["reason"] = ""
    if result.pred_bgs is not None:
        pb = result.pred_bgs
        pbd: dict = {}
        if pb.iob is not None:
            pbd["IOB"] = pb.iob
        if pb.zt is not None:
            pbd["ZT"] = pb.zt
        if pb.cob is not None:
            pbd["COB"] = pb.cob
        if pb.uam is not None:
            pbd["UAM"] = pb.uam
        if pbd:
            d["predBGs"] = pbd
    return d


def _build_glucose_entry(ffi, entry: dict):
    return ffi.FfiGlucoseEntry(
        date=int(entry.get("date", 0)),
        date_string=entry.get("dateString"),
        sgv=_opt_float(entry.get("sgv")),
        device=entry.get("device"),
        entry_type=entry.get("type"),
        glucose=_opt_float(entry.get("glucose")),
        noise=_opt_float(entry.get("noise")),
        direction=entry.get("direction"),
        filtered=_opt_float(entry.get("filtered")),
        unfiltered=_opt_float(entry.get("unfiltered")),
        rssi=_opt_float(entry.get("rssi")),
        raw=_opt_float(entry.get("raw")),
        from_raw=entry.get("fromRaw"),
        display_time=entry.get("display_time"),
        mbg=_opt_float(entry.get("mbg")),
    )


def _build_carb_entry(ffi, entry: dict):
    return ffi.FfiCarbEntry(
        carbs=_opt_float(entry.get("carbs")),
        created_at=entry.get("created_at"),
        entered_by=entry.get("enteredBy"),
    )


def _build_temp_target(ffi, entry: dict):
    return ffi.FfiTempTarget(
        created_at=entry.get("created_at"),
        duration=_opt_float(entry.get("duration")),
        target_bottom=_opt_float(entry.get("targetBottom")),
        target_top=_opt_float(entry.get("targetTop")),
    )


def _build_autotune_profile(ffi, p: dict):
    return ffi.FfiAutotuneProfile(
        dia=float(p.get("dia", 0.0)),
        curve=str(p.get("curve", "")),
        use_custom_peak_time=bool(p.get("useCustomPeakTime", False)),
        insulin_peak_time=float(p.get("insulinPeakTime", 75.0)),
        carb_ratio=float(p.get("carb_ratio", 0.0)),
        basalprofile=_build_basal_entries(ffi, p.get("basalprofile", [])),
        isf_profile=_build_isf_profile(ffi, p.get("isfProfile")),
        autosens_max=_opt_float(p.get("autosens_max")),
        autosens_min=_opt_float(p.get("autosens_min")),
        autotune_isf_adjustment_fraction=_opt_float(p.get("autotune_isf_adjustmentFraction")),
        min_5m_carbimpact=float(p.get("min_5m_carbimpact", 0.0)),
        sens=_opt_float(p.get("sens")),
        csf=_opt_float(p.get("csf")),
    )


def _meal_total_result_to_dict(result) -> dict:
    return {
        "carbs": result.carbs,
        "nsCarbs": result.ns_carbs,
        "bwCarbs": result.bw_carbs,
        "journalCarbs": result.journal_carbs,
        "mealCOB": result.meal_cob,
        "currentDeviation": result.current_deviation,
        "maxDeviation": result.max_deviation,
        "minDeviation": result.min_deviation,
        "slopeFromMaxDeviation": result.slope_from_max_deviation,
        "slopeFromMinDeviation": result.slope_from_min_deviation,
        "allDeviations": result.all_deviations,
        "lastCarbTime": result.last_carb_time,
        "bwFound": result.bw_found,
    }


def _autosens_result_to_dict(result) -> dict:
    return {"ratio": result.ratio, "newisf": result.newisf}


def _autotune_output_to_dict(result) -> dict:
    basalprofile = []
    for entry in result.basalprofile:
        d = {
            "minutes": entry.minutes,
            "rate": entry.rate,
            "start": entry.start,
            "i": entry.i,
        }
        if entry.untuned is not None:
            d["untuned"] = entry.untuned
        basalprofile.append(d)

    isf_profile = {
        "sensitivities": [
            {"sensitivity": s.sensitivity, "start": s.start}
            for s in result.isf_profile.sensitivities
        ],
    }
    if result.isf_profile.units is not None:
        isf_profile["units"] = result.isf_profile.units

    return {
        "dia": result.dia,
        "curve": result.curve,
        "useCustomPeakTime": result.use_custom_peak_time,
        "insulinPeakTime": result.insulin_peak_time,
        "carb_ratio": result.carb_ratio,
        "basalprofile": basalprofile,
        "isfProfile": isf_profile,
        "sens": result.sens,
        "csf": result.csf,
    }


class FfiRunner:

    def __init__(self):
        self._ffi = _get_ffi()
        self._session = None
        self._pushed_history_len: int = 0
        self._glucose_initialized: bool = False
        self._glucose_maxlen: int = 288
        # Cached fds for suppressing Rust eprintln! during FFI calls.
        self._devnull_fd: int = os.open(os.devnull, os.O_WRONLY)
        self._real_fd2: int = os.dup(2)

    def update_profile(self, profile: dict) -> None:
        if self._session is not None:
            self._session.update_profile(_build_profile(self._ffi, profile))

    def run_cycle(
        self,
        pump_history: list,
        glucose: list,
        carb_history: list | None,
        profile: dict,
        clock: str,
        currenttemp: dict,
        basalprofile: list,
        microbolus: bool,
        enable_autosens: bool,
        enable_meal: bool,
    ) -> dict:
        ffi = self._ffi

        if self._session is None:
            self._session = ffi.FfiSession(
                _build_profile(ffi, profile),
                _build_basal_entries(ffi, basalprofile),
            )

        # Push only new events (pump_history is newest-first).
        new_count = len(pump_history) - self._pushed_history_len
        if new_count > 0:
            self._session.push_pump_events(
                [_build_pump_event(ffi, e) for e in pump_history[:new_count]]
            )
            self._pushed_history_len = len(pump_history)

        # First call sends full history; subsequent calls push 1 new reading.
        if self._glucose_initialized:
            if glucose:
                self._session.push_glucose(
                    _build_glucose_entry(ffi, glucose[0]), self._glucose_maxlen,
                )
        elif glucose:
            self._session.set_glucose(
                [_build_glucose_entry(ffi, e) for e in glucose]
            )
            self._glucose_initialized = True

        # Carb history: small list, full replace each cycle.
        if carb_history:
            self._session.set_carb_history(
                [_build_carb_entry(ffi, e) for e in carb_history]
            )

        # Suppress Rust eprintln! during the call.
        suppress = self._devnull_fd >= 0 and self._real_fd2 >= 0
        if suppress:
            os.dup2(self._devnull_fd, 2)
        try:
            result = self._session.run_cycle(
                clock=clock,
                currenttemp=_build_current_temp(ffi, currenttemp),
                microbolus=microbolus,
                run_autosens=enable_autosens,
                run_meal=enable_meal,
            )
        finally:
            if suppress:
                os.dup2(self._real_fd2, 2)

        return {
            'iob': _iob_entry_to_dict(result.iob) if result.iob else {
                "iob": 0.0, "activity": 0.0, "bolussnooze": 0.0,
            },
            'meal': _meal_total_result_to_dict(result.meal) if result.meal else None,
            'autosens': _autosens_result_to_dict(result.autosens) if result.autosens else None,
            'basal': _determine_basal_output_to_dict(result.basal) if result.basal else None,
        }

    def _call_ffi(self, fn, **kwargs):
        suppress = self._devnull_fd >= 0 and self._real_fd2 >= 0
        if suppress:
            os.dup2(self._devnull_fd, 2)
        try:
            return fn(**kwargs)
        finally:
            if suppress:
                os.dup2(self._real_fd2, 2)

    def calculate_iob(
        self,
        pump_history: list,
        profile: dict,
        clock: str,
    ) -> list | None:
        ffi = self._ffi
        try:
            inputs = _build_history_inputs(ffi, pump_history, profile, clock)
            entries = self._call_ffi(ffi.ffi_calculate_iob, inputs=inputs, current_iob_only=False)
            if not entries:
                return None
            return [_iob_entry_to_dict(e) for e in entries]
        except Exception as e:
            _logger.warning("FfiRunner.calculate_iob failed: %s: %s", type(e).__name__, e)
            return None

    def determine_basal(
        self,
        iob_data: list,
        currenttemp: dict,
        glucose: list,
        profile: dict,
        clock: str,
        meal_data: dict | None = None,
        microbolus: bool = False,
        autosens_data: dict | None = None,
    ) -> dict | None:
        ffi = self._ffi
        try:
            gs_dict = _ffi_get_last_glucose(ffi, glucose)
            if gs_dict is None:
                return None

            result = self._call_ffi(
                ffi.ffi_determine_basal,
                glucose_status=_build_glucose_status(ffi, gs_dict),
                currenttemp=_build_current_temp(ffi, currenttemp),
                iob_data=_build_iob_data_array(ffi, iob_data),
                profile=_build_profile(ffi, profile),
                autosens_data=_build_autosens(ffi, autosens_data) if autosens_data else None,
                meal_data=_build_meal_data(ffi, meal_data if meal_data is not None else {}),
                micro_bolus_allowed=microbolus,
                reservoir_data=None,
                current_time=clock,
            )
            return _determine_basal_output_to_dict(result)
        except Exception as e:
            _logger.warning("FfiRunner.determine_basal failed: %s: %s", type(e).__name__, e)
            return None

    def calculate_meal(
        self,
        pump_history: list,
        profile: dict,
        clock: str,
        glucose: list,
        basalprofile: list,
        carb_history: list | None = None,
    ) -> dict | None:
        ffi = self._ffi
        try:
            result = self._call_ffi(
                ffi.ffi_calculate_meal,
                history=[_build_pump_event(ffi, e) for e in pump_history],
                carbs=[_build_carb_entry(ffi, e) for e in (carb_history or [])],
                clock=clock,
                profile=_build_profile(ffi, profile),
                glucose=[_build_glucose_entry(ffi, e) for e in glucose],
                basalprofile=_build_basal_entries(ffi, basalprofile),
            )
            return _meal_total_result_to_dict(result)
        except Exception as e:
            _logger.warning("FfiRunner.calculate_meal failed: %s: %s", type(e).__name__, e)
            return None

    def detect_sensitivity(
        self,
        glucose: list,
        pump_history: list,
        isf: dict,
        basalprofile: list,
        profile: dict,
        carb_history: list | None = None,
    ) -> dict | None:
        ffi = self._ffi
        try:
            clock = glucose[0].get("dateString", "") if glucose else ""
            result = self._call_ffi(
                ffi.ffi_detect_sensitivity,
                glucose=[_build_glucose_entry(ffi, e) for e in glucose],
                history_inputs=_build_history_inputs(ffi, pump_history, profile, clock),
                basalprofile=_build_basal_entries(ffi, basalprofile),
                carbs=[_build_carb_entry(ffi, e) for e in (carb_history or [])],
                temptargets=[],
                retrospective=True,
                deviations=None,
            )
            if result is None:
                return {"ratio": 1}
            return _autosens_result_to_dict(result)
        except Exception as e:
            _logger.warning("FfiRunner.detect_sensitivity failed: %s: %s", type(e).__name__, e)
            return None

    def autotune_prep(
        self,
        pump_history: list,
        profile: dict,
        glucose: list,
        pumpprofile: dict,
        carb_history: list | None = None,
    ) -> dict | None:
        import json
        ffi = self._ffi
        try:
            json_str = self._call_ffi(
                ffi.ffi_autotune_prep,
                history=[_build_pump_event(ffi, e) for e in pump_history],
                carbs=[_build_carb_entry(ffi, e) for e in (carb_history or [])],
                profile=_build_profile(ffi, profile),
                pumpprofile=_build_profile(ffi, pumpprofile),
                glucose=[_build_glucose_entry(ffi, e) for e in glucose],
                categorize_uam_as_basal=None,
                tune_insulin_curve=None,
            )
            return json.loads(json_str)
        except Exception as e:
            _logger.warning("FfiRunner.autotune_prep failed: %s: %s", type(e).__name__, e)
            return None

    def autotune_core(
        self,
        prepped_glucose: dict,
        previous_autotune: dict,
        pumpprofile: dict,
    ) -> dict | None:
        import json
        ffi = self._ffi
        try:
            result = self._call_ffi(
                ffi.ffi_autotune_core,
                prepped_glucose_json=json.dumps(prepped_glucose),
                previous_autotune=_build_autotune_profile(ffi, previous_autotune),
                pump_profile=_build_autotune_profile(ffi, pumpprofile),
            )
            if result is None:
                return None
            return _autotune_output_to_dict(result)
        except Exception as e:
            _logger.warning("FfiRunner.autotune_core failed: %s: %s", type(e).__name__, e)
            return None

    def cleanup(self) -> None:
        if self._devnull_fd >= 0:
            os.close(self._devnull_fd)
            self._devnull_fd = -1
        if self._real_fd2 >= 0:
            os.close(self._real_fd2)
            self._real_fd2 = -1

    def __del__(self):
        self.cleanup()
