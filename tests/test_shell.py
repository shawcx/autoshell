import pytest

import autoshell
from autoshell import Command, Group, GroupInit, Member, Shadow

# Commands register into one process-wide tree, so every name here is unique
# across the test suite.

calls = []


@Command
def add(a, b, n=1, verbose=False, color=True, label=None):
    'add two numbers'
    writeln('sum=%d n=%r verbose=%r color=%r label=%r', int(a) + int(b), n, verbose, color, label)


@Command
def collect(first, *rest):
    writeln('first=%s rest=%r', first, rest)


@Command
def explode():
    raise RuntimeError('kaboom')


@Command
def halt():
    calls.append('halt')
    raise autoshell.stop


@Command
def fail():
    raise autoshell.error('bad')


@Command
def assist():
    'assist docstring'
    raise autoshell.help


@Command
def percent():
    writeln('100%')


@Group
class Inner:
    @Member
    def ping(self):
        writeln('pong')


@Group
class Outer:
    inner = Inner

    @GroupInit
    def enter(self):
        return True

    @Member
    def status(self, x=None):
        writeln('status x=%s', x)

    @Member
    def interrupt(self):
        raise KeyboardInterrupt


@Group
class Plain:
    @Member
    def hello(self, name):
        writeln('hello %s', name)


@Shadow
class Shadowed:
    @Member
    def shadowcmd(self):
        writeln('shadowed')


# arguments

def test_positional_and_defaults(one):
    assert 'sum=5 n=1 verbose=False color=True label=None' in one('add 2 3')


def test_options(one):
    out = one('add 2 3 -n 4 --verbose --color --label hi')
    assert "sum=5 n=4 verbose=True color=False label='hi'" in out


def test_option_type_from_default(one):
    assert 'usage: add' in one('add 2 3 -n notanint')


def test_missing_positional_prints_usage(one):
    assert one('add 1') == 'usage: add [-n int] [--verbose] [--color] [--label LABEL] <a> <b>\n'


def test_varargs(one):
    assert "first=a rest=('b', 'c')" in one('collect a b c')


def test_quoted_argument(one):
    assert "first=a b rest=()" in one('collect "a b"')


def test_kwargs_rejected():
    with pytest.raises(autoshell.error):
        @Command
        def kwcmd(**kw):
            pass


def test_keyword_only_rejected():
    with pytest.raises(autoshell.error):
        @Command
        def kwonlycmd(*, x=1):
            pass


# dispatch

def test_unknown_command(one):
    assert one('nosuch') == 'Unknown command: "nosuch"\n'


def test_comment_is_ignored(one):
    assert one('# add 1 2') == ''


def test_help_lists_usages(one):
    out = one('?')
    assert 'usage: add' in out and 'usage: outer <command>' in out
    assert one('--help') == out


def test_shadow_registers_at_top_level(one):
    assert one('shadowcmd') == 'shadowed\n'


def test_group_subcommand(one):
    assert one('plain hello bob') == 'hello bob\n'


def test_nested_group(one):
    assert one('outer inner ping') == 'pong\n'


# groups in an interactive session

def test_groupinit_enters_group(script):
    out = script('outer', 'status -x 1', 'exit', 'status')
    assert 'outer $ status -x 1\nstatus x=1' in out
    assert '$ status\nUnknown command: "status"' in out


def test_nested_prompt_prefix(script):
    assert 'outer inner $ ' in script('outer', 'inner')


def test_bang_runs_from_root(script):
    assert 'sum=2' in script('outer', '!add 1 1', '! add 1 1')


def test_bang_alone_prints_root_help(script):
    assert 'usage: add' in script('outer', '!')


def test_cd_dotdot_pops_one_level(script):
    out = script('outer', 'inner', 'cd ..', 'status')
    assert 'outer $ status\nstatus x=None' in out


def test_bare_cd_returns_to_root(script):
    out = script('outer', 'inner', 'cd', 'add 1 1')
    assert '\n$ add 1 1\nsum=2' in out


def test_exit_at_root_stops(script):
    out = script('exit', 'add 1 1')
    assert 'sum' not in out


def test_eof_stops(script):
    assert script('add 1 1').endswith('$ \n')


def test_echo_when_not_a_tty(script):
    assert '$ add 1 1\n' in script('add 1 1')


# errors

def test_unbalanced_quote(script):
    out = script('collect "a', 'add 1 1')
    assert 'Parse error: No closing quotation' in out
    assert 'sum=2' in out


def test_empty_string_command(script):
    out = script('""', '! ""', 'add 1 1')
    assert out.count('Unknown command: ""') == 2
    assert 'sum=2' in out


def test_exception_prints_traceback_and_continues(script):
    out = script('explode', 'add 1 1')
    assert 'RuntimeError: kaboom' in out
    assert 'sum=2' in out


def test_keyboard_interrupt_restores_group_stack(script):
    out = script('outer interrupt', 'add 1 1')
    assert '\n$ add 1 1\nsum=2' in out


def test_stop_and_error_are_quiet(one):
    calls.clear()
    assert one('halt') == ''
    assert calls == ['halt']
    assert one('fail') == ''


def test_raising_help_prints_command_help(one):
    assert 'assist docstring' in one('assist')


def test_percent_without_args(one):
    assert one('percent') == '100%\n'
