import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path


from datetime import datetime, timezone
from functools import lru_cache

@lru_cache(maxsize=1)
def _find_node() -> str:
    found = shutil.which("node")
    if found:
        return found
    return "node"


@lru_cache(maxsize=1)
def _find_libfaketime() -> str | None:
    path = os.environ.get("LIBFAKETIME_PATH")
    if path and os.path.isfile(path):
        return path
    ft = shutil.which("faketime")
    if ft:
        lib_dir = os.path.join(os.path.dirname(os.path.dirname(ft)), "lib")
        for name in ("libfaketime.so.1", "libfaketime.so"):
            p = os.path.join(lib_dir, name)
            if os.path.isfile(p):
                return p
    return None


class SubprocessRunner:
    """Runs oref0 CLI binaries via subprocess (or FFI). Returns None on any failure."""

    def __init__(self, backend: str = "rust", oref0_path: Path | None = None,
                 use_ffi: bool = False):
        self.backend = backend
        self.use_ffi = use_ffi
        self._ffi_runner = None
        self._ffi_runner_lock = threading.Lock()
        if oref0_path is not None:
            self.oref0_path = Path(oref0_path)
        elif backend == "rust":
            self.oref0_path = Path(os.environ["OREF0_RS_BIN_DIR"])
        else:
            self.oref0_path = Path(os.environ["OREF0_JS_BIN_DIR"])
        self.tmpdir = tempfile.mkdtemp(prefix="oref0_sim_")
        # SMB requires autotune/ directory to exist in CWD when determine-basal runs.
        # determine_basal.rs:81 checks Path::new("autotune").exists() and silently
        # disables all microboluses if missing.
        os.makedirs(os.path.join(self.tmpdir, "autotune"), exist_ok=True)

        self.subprocess_seconds: dict[str, list[float]] = {}
        self._faketime_lib = _find_libfaketime()
        self._sim_clock: str | None = None

    def _ensure_ffi_runner(self):
        if self._ffi_runner is None:
            with self._ffi_runner_lock:
                if self._ffi_runner is None:
                    from pymgipsim.Controllers.Oref0.ffi_runner import FfiRunner
                    self._ffi_runner = FfiRunner()
        return self._ffi_runner

    def update_profile(self, profile: dict) -> None:
        if self.use_ffi and self._ffi_runner is not None:
            self._ffi_runner.update_profile(profile)

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
        isf: dict | None = None,
    ) -> dict:
        """Run one full oref0 cycle (iob + meal + autosens + determine_basal)."""
        if self.use_ffi:
            return self._ensure_ffi_runner().run_cycle(
                pump_history, glucose, carb_history, profile, clock,
                currenttemp, basalprofile, microbolus, enable_autosens, enable_meal,
            )

        # Pin wall-clock for all subprocess calls in this cycle
        self._sim_clock = clock

        # Individual subprocess fallback
        iob = self.calculate_iob(pump_history, profile, clock)
        if iob is None:
            iob = [{"iob": 0.0, "activity": 0.0, "bolussnooze": 0.0}]

        meal_data = None
        if enable_meal:
            meal_data = self.calculate_meal(
                pump_history, profile, clock, glucose, basalprofile,
                carb_history or None,
            )

        autosens_data = None
        if enable_autosens:
            if isf is None:
                isf = dict(profile.get("isfProfile", {}))
                if "units" not in isf:
                    isf["units"] = "mg/dL"
            autosens_result = self.detect_sensitivity(
                glucose, pump_history, isf, basalprofile, profile,
                carb_history or None,
            )
            autosens_data = autosens_result if autosens_result is not None else {"ratio": 1.0}

        result = self.determine_basal(
            iob, currenttemp, glucose, profile, clock,
            meal_data=meal_data, microbolus=microbolus,
            autosens_data=autosens_data,
        )

        return {
            'iob': iob, 'meal': meal_data,
            'autosens': autosens_data, 'basal': result,
        }

    def _write_json(self, filename: str, data) -> str:
        path = os.path.join(self.tmpdir, filename)
        with open(path, "w") as f:
            json.dump(data, f)
        return path

    def _run_binary(self, binary_name: str, args: list[str]) -> dict | list | None:
        # Both backends run from tmpdir so autotune/ directory is found by
        # determine-basal (fs.existsSync("autotune") / Path::new("autotune").exists()).
        cwd = self.tmpdir
        if self.backend == "rust":
            cmd = [str(self.oref0_path / binary_name)] + args
        else:
            # JS bins do `require(process.cwd() + '/' + arg)` to read input files,
            # so args must be bare filenames (not absolute paths) when cwd=tmpdir.
            bare_args = [os.path.basename(a) if a.startswith(self.tmpdir) else a
                         for a in args]
            cmd = [_find_node(), str(self.oref0_path / f"{binary_name}.js")] + bare_args
        env = None
        if self._faketime_lib and self._sim_clock:
            utc_dt = datetime.fromisoformat(self._sim_clock.replace("Z", "+00:00"))
            local_dt = utc_dt.astimezone()
            env = os.environ.copy()
            env["LD_PRELOAD"] = self._faketime_lib
            env["FAKETIME"] = local_dt.strftime("%Y-%m-%d %H:%M:%S")

        start = time.perf_counter()
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
                cwd=cwd,
                env=env,
            )
            if result.returncode != 0:
                return None
            parsed = json.loads(result.stdout)
            return parsed
        except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError, OSError):
            return None
        finally:
            self.subprocess_seconds.setdefault(binary_name, []).append(
                time.perf_counter() - start
            )

    def calculate_iob(self, pump_history: list, profile: dict, clock: str) -> list | None:
        """Run oref0-calculate-iob. Returns the full IOB array (current snapshot
        + 5-min projections for determine_basal), or None on failure."""
        if self.use_ffi:
            return self._ensure_ffi_runner().calculate_iob(pump_history, profile, clock)
        self._sim_clock = clock
        ph_path = self._write_json("pumphistory.json", pump_history)
        profile_path = self._write_json("profile.json", profile)
        clock_path = self._write_json("clock.json", clock)

        result = self._run_binary("oref0-calculate-iob", [ph_path, profile_path, clock_path])
        if result is None:
            return None
        if isinstance(result, list) and len(result) > 0:
            return result
        if isinstance(result, dict):
            return [result]
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
        """Run oref0-determine-basal. Returns dict with rate/duration/reason, or None on failure."""
        if self.use_ffi:
            return self._ensure_ffi_runner().determine_basal(
                iob_data, currenttemp, glucose, profile, clock,
                meal_data=meal_data, microbolus=microbolus, autosens_data=autosens_data,
            )
        self._sim_clock = clock
        iob_path = self._write_json("iob.json", iob_data)
        temp_path = self._write_json("currenttemp.json", currenttemp)
        glucose_path = self._write_json("glucose.json", glucose)
        profile_path = self._write_json("profile.json", profile)

        args = [iob_path, temp_path, glucose_path, profile_path, "--currentTime", clock]

        if meal_data is not None:
            meal_path = self._write_json("meal.json", meal_data)
            args += ["--meal", meal_path]

        if autosens_data is not None:
            autosens_path = self._write_json("autosens.json", autosens_data)
            args += ["--auto-sens", autosens_path]

        if microbolus:
            args.append("--microbolus")

        result = self._run_binary("oref0-determine-basal", args)
        if isinstance(result, dict):
            return result
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
        """Run oref0-meal. Returns dict with mealCOB/carbs/reason, or None on failure."""
        if self.use_ffi:
            return self._ensure_ffi_runner().calculate_meal(
                pump_history, profile, clock, glucose, basalprofile, carb_history,
            )
        self._sim_clock = clock
        ph_path = self._write_json("pumphistory_meal.json", pump_history)
        profile_path = self._write_json("profile_meal.json", profile)
        clock_path = self._write_json("clock_meal.json", clock)
        glucose_path = self._write_json("glucose_meal.json", glucose)
        basalprofile_path = self._write_json("basalprofile_meal.json", basalprofile)

        args = [ph_path, profile_path, clock_path, glucose_path, basalprofile_path]

        if carb_history is not None:
            carb_path = self._write_json("carbhistory.json", carb_history)
            args.append(carb_path)

        result = self._run_binary("oref0-meal", args)
        if isinstance(result, dict):
            return result
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
        """Run oref0-detect-sensitivity. Returns dict with ratio, or None on failure."""
        if self.use_ffi:
            return self._ensure_ffi_runner().detect_sensitivity(
                glucose, pump_history, isf, basalprofile, profile, carb_history,
            )
        glucose_path = self._write_json("glucose_autosens.json", glucose)
        ph_path = self._write_json("pumphistory_autosens.json", pump_history)
        isf_path = self._write_json("isf.json", isf)
        basalprofile_path = self._write_json("basalprofile_autosens.json", basalprofile)
        profile_path = self._write_json("profile_autosens.json", profile)

        args = [glucose_path, ph_path, isf_path, basalprofile_path, profile_path]

        if carb_history is not None:
            carb_path = self._write_json("carbhistory_autosens.json", carb_history)
            args.append(carb_path)
        else:
            # Placeholder so "retrospective" lands in the temptargets slot (arg 7)
            args.append(self._write_json("carbhistory_autosens.json", []))

        # Retrospective mode: deterministic (no wall-clock dependency).
        args.append("retrospective")

        result = self._run_binary("oref0-detect-sensitivity", args)
        if isinstance(result, dict):
            return result
        return None

    def autotune_prep(
        self,
        pump_history: list,
        profile: dict,
        glucose: list,
        pumpprofile: dict,
        carb_history: list | None = None,
    ) -> dict | None:
        if self.use_ffi:
            return self._ensure_ffi_runner().autotune_prep(
                pump_history, profile, glucose, pumpprofile, carb_history,
            )
        ph_path = self._write_json("pumphistory_atprep.json", pump_history)
        profile_path = self._write_json("profile_atprep.json", profile)
        glucose_path = self._write_json("glucose_atprep.json", glucose)
        pumpprofile_path = self._write_json("pumpprofile_atprep.json", pumpprofile)

        args = [ph_path, profile_path, glucose_path, pumpprofile_path]

        if carb_history is not None:
            carb_path = self._write_json("carbhistory_atprep.json", carb_history)
            args.append(carb_path)

        result = self._run_binary("oref0-autotune-prep", args)
        if isinstance(result, dict):
            return result
        return None

    def autotune_core(
        self,
        prepped_glucose: dict,
        previous_autotune: dict,
        pumpprofile: dict,
    ) -> dict | None:
        if self.use_ffi:
            return self._ensure_ffi_runner().autotune_core(
                prepped_glucose, previous_autotune, pumpprofile,
            )
        prepped_path = self._write_json("prepped_glucose.json", prepped_glucose)
        prev_path = self._write_json("previous_autotune.json", previous_autotune)
        pump_path = self._write_json("pumpprofile_atcore.json", pumpprofile)

        args = [prepped_path, prev_path, pump_path]

        result = self._run_binary("oref0-autotune-core", args)
        if isinstance(result, dict):
            return result
        return None

    def cleanup(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)
