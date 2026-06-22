# Example: Windows PC health check

```bash
python3 scripts/doctor.py connect-test --target admin@100.86.14.12 --key ~/.ssh/doctor_tt
python3 scripts/doctor.py health --target admin@100.86.14.12 --key ~/.ssh/doctor_tt
python3 scripts/doctor.py scan --target admin@100.86.14.12 --key ~/.ssh/doctor_tt
```

Sample output:

```json
{
  "target": "admin@100.86.14.12",
  "os": "windows",
  "metrics": "CPU:9 MEM:16"
}
```

```json
{
  "findings": {
    "raw": "TASKS:OpenClaw Gateway=Running\nPORTS:18789"
  }
}
```
