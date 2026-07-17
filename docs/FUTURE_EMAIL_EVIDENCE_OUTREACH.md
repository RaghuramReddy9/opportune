# Email evidence and outreach: planned v0.2 design

Status: design only; not included in v0.1
Target: the first release after v0.1, subject to privacy and safety validation

## Why this is deferred

Opportune v0.1 focuses on one complete, trustworthy path:

`resume → approved search profile → job discovery → ranking → local dashboard`

Email monitoring, application evidence, and outreach were removed from v0.1 rather than shipped as partially supported legacy features. They should return only when they share one deliberate schema, one review model, and clear privacy boundaries.

## Product promise

The future workflow may:

- read selected job-related email metadata through a user-approved connection;
- suggest links between a message and a saved job;
- propose an application-status change with supporting evidence;
- prepare a follow-up draft for the user to review.

It must not:

- send email without a separate, explicit user approval;
- treat job alerts or marketing messages as application events;
- change application state from weak or ambiguous evidence;
- store account passwords or provider tokens in SQLite;
- keep complete message bodies by default;
- hide why a status change or draft was suggested.

## Proposed architecture

```text
Email provider
    ↓ read-only OAuth scope
Message adapter
    ↓ normalize + redact
Message observation
    ↓ classify
Evidence candidate
    ↓ link to a saved job
Application event suggestion
    ↓ user review
Verified application event
    ↓ optional follow-up policy
Outreach draft
    ↓ explicit user approval
Provider send action
```

The feature should be additive to `tracker/dashboard.db`. It should not recreate separate `jobs.db`, `evidence.db`, CSV, or Gmail-specific state stores.

Provider behavior belongs behind adapters so Gmail is the first provider, not a permanent assumption in the core model.

## Storage schema

All identifiers are strings unless noted. Timestamps are UTC ISO-8601 values. Every mutable record includes `created_at` and `updated_at`.

### `connected_accounts`

Stores provider connection state. Secrets remain in the operating-system keychain or another configured secret store.

| Field | Purpose |
|---|---|
| `account_id` | Stable local UUID; primary key |
| `provider` | `gmail`, with future adapters allowed |
| `account_label` | User-facing label such as `Personal Gmail` |
| `provider_account_hash` | One-way account identifier; never the raw address unless the user opts in |
| `secret_ref` | Keychain/secret-store reference, not a token |
| `scopes_json` | Granted scopes; read-only by default |
| `connection_state` | `connected`, `expired`, `revoked`, `error` |
| `last_sync_at` | Last completed sync |
| `cursor` | Provider-specific incremental sync cursor |

Constraints:

- unique `(provider, provider_account_hash)`;
- tokens, app passwords, and refresh tokens are forbidden columns;
- send scope is requested only when the user enables sending later.

### `message_observations`

Stores a redacted, idempotent observation of a provider message.

| Field | Purpose |
|---|---|
| `observation_id` | Stable local UUID; primary key |
| `account_id` | Foreign key to `connected_accounts` |
| `provider_message_id_hash` | One-way provider-message identifier |
| `received_at` | Provider message timestamp |
| `sender_domain` | Normalized sender domain |
| `subject_redacted` | Contact details and sensitive tokens removed |
| `body_fingerprint` | Hash used for deduplication; not message content |
| `excerpt_redacted` | Small bounded explanation excerpt; optional |
| `message_kind` | Classification enum below |
| `classification_confidence` | Float from `0.0` to `1.0` |
| `retention_state` | `metadata_only`, `redacted_excerpt`, `deleted` |
| `classifier_version` | Version that produced the classification |

Constraints:

- unique `(account_id, provider_message_id_hash)`;
- no complete message body by default;
- excerpts have a strict size limit and pass redaction before persistence.

`message_kind` values:

- `application_confirmation`
- `assessment_request`
- `interview_request`
- `rejection`
- `offer`
- `withdrawal_confirmation`
- `follow_up_reply`
- `job_alert`
- `marketing`
- `unrelated`
- `unknown`

### `evidence_links`

Represents a proposed or verified relationship between an observation and a saved job.

| Field | Purpose |
|---|---|
| `link_id` | Stable local UUID; primary key |
| `observation_id` | Foreign key to `message_observations` |
| `job_uid` | Foreign key to the v0.1 job record |
| `match_method` | `provider_id`, `apply_url`, `company_role`, or `manual` |
| `match_confidence` | Float from `0.0` to `1.0` |
| `verification_state` | `suggested`, `user_verified`, `rejected`, `superseded` |
| `explanation` | Bounded plain-English reason for the link |
| `verified_at` | Set only after user verification |

Constraints:

- one active verified link per observation unless the provider message explicitly covers multiple jobs;
- company-name overlap alone cannot produce `user_verified`;
- a `job_alert` observation cannot create a lifecycle event.

### `application_events`

Append-only lifecycle ledger. Current job status is a projection of verified events, not a replacement for history.

| Field | Purpose |
|---|---|
| `event_id` | Stable local UUID; primary key |
| `job_uid` | Foreign key to the saved job |
| `link_id` | Optional foreign key to supporting evidence |
| `event_type` | Lifecycle enum below |
| `occurred_at` | Best-known event time |
| `source` | `email`, `manual`, `dashboard`, or `import` |
| `confidence` | Float from `0.0` to `1.0` |
| `verification_state` | `suggested`, `verified`, `rejected`, `disputed` |
| `previous_status` | Status before projection |
| `proposed_status` | Status suggested by this event |
| `explanation` | Plain-English reason and uncertainty |
| `verified_by` | `user` or future authorized reviewer |
| `verified_at` | Set only when verified |

`event_type` values:

- `application_submitted`
- `application_confirmed`
- `assessment_received`
- `interview_requested`
- `offer_received`
- `rejection_received`
- `application_withdrawn`
- `follow_up_sent`
- `reply_received`
- `manual_note`

Rules:

- events are never updated in place to rewrite history; corrections append a superseding event;
- only `verified` events may update the projected job status;
- weak evidence remains `suggested` and leaves job status unchanged;
- irreversible or negative changes require user confirmation.

### `contacts`

Stores recipients only when needed for a draft.

| Field | Purpose |
|---|---|
| `contact_id` | Stable local UUID; primary key |
| `job_uid` | Optional related job |
| `company` | Normalized company name |
| `display_name` | Optional name |
| `role` | Optional role or relationship |
| `email_encrypted` | Encrypted locally; never plaintext in exports by default |
| `provenance` | Where the address came from |
| `verification_state` | `unverified`, `user_verified`, `invalid` |

### `outreach_drafts`

Stores reviewable drafts. Draft creation and sending are separate actions.

| Field | Purpose |
|---|---|
| `draft_id` | Stable local UUID; primary key |
| `job_uid` | Related job |
| `contact_id` | Related verified contact |
| `trigger_event_id` | Event that made follow-up appropriate |
| `purpose` | `application_follow_up`, `thank_you`, or `reply` |
| `subject` | Proposed subject |
| `body` | Proposed body |
| `draft_state` | `draft`, `needs_review`, `approved`, `sent`, `cancelled`, `failed` |
| `generator` | `template`, `local_model`, or named remote provider |
| `scheduled_for` | Optional user-selected send time |
| `approved_at` | Explicit approval timestamp |
| `sent_at` | Provider-confirmed send timestamp |
| `provider_send_id_hash` | Idempotent provider result reference |

Constraints:

- inserting a draft can never send it;
- `approved` must be a separate user action;
- sending requires a verified recipient, explicit send scope, and an approved draft;
- retries use `provider_send_id_hash` to prevent duplicate messages.

### `audit_log`

Records privacy-sensitive and lifecycle-changing actions.

| Field | Purpose |
|---|---|
| `audit_id` | Stable local UUID; primary key |
| `action` | Connection, sync, verification, approval, send, export, or deletion action |
| `entity_type` / `entity_id` | Affected record |
| `actor` | `user`, `scheduler`, or `system` |
| `result` | `success`, `denied`, or `error` |
| `details_redacted` | Bounded non-secret context |
| `created_at` | Action time |

The audit log must never contain tokens, complete message bodies, or plaintext recipient addresses.

## Decision thresholds

Initial thresholds should be conservative and validated against labeled fixtures:

| Confidence | Behavior |
|---|---|
| `< 0.70` | Keep as an observation only |
| `0.70–0.89` | Show a suggested job link or event for review |
| `≥ 0.90` | May preselect a suggestion, but still requires user verification |

No confidence threshold permits automatic sending.

## User flow

1. User connects an account and sees requested scopes before approving.
2. Opportune performs a bounded preview sync and shows what it would retain.
3. User chooses retention: metadata only or redacted excerpts.
4. New observations appear in a review queue.
5. The user confirms or rejects proposed job links and status changes.
6. Follow-up eligibility appears only for verified applications after a user-defined delay.
7. Opportune creates a draft; the user edits and approves it.
8. Sending is a separate action with a final recipient/subject preview.
9. The resulting provider confirmation becomes a verified application event.

## Privacy and security boundaries

- OAuth replaces Gmail app passwords.
- Read-only scope is the default and sufficient for evidence sync.
- Send scope is separate, optional, and requested only when needed.
- Provider tokens live outside SQLite.
- Complete message bodies are processed in memory and discarded by default.
- Export omits recipient addresses and excerpts unless the user explicitly includes them.
- Wipe supports account-only, observation-only, outreach-only, and complete-feature deletion.
- Logs and error messages redact query tokens, addresses, message IDs, and excerpts.
- Remote-model analysis is opt-in and uses the same provider disclosure as resume analysis.

## Release gates

This feature cannot ship until all gates pass:

- job-alert false lifecycle update rate is exactly zero on labeled fixtures;
- no weak evidence changes job status;
- duplicate syncs produce no duplicate observations or events;
- duplicate send attempts produce at most one provider message;
- draft creation cannot invoke the send adapter;
- every send has a stored explicit approval timestamp;
- token, email-address, and message-body leak scans pass;
- account revocation and complete feature wipe are verified end to end;
- migration from a clean v0.1 database is reversible from backup;
- Gmail is implemented through the provider interface, not imported by core lifecycle code.

## Intentionally out of scope for the first return

- autonomous outreach campaigns;
- cold-email address discovery;
- automatic replies;
- automatic application submission;
- background send without an approval screen;
- employer CRM behavior;
- multi-user or hosted account sharing.

These exclusions keep the next release focused on trustworthy evidence and user-reviewed follow-up rather than unsupervised outreach.
