"""Record local public synthetic checks without third-party dependencies.

The RED mode copies unchanged tests into a temporary package with the retained
inert stub. It never replaces the working implementation. RED is an expected
negative control, not a failed model implementation or a repair demonstration.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / 'work_agent_pilot' / 'evidence'
COMMANDS = {
    'red': [sys.executable, '-B', '-m', 'unittest', '-v',
            'work_agent_pilot.test_dependencies'],
    'green': [sys.executable, '-B', '-m', 'unittest', '-v',
              'work_agent_pilot.test_dependencies'],
    'root': [sys.executable, '-B', '-m', 'unittest', 'discover', '-v'],
    'smoke': [sys.executable, '-B', 'checks/public_smoke.py'],
    'gate': [sys.executable, '-B', 'checks/publication_gate.py'],
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(mode, output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    inputs = [ROOT / 'work_agent_pilot' / name for name in
              ['SPEC.md', '__init__.py', 'test_dependencies.py',
               'evidence/record_run.py', 'evidence/inert_stub.txt']]
    inputs += [ROOT / name for name in
               ['work_agent_pilot/dependencies.py', 'work_agent_pilot/README.md',
                '.github/workflows/work-agent-pilot.yml',
                'checks/public_smoke.py', 'checks/publication_gate.py']
               if (ROOT / name).exists()]
    hashes = {str(path.relative_to(ROOT)): digest(path) for path in inputs}
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT,
                                   text=True).strip()
    with tempfile.TemporaryDirectory(prefix='work-agent-synthetic-') as temporary:
        cwd = ROOT
        if mode == 'red':
            cwd = Path(temporary)
            package = cwd / 'work_agent_pilot'
            package.mkdir()
            for name in ['__init__.py', 'test_dependencies.py']:
                shutil.copyfile(ROOT / 'work_agent_pilot' / name, package / name)
            shutil.copyfile(EVIDENCE / 'inert_stub.txt', package / 'dependencies.py')
        started = datetime.now(timezone.utc).isoformat()
        begin = time.perf_counter()
        result = subprocess.run(COMMANDS[mode], cwd=cwd, capture_output=True,
                                timeout=120, check=False)
        duration = time.perf_counter() - begin
    stdout = output_dir / f'{mode}.stdout.txt'
    stderr = output_dir / f'{mode}.stderr.txt'
    stdout.write_bytes(result.stdout)
    stderr.write_bytes(result.stderr)
    receipt = {
        'schema': 'work-agent-pilot.execution.v1',
        'data_class': 'PUBLIC_SYNTHETIC',
        'author': 'Work coding agent',
        'mode': mode,
        'synthetic_negative_control': mode == 'red',
        'command_argv': COMMANDS[mode],
        'cwd': 'temporary synthetic package' if mode == 'red' else 'repository root',
        'started_at_utc': started,
        'duration_seconds': duration,
        'exit_code': result.returncode,
        'git_head_before_run': head,
        'python_version': sys.version,
        'input_sha256': hashes,
        'subject_sha256': hashes['work_agent_pilot/evidence/inert_stub.txt'
                                  if mode == 'red' else 'work_agent_pilot/dependencies.py'],
        'stdout': {'file': stdout.name, 'sha256': digest(stdout)},
        'stderr': {'file': stderr.name, 'sha256': digest(stderr)},
    }
    (output_dir / f'{mode}.receipt.json').write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps({'mode': mode, 'exit_code': result.returncode,
                      'duration_seconds': duration}, sort_keys=True))
    sys.stdout.flush()
    sys.stdout.buffer.write(result.stdout)
    sys.stderr.buffer.write(result.stderr)
    return result.returncode


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=COMMANDS)
    parser.add_argument('--output-dir', type=Path, default=EVIDENCE)
    args = parser.parse_args()
    raise SystemExit(run(args.mode, args.output_dir))
