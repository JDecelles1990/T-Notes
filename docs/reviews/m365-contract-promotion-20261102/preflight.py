"""Read-only identity verification and promotion-entry inventory; no promotion."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PROPOSAL = ROOT / 'docs/planning/m365/03_codex_reviews/architecture-contract-proposal-20261102'
TARGET = ROOT / 'docs/contracts/m365'
ENGINE = ROOT / 'docs/planning/m365/offline-execution-engine-prototype'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    report = json.loads((PROPOSAL / 'validation/correction-results.json').read_text(encoding='utf-8'))
    artifacts = report['artifacts']
    checks = [{'path': row['path'], 'expected': row['sha256'], 'actual': sha(PROPOSAL / row['path'])}
              for row in artifacts]
    paths = subprocess.check_output(['git', 'ls-files', '--cached', '--others', '--exclude-standard'], cwd=ROOT, text=True).splitlines()
    files = {p: sha(ROOT / p) for p in paths if (ROOT / p).is_file() and not p.startswith(HERE.relative_to(ROOT).as_posix() + '/')}
    index_name = subprocess.check_output(['git', 'rev-parse', '--git-path', 'index'], cwd=ROOT, text=True).strip()
    index = ROOT / index_name
    intended = [p.relative_to(ROOT).as_posix() for p in TARGET.rglob('*') if p.is_file() and
                p.suffix in ('.md', '.json', '.py') and not p.name.startswith(('correction-results', 'results'))
                and p.name not in ('source-snapshot.json', 'correction-baseline.json', 'CONTRACT_CORRECTION_HANDOFF.md', 'CHECKPOINT.md')]
    intended += ['AGENTS.md', 'GEMINI.md', 'scripts/m365/README.md']
    state = {'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
             'branch': subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT, text=True).strip(),
             'index_sha256': sha(index), 'files': files, 'intended_existing_changes': sorted(intended),
             'proposed_artifacts': checks,
             'proposed_artifact_verification': 'PASS' if all(c['expected'] == c['actual'] for c in checks) else 'FAIL',
             'independent_full_review': 'NOT LOCATED; requested from user',
             'concurrent_drift_since_framework_entry': []}
    prior = json.loads((ROOT / 'scripts/m365/tooling/operation-validation/entry-preservation.json').read_text(encoding='utf-8-sig'))
    state['concurrent_drift_since_framework_entry'] = [p for p, expected in prior['files'].items()
          if not (ROOT / p).is_file() or sha(ROOT / p) != expected]
    output = HERE / 'entry-state.json'
    with output.open('x', encoding='utf-8') as stream:
        json.dump(state, stream, indent=2)
    print(json.dumps({'proposed_artifact_verification': state['proposed_artifact_verification'],
                      'artifact_count': len(checks), 'entry_files': len(files),
                      'concurrent_drift': state['concurrent_drift_since_framework_entry']}))
    return 0 if state['proposed_artifact_verification'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
