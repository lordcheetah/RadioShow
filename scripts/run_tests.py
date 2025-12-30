#!/usr/bin/env python3
"""Run pytest using the repository virtualenv python when available.

Usage: python scripts/run_tests.py [pytest args]

Behavior:
- Looks for python executables in common venv locations: .venv_chatterbox, .venv, venv
- If found, uses that python to run `-m pytest` with passed args; otherwise falls back to current interpreter and prints guidance.
"""
import os
import subprocess
import sys
from pathlib import Path

CANDIDATE_VENVS = [
    '.venv_chatterbox',
    '.venv',
    'venv',
]

def find_venv_python():
    root = Path(__file__).resolve().parents[1]
    for v in CANDIDATE_VENVS:
        p = root / v
        if p.exists():
            if os.name == 'nt':
                py = p / 'Scripts' / 'python.exe'
            else:
                py = p / 'bin' / 'python'
            if py.exists():
                return str(py)
    return None


def main():
    py = find_venv_python()
    args = sys.argv[1:]
    if py:
        # Verify pytest is available in the selected python
        check = subprocess.call([py, '-c', 'import pytest'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if check != 0:
            print(f"pytest is not installed in the venv python ({py}).\nInstall it with:\n  {py} -m pip install pytest")
            raise SystemExit(2)
        cmd = [py, '-m', 'pytest'] + args
        print(f"Using venv python: {py}")
    else:
        # Check current interpreter for pytest
        check = subprocess.call([sys.executable, '-c', 'import pytest'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if check != 0:
            print("pytest is not installed in your current interpreter. Install it with:\n  python -m pip install pytest")
            print("If you have a repo virtualenv, create it at one of: .venv_chatterbox, .venv, venv")
            raise SystemExit(2)
        cmd = [sys.executable, '-m', 'pytest'] + args
        print("Using current python interpreter to run pytest")
    rc = subprocess.call(cmd)
    raise SystemExit(rc)

if __name__ == '__main__':
    main()
