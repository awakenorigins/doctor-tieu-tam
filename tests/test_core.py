import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / f'{name}.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_redact_extended_secret_keys():
    heal = load('openclaw_heal')
    obj = {
        'apiKey': 'x',
        'access_token': 'x',
        'refreshToken': 'x',
        'clientSecret': 'x',
        'authorization': 'Bearer x',
        'privateKey': 'x',
        'safe': 'ok',
    }
    red = heal.redact(obj)
    assert red['safe'] == 'ok'
    assert all(red[k] == '***REDACTED***' for k in obj if k != 'safe')


def test_known_fix_regex_scores_high():
    doctor = load('doctor')
    fix = {'patternRegex': 'Codex.*usage limit', 'confidence': 0.91}
    assert doctor.score_fix('still reports Codex subscription usage limit', fix) == 0.91


def test_detect_os_does_not_assume_windows_on_auth_failure(monkeypatch):
    doctor = load('doctor')
    monkeypatch.setattr(doctor, 'run_remote', lambda *a, **k: (255, '', 'Permission denied (publickey).'))
    assert doctor.detect_os('x@y', None) == 'auth_failed'
