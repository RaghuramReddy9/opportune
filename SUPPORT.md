# Support

Opportune is an open-source local application maintained on a best-effort basis. It does not include paid support or a guaranteed response time.

## Before asking for help

1. Read `README.md` and run:

   ```bash
   uv run opp doctor --json
   ```

2. Search existing GitHub Issues.
3. Confirm the problem still occurs on the latest release.
4. Reduce it to a minimal reproduction with synthetic data.
5. Remove API keys, resume text, personal job-search records, and private paths.

## Choose the right channel

### Bug

Use the **Bug report** Issue form for reproducible broken behavior.

Include the Opportune version, environment, expected behavior, actual behavior, and safe reproduction steps.

### Feature idea

Use the **Feature request** form. Explain the user problem before proposing an implementation.

### New job source

Use the **Job source request** form. Include official access documentation, terms, rate limits, and whether an API key or paid account is required.

### Security issue

Do not open a public Issue. Use GitHub Private Vulnerability Reporting and follow `SECURITY.md`.

## What maintainers can help with

- installation and supported configuration;
- reproducible defects;
- source-adapter behavior;
- ranking and safety regressions;
- privacy or local-data behavior;
- contributor setup and focused PRs.

## What maintainers cannot provide

- personalized career, immigration, legal, or financial advice;
- review of a private resume through a public Issue;
- API keys or paid source accounts;
- help bypassing authentication, CAPTCHAs, rate limits, robots directives, or source terms;
- guarantees that a listing is current, legitimate, or suitable;
- recovery of local data without an available backup.

## Response expectations

Issues are triaged by impact, reproducibility, safety, and maintainer capacity. A concise reproduction with tests or a focused PR is usually the fastest path to resolution.
