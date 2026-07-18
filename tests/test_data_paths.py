"""Cross-platform local data path contracts."""
from __future__ import annotations


def test_source_checkout_preserves_explicit_relative_storage(tmp_path):
    from core.paths import resolve_runtime_paths

    runtime = resolve_runtime_paths(
        project_root=tmp_path,
        project_config_exists=True,
        storage_home="tracker",
        platform="linux",
        home="/home/tester",
        env={},
    )

    assert runtime.config_file == tmp_path / "config.yaml"
    assert runtime.data_dir == tmp_path / "tracker"


def test_installed_package_ignores_example_relative_storage(tmp_path):
    from core.paths import resolve_runtime_paths

    runtime = resolve_runtime_paths(
        project_root=tmp_path,
        project_config_exists=False,
        storage_home="tracker",
        platform="linux",
        home="/home/tester",
        env={"XDG_CONFIG_HOME": "/cfg", "XDG_DATA_HOME": "/data"},
    )

    assert str(runtime.config_file) == "/cfg/opportune/config.yaml"
    assert str(runtime.data_dir) == "/data/opportune"


def test_linux_paths_follow_xdg_and_keep_data_classes_separate():
    from core.paths import resolve_app_paths

    paths = resolve_app_paths(
        platform="linux",
        home="/home/tester",
        env={
            "XDG_CONFIG_HOME": "/cfg",
            "XDG_DATA_HOME": "/data",
            "XDG_CACHE_HOME": "/cache",
        },
    )

    assert str(paths.config_dir) == "/cfg/opportune"
    assert str(paths.data_dir) == "/data/opportune"
    assert str(paths.cache_dir) == "/cache/opportune"
    assert paths.database == paths.data_dir / "dashboard.db"
    assert paths.exports == paths.data_dir / "exports"
    assert paths.backups == paths.data_dir / "backups"


def test_windows_paths_use_roaming_config_and_local_data():
    from core.paths import resolve_app_paths

    paths = resolve_app_paths(
        platform="win32",
        home="C:/Users/Tester",
        env={"APPDATA": "C:/Roaming", "LOCALAPPDATA": "C:/Local"},
    )

    assert str(paths.config_dir) == "C:/Roaming/Opportune"
    assert str(paths.data_dir) == "C:/Local/Opportune"
    assert str(paths.cache_dir) == "C:/Local/Opportune/cache"


def test_macos_paths_use_application_support_and_caches():
    from core.paths import resolve_app_paths

    paths = resolve_app_paths(platform="darwin", home="/Users/tester", env={})

    assert str(paths.config_dir) == "/Users/tester/Library/Application Support/Opportune"
    assert str(paths.data_dir) == "/Users/tester/Library/Application Support/Opportune"
    assert str(paths.cache_dir) == "/Users/tester/Library/Caches/Opportune"


def test_explicit_environment_overrides_take_precedence():
    from core.paths import resolve_app_paths

    paths = resolve_app_paths(
        platform="linux",
        home="/home/tester",
        env={
            "OPPORTUNE_CONFIG_HOME": "/custom/config",
            "JOB_AGENT_HOME": "/custom/data",
            "OPPORTUNE_CACHE_HOME": "/custom/cache",
        },
    )

    assert str(paths.config_dir) == "/custom/config"
    assert str(paths.data_dir) == "/custom/data"
    assert str(paths.cache_dir) == "/custom/cache"
