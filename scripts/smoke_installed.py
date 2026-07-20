"""Cross-platform smoke test for an installed Opportune wheel."""
from __future__ import annotations

import argparse
import os
import re
import socket
import shutil
import subprocess
import tempfile
import sys
import time
import urllib.request
import venv
import zipfile
from pathlib import Path


def _python(venv_dir: Path) -> Path:
    return venv_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _script(venv_dir: Path, name: str) -> Path:
    suffix = ".exe" if os.name == "nt" else ""
    return venv_dir / (f"Scripts/{name}{suffix}" if os.name == "nt" else f"bin/{name}")


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait(url: str, timeout: float = 30.0) -> bytes:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return response.read()
        except Exception as exc:  # bounded readiness polling
            last_error = exc
            time.sleep(0.2)
    raise RuntimeError(f"timed out waiting for {url}: {last_error}")


def _assert_manifest_privacy(wheel: Path) -> None:
    forbidden = {"candidate_profile.yaml", "resume.txt", "resume_profile.md"}
    with zipfile.ZipFile(wheel) as archive:
        names = {Path(name).name for name in archive.namelist()}
    leaked = forbidden & names
    if leaked:
        raise RuntimeError(f"wheel contains candidate-specific artifacts: {sorted(leaked)}")


def smoke(wheel: Path) -> None:
    wheel = wheel.resolve()
    _assert_manifest_privacy(wheel)
    with tempfile.TemporaryDirectory(prefix="opportune-wheel-smoke-") as tmp:
        root = Path(tmp)
        venv_dir = root / "venv"
        uv = shutil.which("uv") or next(
            (
                str(path) for path in (Path.home() / ".local/bin/uv", Path.home() / ".cargo/bin/uv")
                if path.is_file()
            ),
            None,
        )
        if uv:
            subprocess.run(
                [uv, "venv", "--python", sys.executable, str(venv_dir)],
                check=True,
            )
        else:
            venv.EnvBuilder(with_pip=True).create(venv_dir)
        python = _python(venv_dir)
        clean_env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
        install_command = (
            [uv, "pip", "install", "--python", str(python), str(wheel)]
            if uv
            else [str(python), "-m", "pip", "install", "--quiet", str(wheel)]
        )
        subprocess.run(install_command, check=True, cwd=root, env=clean_env)
        subprocess.run(
            [str(_script(venv_dir, "opportune")), "--help"],
            check=True,
            cwd=root,
            env=clean_env,
            stdout=subprocess.PIPE,
        )
        subprocess.run(
            [str(_script(venv_dir, "opp")), "--help"],
            check=True,
            cwd=root,
            env=clean_env,
            stdout=subprocess.PIPE,
        )

        port = _free_port()
        env = {
            **clean_env,
            "JOB_AGENT_HOME": str(root / "data"),
            "OPPORTUNE_CONFIG_HOME": str(root / "config"),
        }
        process = subprocess.Popen(
            [str(_script(venv_dir, "opportune")), "run", "--no-open", "--port", str(port)],
            env=env,
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            try:
                health = _wait(f"http://127.0.0.1:{port}/api/health")
            except Exception as exc:
                if process.poll() is not None and process.stdout:
                    output = process.stdout.read()
                    raise RuntimeError(
                        f"installed server exited before readiness ({process.returncode}):\n{output}"
                    ) from exc
                raise
            if b'"service":"opportune"' not in health.replace(b" ", b""):
                raise RuntimeError("health endpoint did not identify Opportune")
            html = _wait(f"http://127.0.0.1:{port}/")
            assets = re.findall(rb'(?:src|href)="(/assets/[^"]+)"', html)
            if not assets:
                raise RuntimeError("installed dashboard references no packaged assets")
            for asset in assets:
                _wait(f"http://127.0.0.1:{port}{asset.decode('utf-8')}")
            _wait(f"http://127.0.0.1:{port}/favicon.svg")
            for command in (
                ("doctor", "--json"),
                ("privacy", "backup", "--json"),
                ("privacy", "export", "--json"),
            ):
                subprocess.run(
                    [str(_script(venv_dir, "opportune")), *command],
                    check=True,
                    cwd=root,
                    env=env,
                    stdout=subprocess.PIPE,
                )
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            if process.stdout:
                output = process.stdout.read()
                if process.returncode not in {0, -15, 15, 1}:
                    raise RuntimeError(f"server exited unexpectedly ({process.returncode}):\n{output}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("wheel", type=Path)
    args = parser.parse_args(argv)
    smoke(args.wheel)
    print(f"installed wheel smoke passed: {args.wheel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
