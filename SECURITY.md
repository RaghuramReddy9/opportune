# Security policy

## Supported versions

While Opportune is in the v0.x line, security fixes are provided for the latest released minor version. Older unreleased development snapshots are not supported.

| Version | Supported |
|---|---|
| Latest `0.1.x` | Yes |
| Older versions | No |

## Report a vulnerability privately

Use GitHub Private Vulnerability Reporting on the Opportune repository.

Do not open a public Issue containing:

- credentials or provider tokens;
- a resume or personal job-search data;
- private message content;
- an unpatched exploit or detailed reproduction against a real user;
- absolute private paths or database copies.

Include, when safe:

- affected version or commit;
- impact;
- minimal reproduction using synthetic data;
- expected versus actual behavior;
- suggested mitigation, if known.

If private vulnerability reporting is unavailable, open a public Issue that only asks the maintainer to enable a private reporting channel. Do not include vulnerability details.

## Expected response

The maintainer will aim to:

1. acknowledge a private report within seven days;
2. confirm whether it is reproducible;
3. coordinate a fix and disclosure window;
4. credit the reporter if requested and appropriate.

These are targets, not a commercial service-level agreement.

## Security boundaries

### Local dashboard

Opportune binds to `127.0.0.1` by default. The v0.1 dashboard does not implement multi-user authentication because it is not intended to be exposed to a network.

Binding to `0.0.0.0`, a LAN address, a public interface, or a reverse proxy changes the threat model and is not a supported secure default.

The local API uses trusted-host checks and rejects cross-origin state-changing requests. These controls complement the loopback boundary; they do not turn Opportune into an internet-facing service.

### Local storage

Installed builds store supported state in the operating system's user config/data/cache directories. A source checkout with an existing `config.yaml` preserves its configured `tracker/dashboard.db` location for backward compatibility. Protect the operating-system account and filesystem that contain the database, configuration, backups, and exports.

Backups and exports may contain job-search data. Store and share them accordingly.

### Resume providers

Built-in local analysis does not send resume content to a model provider.

OpenAI, OpenRouter, Ollama, and custom compatible providers are user-selected. Common contact details are removed before remote requests on a best-effort basis, but users must review the provider's privacy terms and endpoint ownership.

Job discovery is separate from resume analysis: it contacts only the public job sources the user enables. Opportune does not claim that all application activity is offline merely because profiles and job state are stored locally.

Provider keys are stored separately with restrictive file permissions, omitted from API responses, and ignored by Git.

### Job sources

Enabled source adapters make outbound requests. API keys belong in `.env`. Health and error output must redact credential-like values.

Opportune must not bypass authentication, CAPTCHAs, rate limits, robots rules, or source restrictions.

### Actions Opportune does not take in v0.1

v0.1 does not:

- submit applications;
- send email;
- monitor Gmail;
- perform outreach;
- write user data to a hosted Opportune service.

## Dependency security

Release candidates run Python and frontend dependency vulnerability scans. A report about a dependency should state whether the vulnerable code path is reachable in Opportune and which fixed version is available.

## Public disclosure

Please allow time for a fix and release before public disclosure. The maintainer will coordinate disclosure after users have a reasonable upgrade path.
