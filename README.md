## **mGIPsim - oref(-rs) usage fork

Metabolic simulator of 20 virtual patients with type 1 diabetes, simulates physical activity, meal intakes, and insulin therapies.
* Efficient simulation (vectorized and JIT compiled)
* Modular, easy to extend with models, controllers
* Current therapies: multiple daily injections, sensor augmented pump therapy, vanilla hybrid closed-loop
* [Docs](https://illinoistech-itm.github.io/py-mgipsim/)

## Requirements
* Python 3.12
* Dependencies can be installed via ``pip install -r requirements.txt``

## Usage
### Graphical User Interface
Provides a graphical user interface in a web app.

To run it locally:
```bash
streamlit run interface_gui.py
```

![](static/gui.gif)

### Command Line - Interactive
Provides an interactive prompt environment to set the simulation settings.

Start by running ``interface_cmd.py``.

![](static/cmd.gif)

### Command Line - single command
Simulation settings are defined in a single command line.

Start by running ``interface_cli.py [OPTIONS]``.

### Oref0 Closed-Loop Controller

This fork adds an [oref0-rs](https://github.com/E-Allie/oref0-rs) controller that runs the OpenAPS reference design algorithm as a closed-loop insulin delivery strategy. Both the Rust (`oref0-rs`) and original JS implementations are supported.

#### Prerequisites

You need a built copy of oref0 binaries:

- **Rust**: `cargo build --release` in the oref0-rs repo produces binaries in `target/release/`
- **JS**: the `js/bin/` directory in the oref0 repo (requires `node`)

#### Environment variables

| Variable | Required for | Description |
|----------|-------------|-------------|
| `OREF0_RS_BIN_DIR` | `--backend rust` | Path to directory containing `oref0-determine-basal`, `oref0-calculate-iob` |
| `OREF0_JS_BIN_DIR` | `--backend js` | Path to directory containing `oref0-determine-basal.js`, `oref0-calculate-iob.js` |
| `OREF0_BACKEND` | optional | Default backend (`rust` or `js`), overridden by `--backend` |
| `OREF0_FORWARD_CARBS` | optional | Set to `1` to enable carb forwarding (same as `--forward-carbs`) |
| `OREF0_ENABLE_SMB` | optional | Set to `1` to enable SMB (same as `--enable-smb`) |
| `OREF0_ENABLE_UAM` | optional | Set to `1` to enable UAM (same as `--enable-uam`) |
| `OREF0_ENABLE_AUTOSENS` | optional | Set to `1` to enable autosens (same as `--enable-autosens`) |
| `OREF0_ENABLE_AUTOTUNE` | optional | Set to `1` to enable autotune (same as `--enable-autotune`) |
| `OREF0_AUTOTUNE_INTERVAL` | optional | Hours between autotune runs (default `24`; same as `--autotune-interval`) |

> **Performance note**: Always use `cargo build --release` binaries, never debug builds. With advanced features enabled, the pipeline runs up to 4 subprocess calls per 5-min cycle (iob, meal, autosens, determine-basal). Release binaries are ~10x faster than debug.

#### Running a simulation

```bash
# Set the binary path (or use --oref0-dir)
export OREF0_RS_BIN_DIR=/path/to/oref0-rs/target/release

# Baseline: oref0 with no advanced features (blind to meals)
python run_oref0_sim.py --backend rust --patients 3 --days 1 --seed 100

# With carb forwarding: oref0 sees meal events from the simulator
python run_oref0_sim.py --backend rust --oref0-dir /path/to/oref0-rs/target/release \
  --patients 1 --days 1 --forward-carbs

# With SMB + UAM: faster corrections via microboluses
# Note: UAM only has effect when --enable-smb is also set
python run_oref0_sim.py --backend rust --oref0-dir /path/to/oref0-rs/target/release \
  --patients 1 --days 1 --enable-smb --enable-uam

# With autosens: sensitivity adapts every 5-min cycle
python run_oref0_sim.py --backend rust --oref0-dir /path/to/oref0-rs/target/release \
  --patients 1 --days 1 --enable-autosens

# With autotune: nightly profile adjustment (basal, ISF, carb ratio)
# Most meaningful in multi-day sims, especially with mismatched initial profiles
python run_oref0_sim.py --backend rust --oref0-dir /path/to/oref0-rs/target/release \
  --patients 1 --days 7 --enable-autotune --autotune-interval 24

# All features enabled
python run_oref0_sim.py --backend rust --oref0-dir /path/to/oref0-rs/target/release \
  --patients 1 --days 1 --forward-carbs --enable-smb --enable-uam --enable-autosens --enable-autotune
```

Output includes per-patient glucose statistics (min/max/mean in mg/dL) and plots saved to `SimulationResults/`.

#### Feature flags

| Flag | Default | Description |
|------|---------|-------------|
| `--forward-carbs` | off | Forward py-mgipsim meal events to oref0 as carb entries. Without this flag, oref0 is intentionally blind to meals - useful for testing algorithm robustness. |
| `--enable-smb` | off | Enable oref1 Super Micro Bolus mode. Delivers small correction boluses in addition to temp basal adjustments. Produces significantly lower post-meal peaks. **Warning**: SMB with `enableSMB_always` can cause hypoglycemia in simulation - the virtual patient model has no real-world pump safety limits. |
| `--enable-uam` | off | Enable Unannounced Meal detection. Detects rising glucose patterns as meals and triggers additional SMBs. **Only has effect when `--enable-smb` is also set.** |
| `--enable-autosens` | off | Run `oref0-detect-sensitivity` every 5-min cycle to adapt ISF/basal to the patient's current sensitivity. Increases glucose history window to 24h (288 readings). |
| `--enable-autotune` | off | Run `oref0-autotune-prep` + `oref0-autotune-core` at `--autotune-interval` hour intervals to adjust the working profile (basal rates, ISF, carb ratio). Most meaningful in multi-day simulations, especially when the initial profile is intentionally mismatched from the virtual patient's true parameters. |
| `--autotune-interval` | 24 | Hours of simulated time between autotune runs. Only has effect when `--enable-autotune` is set. Autotune requires at least 3 hours of accumulated glucose data before its first run. |

#### Running the tests

```bash
OREF0_RS_BIN_DIR=/path/to/oref0-rs/target/release \
OREF0_JS_BIN_DIR=/path/to/oref0-rs/js/bin \
PYTHONPATH=. pytest pymgipsim/Controllers/Oref0/tests/ -v \
  --rootdir=pymgipsim/Controllers/Oref0/tests
```

#### Architecture

The controller lives in `pymgipsim/Controllers/Oref0/` and consists of:

| Module | Purpose |
|--------|---------|
| `controller.py` | Main controller class registered in `singlescale.py` |
| `subprocess_runner.py` | Calls oref0 binaries via subprocess with JSON file staging |
| `profile_builder.py` | Maps py-mgipsim patient demographics to oref0 profile format |
| `state_tracker.py` | Accumulates glucose/insulin history with wall-clock timestamps |
| `glucose_formatter.py` | Formats glucose history with CGM trend direction classification |
| `pump_history.py` | Builds oref0-compatible pump history entries (temp basal + bolus) |
| `unit_bridge.py` | Bidirectional unit conversions (mmol/L <-> mg/dL, U/hr <-> mU/min) |

The controller records simulated CGM readings every 5 minutes, then each control cycle calls: `oref0-calculate-iob` -> (optionally) `oref0-meal` -> (optionally) `oref0-detect-sensitivity` -> `oref0-determine-basal`, and converts the recommended rate back to the simulator's insulin input units.

At configurable intervals (default 24h), the optional autotune outer loop runs `oref0-autotune-prep` -> `oref0-autotune-core` to adjust the working profile's basal rates, ISF, and carb ratio. The original pump profile is preserved as a reference anchor - autotune output is clamped to `autosens_max`/`autosens_min` (default 1.2x/0.7x) of the pump profile values.
