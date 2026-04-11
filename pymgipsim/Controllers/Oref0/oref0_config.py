"""Load oref0 profile overrides from a TOML config file."""

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]


def load_oref0_config(path: str) -> dict:
    """Load TOML config, return {"global": {...}, "patient": {"0": {...}, ...}}."""
    with open(path, "rb") as f:
        raw = tomllib.load(f)
    return {
        "global": raw.get("global", {}),
        "patient": raw.get("patient", {}),
    }


def resolve_overrides(config: dict | None, patient_idx: int) -> dict | None:
    """Merge global and per-patient overrides for a given patient index."""
    if not config:
        return None
    merged = {}
    merged.update(config.get("global", {}))
    merged.update(config.get("patient", {}).get(str(patient_idx), {}))
    return merged or None
