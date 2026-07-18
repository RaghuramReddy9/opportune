"""Release package manifest privacy contracts."""
from __future__ import annotations

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 support
    import tomli as tomllib  # type: ignore[import-not-found]
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_release_manifest_excludes_candidate_specific_profile_artifacts():
    data = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    setuptools = data["tool"]["setuptools"]
    data_files = setuptools["data-files"]
    package_data = setuptools.get("package-data", {})
    packaged = {
        value
        for values in data_files.values()
        for value in values
    }

    assert setuptools["include-package-data"] is False
    assert "resume" not in package_data
    assert packaged.isdisjoint(
        {
            "candidate_profile.yaml",
            "resume/resume.txt",
            "resume/resume_profile.md",
        }
    )
