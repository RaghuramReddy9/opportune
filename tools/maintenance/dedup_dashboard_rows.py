"""Merge duplicate company+title rows in dashboard.db.

Keeps the row with the highest resume_match_score and best apply_url.
Remaining duplicates are deleted. This is a one-time repair; the new
upsert logic prevents future duplicates.
"""
import sqlite3
import json

conn = sqlite3.connect("tracker/dashboard.db")
conn.row_factory = sqlite3.Row

# Find all duplicate (company, title) groups where status='discovered'
rows = conn.execute("""
    SELECT job_uid, company, title, apply_url, source, resume_match_score,
           location, action_tag, why_risky, date_discovered
    FROM jobs WHERE status='discovered'
    ORDER BY LOWER(company), LOWER(title), resume_match_score DESC
""").fetchall()

groups = {}
for r in rows:
    key = (r["company"].strip().lower(), r["title"].strip().lower())
    groups.setdefault(key, []).append(r)

deleted = 0
kept = 0
merged_count = 0

for key, entries in groups.items():
    if len(entries) <= 1:
        continue
    merged_count += 1
    # Pick best entry: prefer one with a URL, then highest score
    def sort_key(e):
        has_url = 1 if (e["apply_url"] or "").strip() else 0
        return (has_url, e["resume_match_score"] or 0)
    entries.sort(key=sort_key, reverse=True)
    keep = entries[0]
    duplicates = entries[1:]
    # Merge why_risky and source from duplicates into the kept row
    sources = {e["source"] for e in entries if e["source"]}
    all_notes = "\n".join(e["why_risky"] for e in entries if e["why_risky"])
    conn.execute(
        "UPDATE jobs SET source=?, why_risky=? WHERE job_uid=?",
        ("+".join(sorted(sources)) if len(sources) > 1 else keep["source"],
         all_notes or keep["why_risky"],
         keep["job_uid"])
    )
    kept += 1
    # Delete duplicates
    for dup in duplicates:
        conn.execute("DELETE FROM jobs WHERE job_uid=?", (dup["job_uid"],))
        deleted += 1

conn.commit()

# Re-count
stats = {}
for row in conn.execute("SELECT action_tag, count(*) c FROM jobs WHERE status='discovered' GROUP BY action_tag"):
    stats[row["action_tag"]] = row["c"]
total = conn.execute("SELECT count(*) FROM jobs WHERE status='discovered'").fetchone()[0]
conn.close()

print(json.dumps({
    "merged_groups": merged_count,
    "rows_kept": kept,
    "rows_deleted": deleted,
    "discovered_after": total,
    "stats": stats,
}))