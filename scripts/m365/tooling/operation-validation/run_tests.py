"""Run fixed framework tests and preserve a unique report for every attempt."""
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
import uuid
import validate_operation as v


def main():
    import test_validator
    destination = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else v.HERE / 'evidence'
    destination.mkdir(parents=True, exist_ok=True)
    stamp = v.utc().replace(':', '').replace('-', '') + '-' + uuid.uuid4().hex[:8]
    log = io.StringIO()
    result = unittest.TextTestRunner(stream=log, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(test_validator))
    pwsh = shutil.which('pwsh')
    pester = {'status': 'NOT RUN', 'reason': 'PowerShell unavailable'}
    if pwsh:
        path = destination / f'pester-{stamp}.json'
        run = subprocess.run([pwsh, '-NoLogo', '-NoProfile', '-NonInteractive', '-File',
                              str(v.HERE / 'Run-FrameworkTests.ps1'), '-ReportPath', str(path)],
                             capture_output=True, text=True, encoding='utf-8', timeout=90)
        pester = v.read(path) if path.exists() else {'status': 'FAIL', 'exit_code': run.returncode}
    report = {'scope': 'SYNTHETIC_FRAMEWORK_TESTS_ONLY', 'tests_run': result.testsRun,
              'failures': len(result.failures), 'errors': len(result.errors), 'skipped': len(result.skipped),
              'python': sys.version, 'pester': pester, 'test_log': log.getvalue(),
              'source_hashes': {p.name: v.digest(p) for p in v.HERE.iterdir() if p.suffix in ('.py', '.ps1')},
              'status': 'FAIL' if not result.wasSuccessful() or pester['status'] == 'FAIL' else
                        'NOT RUN' if pester['status'] == 'NOT RUN' else 'PASS'}
    path = destination / f'tests-{stamp}.json'
    v.save_report(report, path, (test_validator.REFERENCE, test_validator.CONTRACT))
    print(json.dumps({'report': str(path), 'tests': result.testsRun, 'status': report['status'], 'pester': pester}))
    return {'PASS': 0, 'FAIL': 1, 'NOT RUN': 2}[report['status']]


if __name__ == '__main__':
    sys.exit(main())
