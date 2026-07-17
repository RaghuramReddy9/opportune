## What changed?

Describe the user problem and the smallest complete solution.

Fixes #

## Boundaries

- [ ] No new network or external-write boundary
- [ ] No new secret, resume, or personal-data storage
- [ ] Any new boundary is explained below and approved in the linked Issue

Boundary notes:

## Verification

List exact commands and manual checks run.

```text
uv run ruff check .
uv run pytest -q
uv run opp quality --json
cd frontend && npm run lint && npm run build
```

## UI changes

- [ ] No visible UI change
- [ ] Screenshot or recording attached
- [ ] Loading, empty, error, keyboard, and narrow-width states checked

## Contributor checklist

- [ ] The change is focused and does not include unrelated refactoring.
- [ ] Tests cover new or changed behavior.
- [ ] Existing safety and privacy gates were not weakened.
- [ ] User-facing copy is concise and natural.
- [ ] Documentation and examples match the implementation.
- [ ] No secrets, personal data, local databases, exports, or private paths are included.
- [ ] I reviewed `CONTRIBUTING.md`, `SECURITY.md`, and `CODE_OF_CONDUCT.md`.
