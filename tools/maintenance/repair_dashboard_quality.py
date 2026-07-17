"""One-time/cron-safe dashboard quality repair.

Demotes stale scraped discoveries that predate the stricter scoring/location
rules. Does not change user-managed active pipeline statuses.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "tracker" / "dashboard.db"
DIRECT_ATS = {"greenhouse", "ashby", "lever", "workday", "smartrecruiters"}


def repair_dashboard_quality(db_path: Path = DB_PATH) -> dict[str, int]:
    if not db_path.exists():
        return {"missing_db": 1}
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    counts = {"demoted_blank_untrusted": 0, "hidden_blank_direct": 0}
    try:
        rows = conn.execute(
            """
            select job_uid, source, action_tag, resume_match_score, why_risky
            from jobs
            where status = 'discovered' and trim(coalesce(location, '')) = ''
            """
        ).fetchall()
        for row in rows:
            source = (row["source"] or "").lower()
            if source in DIRECT_ATS:
                note = "Hidden from Apply/Watch: direct ATS row has no verified U.S. location yet."
                conn.execute(
                    """
                    update jobs
                    set action_tag = 'skip',
                        resume_match_score = min(resume_match_score, 40),
                        why_risky = case when instr(why_risky, ?) = 0 then trim(? || ' ' || coalesce(why_risky, '')) else why_risky end,
                        date_updated = datetime('now')
                    where job_uid = ?
                    """,
                    (note, note, row["job_uid"]),
                )
                counts["hidden_blank_direct"] += 1
            else:
                note = "Hidden from Apply/Watch: location missing from untrusted board/API source."
                conn.execute(
                    """
                    update jobs
                    set action_tag = 'skip',
                        resume_match_score = min(resume_match_score, 40),
                        why_risky = case when instr(why_risky, ?) = 0 then trim(? || ' ' || coalesce(why_risky, '')) else why_risky end,
                        date_updated = datetime('now')
                    where job_uid = ?
                    """,
                    (note, note, row["job_uid"]),
                )
                counts["demoted_blank_untrusted"] += 1
        conn.commit()
    finally:
        conn.close()
    return counts


if __name__ == "__main__":
    print(repair_dashboard_quality())
