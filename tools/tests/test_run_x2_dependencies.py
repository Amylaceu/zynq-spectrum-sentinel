"""Retries must bind to successful executions of the same deployed files."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from run_x2_board import dependency, accepted_dependency, recoverable_library
from x2_transport import write_evidence, sha


def test_later_successful_attempt_is_selected(tmp_path):
    for attempt, status, deployment in ((1, 'FAIL_EXECUTION', 'a'),
            (2, 'PASS_EXECUTION', 'a'), (3, 'PASS_EXECUTION', 'other')):
        write_evidence(tmp_path/('task_r%d_execution.json' % attempt),
                       dict(status=status, deployment_sha256=deployment))
    path, _ = dependency('task', 'a', tmp_path)
    assert path.name == 'task_r2_execution.json'


def test_other_deployment_cannot_satisfy_prerequisite(tmp_path):
    write_evidence(tmp_path/'task_r1_execution.json',
                   dict(status='PASS_EXECUTION', deployment_sha256='other'))
    with pytest.raises(ValueError, match='No successful'):
        dependency('task', 'a', tmp_path)


def test_new_unaccepted_attempt_does_not_hide_accepted_run(tmp_path):
    for attempt in (1, 2):
        execution = tmp_path/('task_r%d_execution.json' % attempt)
        write_evidence(execution, dict(status='PASS_EXECUTION', deployment_sha256='a'))
    measurement = tmp_path/'task_r1.json'
    write_evidence(measurement, dict(status='completed'))
    write_evidence(tmp_path/'task_r1_acceptance.json', dict(status='PASS',
        measurement_sha256=sha(measurement), execution_sha256=sha(tmp_path/'task_r1_execution.json')))
    path, _ = accepted_dependency('task', 'a', tmp_path)
    assert path.name == 'task_r1_execution.json'


def test_library_after_failed_postflight_can_be_recovered_only_if_unchanged(tmp_path):
    path = tmp_path/'x2_build_library_r1_execution.json'
    write_evidence(path, dict(status='FAIL_EXECUTION', deployment_sha256='a',
        ssh_exit_code=0, library_sha256='lib', original_library_preserved=True,
        original_library_sha256='old'))
    assert recoverable_library('a', 'lib', 'old', tmp_path) == path
    for deployment, library, original in (('b', 'lib', 'old'), ('a', 'changed', 'old'), ('a', 'lib', 'changed')):
        with pytest.raises(ValueError, match='no matching'):
            recoverable_library(deployment, library, original, tmp_path)


def test_screening_never_satisfies_formal_dependency(tmp_path):
    execution = tmp_path/'task_r1_execution.json'
    measurement = tmp_path/'task_r1.json'
    write_evidence(execution, dict(status='PASS_EXECUTION', deployment_sha256='a'))
    write_evidence(measurement, dict(status='completed'))
    write_evidence(tmp_path/'task_r1_acceptance.json', dict(status='PASS_SCREENING',
        measurement_sha256=sha(measurement), execution_sha256=sha(execution)))
    assert accepted_dependency('task', 'a', tmp_path, screening=True)[0] == execution
    with pytest.raises(ValueError, match='No independently accepted'):
        accepted_dependency('task', 'a', tmp_path)
