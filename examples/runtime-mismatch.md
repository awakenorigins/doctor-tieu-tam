# Example: selected Claude model but Codex usage limit appears

## Symptom
The bot reports the selected model as:

```text
claudekkg/cc/claude-opus-4-8
```

But messages fail with:

```text
You've reached your Codex subscription usage limit
```

## Diagnosis
Model selection changed, but the runtime/harness did not. The session still used the Codex harness, so no request reached the Claude/OpenAI-compatible proxy.

## Fix
```bash
python3 scripts/openclaw_heal.py set-runtime --target admin@100.86.14.12 \
  --provider claudekkg --runtime openclaw --key ~/.ssh/doctor_tt
python3 scripts/openclaw_heal.py restart --target admin@100.86.14.12 --key ~/.ssh/doctor_tt
```

## Verification
```bash
python3 scripts/doctor.py verify --target admin@100.86.14.12 --key ~/.ssh/doctor_tt
```

Expected evidence includes:

```json
{
  "os": "windows",
  "checks": ["GATEWAY_TASK=Running", "PORT_18789=listen"],
  "ok": true
}
```
