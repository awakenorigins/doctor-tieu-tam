# Contributing

Thanks for improving Doctor Tieu Tam.

## Good contributions
- Safer verification steps
- Better redaction patterns
- New known-fix schemas
- Mock SSH/integration tests
- OpenClaw repair playbooks
- Tailscale SSH / ACL improvements

## Development
```bash
python -m py_compile scripts/*.py
python -m pip install pytest
pytest -q
```

## Safety bar
Remote-heal code must be conservative:
- backup before write
- redact secrets
- verify after fix
- dry-run/diff for risky changes
- escalate high-risk operations
