# Opportune Version 1 Source Quality Specification

## 1. Purpose

Measure whether each enabled source reliably produces fresh, valid, relevant and affordable listings that survive Opportune’s ranking and safety gates. Registry entries are configuration, not evidence of live quality.

The workflow remains local-first. It reads public job data externally only when the user runs discovery. Metrics are stored locally and exported only by user action.

## 2. Current evidence

- **Configured coverage — `Verified`:** `source_registry.yaml` contains 71 company entries, 41 enabled: 21 Greenhouse, 17 Ashby, 3 Workable.
- **Runtime local state — `Verified` for one environment:** prior completed run metadata recorded 41 reconciled source scopes and 6,515 observed listings; 6,494 catalog rows were active. This does not prove relevance or current live health.
- **Existing controls — `Partially verified`:** `core/source_health.py:classify_error/cooldown_until_for` stores per-source/global circuit state in `tracker/source_health.json`, with 24-hour cooldowns for blocked/rate-limited responses and six hours for server/timeouts. `core/link_check.py:verify_job_link` verifies TLS, rejects unsafe/placeholder URLs and tries HEAD then GET with a 12-second timeout. HTTP 404/410 are classified as dead; 401/403/429/5xx remain inconclusive. `pipeline/scrape.py`, catalog reconciliation, adapter freshness tests and circuit logic otherwise exist.
- **Gap — `Partially verified`:** no complete persistent per-source request/funnel/latency/parse/dead-link/cost/retention report was found.

No live source requests were initiated for this specification.

## 3. Required labels

Every source/provider shown in configuration, UI and reports carries applicable labels:

- `local`
- `free`
- `free with limits`
- `requires API key`
- `paid`
- `sends resume data externally`
- `reads public job data externally`

Direct ATS boards normally read public data externally and are free unless terms/limits indicate otherwise. Unknown cost is `unknown`, never assumed zero.

## 4. Storage model

Use ordered SQLite migrations and foreign keys. Exact names may adapt to repository conventions, but the semantics are required.

### `source_runs`

| Column | Type | Meaning |
|---|---|---|
| `run_id` | TEXT PK | UUID/ULID |
| `profile_version_id` | TEXT NULL | active approved context; omit/hash in anonymized export |
| `source_id` | TEXT NOT NULL | registry/adapter source identity |
| `adapter_name` | TEXT NOT NULL | adapter class/name |
| `adapter_version` | TEXT NOT NULL | code/config version |
| `query_class` | TEXT NOT NULL | broad role/location strategy identifier |
| `config_hash` | TEXT NOT NULL | sanitized effective config hash |
| `started_at_utc` | TEXT | wall clock |
| `finished_at_utc` | TEXT | wall clock |
| `duration_ms` | INTEGER | monotonic elapsed |
| `status` | TEXT | success/partial/failed/skipped/circuit_open |
| `request_count` | INTEGER | attempted public requests |
| `estimated_cost_amount` | REAL NULL | configured/known estimate |
| `estimated_cost_currency` | TEXT NULL | usually USD |
| `cost_basis` | TEXT | verified_free/configured_rate/provider_reported/unknown |
| `error_category` | TEXT NULL | normalized final category |
| `created_at_utc` | TEXT | record time |

Indexes: `(source_id, started_at_utc)`, `(status, started_at_utc)`, `(profile_version_id, started_at_utc)`.

### `source_requests`

| Column | Type | Meaning |
|---|---|---|
| `request_id` | TEXT PK | stable request record |
| `run_id` | TEXT FK | cascade with run according to retention |
| `source_id` | TEXT | denormalized for reporting |
| `endpoint_class` | TEXT | sanitized domain/path class, no query secrets |
| `method` | TEXT | GET/POST as applicable |
| `started_at_utc` / `finished_at_utc` | TEXT | wall times |
| `duration_ms` | INTEGER | monotonic elapsed |
| `outcome` | TEXT | success/http_error/timeout/network_error/blocked/rate_limited/auth_required |
| `http_status_class` | TEXT NULL | 2xx/3xx/4xx/5xx, exact code only where safe/useful |
| `retry_count` | INTEGER | bounded retries |
| `cache_hit` | INTEGER | boolean |
| `response_bytes` | INTEGER NULL | size only, not body |
| `error_category` | TEXT NULL | taxonomy below |

Never persist request/authorization headers, API keys, full provider responses, resume content or raw prompts.

### `source_results`

One row per run/source:

- `run_id` + `source_id` composite key;
- `raw_count`;
- `parsed_count`;
- `parse_failure_count`;
- `normalized_count`;
- `invalid_url_count`;
- `broad_role_location_count`;
- `date_confirmed_count`;
- `date_unknown_count`;
- `duplicate_count`;
- `unique_count`;
- `ranking_input_count`;
- `ready_count`;
- `review_count`;
- `excluded_count`;
- `persisted_count`;
- `dashboard_visible_count`;
- `missing_count`/`closed_count` from reconciliation;
- timestamps.

### `listing_observations`

| Field | Purpose |
|---|---|
| `observation_id` PK | immutable observation |
| `run_id`, `source_id` FKs | lineage |
| `canonical_listing_id` | normalized identity |
| `source_listing_id` | source identity where available |
| `canonical_url_hash` | dedupe/report identity without exporting raw URL |
| `content_hash` | change/duplicate lineage |
| `normalized_title_hash` / `company_key` | duplicate support |
| `published_at` / `date_confidence` | freshness evidence |
| `observed_at_utc` | snapshot time |
| `lifecycle_state` | active/missing/confirmed_closed/unknown |
| `duplicate_cluster_id` | cluster |
| `final_bucket` | Ready/Review/Excluded |
| `reason_codes_json` | bounded normalized reasons |

Store full listing content only in the existing local job store when product behavior requires it; source metrics need hashes/reason codes, not duplicate response bodies.

### `listing_validation_results`

- `validation_id` PK;
- `canonical_listing_id`;
- `source_id`;
- `checked_at_utc`;
- `cached_until_utc`;
- `status`: `active`, `confirmed_closed`, `http_404`, `http_410`, `redirected`, `timeout`, `blocked`, `rate_limited`, `authentication_required`, `tls_error`, `network_error`, `unknown`;
- `http_status` nullable;
- `final_domain` sanitized;
- `redirect_count`;
- `duration_ms`;
- bounded evidence/reason code.

## 5. Collection methodology

### Instrumentation boundaries

1. `pipeline/scrape.py` creates run records and records the complete discovery funnel.
2. `_execute_source_tasks`/request wrappers record request attempts and normalized outcomes.
3. Every adapter returns a common result envelope: jobs, parse failures, request observations, adapter version, cost basis.
4. Normalization records valid/invalid counts.
5. `core/dedupe.py` returns cluster/action counts.
6. role/location broad filter and ranking record retained counts.
7. catalog reconciliation records missing/closed transitions.
8. responsible link checker records cached validation categories.
9. transactionally finalize run/result rows; a crashed run becomes `failed`/`partial`, never silently successful.

Use monotonic clocks for durations and UTC wall times for reports.

### Query comparability

Store query class and sanitized config hash. Compare sources only over equivalent role/location windows and time periods. Do not compare a nationwide broad source with a narrow metro source as though they received the same query.

### Run types

- `fixture`: deterministic parser/normalization test, no network.
- `pilot_live`: explicitly initiated live quality run.
- `user_discovery`: ordinary approved-profile run.
- `link_validation`: bounded cached lifecycle check.

Reports separate these types.

## 6. Required metrics and formulas

For every enabled source and aggregate period:

1. **Companies/feeds covered:** distinct configured and distinct attempted/successful identities.
2. **Listings discovered:** `raw_count` and `normalized_count`.
3. **Broad-filter pass:** `broad_role_location_count`; rate / normalized.
4. **Confirmed publication-date rate:** `date_confirmed / normalized`.
5. **Unknown-date rate:** `date_unknown / normalized`.
6. **Duplicate rate:** duplicate observations removed/merged divided by normalized observations, reported within-source and cross-source.
7. **Dead-link rate:** confirmed closed/404/410 among listings with a conclusive validation; also report over all checked.
8. **Closed-listing rate:** catalog observations classified confirmed closed / observed listings.
9. **Parsing failure rate:** parse failures / parseable records attempted; define adapter-specific denominator.
10. **Source request failure rate:** failed requests / attempted requests, with category breakdown.
11. **Median response time:** p50 request duration; also p90/p95 and sample count.
12. **Discovery-run duration:** end-to-end monotonic elapsed, median/p90 by run type.
13. **Cost per run:** amount/currency/basis; `unknown` if not known.
14. **Free versus paid coverage:** equivalent-query yield/freshness/reliability/retention and verified/configured cost.
15. **Results retained after ranking/safety:** Ready/Review/Excluded, persisted and dashboard-visible counts/rates.

Also report empty-success rate, circuit skips, redirects, cache hit rate and first-zero funnel stage.

## 7. Failure taxonomy

A source attempt ends in exactly one normalized category:

- `success_with_results`
- `success_empty`
- `partial_parse`
- `parse_failure`
- `timeout`
- `dns_or_network_error`
- `tls_error`
- `http_4xx`
- `http_5xx`
- `rate_limited`
- `blocked_or_challenge`
- `authentication_required`
- `configuration_missing`
- `circuit_open`
- `cancelled_budget`
- `unknown_error`

Partial source failure must not discard successful source results. Error messages and exports are redacted and bounded.

## 8. Freshness methodology

- Prefer explicit structured publication timestamp from source.
- Record raw evidence type and normalized UTC time.
- Do not substitute first-seen date for publication date without labeling it `first_seen`.
- Unknown date remains unknown and is handled by ranking policy/Review.
- Report freshness buckets relative to frozen run time: within user preference, older, unknown.
- Source reports show confirmed/unknown rates and retained Ready/Review counts by freshness state.

## 9. Duplicate methodology

Create stable canonical identifiers using source ID/job ID where reliable, canonicalized URL, company/title/location and content hash. Report:

- exact duplicates;
- cross-source duplicates;
- near-duplicate cluster candidates;
- retained representative rule;
- false merge/split rate from benchmark labels.

Duplicate rate is not automatically bad: cross-source duplication can indicate coverage. The user outcome is one correct representative with preserved source evidence.

## 10. Dead-link and lifecycle validation

- Respect source terms, robots/policies and rate limits.
- Default global/per-domain concurrency and timeout/retry/redirect limits are configuration with tests.
- Cache conclusive and inconclusive outcomes with documented TTLs.
- Prefer source catalog reconciliation over aggressive per-link probing where possible.
- Never bypass CAPTCHA, authentication or anti-bot controls.
- Only explicit source closure, HTTP 404/410 under defined conditions, or validated closed markup can become `confirmed_closed`.
- Timeout, blocking, 401/403, rate limiting, TLS/network error and ambiguous redirect remain Review/unknown—not closed.
- This policy is implemented in `core/link_check.py`: only 404/410 become `dead`; timeout, blocking, 401/403, rate limiting, TLS/network errors, ambiguous redirects and server errors remain inconclusive/unknown.

## 11. Cost reporting

For every source record:

- provider/source label;
- unit/rate and currency where configured;
- requests/credits used if provider reports them;
- estimated cost and basis;
- free-limit assumptions and observation window;
- `unknown` when cost cannot be verified.

Do not infer “free” from the absence of an API key. Direct public ATS reads may be free monetarily but still incur network, terms and reliability costs.

## 12. Free versus paid comparison

Use equivalent query classes, profile constraints and time windows. Publish:

- unique normalized listings;
- broad-filter and Ready/Review retained listings;
- incremental unique retained coverage over free defaults;
- freshness/unknown-date/dead-link/duplicate/failure rates;
- latency/run duration;
- monetary cost and cost per retained useful listing;
- terms/privacy/network labels.

Paid sources are optional and never required for baseline V1 unless free-source coverage fails an explicitly approved release gate.

## 13. Local reports and export

### CLI/API/UI

- `opportune sources report --period 7d --json`
- `GET /api/source-quality?period=7d`
- dashboard source-health section with last success, current failures, yield/freshness and limitations.

### Export

Versioned JSON/CSV written only by explicit user action. Remove profile identity, raw URLs, raw descriptions, request query strings, headers, keys, prompts, resumes, notes and local paths. Include config hashes, aggregate counts and redaction manifest.

### Retention

Keep aggregate run/result records longer than request details. Make retention configurable and document deletion. Vacuum/cleanup must not break job/user state. Exact defaults require maintainer approval after storage-size measurement.

## 14. Provisional quality gates

These gates apply after a minimum evidence window is recorded; small samples remain “insufficient evidence.”

| Gate | Proposed rule |
|---|---|
| Default source request reliability | ≥95% success over at least 20 comparable attempts, otherwise mark experimental/degraded |
| Parsing failure | <5% when denominator ≥100 records; otherwise investigate adapter |
| Date evidence | publish confirmed/unknown rates; sources with high unknown rate cannot place unknown-date jobs in Ready without policy evidence |
| Ready link state | 0 confirmed-closed Ready links in release sample; inconclusive checks are Review/unknown |
| Dead-link rate | ≤5% confirmed dead among conclusive checked retained listings; stricter baseline after measurement |
| Zero retained yield | source with zero broad-filter/Ready/Review yield across 10 comparable successful runs is disabled or justified |
| Secret/privacy | zero keys/headers/resume/prompt/full-response leakage in records/export |
| Cost | no paid/keyed source enabled by default without explicit label/consent; unknown cost cannot be treated as free |
| Partial failure | successful sources remain available and failed source/reason is visible |

Thresholds are proposals. Baseline reports must show distributions before final hard gates are frozen.

## 15. Release evidence

Publish locally and, when approved, publicly:

- registry/config hash and adapter versions;
- observation period and run types;
- per-source metric table with sample counts;
- aggregate free/paid comparison;
- known outages/terms limitations;
- retained-results funnel;
- gate status and reasons;
- report schema/version and code commit.

Do not publish private profile details or identifying local job-search history.

## 16. Known limitations

- Live source behavior changes independently of releases.
- Anti-bot blocking can make link state inconclusive.
- Relevance yield depends on profile/query scope; cross-source comparisons require matched conditions.
- Small employers/feeds may not meet sample thresholds quickly.
- Cost estimates can be stale or provider-specific.
- Configured coverage and one historical local run do not establish long-term reliability.
