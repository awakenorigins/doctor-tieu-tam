# Security Policy

Doctor Tieu Tam can connect to remote machines and patch OpenClaw configuration. Treat it like an operations tool.

## Supported versions
Security fixes target the latest release.

## Reporting a vulnerability
Open an issue with a minimal reproduction. Do **not** paste real tokens, SSH private keys, cookies, API keys, or bot tokens.

## Safety expectations
- Use operator-provisioned SSH keys only.
- Prefer Tailscale/ private network access.
- Run dry-run/selfcheck first when possible.
- Review diffs for high-risk changes.
- Revoke leaked tokens immediately.

## Secrets
The tool redacts common secret fields, including API keys, access/refresh tokens, authorization headers, cookies, private keys, and session keys. Still, avoid pasting raw production configs into public issues.
