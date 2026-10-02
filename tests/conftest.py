import io

import pytest

import autoshell


def run_script(*lines):
    'feed lines to a fresh shell and return everything it wrote'
    out = io.StringIO()
    shell = autoshell.Shell(stdin=io.StringIO(''.join(l + '\n' for l in lines)), stdout=out)
    shell.Start()
    return out.getvalue()


def run_one(cmd):
    'run a single command and return its output'
    out = io.StringIO()
    autoshell.Shell(stdout=out).One(cmd)
    return out.getvalue()


@pytest.fixture
def script():
    return run_script


@pytest.fixture
def one():
    return run_one
