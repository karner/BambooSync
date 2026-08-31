"""
NSUserDefaults-backed preferences store.

Component Type: Utility (Cross-cutting).
Single source of truth for all user-configurable values. Persisted to
~/Library/Preferences/com.bamboo-slate.plist. On vault save, propagates
VAULT_<NAME>_PATH to the current process environment and via launchctl
so other processes on the same login session can read them.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from Foundation import NSUserDefaults

from app.utilities.logger import get_logger

_log  = get_logger(__name__)
_SUITE = "com.bamboo-slate"

_DEFAULT_HANDLERS = [
    {"name": "ollama-gemma",     "url": "http://localhost:11434", "model": "gemma4:26b",  "enabled": True},
    {"name": "ollama-moondream", "url": "http://localhost:11434", "model": "moondream",    "enabled": True},
]


class Settings:
    """
    Reads and writes all user preferences.

    Component Type: Utility (Cross-cutting).
    Wraps NSUserDefaults. Callable by any layer. Propagates vault paths
    to VAULT_<NAME>_PATH environment variables on every write.
    """

    def __init__(self) -> None:
        self.m_defaults = NSUserDefaults.alloc().initWithSuiteName_(_SUITE)

    # ------------------------------------------------------------------
    # Vaults
    # ------------------------------------------------------------------

    def get_vaults(self) -> list[dict]:
        val = self.m_defaults.arrayForKey_("vaults")
        return [dict(v) for v in val] if val else []

    def set_vaults(self, vaults: list[dict]) -> None:
        self.m_defaults.setObject_forKey_(vaults, "vaults")
        self._propagate_vault_env_vars(vaults)

    def export_env_file(self, out_path: Path) -> None:
        """Writes a shell-sourceable file: export VAULT_<NAME>_PATH="<path>"."""
        lines = []
        for vault in self.get_vaults():
            name = vault.get("name", "").upper().strip()
            path = vault.get("path", "").strip()
            if name and path:
                lines.append(f'export VAULT_{name}_PATH="{path}"\n')
        out_path.write_text("".join(lines), encoding="utf-8")

    def _propagate_vault_env_vars(self, vaults: list[dict]) -> None:
        for vault in vaults:
            name = vault.get("name", "").upper().strip()
            path = vault.get("path", "").strip()
            if not name or not path:
                continue
            key = f"VAULT_{name}_PATH"
            os.environ[key] = path
            try:
                subprocess.run(
                    ["launchctl", "setenv", key, path],
                    check=True, capture_output=True,
                )
            except Exception as exc:
                _log.warning("launchctl setenv failed for %s: %s", key, exc)

    # ------------------------------------------------------------------
    # Device
    # ------------------------------------------------------------------

    def get_device_name(self) -> str:
        return self.m_defaults.stringForKey_("device_name") or ""

    def set_device_name(self, name: str) -> None:
        self.m_defaults.setObject_forKey_(name.strip(), "device_name")

    def get_device_address(self) -> str:
        """
        The configured device. Preferences is authoritative: config.toml only
        seeds this on first launch (see seed_device_from_config). An empty
        result means the user cleared the device, not that none was ever set.
        """
        return self.m_defaults.stringForKey_("device_address") or ""

    def set_device_address(self, address: str) -> None:
        self.m_defaults.setObject_forKey_(address.strip(), "device_address")

    def get_host_id(self) -> bytes:
        """
        The persistent 6-byte identity this Mac presents to the Slate.

        Seeded from config.toml [host].id on first run, because changing it
        would invalidate an existing registration on the device. Generated once
        and stored only when nothing is configured anywhere — in that case the
        Slate has to be paired before it will talk to us.
        """
        host_id = self._decode_host_id(self.m_defaults.stringForKey_("host_id"))
        if host_id is not None:
            return host_id

        try:
            from app.utilities.config import load_config
            host_id = self._decode_host_id(load_config().get("host", {}).get("id"))
        except Exception as exc:
            _log.warning("Could not read host id from config.toml: %s", exc)

        if host_id is None:
            host_id = os.urandom(6)
            _log.info(
                "Generated host id %s — pair the Slate in Preferences before syncing",
                host_id.hex(),
            )
        self.m_defaults.setObject_forKey_(host_id.hex(), "host_id")
        return host_id

    @staticmethod
    def _decode_host_id(value) -> bytes | None:
        """Returns the 6 bytes for a 12-character hex string, or None if unusable."""
        text = str(value or "").strip()
        if len(text) != 12:
            return None
        try:
            return bytes.fromhex(text)
        except ValueError:
            return None

    def seed_device_from_config(self) -> None:
        """
        First launch only: copies the factory device from config.toml into
        Preferences. Keyed on the plist entry being absent rather than empty,
        so a device cleared in Preferences stays cleared instead of silently
        reverting to config.toml on the next sync.
        """
        if self.m_defaults.objectForKey_("device_address") is not None:
            return
        try:
            from app.utilities.config import load_config
            device = load_config().get("device", {})
        except Exception as exc:
            _log.warning("Could not seed device from config.toml: %s", exc)
            return

        address = str(device.get("address", "")).strip()
        if not address:
            return
        self.set_device_address(address)
        name = str(device.get("name", "")).strip()
        if name and not self.get_device_name():
            self.set_device_name(name)
        _log.info("Seeded device %s from config.toml", address)

    def get_device_scan_timeout(self) -> float:
        val = self.m_defaults.floatForKey_("device_scan_timeout")
        return float(val) if val else 30.0

    def set_device_scan_timeout(self, timeout: float) -> None:
        self.m_defaults.setFloat_forKey_(max(5.0, float(timeout)), "device_scan_timeout")

    # ------------------------------------------------------------------
    # AI Handlers
    # ------------------------------------------------------------------

    def get_handlers(self) -> list[dict]:
        val = self.m_defaults.arrayForKey_("handlers")
        return [dict(h) for h in val] if val else list(_DEFAULT_HANDLERS)

    def set_handlers(self, handlers: list[dict]) -> None:
        self.m_defaults.setObject_forKey_(handlers, "handlers")

    def get_default_handler(self) -> str:
        return self.m_defaults.stringForKey_("default_handler") or "ollama-gemma"

    def set_default_handler(self, name: str) -> None:
        self.m_defaults.setObject_forKey_(name, "default_handler")

    # ------------------------------------------------------------------
    # Sync
    # ------------------------------------------------------------------

    def get_auto_sync(self) -> bool:
        return bool(self.m_defaults.boolForKey_("auto_sync"))

    def set_auto_sync(self, enabled: bool) -> None:
        self.m_defaults.setBool_forKey_(enabled, "auto_sync")

    def get_unrouted_action(self) -> str:
        return self.m_defaults.stringForKey_("unrouted_action") or "quarantine"

    def set_unrouted_action(self, action: str) -> None:
        self.m_defaults.setObject_forKey_(action, "unrouted_action")

    def get_scratch_dir(self) -> str:
        return self.m_defaults.stringForKey_("scratch_dir") or ""

    def set_scratch_dir(self, path: str) -> None:
        self.m_defaults.setObject_forKey_(path, "scratch_dir")

    # ------------------------------------------------------------------
    # Notifications
    # ------------------------------------------------------------------

    def get_notify_sync_complete(self) -> bool:
        val = self.m_defaults.objectForKey_("notify_sync_complete")
        return bool(val) if val is not None else True

    def set_notify_sync_complete(self, enabled: bool) -> None:
        self.m_defaults.setBool_forKey_(enabled, "notify_sync_complete")

    def get_show_count_in_menu(self) -> bool:
        return bool(self.m_defaults.boolForKey_("show_count_in_menu"))

    def set_show_count_in_menu(self, enabled: bool) -> None:
        self.m_defaults.setBool_forKey_(enabled, "show_count_in_menu")

    # ------------------------------------------------------------------
    # Startup
    # ------------------------------------------------------------------

    def apply_on_startup(self) -> None:
        """Seeds first-run defaults and propagates saved vault paths to environment."""
        self.seed_device_from_config()
        self._propagate_vault_env_vars(self.get_vaults())
