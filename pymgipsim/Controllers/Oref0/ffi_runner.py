from __future__ import annotations

import contextlib
import logging
import math
import os
from typing import Any

_logger = logging.getLogger(__name__)


@contextlib.contextmanager
def _suppress_fd2():
    """Redirect OS-level stderr (fd 2) to /dev/null for the duration of the block.

    Rust's eprintln! writes directly to fd 2, bypassing Python's sys.stderr.
    The subprocess path silently discards this output via the pipe; the FFI
    path must suppress it explicitly to avoid flooding the terminal with
    algorithm debug lines on every 5-minute cycle.

    Real error information is returned in result.error (not stderr), so
    suppressing fd 2 does not hide actionable errors.
    """
    devnull_fd = os.open(os.devnull, os.O_WRONLY)
    saved_fd2 = os.dup(2)
    try:
        os.dup2(devnull_fd, 2)
        yield
    finally:
        os.dup2(saved_fd2, 2)
        os.close(saved_fd2)
        os.close(devnull_fd)

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
            if not hasattr(oref0_ffi, "ffi_determine_basal") or not hasattr(oref0_ffi, "ffi_calculate_iob"):
                visible_attrs = sorted(a for a in dir(oref0_ffi) if not a.startswith("_"))[:10]
                raise RuntimeError(
                    f"oref0_ffi wheel is malformed: missing expected functions. "
                    f"Found attributes: {visible_attrs}. "
                    f"Rebuild with: cd oref0-rs/crates/oref0-ffi && maturin develop --release"
                )
            _oref0_ffi = oref0_ffi
        except ImportError as e:
            raise RuntimeError(
                "use_ffi=True requires the oref0_ffi wheel to be installed. "
                "Install with: cd oref0-rs/crates/oref0-ffi && maturin develop --release"
            ) from e
        except (OSError, AttributeError) as e:
            raise RuntimeError(
                f"oref0_ffi wheel appears installed but is broken: {type(e).__name__}: {e}. "
                "Rebuild with: cd oref0-rs/crates/oref0-ffi && maturin develop --release"
            ) from e
    return _oref0_ffi


def _opt_float(v: Any) -> float | None:
    if v is None:
        return None
    f = float(v)
    return None if math.isnan(f) else f


def _opt_int(v: Any) -> int | None:
    return None if v is None else int(v)


def _get_last_glucose(glucose_list: list) -> dict | None:
    """Port of js/lib/glucose-get-last.js - must stay byte-compatible with the JS oracle."""
    data = []
    for obj in glucose_list:
        g = obj.get("glucose") or obj.get("sgv")
        if g:
            entry = dict(obj)
            entry["glucose"] = g
            data.append(entry)

    if not data:
        return None

    now = data[0]
    now_glucose = float(now["glucose"])
    now_date = float(now.get("date") or 0)

    last_deltas: list[float] = []
    short_deltas: list[float] = []
    long_deltas: list[float] = []

    for i in range(1, len(data)):
        entry = data[i]
        if entry.get("type") == "cal":
            break
        g = float(entry.get("glucose") or entry.get("sgv") or 0)
        if g <= 38:
            continue
        if entry.get("device") != now.get("device"):
            continue

        then_date = float(entry.get("date") or 0)
        if now_date == 0 or then_date == 0:
            continue

        minutesago = round((now_date - then_date) / (1000 * 60))
        if minutesago == 0:
            continue

        change = now_glucose - g
        avgdelta = change / minutesago * 5

        if -2 < minutesago < 2.5:
            now_glucose = (now_glucose + g) / 2
            now_date = (now_date + then_date) / 2
        elif 2.5 < minutesago < 17.5:
            short_deltas.append(avgdelta)
            if 2.5 < minutesago < 7.5:
                last_deltas.append(avgdelta)
        elif 17.5 < minutesago < 42.5:
            long_deltas.append(avgdelta)

    last_delta = sum(last_deltas) / len(last_deltas) if last_deltas else 0.0
    short_avgdelta = sum(short_deltas) / len(short_deltas) if short_deltas else 0.0
    long_avgdelta = sum(long_deltas) / len(long_deltas) if long_deltas else 0.0

    return {
        "glucose": round(now_glucose * 100) / 100,
        "date": int(now_date),
        "delta": round(last_delta * 100) / 100,
        "short_avgdelta": round(short_avgdelta * 100) / 100,
        "long_avgdelta": round(long_avgdelta * 100) / 100,
        "noise": now.get("noise"),
        "device": now.get("device"),
    }


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


def _build_iob_data_input(ffi, iob: dict):
    zwt_raw = iob.get("iobWithZeroTemp")
    zwt = _build_iob_with_zero_temp(ffi, zwt_raw) if zwt_raw is not None else None

    lt_raw = iob.get("lastTemp")
    lt = _build_last_temp(ffi, lt_raw) if lt_raw is not None else None

    entry = ffi.FfiIobData(
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
    return ffi.FfiIobDataInput.SINGLE(entry)


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


def _build_profile(ffi, pd: dict):
    basal_entries = []
    for entry in pd.get("basalprofile", []):
        basal_entries.append(ffi.FfiBasalProfileEntry(
            minutes=int(entry.get("minutes", 0)),
            rate=float(entry.get("rate", 0.0)),
            start=str(entry.get("start", "00:00:00")),
            i=int(entry.get("i", 0)),
        ))

    # ProfileBuilder uses "carb_ratios" (snake_case); test vectors use "carbRatios" (camelCase)
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

    isf_profile = None
    isf_raw = pd.get("isfProfile")
    if isf_raw:
        sensitivities = []
        for entry in isf_raw.get("sensitivities", []):
            sensitivities.append(ffi.FfiIsfSensitivity(
                end_offset=_opt_int(entry.get("endOffset")),
                offset=_opt_int(entry.get("offset")),
                x=_opt_int(entry.get("x")),
                sensitivity=float(entry.get("sensitivity", 0.0)),
                start=str(entry.get("start", "00:00:00")),
                i=_opt_int(entry.get("i")),
            ))
        isf_profile = ffi.FfiIsfProfile(
            first=_opt_int(isf_raw.get("first")),
            sensitivities=sensitivities,
            user_preferred_units=isf_raw.get("user_preferred_units"),
            units=isf_raw.get("units"),
        )

    # ProfileBuilder uses "bg_targets" (snake_case); test vectors use "bgTargets" (camelCase)
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


class FfiRunner:
    """Drop-in for SubprocessRunner using in-process oref0_ffi calls instead of subprocesses."""

    def calculate_iob(
        self,
        pump_history: list,
        profile: dict,
        clock: str,
    ) -> dict | None:
        ffi = _get_ffi()
        try:
            inputs = _build_history_inputs(ffi, pump_history, profile, clock)
            with _suppress_fd2():
                entries = ffi.ffi_calculate_iob(inputs=inputs, current_iob_only=False)
            if not entries:
                return None
            return _iob_entry_to_dict(entries[0])
        except Exception as e:
            _logger.warning(
                "FfiRunner.calculate_iob failed: %s: %s. "
                "Returning None.",
                type(e).__name__, e,
            )
            return None

    def determine_basal(
        self,
        iob_data: dict,
        currenttemp: dict,
        glucose: list,
        profile: dict,
        clock: str,
        meal_data: dict | None = None,
        microbolus: bool = False,
        autosens_data: dict | None = None,
    ) -> dict | None:
        ffi = _get_ffi()
        try:
            gs_dict = _get_last_glucose(glucose)
            if gs_dict is None:
                return None

            gs = _build_glucose_status(ffi, gs_dict)
            ct = _build_current_temp(ffi, currenttemp)
            iob = _build_iob_data_input(ffi, iob_data)
            prof = _build_profile(ffi, profile)
            meal = _build_meal_data(ffi, meal_data if meal_data is not None else {})
            autosens = _build_autosens(ffi, autosens_data) if autosens_data else None

            with _suppress_fd2():
                result = ffi.ffi_determine_basal(
                    glucose_status=gs,
                    currenttemp=ct,
                    iob_data=iob,
                    profile=prof,
                    autosens_data=autosens,
                    meal_data=meal,
                    micro_bolus_allowed=microbolus,
                    reservoir_data=None,
                    current_time=clock,
                )
            return _determine_basal_output_to_dict(result)
        except Exception as e:
            _logger.warning(
                "FfiRunner.determine_basal failed: %s: %s. "
                "Returning None.",
                type(e).__name__, e,
            )
            return None

    def cleanup(self) -> None:
        pass
