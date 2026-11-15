"""Pinned mini-SWE-agent Docker runtime smoke, with the upstream deterministic model.

This exercises the real upstream agent control loop, but NOT an actual LLM.
No private source, network access from sandbox, production data or secrets.
"""
from __future__ import annotations

import json
import os
import subprocess

from minisweagent import __version__
from minisweagent.agents.default import DefaultAgent
from minisweagent.environments.docker import DockerEnvironment
from minisweagent.models.test_models import DeterministicModel, make_output

FIXTURE = """cat > /work/test_solution.py <<'PY'
import unittest
from solution import add

class TestAddition(unittest.TestCase):
    def test_positive(self): self.assertEqual(add(2, 3), 5)
    def test_negative(self): self.assertEqual(add(-2, 1), -1)
    def test_zero(self): self.assertEqual(add(0, 0), 0)

if __name__ == '__main__':
    unittest.main()
PY"""

BAD = """cat > /work/solution.py <<'PY'
def add(a: int, b: int) -> int:
    return a - b
PY"""

GOOD = """cat > /work/solution.py <<'PY'
def add(a: int, b: int) -> int:
    return a + b
PY"""

NET_PROBE = """python3 - <<'PY'
import socket
try:
    socket.create_connection(('1.1.1.1', 80), timeout=0.5)
except OSError:
    print('NETWORK_DENIED=PASS')
else:
    raise SystemExit('NETWORK_DENIED=FAIL')
PY"""


def assert_isolation(container_id: str) -> None:
    spec = json.loads(subprocess.check_output(
        ['docker', 'inspect', container_id], text=True
    ))[0]
    host = spec['HostConfig']
    assert host['NetworkMode'] == 'none'
    assert host['ReadonlyRootfs'] is True
    assert host['Privileged'] is False
    assert 'ALL' in {x.upper() for x in host['CapDrop']}
    assert 'no-new-privileges' in host['SecurityOpt']
    assert host['PidsLimit'] == 48
    assert host['Memory'] == 256 * 1024 * 1024
    assert not host.get('Binds'), 'host volume binds forbidden'
    assert spec['Config']['User'] == '65532:65532'
    # Docker --tmpfs declarations are represented in HostConfig.Tmpfs;
    # Mounts normally lists volumes/bind mounts instead.
    tmpfs = host.get('Tmpfs') or {}
    assert '/work' in tmpfs, tmpfs
    assert 'uid=65532' in tmpfs['/work'] and 'gid=65532' in tmpfs['/work'], tmpfs
    assert '/tmp' in tmpfs, tmpfs
    print('SANDBOX_BOUNDARY=PASS')


def main() -> None:
    env = DockerEnvironment(
        image=os.environ['PANAM_SYNTHETIC_IMAGE'],
        cwd='/work',
        timeout=20,
        container_timeout='8m',
        run_args=[
            '--rm', '--network=none', '--ipc=none', '--read-only',
            '--cap-drop=ALL', '--security-opt=no-new-privileges',
            '--pids-limit=48', '--memory=256m', '--cpus=1',
            '--user=65532:65532',
            '--tmpfs=/work:rw,nosuid,nodev,size=32m,uid=65532,gid=65532',
            '--tmpfs=/tmp:rw,nosuid,nodev,size=16m',
        ],
    )
    try:
        assert env.container_id is not None
        assert_isolation(env.container_id)
        p = env.execute({'command': NET_PROBE})
        assert p['returncode'] == 0 and 'NETWORK_DENIED=PASS' in p['output'], p
        print('NETWORK_DENIED=PASS')
        fixture = env.execute({'command': FIXTURE})
        assert fixture['returncode'] == 0, fixture

        model = DeterministicModel(
            cost_per_call=0,
            outputs=[
                make_output('Create deliberately faulty solution', [{'command': BAD}], cost=0),
                make_output('Run RED tests', [{'command': 'python3 -m unittest -v test_solution.py'}], cost=0),
                make_output('Correct implementation', [{'command': GOOD}], cost=0),
                make_output('Run GREEN tests', [{'command': 'python3 -m unittest -v test_solution.py'}], cost=0),
                make_output('Submit', [{'command': "printf 'COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT\\nSYNTHETIC_AGENT_TASK=PASS\\n'"}], cost=0),
            ],
        )
        agent = DefaultAgent(
            model, env,
            system_template='You are executing synthetic-only experiment actions.',
            instance_template='Synthetic task: {{ task }}',
            step_limit=6,
            wall_time_limit_seconds=150,
            cost_limit=0,
        )
        result = agent.run('Implement and test pure function add(a, b).')
        observations = [
            m['extra'] for m in agent.messages
            if m['role'] == 'user' and 'returncode' in m.get('extra', {})
        ]
        assert len(observations) == 4, observations
        assert [x['returncode'] for x in observations][0] == 0
        assert observations[1]['returncode'] != 0 and 'FAILED' in observations[1]['raw_output']
        assert observations[2]['returncode'] == 0
        assert observations[3]['returncode'] == 0 and 'OK' in observations[3]['raw_output']
        assert result['exit_status'] == 'Submitted', result
        assert 'SYNTHETIC_AGENT_TASK=PASS' in result['submission']
        assert agent.n_calls == 5
        assert __version__ == '2.4.6'
        print('UPSTREAM_MINI_SWE_VERSION=' + __version__)
        print('AGENT_MODEL=UPSTREAM_DETERMINISTIC_NO_LLM')
        print('TDD_RED=PASS expected_test_failure=YES')
        print('TDD_GREEN=PASS tests=3')
        print('MINI_SWE_RUNTIME=PASS steps=5')
        print('PRIVATE_CODE_ACCESS=NO')
        print('PRODUCTION_ACCESS=NO')
    finally:
        if env.container_id:
            subprocess.run(
                ['docker', 'rm', '-f', env.container_id],
                text=True, capture_output=True, timeout=30
            )


if __name__ == '__main__':
    main()
