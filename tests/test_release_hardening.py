from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[1]


def test_release_version_is_consistent():
    with (ROOT / "pyproject.toml").open("rb") as handle:
        version = tomllib.load(handle)["project"]["version"]
    assert version == "0.1.1"
    assert f"(`{version}`)" in (ROOT / "README.md").read_text(encoding="utf-8")
    assert f"## [{version}]" in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"v{version}" in (ROOT / "RELEASE_NOTES.md").read_text(encoding="utf-8")


def test_installers_use_immutable_verified_release_artifacts():
    for name in ("install.sh", "install.ps1"):
        text = (ROOT / "scripts" / name).read_text(encoding="utf-8")
        assert "0.1.1" in text
        assert "SHA256SUMS" in text
        assert "main" not in text
        assert "git clone" not in text
        assert "uv tool install" in text


def test_release_manifest_records_hash_size_version_and_commit(tmp_path):
    wheel = tmp_path / "opportune-0.1.1-py3-none-any.whl"
    sdist = tmp_path / "opportune-0.1.1.tar.gz"
    wheel.write_bytes(b"wheel")
    sdist.write_bytes(b"sdist")
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "generate_release_manifest.py"), str(tmp_path)],
        cwd=ROOT,
        check=True,
    )
    manifest = json.loads((tmp_path / "release-manifest.json").read_text(encoding="utf-8"))
    assert manifest["version"] == "0.1.1"
    assert manifest["tag"] == "v0.1.1"
    assert len(manifest["commit"]) == 40
    records = {item["filename"]: item for item in manifest["artifacts"]}
    assert records[wheel.name]["sha256"] == hashlib.sha256(b"wheel").hexdigest()
    assert records[wheel.name]["size"] == 5
    sums = (tmp_path / "SHA256SUMS").read_text(encoding="utf-8")
    assert wheel.name in sums and sdist.name in sums
