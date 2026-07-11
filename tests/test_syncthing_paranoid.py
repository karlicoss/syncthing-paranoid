"""Characterization tests for syncthing_paranoid -- no mocks, everything runs for real.

- every test exercises the real ``fd`` binary (it's a hard dependency of the script anyway).
- the case-conflict test needs two names differing only in case to coexist, which this machine's
  case-insensitive filesystem can't represent: on macOS we mount a small case-sensitive APFS
  image via hdiutil; on an already case-sensitive filesystem (e.g. typical Linux tmp) plain
  files are used.
- the wrong-owner check is deliberately untested: making it fire requires a file owned by
  someone else, which only root can arrange, and mocking fd's output ends up just re-stating
  the implementation. the negative path -- own files produce no owner errors -- is implicitly
  asserted by every other test, through the real fd.
- ``run()``'s error filtering is injected through its ``ignored`` parameter instead of
  monkeypatching, so the machine-local private config never influences test outcomes.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

import syncthing_paranoid as sp

CONFLICT_NAME = 'foo.sync-conflict-20240101-000000-ABCDEF.txt'


def _errors(path: Path) -> list[sp.Error]:
    return list(sp.check(path))


def _never_ignore(_err: sp.Error) -> bool:
    return False


def _always_ignore(_err: sp.Error) -> bool:
    return True


@pytest.fixture
def case_sensitive_dir(tmp_path: Path) -> Iterator[Path]:
    """A directory on a case-sensitive filesystem, real files only.

    If tmp_path is already case-sensitive, use it as is; otherwise (macOS default)
    mount a throwaway case-sensitive APFS image.
    """
    probe = tmp_path / 'case_probe'
    probe.touch()
    case_insensitive = (tmp_path / 'CASE_PROBE').exists()
    probe.unlink()
    if not case_insensitive:
        yield tmp_path
        return

    if sys.platform != 'darwin':
        pytest.skip('filesystem is case-insensitive and no way to conjure a case-sensitive one here')

    image = tmp_path / 'cs.dmg'
    mnt = tmp_path / 'mnt'
    subprocess.check_call(
        ['hdiutil', 'create', '-size', '32m', '-fs', 'Case-sensitive APFS', '-volname', 'stparanoid_test', str(image)]
    )
    subprocess.check_call(['hdiutil', 'attach', str(image), '-mountpoint', str(mnt), '-nobrowse'])
    try:
        yield mnt
    finally:
        subprocess.check_call(['hdiutil', 'detach', str(mnt), '-force'])


# --- sync-conflict detection -------------------------------------------------


def test_check_flags_sync_conflict(tmp_path: Path) -> None:
    conflict = tmp_path / CONFLICT_NAME
    conflict.write_text('x')
    (tmp_path / 'innocent.txt').write_text('y')

    # the conflict is the *only* error: also implicitly asserts the wrong-owner
    # and special-character checks stay quiet on normal files
    assert _errors(tmp_path) == [sp.Error(path=conflict, info='syncthing conflict')]


def test_run_exits_on_sync_conflict(tmp_path: Path) -> None:
    folder = tmp_path / 'myfolder'
    (folder / '.stfolder').mkdir(parents=True)
    (folder / CONFLICT_NAME).write_text('x')

    with pytest.raises(SystemExit) as excinfo:
        sp.run([tmp_path], ignored=_never_ignore)
    assert excinfo.value.code == 1


def test_run_clean_tree_ok(tmp_path: Path) -> None:
    folder = tmp_path / 'myfolder'
    (folder / '.stfolder').mkdir(parents=True)
    (folder / 'notes.txt').write_text('hello')

    # clean tree -> run() must return normally, without sys.exit
    sp.run([tmp_path], ignored=_never_ignore)


# --- forbidden characters ----------------------------------------------------


def test_forbidden_characters(tmp_path: Path) -> None:
    # one offending char per file so each maps to a single-element `extra` set
    # (all of these are legal on APFS -- only '/' and NUL aren't)
    names = {
        '?': 'foo?.txt',
        ':': 'bar:baz.txt',
        '*': 'qux*.txt',
        '"': 'zap".txt',
    }
    for name in names.values():
        (tmp_path / name).write_text('x')

    errors = [e for e in _errors(tmp_path) if e.info.startswith('file name contains special characters')]
    assert len(errors) == len(names)

    extras: set[str] = set()
    for e in errors:
        assert isinstance(e.extra, set)
        extras |= e.extra
    assert set(names).issubset(extras)


def test_clean_names_no_errors(tmp_path: Path) -> None:
    (tmp_path / 'clean.txt').write_text('x')
    (tmp_path / 'another_file.md').write_text('y')
    (tmp_path / 'subdir').mkdir()
    (tmp_path / 'subdir' / 'nested-file.txt').write_text('z')

    assert _errors(tmp_path) == []


# --- case conflicts ----------------------------------------------------------


def test_case_conflicts(case_sensitive_dir: Path) -> None:
    (case_sensitive_dir / 'Foo.txt').write_text('a')
    (case_sensitive_dir / 'foo.txt').write_text('b')
    # guard against a silently case-insensitive fixture: both must exist as distinct entries
    assert {'Foo.txt', 'foo.txt'} <= {p.name for p in case_sensitive_dir.iterdir()}

    conflicts = [e for e in _errors(case_sensitive_dir) if e.info == 'file name case conflicts']
    assert len(conflicts) == 1


# --- IGNORED filtering -------------------------------------------------------


def test_ignored_suppresses_exit(tmp_path: Path) -> None:
    folder = tmp_path / 'myfolder'
    (folder / '.stfolder').mkdir(parents=True)
    (folder / CONFLICT_NAME).write_text('x')

    # same tree as test_run_exits_on_sync_conflict, but everything ignored -> no sys.exit
    sp.run([tmp_path], ignored=_always_ignore)
