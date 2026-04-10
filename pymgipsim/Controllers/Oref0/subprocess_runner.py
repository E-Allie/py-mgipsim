import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path


from functools import lru_cache

@lru_cache(maxsize=1)
def _find_node() -> str:
    found = shutil.which("node")
    if found:
        return found
    return "node"


class SubprocessRunner:
    """Calls oref0 CLI binaries via subprocess.

    Manages a temp directory for JSON staging files.
    All calls have a 10-second timeout.
    On any failure (non-zero exit, timeout, parse error), returns None.
    """

    def __init__(self, backend: str = "rust", oref0_path: Path | None = None,
                 use_ffi: bool = False):
        self.backend = backend
        self.use_ffi = use_ffi
        self._ffi_runner = None
        # Per-instance lock guarding lazy FfiRunner instantiation. Prevents
        # duplicate FfiRunner creation if multiple threads share a
        # SubprocessRunner instance (e.g. future parallel patient simulation).
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

    def _ensure_ffi_runner(self):
        # Double-checked locking: fast path avoids lock acquisition once
        # the runner is initialized, slow path serializes concurrent first
        # callers so only one FfiRunner is ever created per instance.
        if self._ffi_runner is None:
            with self._ffi_runner_lock:
                if self._ffi_runner is None:
                    from pymgipsim.Controllers.Oref0.ffi_runner import FfiRunner
                    self._ffi_runner = FfiRunner()
        return self._ffi_runner

    def _write_json(self, filename: str, data) -> str:
        """Write data as JSON to tmpdir/filename, return full path."""
        path = os.path.join(self.tmpdir, filename)
        with open(path, "w") as f:
            json.dump(data, f)
        return path

    def _run_binary(self, binary_name: str, args: list[str]) -> dict | list | None:
        """Run a binary with args, return parsed JSON stdout or None on failure."""
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
        start = time.perf_counter()
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
                cwd=cwd,
            )
            if result.returncode != 0:
                return None
            return json.loads(result.stdout)
        except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError, OSError):
            return None
        finally:
            self.subprocess_seconds.setdefault(binary_name, []).append(
                time.perf_counter() - start
            )

    def calculate_iob(self, pump_history: list, profile: dict, clock: str) -> dict | None:
        """Calculate IOB from pump history.

        Args:
            pump_history: list of pump history entries
            profile: oref0 profile dict
            clock: ISO 8601 timestamp string

        Returns:
            IOB dict {"iob": float, "activity": float, "bolussnooze": float}
            or None on failure
        """
        if self.use_ffi:
            return self._ensure_ffi_runner().calculate_iob(pump_history, profile, clock)
        ph_path = self._write_json("pumphistory.json", pump_history)
        profile_path = self._write_json("profile.json", profile)
        clock_path = self._write_json("clock.json", clock)

        result = self._run_binary("oref0-calculate-iob", [ph_path, profile_path, clock_path])
        if result is None:
            return None
        # calculate-iob returns an array; we want the first element (current IOB)
        if isinstance(result, list) and len(result) > 0:
            first = result[0]
            if isinstance(first, dict):
                return first
            return None
        if isinstance(result, dict):
            return result
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
        """Determine temp basal rate.

        Args:
            iob_data: IOB dict from calculate_iob
            currenttemp: current temp basal dict
            glucose: list of glucose entries (newest first)
            profile: oref0 profile dict
            clock: ISO 8601 timestamp string (used as --currentTime)
            meal_data: optional meal data dict
            microbolus: enable SMB microboluses (requires autotune/ in CWD)
            autosens_data: optional autosens ratio dict

        Returns:
            dict with "rate" (U/hr), "duration", "reason", etc.
            or None on failure
        """
        if self.use_ffi:
            return self._ensure_ffi_runner().determine_basal(
                iob_data, currenttemp, glucose, profile, clock,
                meal_data=meal_data, microbolus=microbolus, autosens_data=autosens_data,
            )
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
        """Calculate meal data (COB, carbs).

        Args:
            pump_history: list of pump history entries
            profile: oref0 profile dict
            clock: ISO 8601 timestamp string
            glucose: list of glucose entries
            basalprofile: list of basal profile entries
            carb_history: optional list of carb entries

        Returns:
            dict with "mealCOB", "carbs", "reason", etc.
            or None on failure
        """
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
        """Detect insulin sensitivity (autosens ratio).

        Args:
            glucose: list of glucose entries (newest first)
            pump_history: list of pump history entries
            isf: dict with "units" and "sensitivities" [{"sensitivity": value}]
            basalprofile: list of basal profile entries
            profile: oref0 profile dict
            carb_history: optional list of carb entries

        Returns:
            dict with "ratio" (float), "reason", etc.
            or None on failure
        """
        glucose_path = self._write_json("glucose_autosens.json", glucose)
        ph_path = self._write_json("pumphistory_autosens.json", pump_history)
        isf_path = self._write_json("isf.json", isf)
        basalprofile_path = self._write_json("basalprofile_autosens.json", basalprofile)
        profile_path = self._write_json("profile_autosens.json", profile)

        args = [glucose_path, ph_path, isf_path, basalprofile_path, profile_path]

        if carb_history is not None:
            carb_path = self._write_json("carbhistory_autosens.json", carb_history)
            args.append(carb_path)

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
