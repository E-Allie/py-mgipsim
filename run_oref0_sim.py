#!/usr/bin/env python3
"""End-to-end simulation of py-mgipsim with the Oref0 closed-loop controller.

Usage:
    PYTHONPATH=. .venv/bin/python3 run_oref0_sim.py --backend rust --patients 1 --days 1 --seed 100
"""
import argparse
import os
import sys
import time


def parse_args():
    p = argparse.ArgumentParser(
        description="Run py-mgipsim with oref0 controller",
        epilog="Required env vars: OREF0_RS_BIN_DIR (path to Rust binaries), "
               "OREF0_JS_BIN_DIR (path to JS bin/ scripts)")
    p.add_argument("--backend", choices=["rust", "js"], default="rust",
                   help="Oref0 backend: rust binary or js via node")
    p.add_argument("--oref0-dir", dest="oref0_dir",
                   help="Override binary directory (sets OREF0_RS_BIN_DIR or OREF0_JS_BIN_DIR)")
    p.add_argument("--patients", type=int, default=3,
                   help="Number of virtual patients")
    p.add_argument("--days", type=int, default=1,
                   help="Simulation duration in whole days (min 1)")
    p.add_argument("--seed", type=int, default=100,
                    help="Random seed for reproducibility")
    p.add_argument("--forward-carbs", action="store_true", default=False,
                   help="Forward py-mgipsim carb events to oref0 (COB-aware control). "
                        "Without this flag, oref0 is blind to meals.")
    p.add_argument("--enable-smb", action="store_true", default=False,
                   help="Enable SMB (Super Micro Bolus) oref1 microboluses.")
    p.add_argument("--enable-uam", action="store_true", default=False,
                   help="Enable UAM (Unannounced Meals) detection. "
                        "Only has effect when --enable-smb is also set.")
    p.add_argument("--enable-autosens", action="store_true", default=False,
                   help="Enable autosens sensitivity detection every 5-min cycle.")
    p.add_argument("--enable-autotune", action="store_true", default=False,
                   help="Enable autotune nightly profile adjustment (basal, ISF, CR). "
                        "Runs every --autotune-interval hours of simulated time.")
    p.add_argument("--autotune-interval", type=float, default=24,
                   help="Hours between autotune runs (default 24). "
                        "Only has effect when --enable-autotune is set.")
    p.add_argument("--debug-log", default=None,
                   help="Write JSON-lines debug log of determine_basal decisions "
                        "where BG <= --debug-bg-threshold. One line per decision.")
    p.add_argument("--debug-bg-threshold", type=float, default=90,
                   help="BG threshold (mg/dL) for debug logging (default 90).")
    p.add_argument("--profile", action="store_true", default=False,
                   help="Print per-binary subprocess timing breakdown at end of run.")
    p.add_argument("--use-ffi", dest="use_ffi", action="store_true", default=False,
                   help="Use in-process oref0_ffi wheel instead of subprocess calls. "
                        "Requires the oref0_ffi wheel (maturin develop --release).")
    p.add_argument("--oref0-config", dest="oref0_config", default=None,
                   help="TOML config file for oref0 profile overrides. "
                        "Supports [global] and [patient.N] sections.")
    return p.parse_args()


def main():
    args = parse_args()

    if args.use_ffi:
        try:
            import oref0_ffi  # noqa: F401
        except ImportError as e:
            raise RuntimeError(
                "--use-ffi requires the oref0_ffi wheel. "
                "Install with: cd oref0-rs/crates/oref0-ffi && maturin develop --release"
            ) from e
        os.environ["OREF0_USE_FFI"] = "1"

    if args.oref0_config:
        os.environ["OREF0_CONFIG_FILE"] = os.path.abspath(args.oref0_config)

    os.environ["OREF0_BACKEND"] = args.backend
    if args.oref0_dir:
        env_key = "OREF0_RS_BIN_DIR" if args.backend == "rust" else "OREF0_JS_BIN_DIR"
        os.environ[env_key] = args.oref0_dir
    if args.forward_carbs:
        os.environ["OREF0_FORWARD_CARBS"] = "1"
    if args.enable_smb:
        os.environ["OREF0_ENABLE_SMB"] = "1"
    if args.enable_uam:
        os.environ["OREF0_ENABLE_UAM"] = "1"
    if args.enable_autosens:
        os.environ["OREF0_ENABLE_AUTOSENS"] = "1"
    if args.enable_autotune:
        os.environ["OREF0_ENABLE_AUTOTUNE"] = "1"
        os.environ["OREF0_AUTOTUNE_INTERVAL"] = str(args.autotune_interval)
    if args.debug_log:
        os.environ["OREF0_DEBUG_LOG"] = os.path.abspath(args.debug_log)
        os.environ["OREF0_DEBUG_BG"] = str(args.debug_bg_threshold)


    # Must set Agg backend before any pymgipsim import touches matplotlib
    import matplotlib
    matplotlib.use("Agg")

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    import numpy as np
    np.random.seed(args.seed)

    from pymgipsim.Utilities.paths import results_path, default_settings_path
    from pymgipsim.Utilities import simulation_folder
    from pymgipsim.Utilities.Scenario import load_scenario
    from pymgipsim.InputGeneration.activity_settings import activity_args_to_scenario
    from pymgipsim.generate_settings import generate_simulation_settings_main
    from pymgipsim.generate_inputs import generate_inputs_main
    from pymgipsim.generate_subjects import generate_virtual_subjects_main
    from pymgipsim.generate_results import generate_results_main
    from pymgipsim.generate_plots import generate_plots_main
    from pymgipsim.Interface.parser import generate_parser_cli
    from pymgipsim.Utilities.units_conversions_constants import UnitConversion

    _, _, _, rfp = simulation_folder.create_simulation_results_folder(results_path)

    sf = load_scenario(os.path.join(default_settings_path, "scenario_default.json"))

    cli_args = generate_parser_cli().parse_args([])
    cli_args.number_of_subjects = args.patients
    cli_args.number_of_days = args.days
    cli_args.random_seed = args.seed
    cli_args.no_print = True
    cli_args.no_progress_bar = True
    cli_args.running_speed = 0.0
    cli_args.cycling_power = [0.0]
    cli_args.plot_blood_glucose = True
    cli_args.controller_name = "Oref0"
    cli_args.to_excel = False

    activity_args_to_scenario(sf, cli_args)

    sf = generate_simulation_settings_main(scenario_instance=sf, args=cli_args, results_folder_path=rfp)
    sf = generate_virtual_subjects_main(scenario_instance=sf, args=cli_args, results_folder_path=rfp)
    sf = generate_inputs_main(scenario_instance=sf, args=cli_args, results_folder_path=rfp)

    sf.controller.name = "Oref0"

    sim_start = time.perf_counter()
    # generate_results_main expects args as dict, not Namespace
    cohort, _ = generate_results_main(
        scenario_instance=sf,
        args=vars(cli_args),
        results_folder_path=rfp
    )
    sim_elapsed = time.perf_counter() - sim_start

    generate_plots_main(rfp, cli_args)

    model = cohort.model_solver.model
    state_arr = model.states.as_array
    flags = []
    if args.forward_carbs:
        flags.append("carbs")
    if args.enable_smb:
        flags.append("smb")
    if args.enable_uam:
        flags.append("uam")
    if args.enable_autosens:
        flags.append("autosens")
    if args.enable_autotune:
        flags.append(f"autotune@{args.autotune_interval}h")
    flags_str = "+".join(flags) if flags else "baseline"

    print(f"\n=== Oref0 Simulation ({args.backend} backend) ===")
    print(f"Patients: {args.patients}, Days: {args.days}, Seed: {args.seed}")
    print(f"Flags: {flags_str}")
    print(f"Wall-clock: {sim_elapsed:.2f}s")
    print(f"Results: {rfp}")
    for i in range(args.patients):
        g_mmol = state_arr[i, model.glucose_state, :] / model.parameters.VG[i]
        g_mgdl = UnitConversion.glucose.concentration_mmolL_to_mgdL(g_mmol)
        print(f"  Patient {i+1}: min={g_mgdl.min():.1f} max={g_mgdl.max():.1f} mean={g_mgdl.mean():.1f} mg/dL")

    if args.profile:
        controller = getattr(cohort.model_solver, 'controller', None)
        runners = getattr(controller, 'runners', None) if controller else None
        if runners:
            aggregated: dict[str, list[float]] = {}
            for runner in runners:
                for name, samples in runner.subprocess_seconds.items():
                    aggregated.setdefault(name, []).extend(samples)

            print("\n=== Subprocess profile ===")
            total_time = 0.0
            total_calls = 0
            rows = sorted(aggregated.items(), key=lambda kv: -sum(kv[1]))
            for name, samples in rows:
                total = sum(samples)
                total_time += total
                total_calls += len(samples)
                avg_ms = (total / len(samples)) * 1000 if samples else 0
                print(f"  {name:30s} calls={len(samples):5d} total={total:7.2f}s avg={avg_ms:6.2f}ms")
            print(f"  {'TOTAL':30s} calls={total_calls:5d} total={total_time:7.2f}s "
                  f"({100 * total_time / sim_elapsed:.1f}% of wall-clock)")

    if hasattr(cohort.model_solver, 'controller') and hasattr(cohort.model_solver.controller, 'cleanup'):
        cohort.model_solver.controller.cleanup()

    print("Done. Plots in:", os.path.join(rfp, "figures"))
    return rfp


if __name__ == "__main__":
    main()
