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


# --- H1: heal/write path shares hardened detect_os ---
def test_heal_detect_os_is_hardened(monkeypatch):
    import sys
    heal = load('openclaw_heal')
    dc = sys.modules.get('common') or sys.modules.get('_doctor_common')
    monkeypatch.setattr(dc, 'run_remote', lambda *a, **k: (255, '', 'Permission denied (publickey).'))
    assert heal.detect_os('x@y', None) == 'auth_failed'


# --- H2: restart judged by real evidence, not masked rc ---
def test_restart_reports_failure_without_evidence(monkeypatch):
    import sys
    heal = load('openclaw_heal')
    dc = sys.modules.get('common') or sys.modules.get('_doctor_common')
    monkeypatch.setattr(heal, 'run_remote', lambda *a, **k: (0, '', ''))
    monkeypatch.setattr(dc, 'run_remote', lambda *a, **k: (0, '', ''))
    ok, _ = heal.restart_gateway('x@y', None, 'linux')
    assert ok is False


def test_restart_reports_success_with_port_evidence(monkeypatch):
    heal = load('openclaw_heal')

    import sys
    dc = sys.modules.get('common') or sys.modules.get('_doctor_common')

    def fake(target, key, cmd, timeout=40):
        if 'ss -ltn' in cmd:
            return (0, 'PORT_18789=listen', '')
        return (0, '', '')

    monkeypatch.setattr(heal, 'run_remote', fake)
    monkeypatch.setattr(dc, 'run_remote', fake)
    ok, ev = heal.restart_gateway('x@y', None, 'linux')
    assert ok is True
    assert 'PORT_18789=listen' in ev


# --- H3: redaction catches prefixed key names and in-value secrets ---
def test_redact_prefixed_and_value_secrets():
    heal = load('openclaw_heal')
    obj = {
        'openaiApiKey': 'sk-LIVE0123456789',
        'nested': {'botToken': 'abc'},
        'url': 'https://api.example/cb?token=SUPERSECRETVALUE&safe=1',
        'plain': 'just a normal string',
    }
    red = heal.redact(obj)
    assert red['openaiApiKey'] == '***REDACTED***'
    assert red['nested']['botToken'] == '***REDACTED***'
    assert 'SUPERSECRETVALUE' not in red['url']
    assert 'safe=1' in red['url']
    assert red['plain'] == 'just a normal string'
