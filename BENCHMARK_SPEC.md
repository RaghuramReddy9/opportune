# Opportune Version 1 Benchmark Specification

## 1. Goals

This benchmark evaluates the complete recommendation pipeline, not only a numerical match score:

```text
profile + listing snapshot
  → normalization
  → role/level/skill/location/work-mode/authorization/freshness/source classification
  → duplicate and lifecycle handling
  → eligibility and safety gates
  → Ready / Review / Excluded
  → explanation
  → ranked candidate set
```

It must answer:

1. Does Opportune surface useful jobs near the top?
2. Does it exclude unsafe/ineligible jobs?
3. Does it abstain to Review when evidence is ambiguous?
4. Does the explanation agree with the actual decision and evidence?
5. Which role, level, source and safety segments fail?

The benchmark is deterministic and no-network. It is separate from local pilot evaluation.

## 2. Current baseline

- **Classification:** `Verified`.
- **Evidence:** `ranking/fixtures/v1_jobs.json` has 16 cases; `ranking/benchmark.py` defines the current runner and four quality gates.
- **Runtime result at audited commit:** 16 fixtures; exact bucket accuracy 0.9375; Apply precision 1.0; surface recall 1.0; unsafe false applies 0; one `apply_now` expected case predicted `watch`.
- **Limitation:** one default profile, no candidate sets/splits/leakage controls/segments/confidence intervals; it is a regression fixture, not the public V1 benchmark.

Keep this suite as `legacy_regression`; do not mix it into the new final test.

## 3. Capability policy

Before dataset freeze, maintainers mark each family:

- `recommendation_supported`
- `classification_only`
- `negative_example_only`
- `unsupported`

Candidate V1 policy:

| Family | Candidate benchmark treatment |
|---|---|
| Applied AI / LLM | recommendation-supported |
| AI/ML engineering | recommendation-supported after segment gate |
| Software engineering | classification/negative until deliberate support is approved |
| Data engineering | classification/negative until deliberate support is approved |
| Product | classification-only unless implemented and gated |
| Analytics | classification-only unless implemented and gated |

Unsupported families must not inflate recommendation metrics, but must test correct classification/exclusion.

## 4. Dataset unit and scenario-derived size

### Unit

The primary unit is a **profile × candidate set × listing snapshot judgment**. A candidate set contains exactly ten listings because Precision@10 cannot be evaluated with fewer. Each row records both component labels and expected final behavior.

### Profile strata

The initial V1 matrix contains eight profile archetypes because this is the smallest set that separately covers the requested role families, realistic positive levels, authorization variation and classification-only families:

1. Applied AI new graduate; sponsorship needed; U.S. flexible.
2. LLM/agent entry-level; no sponsorship needed; remote U.S.
3. AI/ML junior; sponsorship needed; hybrid in a named metro.
4. Software engineering junior; no sponsorship needed; onsite.
5. Data engineering mid-level; no sponsorship needed; hybrid.
6. AI engineering mid-level; ambiguous authorization; remote/hybrid.
7. Product new graduate/entry; classification-only unless support is approved.
8. Analytics entry-level; classification-only unless support is approved.

Profiles contain only synthetic data and the minimum evidence needed for the task.

### Candidate-set themes

Each profile receives four ten-listing candidate sets:

A. Role family, experience and skill evidence.
B. Location, remote/hybrid/onsite and U.S. geography.
C. Authorization/sponsorship, freshness and ambiguity.
D. Source quality, duplicate clusters, closed/dead links and incomplete descriptions.

This yields:

- 8 profiles × 4 candidate sets = 32 candidate sets.
- 32 sets × 10 listing judgments = **320 profile-listing judgments**.
- 6 candidate recommendation profiles × 4 sets × 10 = 240 recommendation judgments.
- 2 classification-only profiles × 4 sets × 10 = 80 classification/safety judgments.

This number is derived from scenario and P@10 requirements, not a round target. If the approved capability matrix changes, recalculate and record the formula rather than preserving 320.

Every candidate set must include a documented mixture of Ready, Review and Excluded labels where semantically possible. Unsupported-profile sets may contain no Ready labels and are excluded from recommendation P@K aggregates.

## 5. Repository architecture

```text
benchmarks/
  README.md
  schemas/
    profile.schema.json
    listing.schema.json
    benchmark_case.schema.json
    prediction.schema.json
    report.schema.json
  datasets/
    development/
      manifest.json
    validation/
      manifest.json
    final_test/
      manifest.json
  labels/
    LABELING_GUIDE.md
    CHANGELOG.md
    adjudications/
  runners/
    run_pipeline.py
    validate_dataset.py
    leakage_check.py
    report.py
  reports/
    .gitkeep
```

`ranking/fixtures/v1_jobs.json` remains separate.

## 6. Case schema

Each judgment must contain:

```json
{
  "case_id": "stable-id",
  "candidate_set_id": "stable-set-id",
  "profile_id": "synthetic-profile-id",
  "listing_id": "stable-snapshot-id",
  "duplicate_cluster_id": null,
  "dataset_version": "1.0.0",
  "schema_version": "1.0.0",
  "labeling_guide_version": "1.0.0",
  "split": "development|validation|final_test",
  "frozen_evaluation_time": "ISO-8601 UTC",
  "profile": {
    "target_role_families": [],
    "target_roles": [],
    "target_levels": [],
    "skills_with_evidence": [],
    "locations": [],
    "work_modes": [],
    "authorization": {},
    "freshness_days": 0,
    "exclusions": []
  },
  "listing": {
    "title": "",
    "company_class": "synthetic|permitted-public",
    "description_or_permitted_snippets": "",
    "location": "",
    "work_mode_claim": "",
    "authorization_text": "",
    "published_at": null,
    "source_type": "",
    "canonical_job_id": "",
    "url_state_fixture": "active|closed|redirected|blocked|unknown"
  },
  "labels": {
    "role_family": "",
    "role_evidence_spans": [],
    "experience_level": "",
    "experience_evidence_spans": [],
    "required_skills": [],
    "preferred_skills": [],
    "matched_skills": [],
    "missing_skills": [],
    "location_compatibility": "compatible|incompatible|ambiguous",
    "work_mode": "remote|hybrid|onsite|ambiguous",
    "authorization": "compatible|incompatible|ambiguous",
    "freshness": "fresh|old|unknown",
    "source_quality": "acceptable|review|unacceptable",
    "duplicate_action": "keep|merge|exclude_duplicate",
    "listing_state": "active|closed|stale|unknown",
    "final_decision": "ready|review|excluded",
    "required_reason_codes": [],
    "forbidden_reason_codes": [],
    "unsafe_to_recommend": false,
    "human_rationale": ""
  },
  "provenance": {
    "kind": "synthetic|licensed|permitted_excerpt",
    "license_or_permission": "",
    "content_hash": "sha256",
    "lineage_ids": []
  },
  "labeling": {
    "labeler_ids": [],
    "adjudicator_id": null,
    "labeled_at": "ISO-8601 UTC",
    "adjudication_record": null
  }
}
```

Names, emails, real resumes, private notes, API keys and unnecessary full job descriptions are prohibited.

## 7. Labeling instructions

### General rules

1. Label without Opportune predictions visible.
2. Use only the frozen profile/listing evidence; do not browse unless a separate provenance task explicitly updates the snapshot before labeling.
3. Mark ambiguity rather than guessing.
4. Cite evidence spans for role, level, skills and authorization.
5. Treat required versus preferred skills separately.
6. Unknown posting date is not fresh.
7. Timeout/blocked/auth-required is not confirmed closed.
8. A duplicate decision is made at cluster level before top-K scoring.
9. Final decision must be derivable from component labels and documented policy.
10. `unsafe_to_recommend=true` when Ready would violate authorization, location, seniority/required-level or confirmed-closed hard constraints.

### Decision labels

- **Ready:** compatible and sufficiently evidenced; no hard conflict; live state acceptable; explanation can be affirmative without hiding uncertainty.
- **Review:** potentially relevant but decisive evidence is ambiguous/incomplete (for example authorization, date, level or description).
- **Excluded:** hard incompatibility, confirmed closed/stale per policy, duplicate not retained, unsupported family where exclusion is intended, or safety conflict.

### Human quality control

- Double-label 100% of final-test judgments.
- Double-label every safety-critical judgment in development/validation.
- Double-label at least 25% of the remaining development/validation judgments using stratified sampling.
- Report agreement by field and segment, not only globally. Use Cohen’s kappa for categorical fields and exact/Jaccard-style agreement for evidence/skill sets.
- Adjudicator sees both labels and evidence, not system prediction.
- Corrections require changelog entry; final-test correction cannot be justified solely by a model/system error.

## 8. Split and contamination prevention

### Assignment

Each of eight profiles has two theme sets in development, one in validation and one in final test:

- Development: 16 candidate sets / 160 judgments.
- Validation: 8 candidate sets / 80 judgments.
- Final test: 8 candidate sets / 80 judgments.

Rotate themes so every split covers role/level/skill, location/work mode, authorization/freshness and source/duplicate/lifecycle overall.

### Cluster-level separation

The following may not cross splits:

- exact content hash;
- canonical job ID;
- duplicate cluster;
- same company plus normalized near-identical title;
- descriptions derived from one source text;
- superficial profile copies;
- synthetic templates with only names/numbers changed.

`leakage_check.py` must use exact hashes, normalized title/company keys, canonical IDs and documented text-similarity thresholds. Final manifest/checksums are frozen. Any membership/content change increments dataset version and records why.

### Tuning policy

- Rules/models may be edited using development data.
- Validation may select thresholds and compare alternatives.
- Final test runs only for a release candidate or documented evaluation event.
- Final-test failures create future development cases from independently authored examples; the failing final examples themselves are not used to tune.

## 9. Metrics and denominators

All reports publish numerator, denominator, point estimate and segment values.

### Ranking

- **Precision@5 / @10:** relevant (`Ready` or useful `Review`) labels among top K, only for recommendation-supported candidate sets.
- **Recall:** true surfaceable (`Ready` or `Review`) listings predicted surfaceable, over all true surfaceable listings.
- **False-positive rate:** true Excluded predicted Ready/Review divided by all true Excluded.
- **False-negative rate:** true Ready/Review predicted Excluded divided by all true Ready/Review.
- **Ready-bucket precision:** true Ready among predicted Ready.
- **Exclusion accuracy:** correct excluded/non-excluded classification over all cases, plus excluded-class recall.
- **Review-bucket usefulness:** predicted Review cases whose true label is Review or Ready-with-documented-ambiguity, divided by predicted Review.
- **Unsafe recommendation rate:** predicted Ready rows with `unsafe_to_recommend=true` divided by all predicted Ready; also report count per all safety opportunities.

### Components

- Role-family accuracy.
- Experience-level accuracy.
- Location compatibility accuracy.
- Work-mode accuracy.
- Authorization accuracy, with ambiguous class preserved.
- Freshness accuracy.
- Duplicate-action accuracy at cluster level.
- Closed/stale/unknown listing-state accuracy.
- Source-quality treatment accuracy.
- Skill-match precision/recall/F1 over labeled normalized skills.
- Missing-skill explanation precision/recall/F1.

### Explanations

**Explanation consistency** requires:

- final decision equals the deterministic policy result from predicted components;
- every required decisive reason appears;
- no forbidden/contradictory reason appears;
- evidence cited by explanation exists in the snapshot;
- uncertainty is stated for Review.

Report exact consistency rate and contradiction count.

### Segment tables

Publish by:

- role family;
- experience level;
- source type;
- authorization state;
- work mode/location type;
- freshness state;
- listing completeness;
- supported versus classification-only capability.

Do not publish a metric for a segment with fewer than the configured minimum without the numerator/denominator and “insufficient sample” warning.

## 10. Confidence intervals

- Bootstrap candidate sets, not individual rows, for P@K/recall/precision and segment metrics; publish 95% percentile intervals and seed.
- Use Wilson or exact binomial intervals for proportions when bootstrap is unsuitable.
- For unsafe recommendation rate, publish a one-sided 95% upper confidence bound even when zero unsafe events are observed.
- Never describe zero observed events as zero true risk.

## 11. Proposed release gates

These are proposals pending baseline review:

| Gate | Proposed threshold |
|---|---:|
| Unsafe recommendations | 0 observed on final test and one-sided 95% upper bound ≤ 5% |
| Ready precision | ≥ 0.95 |
| Precision@5 | ≥ 0.80 |
| Precision@10 | ≥ 0.70 |
| Surface recall | ≥ 0.80 |
| False-positive rate | ≤ 0.10 |
| False-negative rate | ≤ 0.20 |
| Review usefulness | ≥ 0.70 |
| Exclusion accuracy | ≥ 0.90 |
| Role/level/location/authorization/freshness accuracy | each ≥ 0.90 |
| Duplicate-action accuracy | ≥ 0.95 |
| Explanation consistency | ≥ 0.95 and zero safety contradictions |
| Supported segment Ready precision | no segment < 0.90 when sample is sufficient |

A global pass cannot waive an authorization, confirmed-closed, or unsupported-segment safety failure. Threshold changes must be justified before final-test execution and versioned in configuration.

## 12. Reproducibility record

Every run stores/publishes:

- code commit SHA;
- package version;
- dataset/schema/labeling-guide versions;
- all manifest SHA-256 checksums;
- benchmark config and hash;
- random seed;
- frozen evaluation time/timezone;
- Python/dependency lock/platform details;
- raw machine-readable predictions;
- aggregate/segment report;
- gate results and known limitations.

The runner disables network access and uses stored normalized snapshots. A clean checkout with the same lockfile/config must reproduce predictions and metrics exactly where deterministic; any permitted nondeterminism must be named and bounded.

## 13. Failure handling

Dataset validation fails on missing labels, illegal enum/state, missing provenance, cross-split leakage, duplicate IDs, changed frozen checksum, unsupported metric denominator or private-data patterns. A failed benchmark does not overwrite the last published report.

## 14. Known limitations

- Synthetic/permitted snippets may not reproduce every real posting ambiguity.
- Eight profiles cannot represent all candidates or U.S. geographies.
- Final-test confidence for rare safety events remains limited; report bounds.
- Link-state fixtures validate logic, not current internet availability.
- Human labels encode the published V1 policy and may disagree with individual preferences.
- Product/analytics recommendation claims remain excluded unless capability and benchmark support are deliberately added.
