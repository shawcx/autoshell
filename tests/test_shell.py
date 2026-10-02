import io

import pytest
import rich
from rich import print

import autoshell
from autoshell import Command, Group, GroupInit, Member, Shadow

from conftest import run_one, run_script

calls = []


@Command
def add(a, b, n=1, verbose=False, color=True, label=None):
    'add two numbers'
    print(f'sum={int(a) + int(b)} n={n!r} verbose={verbose!r} color={color!r} label={label!r}')


@Command
def collect(first, *rest):
    print(f'first={first} rest={rest!r}')


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
def styled():
    print('[bold red]alert[/] done')


@Group
class Inner:
    @Member
    def ping(self):
        print('pong')


@Group
class Outer:
    'the outer group'
    inner = Inner

    @GroupInit
    def enter(self):
        return True

    @Member
    def status(self, x=None):
        print(f'status x={x}')

    @Member
    def interrupt(self):
        raise KeyboardInterrupt


@Group
class Plain:
    @Member
    def hello(self, name):
        print(f'hello {name}')


@Shadow
class Shadowed:
    @Member
    def shadowcmd(self):
        print('shadowed')


COMMANDS = [add, collect, explode, halt, fail, assist, styled, Outer, Plain, Shadowed]


@pytest.fixture
def one():
    return lambda cmd: run_one(cmd, commands=COMMANDS)


@pytest.fixture
def script():
    return lambda *lines: run_script(*lines, commands=COMMANDS)


# arguments

def test_positional_and_defaults(one):
    assert 'sum=5 n=1 verbose=False color=True label=None' in one('add 2 3')


def test_options(one):
    out = one('add 2 3 -n 4 --verbose --no-color --label hi')
    assert "sum=5 n=4 verbose=True color=False label='hi'" in out


def test_option_type_from_default(one):
    assert 'usage: add' in one('add 2 3 -n notanint')


def test_missing_positional_prints_usage(one):
    assert one('add 1') == 'usage: add [-n int] [--verbose] [--no-color] [--label LABEL] <a> <b>\n'


def test_varargs(one):
    assert "first=a rest=('b', 'c')" in one('collect a b c')


def test_quoted_argument(one):
    assert "first=a b rest=()" in one('collect "a b"')


@Command
def convert(count: int, ratio: float, enabled: bool, dry_run=False, keep_going=True,
            max_size: int = None, level=3, name='x'):
    print(f'{count!r} {ratio!r} {enabled!r} {dry_run!r} {keep_going!r} {max_size!r} {level!r} {name!r}')


def test_annotated_positionals_are_converted():
    assert run_one('convert 3 1.5 yes', commands=[convert]) == '3 1.5 True False True None 3 \'x\'\n'


@pytest.mark.parametrize('text,value', [
    ('yes', True), ('Y', True), ('on', True), ('true', True), ('t', True), ('1', True),
    ('no', False), ('N', False), ('off', False), ('false', False), ('f', False), ('0', False),
])
def test_bool_words(text, value):
    assert run_one(f'convert 1 1 {text}', commands=[convert]).split()[2] == repr(value)


def test_bad_bool_prints_usage():
    assert run_one('convert 1 1 maybe', commands=[convert]).startswith('usage: convert')


def test_bad_annotated_int_prints_usage():
    assert run_one('convert x 1 yes', commands=[convert]).startswith('usage: convert')


def test_dashed_option_names():
    out = run_one('convert 1 1 no --dry-run --no-keep-going --max-size 9 --level 4 --name y',
                  commands=[convert])
    assert out == "1 1.0 False True False 9 4 'y'\n"


def test_underscore_spelling_is_not_accepted():
    assert run_one('convert 1 1 no --dry_run', commands=[convert]).startswith('usage: convert')


def test_usage_shows_conventions():
    # argparse wraps usage to the terminal width
    assert ' '.join(run_one('convert', commands=[convert]).split()) == (
        'usage: convert [--dry-run] [--no-keep-going] [--max-size int] [--level int] '
        '[--name str] <count> <ratio> <enabled>')


def test_double_dash_ends_options(one):
    assert "first=--x rest=('--y',)" in one('collect -- --x --y')
    assert "first=a rest=('--x',)" in one('collect a -- --x')


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


def test_help_lists_groups_and_commands(one):
    out = one('help')
    assert 'Groups\n  outer      the outer group\n  plain\n' in out
    assert '  add        add two numbers\n' in out
    assert one('?') == out
    assert one('--help') == out


def test_help_for_group(one):
    out = one('help outer')
    assert out.startswith('outer\nthe outer group\n')
    assert 'Groups\n  inner\n' in out
    assert 'Commands\n  interrupt\n  status\n' in out


def test_help_title_for_nested_group(one):
    assert one('help outer inner').startswith('outer › inner\n')


def test_help_for_command(one):
    out = one('help add')
    assert out.startswith('usage: add')
    assert 'add two numbers' in out


def test_help_for_nested_command(one):
    assert one('help outer inner ping').startswith('usage: ping')


def test_help_unknown(one):
    assert one('help outer nope') == 'Unknown command: "outer nope"\n'


def test_help_inside_group(script):
    assert 'Commands\n  interrupt\n  status\n' in script('outer', 'help')


def test_command_named_help_wins():
    @Command
    def help():
        print('custom help')
    assert run_one('help', commands=[help]) == 'custom help\n'


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


def test_nested_prompt_has_separator(script):
    assert '\nouter › inner $ ' in script('outer', 'inner')


def test_custom_separator():
    out = io.StringIO()
    shell = autoshell.Shell(stdout=out, commands=COMMANDS, separator='/', prompt='> ')
    shell.One('outer inner')
    assert shell.render_prompt() == 'outer/inner > '


def test_prompt_colours_on_a_terminal():
    from rich.console import Console
    out = io.StringIO()
    shell = autoshell.Shell(stdout=out, commands=COMMANDS)
    shell.console = Console(file=out, force_terminal=True, color_system='standard')
    shell.One('outer inner')
    assert shell.render_prompt() == (
        '\x1b[1;36mouter\x1b[0m\x1b[2m › \x1b[0m\x1b[1;35minner\x1b[0m $ ')


@pytest.mark.parametrize('libedit,expected', [
    (False, '\x01\x1b[1;36m\x02outer\x01\x1b[0m\x02 $ '),
    (True, '\x1b[1;36mouter\x1b[0m $ '),
])
def test_prompt_colours_are_marked_for_gnu_readline_only(monkeypatch, libedit, expected):
    from rich.console import Console
    from autoshell import shell as shellmod
    out = io.StringIO()
    shell = autoshell.Shell(stdout=out, commands=COMMANDS)
    shell.console = Console(file=out, force_terminal=True, color_system='standard')
    monkeypatch.setattr(shell, '_interactive', lambda: True)
    monkeypatch.setattr(shellmod, '_libedit', lambda: libedit)
    shell.One('outer')
    assert shell.render_prompt() == expected


def test_root_prompt_is_plain(one):
    assert autoshell.Shell(stdout=io.StringIO(), commands=COMMANDS).render_prompt() == '$ '


def test_bang_runs_from_root(script):
    assert 'sum=2' in script('outer', '!add 1 1', '! add 1 1')


def test_bang_alone_prints_root_help(script):
    assert '  add        add two numbers' in script('outer', '!')


def test_dotdot_pops_one_level(script):
    out = script('outer', 'inner', '..', 'status')
    assert 'outer $ status\nstatus x=None' in out


def test_dotdot_at_root_stops(script):
    assert 'sum' not in script('..', 'add 1 1')


def test_cd_dotdot_is_no_longer_special(script):
    out = script('outer', 'cd ..', 'status')
    assert 'Unknown command: "cd"' in out
    assert 'status x=None' in out


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


# rich output

def test_rich_markup_goes_to_shell_stream(one):
    assert one('styled') == 'alert done\n'


def test_global_console_restored_after_command():
    glob = rich.get_console()
    before = glob.file
    run_one('styled', commands=COMMANDS)
    assert rich.get_console() is glob
    assert glob.file is before


def test_root_console_writes_to_shell_stream():
    out = io.StringIO()
    shell = autoshell.Shell(stdout=out, commands=[])
    shell.root.console.print('hi')
    assert out.getvalue() == 'hi\n'


def test_console_restored_when_command_raises():
    glob = rich.get_console()
    before = glob.file
    run_script('explode', commands=COMMANDS)
    assert glob.file is before


# building shells

def test_shells_are_independent():
    assert run_one('add 1 1', commands=[collect]) == 'Unknown command: "add"\n'
    assert 'sum=2' in run_one('add 1 1', commands=[add])


def test_default_is_everything_decorated():
    assert 'sum=2' in run_one('add 1 1')
    assert 'shadowed' in run_one('shadowcmd')


def test_empty_command_list():
    assert run_one('add 1 1', commands=[]) == 'Unknown command: "add"\n'


def test_nested_group_is_not_top_level_when_listed():
    assert run_one('inner ping', commands=[Inner, Outer]) == 'Unknown command: "inner"\n'
    assert run_one('outer inner ping', commands=[Inner, Outer]) == 'pong\n'


def test_nested_group_can_be_listed_alone():
    assert run_one('inner ping', commands=[Inner]) == 'pong\n'


def test_rejects_undecorated():
    def plain():
        pass
    with pytest.raises(ValueError):
        autoshell.Shell(commands=[plain])


@Group
class Counter:
    def __init__(self, start=0):
        self.n = start

    @Member
    def inc(self):
        self.n += 1
        print(f'n={self.n}')


def test_group_instance_with_constructor_args():
    out = run_script('counter inc', 'counter inc', commands=[Counter(10)])
    assert 'n=11\n' in out and 'n=12\n' in out


def test_group_class_gets_a_fresh_instance_per_shell():
    assert 'n=1\n' in run_one('counter inc', commands=[Counter])
    assert 'n=1\n' in run_one('counter inc', commands=[Counter])


def test_group_instance_reused_across_shells():
    counter = Counter()
    run_one('counter inc', commands=[counter])
    assert 'n=2' in run_one('counter inc', commands=[counter])


@Group
class Child:
    @property
    def parent_name(self):
        return type(self._parent).__name__

    @Member
    def who(self):
        print(self.parent_name)


@Group
class Parent:
    child = Child


def test_properties_are_not_evaluated_while_building():
    assert run_one('parent child who', commands=[Parent]) == 'Parent\n'


def test_links():
    outer = Outer()
    shell = autoshell.Shell(commands=[outer, add], stdout=io.StringIO())
    inner = shell.parser.handlers['outer'].handlers['inner'].instance
    assert outer._root is shell.root and outer._parent is shell.root
    assert outer._parser is shell.parser.handlers['outer']
    assert inner._parent is outer and inner._root is shell.root
    assert add._root is shell.root
