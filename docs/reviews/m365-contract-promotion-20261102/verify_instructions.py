"""Verify mandatory root references and preservation of pre-existing rules."""
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BACKUP = Path('C:/Dev/TNotes-ReviewBackups/M365-ContractPromotion-20261102-2108')
checks = []
for name in ('AGENTS.md', 'GEMINI.md'):
    text = (ROOT / name).read_text(encoding='utf-8')
    old = (BACKUP / name).read_text(encoding='utf-8')
    for required in ('Every future M365 PowerShell operation must use the official',
                     'docs/contracts/m365/CONTRACT.md', 'tnotes.m365 / 0.3.0',
                     'APPROVED — IMPLEMENTATION CONTRACT', 'approval record',
                     'ABI', 'manifest validity', 'authentication', 'trust requirements',
                     'permissions/RBAC', 'operation-specific tests', 'independent approval',
                     'F7Hub', 'PySide6', 'SQLite', 'separate authorization'):
        checks.append({'name': name + ': ' + required, 'status': 'PASS' if required in text else 'FAIL'})
    for link in re.findall(r'\[[^\]]+\]\(([^)]+)\)', text):
        if '://' not in link:
            checks.append({'name': name + ': link ' + link, 'status': 'PASS' if (ROOT / link).exists() else 'FAIL'})
    if name == 'AGENTS.md':
        preserved = text.startswith(old.rstrip())
    else:
        old_prefix, old_tail = old.split('The intended canonical contract location is docs/contracts/m365/.', 1)
        old_tail = old_tail.split('Confirm the actual files and version read before coding.', 1)[1]
        preserved = text.startswith(old_prefix.replace('Instruction revision: 1', 'Instruction revision: 2')) and text.endswith(old_tail)
    checks.append({'name': name + ': existing rules preserved', 'status': 'PASS' if preserved else 'FAIL'})
report = {'status': 'PASS' if all(c['status'] == 'PASS' for c in checks) else 'FAIL', 'checks': checks,
          'files': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in ('AGENTS.md', 'GEMINI.md')},
          'official_contract_promotion': 'PENDING; canonical CONTRACT.md still declares proposed version',
          'scope': 'Documentation references only; no promotion or operation execution'}
with (HERE / 'instruction-verification.json').open('x', encoding='utf-8') as stream:
    json.dump(report, stream, indent=2)
print(json.dumps({'status': report['status'], 'checks': len(checks)}))
raise SystemExit(0 if report['status'] == 'PASS' else 1)
