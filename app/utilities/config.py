"""
Configuration loader.

Component Type: Utility (Cross-cutting).
Reads config.toml and environment variables. Returns plain dicts/values.
No business logic.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path


_CONFIG_FILE = Path(__file__).parent.parent.parent / "config.toml"


def load_config() -> dict:
    with open(_CONFIG_FILE, "rb") as f:
        return tomllib.load(f)


def resolve_vault_path(vault_name: str) -> Path | None:
    """
    Returns the filesystem path for a vault name, or None if not configured.
    Checks Settings (plist) first, then falls back to VAULT_<NAME>_PATH env var.
    """
    # Avoid circular import — Settings imports config, so import lazily here.
    try:
        from app.utilities.settings import Settings
        for vault in Settings().get_vaults():
            if vault.get("name", "").upper() == vault_name.upper():
                raw = vault.get("path", "")
                if raw:
                    return Path(raw).expanduser()
    except Exception:
        pass

    key = f"VAULT_{vault_name.upper()}_PATH"
    raw = os.environ.get(key)
    if raw is None:
        return None
    return Path(raw).expanduser()


def resolve_all_vault_paths() -> dict[str, Path]:
    """Returns all configured vaults as {name: path}, merging Settings and env vars."""
    result: dict[str, Path] = {}
    try:
        from app.utilities.settings import Settings
        for vault in Settings().get_vaults():
            name = vault.get("name", "").upper()
            raw  = vault.get("path", "")
            if name and raw:
                result[name] = Path(raw).expanduser()
    except Exception:
        pass
    # Env vars fill any gaps not covered by Settings.
    for key, value in os.environ.items():
        if key.startswith("VAULT_") and key.endswith("_PATH"):
            name = key[len("VAULT_"):-len("_PATH")].upper()
            if name not in result:
                result[name] = Path(value).expanduser()
    return result


def pending_dir() -> Path:
    """Local directory for incomplete notes awaiting follow-up."""
    base = Path(__file__).parent.parent.parent / "_pending"
    base.mkdir(parents=True, exist_ok=True)
    return base


def unrouted_dir() -> Path:
    """Local directory for notes that could not be routed (missing vault env var)."""
    base = Path(__file__).parent.parent.parent / "_unrouted"
    base.mkdir(parents=True, exist_ok=True)
    return base
