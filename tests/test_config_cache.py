from unittest.mock import patch

import config


def test_load_config_reuses_yaml_until_file_changes(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("profile:\n  timeline:\n    max_age_days: 7\n")
    config._CONFIG_CACHE_KEY = None
    config._CONFIG_CACHE_VALUE = None

    with patch.object(config, "CONFIG_PATH", path), patch("config.yaml.safe_load", wraps=config.yaml.safe_load) as load:
        assert config.load_config()["profile"]["timeline"]["max_age_days"] == 7
        assert config.load_config()["profile"]["timeline"]["max_age_days"] == 7

    assert load.call_count == 1

    path.write_text("profile:\n  timeline:\n    max_age_days: 3\n")
    with patch.object(config, "CONFIG_PATH", path):
        assert config.load_config()["profile"]["timeline"]["max_age_days"] == 3


def test_enabled_sources_reflects_runtime_config_changes(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("sources:\n  - name: greenhouse\n    enabled: false\n    mode: free\n")
    config._CONFIG_CACHE_KEY = None
    config._CONFIG_CACHE_VALUE = None

    with patch.object(config, "CONFIG_PATH", path):
        assert config.enabled_sources() == []
        path.write_text("sources:\n  - name: greenhouse\n    enabled: true\n    mode: free\n")
        assert [source["name"] for source in config.enabled_sources()] == ["greenhouse"]
