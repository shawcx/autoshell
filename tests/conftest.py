import io

import autoshell


def run_script(*lines, commands=None):
    'feed lines to a fresh shell and return everything it wrote'
    out = io.StringIO()
    stdin = io.StringIO(''.join(l + '\n' for l in lines))
    autoshell.Shell(stdin=stdin, stdout=out, commands=commands).Start()
    return out.getvalue()


def run_one(cmd, commands=None):
    'run a single command and return its output'
    out = io.StringIO()
    autoshell.Shell(stdout=out, commands=commands).One(cmd)
    return out.getvalue()
