#!/usr/bin/python3
import argparse
from collections import Counter
from dataclasses import dataclass
from subprocess import check_output
from pathlib import Path
from typing import Iterator, Any
import os
import re
import shutil
import sys


from syncthing_paranoid_config import IGNORED


# make android friendly https://stackoverflow.com/a/48182875/706389
# TODO hmm it actually might be fine these days?
# since android is using f2fs now? https://en.wikipedia.org/wiki/Comparison_of_file_systems#Limits
# 20230506 hmm, ok so "?" is definitely not working -- tried creating a file on PC, didn't sync on either pixel of samsung device
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


def run(roots: list[Path]) -> None:
    errors = []
    for root in roots:
        fd_bin = shutil.which('fdfind') or shutil.which('fd')
        res = check_output([fd_bin, '--hidden', '.stfolder', root, '--type', 'd', '-0'])
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

