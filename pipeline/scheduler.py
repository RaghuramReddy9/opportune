"""Small local scheduler for recurring discovery runs.

The scheduler owns no background service installation. It can run as a
foreground daemon, a systemd user service, or a one-shot cron task while using
the same durable state and overlap lock.
"""
from __future__ import annotations

import json
import os
import random
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from config import TRACKER_DIR, load_config

DEFAULT_STATE_PATH = TRACKER_DIR / "scheduler-state.json"
DEFAULT_LOCK_PATH = TRACKER_DIR / "scheduler.lock"


@dataclass(frozen=True)
class ScheduleConfig:
    direct_interval_minutes: int = 180
    board_interval_minutes: int = 360
    jitter_minutes: int = 10
    poll_seconds: int = 30


def load_schedule_config(data: dict | None = None) -> ScheduleConfig:
    raw = (data if data is not None else load_config()).get("scheduler", {}) or {}
    return ScheduleConfig(
        direct_interval_minutes=max(30, int(raw.get("direct_interval_minutes", 180))),
        board_interval_minutes=max(60, int(raw.get("board_interval_minutes", 360))),
        jitter_minutes=max(0, min(60, int(raw.get("jitter_minutes", 10)))),
        poll_seconds=max(5, min(300, int(raw.get("poll_seconds", 30)))),
    )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def load_scheduler_state(path: Path = DEFAULT_STATE_PATH) -> dict:
    if not path.exists():
        return {"version": 1, "direct": {}, "board": {}, "board_window_index": 0}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("version", 1)
            data.setdefault("direct", {})
            data.setdefault("board", {})
            data.setdefault("board_window_index", 0)
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {"version": 1, "direct": {}, "board": {}, "board_window_index": 0}


def save_scheduler_state(state: dict, path: Path = DEFAULT_STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def _process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


class SchedulerAlreadyRunning(RuntimeError):
    pass


class SchedulerLock:
    """Atomic PID lock with stale-owner recovery."""

    def __init__(self, path: Path = DEFAULT_LOCK_PATH, *, stale_seconds: int = 7200):
        self.path = path
        self.stale_seconds = stale_seconds
        self.fd: int | None = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for attempt in range(2):
            try:
                self.fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.write(self.fd, json.dumps({"pid": os.getpid(), "created_at": _iso(_utc_now())}).encode())
                return self
            except FileExistsError:
                try:
                    record = json.loads(self.path.read_text(encoding="utf-8"))
                    pid = int(record.get("pid", 0))
                    age = time.time() - self.path.stat().st_mtime
                except (OSError, ValueError, json.JSONDecodeError):
                    pid, age = 0, self.stale_seconds + 1
                if attempt == 0 and age > self.stale_seconds and not _process_alive(pid):
                    try:
                        self.path.unlink()
                    except FileNotFoundError:
                        pass
                    continue
                raise SchedulerAlreadyRunning(f"scheduler lock is held at {self.path}")
        raise SchedulerAlreadyRunning(f"scheduler lock is held at {self.path}")

    def __exit__(self, _exc_type, exc, _tb):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


def _is_due(task_state: dict, now: datetime) -> bool:
    next_run = _parse_iso(str(task_state.get("next_run_at") or ""))
    return next_run is None or next_run <= now


def _default_runner(**kwargs):
    from jobhunt import run_scrape

    return run_scrape(live=True, **kwargs)


def run_scheduled_once(
    *,
    force: bool = False,
    now: datetime | None = None,
    schedule: ScheduleConfig | None = None,
    state_path: Path = DEFAULT_STATE_PATH,
    lock_path: Path = DEFAULT_LOCK_PATH,
    scrape_runner: Callable[..., dict] | None = None,
    jitter_fn: Callable[[int], int] | None = None,
) -> dict:
    """Run every due task once and persist its next due time."""
    current = (now or _utc_now()).astimezone(timezone.utc)
    settings = schedule or load_schedule_config()
    runner = scrape_runner or _default_runner
    choose_jitter = jitter_fn or (lambda upper: random.randint(0, upper))
    try:
        with SchedulerLock(lock_path):
            state = load_scheduler_state(state_path)
            task_specs = (
                ("direct", settings.direct_interval_minutes, "morning"),
                (
                    "board",
                    settings.board_interval_minutes,
                    ("morning", "afternoon", "evening")[int(state.get("board_window_index", 0)) % 3],
                ),
            )
            completed = []
            skipped = []
            for group, interval_minutes, window in task_specs:
                task_state = state.setdefault(group, {})
                if not force and not _is_due(task_state, current):
                    skipped.append(group)
                    continue
                started = _utc_now()
                record = {
                    "group": group,
                    "window": window,
                    "started_at": _iso(started),
                    "status": "completed",
                    "error": "",
                }
                try:
                    result = runner(window=window, source_group=group)
                    record["raw_count"] = int(result.get("raw_count", 0) or 0)
                    record["review_count"] = len(result.get("dashboard_jobs", []))
                    record["failed_sources"] = len(result.get("failed_sources", []))
                except Exception as exc:  # keep the other schedule group healthy
                    record["status"] = "failed"
                    record["error"] = f"{type(exc).__name__}: {exc}"[:1000]
                jitter_seconds = choose_jitter(settings.jitter_minutes * 60)
                next_run = current + timedelta(minutes=interval_minutes, seconds=jitter_seconds)
                record["finished_at"] = _iso(_utc_now())
                record["next_run_at"] = _iso(next_run)
                state[group] = record
                completed.append(record)
                if group == "board":
                    state["board_window_index"] = (int(state.get("board_window_index", 0)) + 1) % 3
                save_scheduler_state(state, state_path)
            return {
                "ok": all(item["status"] == "completed" for item in completed),
                "ran": completed,
                "skipped": skipped,
                "state_path": str(state_path),
            }
    except SchedulerAlreadyRunning as exc:
        return {"ok": False, "already_running": True, "error": str(exc), "ran": [], "skipped": []}


def scheduler_status(
    *,
    state_path: Path = DEFAULT_STATE_PATH,
    lock_path: Path = DEFAULT_LOCK_PATH,
) -> dict:
    state = load_scheduler_state(state_path)
    return {
        "ok": True,
        "running": lock_path.exists(),
        "state": state,
        "config": load_schedule_config().__dict__,
        "state_path": str(state_path),
        "lock_path": str(lock_path),
    }


def run_forever(*, emit: Callable[[dict], None] | None = None) -> None:
    """Run due work forever; intended for a foreground service process."""
    output = emit or (lambda item: print(json.dumps(item), flush=True))
    while True:
        output(run_scheduled_once())
        time.sleep(load_schedule_config().poll_seconds)
