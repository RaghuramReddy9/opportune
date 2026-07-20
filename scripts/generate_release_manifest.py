"""Generate release checksums and a machine-readable artifact manifest."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path


def main() -> int:
    dist = Path(sys.argv[1] if len(sys.argv) > 1 else "dist")
    artifacts = sorted((*dist.glob("*.whl"), *dist.glob("*.tar.gz")))
    if not artifacts:
        raise SystemExit("no release artifacts found")
    versions = {
        path.name.removeprefix("opportune-").removesuffix(".tar.gz")
        if path.name.endswith(".tar.gz") else path.name.split("-")[1]
        for path in artifacts
    }
    if len(versions) != 1:
        raise SystemExit("release artifacts do not share one version")
    version = versions.pop()
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    records = []
    for path in artifacts:
        records.append({
            "filename": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "size": path.stat().st_size,
        })
    (dist / "SHA256SUMS").write_text(
        "".join(f"{item['sha256']}  {item['filename']}\n" for item in records),
        encoding="utf-8",
    )
    (dist / "release-manifest.json").write_text(
        json.dumps({
            "schema_version": "1.0",
            "version": version,
            "tag": f"v{version}",
            "commit": commit,
            "artifacts": records,
        }, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
