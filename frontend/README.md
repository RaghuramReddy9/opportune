# Opportune frontend

React and TypeScript interface for the local Opportune FastAPI service.

## Screens

- Main dashboard and best matches
- Discover filters
- Review queue and match explanation drawer
- Search profile switching
- Source and local-data settings
- Guided resume onboarding

## Development

From `frontend/`:

```bash
npm ci
npm run dev
```

The Vite development server expects the Opportune API. Start the backend from the project root in another terminal:

```bash
uv run opp start
```

For the production bundle used by FastAPI:

```bash
npm run lint
npm run build
```

Output is written to `frontend/dist/` and included in the Python wheel.

## Structure

| Path | Purpose |
|---|---|
| `src/App.tsx` | Dashboard, discovery, review, profiles, and settings |
| `src/api.ts` | Typed client for supported local API calls |
| `src/index.css` | Main dashboard styles |
| `src/onboarding/` | Approval-gated onboarding flow and styles |
| `public/` | Static icons copied into the production build |

## UI rules

- Keep product copy concise and natural.
- Explain what the user can do, not internal implementation details.
- Keep safety, privacy, uncertainty, and destructive-action wording explicit.
- Do not display provider keys, resume text, or private local paths.
- Do not create a second profile-activation path outside onboarding approval.
- Preserve keyboard labels, dialog roles, and visible focus behavior.
- Treat loading, empty, error, and no-profile states as first-class screens.

## API boundary

The frontend talks only to `/api` on the same local origin. It must not call job sources or model providers directly from the browser.

State-changing API requests are same-origin. Provider secrets are submitted to the local server, stored outside browser state, and never returned.

## Verification

Every frontend change must pass:

```bash
npm run lint
npm run build
```

Visible changes should also be checked in the browser at desktop and narrow/mobile widths. Onboarding changes should be checked both with an empty database and with an existing active profile.
