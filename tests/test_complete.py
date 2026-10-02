import io

import pytest

import autoshell
from autoshell import shell as shellmod
from autoshell import Command, Group, GroupInit, Member


@Command
def deploy(target, force=False, region=None):
    pass

deploy.complete = lambda text, args: ['staging', 'production']


@Group
class Db:
    @GroupInit
    def enter(self):
        return True

    @Member
    def migrate(self, version, dry=False):
        pass

    def complete_migrate(self, text, args):
        return [1, 2, 10] if not args else []

    @Member
    def backup(self):
        pass

    @Member
    def broken(self):
        pass

    def complete_broken(self, text, args):
        raise RuntimeError


@Group
class Ops:
    db = Db


COMMANDS = [deploy, Ops]


@pytest.fixture
def shell():
    return autoshell.Shell(stdout=io.StringIO(), commands=COMMANDS)


def test_top_level_names(shell):
    assert shell.completions('', '') == ['deploy ', 'ops ', 'help ', 'exit ']
    assert shell.completions('', 'd') == ['deploy ']


def test_group_members(shell):
    assert shell.completions('ops ', '') == ['db ']
    assert shell.completions('ops db ', 'b') == ['backup ', 'broken ']


def test_options(shell):
    assert shell.completions('deploy ', '--') == ['--force ', '--region ']
    assert shell.completions('deploy x --force ', '--') == ['--region ']


def test_function_hook(shell):
    assert shell.completions('deploy ', 'p') == ['production ']


def test_method_hook_gets_args_and_values_are_stringified(shell):
    assert shell.completions('ops db migrate ', '1') == ['1 ', '10 ']
    assert shell.completions('ops db migrate 1 ', '') == []


def test_hook_errors_are_ignored(shell):
    assert shell.completions('ops db broken ', '') == []


def test_no_hook(shell):
    assert shell.completions('ops db backup ', '') == []


def test_unknown_command(shell):
    assert shell.completions('nope ', '') == []


def test_unbalanced_quote(shell):
    assert shell.completions('deploy "x ', '') == []


def test_inside_group(shell):
    shell.One('ops db')
    assert shell.completions('', '') == ['backup ', 'broken ', 'migrate ', 'help ', 'exit ', '.. ']
    assert shell.completions('', '!') == ['!deploy ', '!ops ', '!help ']
    assert shell.completions('!', '') == ['deploy ', 'ops ', 'help ']
    assert shell.completions('!ops ', '') == ['db ']


def test_help_paths(shell):
    assert shell.completions('help ', '') == ['deploy ', 'ops ']
    assert shell.completions('help ops ', '') == ['db ']
    assert shell.completions('? ops db ', 'm') == ['migrate ']
    assert shell.completions('help deploy ', '') == []


class FakeReadline:
    'stands in for the readline module'
    backend = 'readline'
    __doc__ = ''

    def __init__(self, history=()):
        self.completer = 'old'
        self.delims = 'old delims'
        self.history = list(history)
        self.saved = None
        self.bindings = []

    def get_completer(self): return self.completer
    def set_completer(self, fn): self.completer = fn
    def get_completer_delims(self): return self.delims
    def set_completer_delims(self, d): self.delims = d
    def parse_and_bind(self, s): self.bindings.append(s)
    def read_history_file(self, path):
        with open(path) as f:
            self.history = f.read().split()
    def write_history_file(self, path):
        self.saved = (path, self.history)


def interactive(monkeypatch, lines, rl, history_file=None, commands=COMMANDS):
    monkeypatch.setattr(shellmod, 'readline', rl)
    feed = iter(lines)
    def fake_input(prompt):
        try:
            line = next(feed)
        except StopIteration:
            raise EOFError
        rl.history.append(line)
        return line
    monkeypatch.setattr('builtins.input', fake_input)
    shell = autoshell.Shell(commands=commands, history_file=history_file)
    shell.Start()
    return shell


def test_start_installs_and_restores_completer(monkeypatch):
    rl = FakeReadline()
    seen = []
    @Command
    def peek():
        seen.append((rl.completer, rl.delims))
    interactive(monkeypatch, ['peek'], rl, commands=[peek])
    assert seen[0][0].__func__ is autoshell.Shell._complete
    assert seen[0][1] == ' \t\n'
    assert rl.bindings == ['tab: complete']
    assert (rl.completer, rl.delims) == ('old', 'old delims')


def test_libedit_binding(monkeypatch):
    rl = FakeReadline()
    rl.backend = 'editline'
    interactive(monkeypatch, [], rl)
    assert rl.bindings == ['bind ^I rl_complete']


def test_history_file_round_trip(monkeypatch, tmp_path):
    path = tmp_path / 'hist'
    path.write_text('earlier\n')
    rl = FakeReadline()
    interactive(monkeypatch, ['deploy x'], rl, history_file=str(path))
    assert rl.saved == (str(path), ['earlier', 'deploy x'])


def test_missing_history_file_is_fine(monkeypatch, tmp_path):
    rl = FakeReadline()
    interactive(monkeypatch, [], rl, history_file=str(tmp_path / 'none'))
    assert rl.saved == (str(tmp_path / 'none'), [])


def test_history_file_expands_user():
    shell = autoshell.Shell(commands=[], history_file='~/.x_history')
    assert not shell.history_file.startswith('~')


def test_no_readline_session_for_custom_streams(monkeypatch):
    rl = FakeReadline()
    monkeypatch.setattr(shellmod, 'readline', rl)
    autoshell.Shell(stdin=io.StringIO('deploy x\n'), stdout=io.StringIO(), commands=COMMANDS).Start()
    assert rl.bindings == []
