#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from syncthing_paranoid_config import IGNORED

# make android friendly (see https://stackoverflow.com/questions/2679699/what-characters-allowed-in-file-names-on-android/48182875#48182875)
# TODO hmm it actually might be fine these days?
# since android is using f2fs now? https://en.wikipedia.org/wiki/Comparison_of_file_systems#Limits
# 20230506 hmm, ok so "?" is definitely not working -- tried creating a file on PC, didn't sync on either pixel of samsung device
# : definitely not working for inbound sync on android -- errors durung tmp file creation or something like that
ANDROID = r'''|\?*<\":>+\[\]/'"'''
MISC = ''.join([
    '·', # not sure what's a better way to deal with it?
    '^', # not allowed in windows
])
FORBIDDEN = ANDROID + MISC


@dataclass
class Error:
    path: Path
    info: str
    extra: Any = None


def check(syncthing: Path) -> Iterator[Error]:
    print("checking", syncthing)

    for r, dirs, files in os.walk(syncthing):
        xx = dirs + files

        ## check sync conflicts
        for x in xx:
            if 'sync-conflict' in x:
                yield Error(path=Path(r) / x, info='syncthing conflict')
        ##

        ## check potential case conflicts (macos stumbles over these)
        cnt = Counter([f.lower() for f in xx])
        for k, v in cnt.items():
            if v > 1:
                yield Error(path=Path(r) / k, info='file name case conflicts')
        ##

        ## check filenames potentially unfriendly to Android
        for x in xx:
            if re.search(f'[{FORBIDDEN}]', x):
                contained = {c for c in FORBIDDEN if c in x}
                yield Error(path=Path(r) / x, info='file name contains special characters, might be bad for Windows/Android', extra=contained)
        ##


def fdfind(*args: str | Path) -> bytes:
    fd_bin = shutil.which('fdfind') or shutil.which('fd')  # sometimes has different name, e.g. on linux vs osx
    assert fd_bin is not None
    return subprocess.check_output([fd_bin, *args])


def run(roots: list[Path]) -> None:
    errors = []
    for root in roots:
        res = fdfind('--hidden', '.stfolder', root, '--type', 'd', '-0')
        split = res.decode('utf8').split('\0')
        assert split[-1] == '', split
        del split[-1]
        syncthings = [Path(s).parent for s in split]
        for ss in syncthings:
            for err in check(ss):
                if IGNORED(err):
                    continue
                print("ERROR: ", err)
                errors.append(err)
    if len(errors) > 0:
        sys.exit(1)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument('roots', nargs='+')
    args = p.parse_args()
    run(list(map(Path, args.roots)))


if __name__ == '__main__':
    main()

