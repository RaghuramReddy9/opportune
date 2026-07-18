#!/usr/bin/env python3
"""Build a clean Opportune release candidate from an explicit public allowlist."""

from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path


PUBLIC_FILES = (
    ".env.example",
    ".gitignore",
    "AGENTS.md",
    "ARCHITECTURE.md",
    "BENCHMARK_SPEC.md",
    "CHANGELOG.md",
    "CODE_OF_CONDUCT.md",
    "CONTRIBUTOR_BACKLOG.md",
    "CONTRIBUTING.md",
    "LICENSE",
    "MAINTAINING.md",
    "ONBOARDING_IMPROVEMENT_PLAN.md",
    "PILOT_TEST_PLAN.md",
    "PUBLIC_RELEASE.md",
    "README.md",
    "RELEASE_SCORECARD.md",
    "ROADMAP.md",
    "SECURITY.md",
    "SOURCE_QUALITY_SPEC.md",
    "SUPPORT.md",
    "VERSION_1_AUDIT.md",
    "VERSION_1_PLAN.md",
    "candidate_profile.yaml",
    "config.example.yaml",
    "config.py",
    "desktop_launcher.py",
    "jobhunt.py",
    "pilot_metrics.py",
    "profile_context.py",
    "public_ops.py",
    "pyproject.toml",
    "source_registry.yaml",
    "uv.lock",
)

OPTIONAL_PUBLIC_FILES = (
    ".python-version",
    "CLAUDE.md",
    "MANIFEST.in",
    "pytest.ini",
)

PUBLIC_DIRECTORIES = (
    ".github",
    "adapters",
    "assets",
    "benchmarks",
    "core",
    "data",
    "dashboard",
    "dashapi",
    "docs",
    "frontend",
    "integrations/agents",
    "onboarding",
    "pipeline",
    "profile",
    "ranking",
    "resume",
    "scripts",
    "tests",
    "tools/maintenance",
    "tools/release",
)

IGNORED_DIRECTORY_NAMES = {
    ".git",
    ".hermes",
    ".kilo",
    ".memory",
    ".mypy_cache",
    ".pytest_cache",
    ".release",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "backups",
    "exports",
    "logs",
    "node_modules",
    "opportune.egg-info",
    "tracker",
}

IGNORED_FILE_NAMES = {
    ".env",
    "config.yaml",
    "credentials.json",
    "job_hunt_command_center.html",
    "ready_jobs.json",
    "token.json",
}

IGNORED_SUFFIXES = {
    ".db",
    ".log",
    ".pyc",
    ".pyo",
    ".sqlite",
    ".sqlite3",
    ".tsbuildinfo",
}

FORBIDDEN_TOP_LEVEL = {
    ".hermes",
    ".kilo",
    ".memory",
    ".release",
    ".venv",
    "backups",
    "evidence",
    "exports",
    "logs",
    "mail_monitor",
    "outreach",
    "reporting",
    "tracker",
}


@dataclass(frozen=True)
class ExportResult:
    destination: str
    file_count: int


def _ignore_names(_directory: str, names: list[str]) -> set[str]:
    ignored: set[str] = set()
    for name in names:
        path = Path(name)
        if name in IGNORED_DIRECTORY_NAMES or name in IGNORED_FILE_NAMES:
            ignored.add(name)
        elif name.startswith(".env.") and name != ".env.example":
            ignored.add(name)
        elif path.suffix.lower() in IGNORED_SUFFIXES:
            ignored.add(name)
    return ignored


def validate_candidate(destination: Path) -> None:
    """Reject private/runtime state or incomplete public exports."""
    destination = destination.resolve()
    required = (
        "README.md",
        "LICENSE",
        "pyproject.toml",
        "uv.lock",
        ".github/workflows/ci.yml",
        "data/skill_taxonomy.yaml",
        "frontend/dist/index.html",
        "desktop_launcher.py",
        "profile_context.py",
        "pilot_metrics.py",
        "benchmarks/report.py",
        "scripts/smoke_installed.py",
        "onboarding/service.py",
        "profile/availability.yaml",
        "profile/skills.example.yaml",
        "docs/FUTURE_EMAIL_EVIDENCE_OUTREACH.md",
    )
    missing = [item for item in required if not (destination / item).is_file()]
    if missing:
        raise ValueError(f"candidate is missing required files: {', '.join(missing)}")

    for name in FORBIDDEN_TOP_LEVEL:
        if (destination / name).exists():
            raise ValueError(f"forbidden release path: {name}")

    violations: list[str] = []
    for path in destination.rglob("*"):
        relative = path.relative_to(destination)
        if any(part in IGNORED_DIRECTORY_NAMES for part in relative.parts):
            violations.append(str(relative))
            continue
        if path.is_file():
            if path.name in IGNORED_FILE_NAMES:
                violations.append(str(relative))
            elif path.name.startswith(".env.") and path.name != ".env.example":
                violations.append(str(relative))
            elif path.suffix.lower() in IGNORED_SUFFIXES:
                violations.append(str(relative))
    if violations:
        sample = ", ".join(sorted(violations)[:10])
        raise ValueError(f"candidate contains private/runtime paths: {sample}")


def export_candidate(source: Path, destination: Path, *, replace: bool = False) -> ExportResult:
    """Copy the public allowlist into destination and validate the result."""
    source = source.resolve()
    destination = destination.resolve()
    if source == destination:
        raise ValueError("source and destination must differ")
    if destination.exists():
        if not replace:
            raise FileExistsError(f"destination exists; pass replace=True: {destination}")
        shutil.rmtree(destination)
    destination.mkdir(parents=True)

    missing_source = [item for item in PUBLIC_FILES if not (source / item).is_file()]
    if missing_source:
        raise FileNotFoundError(f"source is missing public files: {', '.join(missing_source)}")

    for relative in PUBLIC_FILES:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / relative, target)

    for relative in OPTIONAL_PUBLIC_FILES:
        src = source / relative
        if src.is_file():
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)

    for relative in PUBLIC_DIRECTORIES:
        src = source / relative
        if not src.is_dir():
            raise FileNotFoundError(f"source is missing public directory: {relative}")
        shutil.copytree(src, destination / relative, ignore=_ignore_names)

    validate_candidate(destination)
    file_count = sum(1 for path in destination.rglob("*") if path.is_file())
    return ExportResult(destination=str(destination), file_count=file_count)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--replace", action="store_true", help="replace an existing destination")
    args = parser.parse_args()

    result = export_candidate(args.source, args.destination, replace=args.replace)
    print(json.dumps(asdict(result), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
