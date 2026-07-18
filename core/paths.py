"""Cross-platform path policy for local Opportune state."""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class AppPaths:
    config_dir: Path
    data_dir: Path
    cache_dir: Path
    logs: Path
    exports: Path
    backups: Path
    database: Path


@dataclass(frozen=True)
class RuntimePaths:
    config_file: Path
    data_dir: Path
    cache_dir: Path
    logs: Path
    exports: Path
    backups: Path
    database: Path


def resolve_runtime_paths(
    *,
    project_root: Path,
    project_config_exists: bool,
    storage_home: str | Path | None = None,
    platform: str | None = None,
    home: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> RuntimePaths:
    """Apply source-checkout compatibility to the platform path policy."""
    env = os.environ if env is None else env
    base = resolve_app_paths(platform=platform, home=home, env=env)
    configured = Path(storage_home).expanduser() if storage_home else None
    if "JOB_AGENT_HOME" in env:
        data_dir = Path(env["JOB_AGENT_HOME"]).expanduser()
    elif configured and configured.is_absolute():
        data_dir = configured
    elif project_config_exists and configured:
        data_dir = project_root / configured
    else:
        data_dir = base.data_dir

    config_file = project_root / "config.yaml" if project_config_exists else base.config_dir / "config.yaml"
    return RuntimePaths(
        config_file=config_file,
        data_dir=data_dir,
        cache_dir=base.cache_dir,
        logs=data_dir / "logs",
        exports=data_dir / "exports",
        backups=data_dir / "backups",
        database=data_dir / "dashboard.db",
    )


def resolve_app_paths(
    *,
    platform: str | None = None,
    home: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> AppPaths:
    """Resolve user-writable config/data/cache roots without creating them."""
    platform = platform or sys.platform
    env = os.environ if env is None else env
    home_path = Path(home or Path.home()).expanduser()

    if platform.startswith("win"):
        roaming = Path(env.get("APPDATA") or home_path / "AppData" / "Roaming")
        local = Path(env.get("LOCALAPPDATA") or home_path / "AppData" / "Local")
        config_dir = roaming / "Opportune"
        data_dir = local / "Opportune"
        cache_dir = data_dir / "cache"
    elif platform == "darwin":
        support = home_path / "Library" / "Application Support" / "Opportune"
        config_dir = support
        data_dir = support
        cache_dir = home_path / "Library" / "Caches" / "Opportune"
    else:
        config_dir = Path(env.get("XDG_CONFIG_HOME") or home_path / ".config") / "opportune"
        data_dir = Path(env.get("XDG_DATA_HOME") or home_path / ".local" / "share") / "opportune"
        cache_dir = Path(env.get("XDG_CACHE_HOME") or home_path / ".cache") / "opportune"

    config_dir = Path(env.get("OPPORTUNE_CONFIG_HOME") or config_dir).expanduser()
    data_dir = Path(env.get("JOB_AGENT_HOME") or data_dir).expanduser()
    cache_dir = Path(env.get("OPPORTUNE_CACHE_HOME") or cache_dir).expanduser()

    return AppPaths(
        config_dir=config_dir,
        data_dir=data_dir,
        cache_dir=cache_dir,
        logs=data_dir / "logs",
        exports=data_dir / "exports",
        backups=data_dir / "backups",
        database=data_dir / "dashboard.db",
    )
