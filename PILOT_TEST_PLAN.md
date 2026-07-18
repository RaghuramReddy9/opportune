# Opportune Version 1 Local Pilot Test Plan

## 1. Purpose

Validate that real job seekers can install Opportune, complete detailed onboarding, approve an accurate profile, receive useful listings, understand recommendations/privacy, and return to use the product—all without default external analytics.

The pilot is not a substitute for `BENCHMARK_SPEC.md`; it measures usability, trust and outcomes.

## 2. Study design

- **Initial cohort:** 8–12 invited U.S.-focused early-career job seekers.
- **Duration:** moderated first session plus four-week local-use period and exit interview.
- **Product build:** one checksummed release candidate; changes during a cohort require a new cohort/build identifier.
- **Pilot mode:** off by default; explicit local consent; no automatic upload.
- **Compensation/recruitment:** defined by maintainer before recruitment; participation never requires sharing a raw resume with the maintainer.

## 3. Participant criteria

### Include

- Actively or imminently seeking U.S. employment.
- New graduate, entry, junior or selected mid-level candidate in the V1 capability matrix.
- Mix of applied AI/LLM, AI/ML, software and data roles; product/analytics participants only if clearly labeled classification-only or supported.
- Mix of sponsorship needed, not needed and uncertain.
- Mix of remote, hybrid and onsite preferences and U.S. locations.
- Mix of Windows 11, supported macOS and Ubuntu; WSL/Docker reported separately.
- Willing to perform first-run tasks and provide relevance/privacy ratings.

### Exclude or analyze separately

- Senior-only searches when V1 is early-career scoped.
- Non-U.S.-only searches unless capability is approved.
- Participants whose employer/privacy policy prohibits local resume processing.
- Maintainer/developer-only cohort; at least 75% must not have contributed code.

### Cohort balance target

No single OS, authorization state or role family should exceed half the cohort where recruitment permits. Record deviations as limitations rather than silently changing the denominator.

## 4. Privacy and consent safeguards

Before pilot mode starts, show:

> Profiles, jobs, notes, and application data remain on the user’s machine. Resume analysis can remain fully local. When a user intentionally selects an external model provider, necessary resume content may be sent to that provider after best-effort redaction.

Consent must separately cover:

1. Local pilot event recording.
2. Optional remote model provider selection.
3. Optional creation of a sanitized export.
4. Optional sharing of that export with the maintainer.

The participant can inspect, disable and delete pilot metrics at any time. Withdrawal stops future local recording; shared exports already sent cannot be remotely deleted by the app and must follow the study’s stated retention process.

Never record/export:

- name, email, phone, address or account identifiers;
- resume text or extracted evidence spans;
- notes or application details;
- full job descriptions;
- company/title combinations that could identify a participant’s activity;
- raw or identifying job URLs;
- provider keys, headers, prompts or full responses;
- local paths, filenames or machine usernames;
- exact free-text survey responses unless separately reviewed/redacted.

## 5. Local data model

### `pilot_sessions`

- `pilot_session_id` random local UUID;
- `participant_id` random non-account ID;
- `app_version`, `code_sha`, `config_hash`, `benchmark_version`;
- OS family/version/architecture and Python/package method at coarse granularity;
- consent version/timestamp and enabled/disabled timestamps;
- study phase (`moderated`, `field`, `exit`);
- created/finished timestamps.

### `pilot_events`

- `event_id`, `pilot_session_id`;
- `event_type` from allowlist;
- monotonic offset/duration and UTC coarse timestamp;
- integer/boolean counters and normalized reason codes only;
- schema version.

Allowlist includes install result (manual import), launch ready, onboarding section viewed/saved, extracted field corrected/rejected, draft resumed, profile approved, discovery started/completed, first visible listing, listing rated, saved/hidden/applied, repeat run, backup/restore, privacy answer and export created.

### `pilot_ratings`

- top-K relevance judgments using ordinal 1–5 or relevant/not-relevant plus reason category;
- explanation trust 1–5;
- privacy understanding quiz answers;
- onboarding clarity/effort 1–5;
- no raw resume/listing text.

### `pilot_exports`

- export ID/version/time;
- sanitized report hash;
- redaction summary;
- destination is never stored unless user supplies it outside Opportune.

## 6. Moderator setup

1. Give participant the checksummed release artifact and concise install instructions.
2. Start screen/time observation only with separate consent; do not collect raw resume files.
3. Ask participant to use their own device where feasible.
4. Record OS/package method and whether help was required.
5. If seeding a failure, use a safe known issue such as an occupied port or missing browser—not a destructive database condition.
6. Do not coach through normal labels unless the participant is blocked; record assistance.

## 7. Test tasks

### Task A — Install and one-command launch

1. Install from the release artifact without repository knowledge or Node.
2. Run `opportune run`.
3. Confirm the local dashboard opens automatically.
4. Run/observe `opportune desktop` app mode or documented fallback.
5. Diagnose one seeded startup problem using the displayed message/doctor command.

### Task B — Detailed onboarding

1. Read privacy/provider choices.
2. Choose local analysis or intentionally choose a remote provider.
3. Add a resume.
4. Review extracted roles, level, skills/evidence, locations/work modes, authorization, freshness and exclusions.
5. Correct at least one seeded or naturally observed extraction error.
6. Leave and resume the draft.
7. Inspect live effective search-profile preview.
8. Review all assumptions/exclusions and explicitly approve.

### Task C — Discovery and recommendation review

1. Run discovery.
2. If zero results occur, explain the funnel reason and correct the profile if appropriate.
3. Rate top 5 and top 10 visible results.
4. Explain one Ready, Review and Excluded decision.
5. Verify source/freshness/link evidence and uncertainty.

### Task D — Tracking and return use

1. Save one job, hide one irrelevant job and mark one applied if truthful.
2. Restart Opportune and verify state.
3. Run discovery again on a later day.
4. Back up and restore in the moderated safe fixture where supported.
5. Return during the field period and continue normal job search.

### Task E — Privacy and voluntary export

1. State what stays local.
2. State what a selected external model provider may receive.
3. State that public job sources are contacted externally.
4. Inspect local pilot report.
5. Create and inspect anonymized export.
6. Optionally share it using a channel outside the app.
7. Delete/disable pilot metrics.

## 8. Metrics

Each metric publishes numerator/denominator and missing-data count.

1. **Installation success:** participants reaching a valid installed `opportune --help` without maintainer code changes / attempts.
2. **Time to first successful launch:** start of install to healthy opened dashboard; separately command-to-dashboard time after installation.
3. **Onboarding completion rate:** approved profiles / participants who started onboarding.
4. **Onboarding completion time:** active onboarding time excluding deliberate breaks.
5. **Fields corrected after extraction:** corrected/rejected fields and participants with ≥1 correction; do not export values.
6. **Profiles abandoned before approval:** onboarding starts without approval by session/cohort end.
7. **Time to first relevant result:** approval to first participant-rated relevant visible listing; report zero-result cases separately.
8. **Top-5 and top-10 relevance:** participant-labeled relevant listings / rated top K; aggregate by participant first.
9. **Jobs saved:** count and participants saving ≥1.
10. **Jobs hidden as irrelevant:** count and rate among viewed/rated listings.
11. **Jobs marked applied:** count and participants with ≥1 truthful mark.
12. **Repeat discovery runs:** participants with a later distinct run / participants entering field period.
13. **Returning users:** participants with a session on a different calendar day / eligible field participants.
14. **Stale listings avoided:** confirmed stale/closed listings excluded or surfaced with correct warning; benchmark/source evidence plus pilot reports.
15. **Duplicate listings avoided:** duplicate representatives suppressed/merged, with participant duplicate reports.
16. **Applications originating from Opportune:** participant confirms application began from a discovered job; count only, no employer/title.
17. **Trust in explanations:** 1–5 rating after examining Ready/Review/Excluded cases.
18. **Privacy understanding:** percentage correct on local/remote/source/retention questions.

Also report help requests, launch fallback rate, auto-save recovery, location/profile corrections, source failure encounters and accessibility blockers.

## 9. Feedback questions

### Onboarding

- Which question was hardest to understand, and why?
- Did the progress and resume-later behavior feel reliable?
- Which extracted information was wrong or unsupported?
- Did the effective profile match the search you intended?
- Did “why this matters” examples help or add noise?
- Did approval feel meaningful rather than ceremonial?

### Listings and ranking

- How many of the first five and ten would you seriously inspect or apply to?
- What made a listing irrelevant?
- Did any unsafe/ineligible job appear Ready?
- Was Review useful, or did it become a junk bucket?
- Could you tell whether zero/few results came from sources or your profile rules?
- Which explanation increased or reduced trust?

### Launch/install

- Was the one command memorable?
- Did the app-mode/browser fallback meet expectations?
- Were startup errors actionable without developer help?

### Privacy

- What data do you believe stays local?
- What may be sent to a selected external provider?
- What public sources does discovery contact?
- Did you understand and trust the export before sharing?

### Outcome

- Did Opportune change which jobs you considered?
- Did it lead to an application?
- Would you use it next week? Why or why not?

## 10. Export format

```json
{
  "schema_version": "1.0.0",
  "exported_at": "ISO-8601 UTC",
  "participant_id": "random-id",
  "app": {"version": "", "code_sha": "", "config_hash": ""},
  "environment": {"os_family": "", "os_major": "", "architecture": "", "install_method": ""},
  "consent": {"version": "", "local_metrics_enabled_at": ""},
  "durations_seconds": {},
  "counts": {},
  "rates": {},
  "ratings": {},
  "privacy_quiz": {"correct": 0, "total": 0},
  "redaction": {"rules_version": "", "removed_categories": []}
}
```

Export validation rejects unexpected keys and scans for emails, phone patterns, URL/path forms, provider-key shapes and prohibited raw fields. The participant previews exact JSON before writing/sharing it.

## 11. Proposed success thresholds

These are cohort gates, not population estimates:

| Outcome | Success threshold |
|---|---:|
| Install success | ≥90% overall and no OS with repeated release-blocking failure |
| Installed command-to-dashboard | median ≤30 seconds after dependencies installed |
| Onboarding completion | ≥80% |
| Onboarding time | median ≤15 minutes while preserving all mandatory fields |
| Abandonment before approval | ≤20% |
| Draft resume/recovery | 100% of seeded refresh/resume tasks recover latest saved non-conflicting state |
| First relevant result | ≥80% receive one within 10 minutes after approval/discovery completion |
| Top-5 relevance | median participant precision ≥0.60 |
| Top-10 relevance | median participant precision ≥0.50 |
| Unsafe Ready result | 0 observed; any event is release-blocking investigation |
| Returning users | ≥60% of field participants on a different day |
| Repeat discovery | ≥60% |
| Application outcome | ≥50% of participants identify at least one application-worthy result; actual applications reported separately |
| Explanation trust | median ≥4/5 and ≥70% rate 4–5 |
| Privacy understanding | ≥80% answer every core local/remote/source question correctly after onboarding |
| Export privacy | 0 prohibited fields/patterns in validation and manual sample |

With 8–12 participants, confidence is limited; publish raw counts and do not over-generalize.

## 12. Failure thresholds and response

Stop or block release when:

- any P0 security/privacy/destructive issue is observed;
- an unapproved profile initiates source requests;
- any clearly authorization/location/closed incompatible listing appears Ready;
- participant export contains identity, resume, job URL, notes, key, prompt/response or local path;
- a supported OS repeatedly cannot install/launch;
- zero-result cases cannot identify the failed funnel stage;
- data loss occurs during save/restart/backup/restore.

Return to improvement work when onboarding, relevance, trust, privacy understanding or return-use thresholds fail. Do not add sources or AI until the observed bottleneck is identified.

## 13. Reporting

Publish a cohort report with build/checksum, participant matrix, task success, all metrics/denominators, assist rates, failure narratives, privacy incidents, limitations and prioritized changes. Do not publish participant-level identifying combinations or raw free text.
