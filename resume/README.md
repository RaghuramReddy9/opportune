# Resume fallback examples

The files in this directory are generic public examples used by tests, packaging, and fallback matching. Do not replace them with a personal resume or commit personal data here.

## Normal user flow

1. Start the dashboard with `uv run opp start`.
2. Complete guided onboarding.
3. Add a PDF, DOCX, TXT, Markdown, or pasted-text resume.
4. Review the extracted directions and answer five search questions.
5. Approve the final plan.

The approved profile is stored in local SQLite and takes precedence over these example files.

## Why fallback files exist

`resume_profile.py` can still read the checked-in generic profile when no active SQLite profile is available. This keeps tests, package smoke checks, and non-discovery inspection commands deterministic.

Discovery itself requires an approved active profile.

## Privacy

Do not commit:

- personal resumes;
- names, addresses, email addresses, or phone numbers;
- provider keys;
- job-search history.

User-owned onboarding/profile state lives under ignored local storage, primarily `tracker/dashboard.db` and `tracker/onboarding/`.
