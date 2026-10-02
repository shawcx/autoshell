import io

import pytest

import autoshell
from autoshell import io as aio


@pytest.fixture
def out(monkeypatch):
    buf = io.StringIO()
    monkeypatch.setattr(aio, 'stdout', buf)
    return buf


def test_builtins_installed():
    assert printf is aio.printf
    assert writeln is aio.writeln
    assert hexdump is aio.hexdump


def test_writeln_formats_only_with_args(out):
    writeln('100%')
    writeln('%d%%', 5)
    writeln()
    assert out.getvalue() == '100%\n5%\n\n'


def test_printf_has_no_newline(out):
    printf('a')
    printf('%s', 'b')
    assert out.getvalue() == 'ab'


def test_colors(out):
    writeln.red('%s', 'x')
    printf.green('50%')
    assert out.getvalue() == '\x1b[1;31mx\x1b[0m\n\x1b[1;32m50%\x1b[0m'


def test_falls_back_to_sys_stdout(monkeypatch, capsys):
    monkeypatch.setattr(aio, 'stdout', None)
    writeln('hi')
    assert capsys.readouterr().out == 'hi\n'


def strip(s):
    import re
    return re.sub(r'\x1b\[[0-9;]*m', '', s)


def test_hexdump_bytes(out):
    hexdump(b'\x00\x01ab')
    assert strip(out.getvalue()) == '0: 00 01 61 62' + ' ' * 38 + '..ab\n'


def test_hexdump_str_is_utf8(out):
    hexdump('é')
    assert strip(out.getvalue()).startswith('0: c3 a9')


def test_hexdump_multiple_lines_and_offset(out):
    hexdump(bytes(range(17)), offset=0x100)
    lines = strip(out.getvalue()).splitlines()
    assert len(lines) == 2
    assert lines[0].startswith('100: 00 01')
    assert lines[1].startswith('110: 10')


@autoshell.Command
def iowrite():
    writeln('100%')


def test_shell_binds_its_stdout():
    buf = io.StringIO()
    autoshell.Shell(stdout=buf).One('iowrite')
    assert buf.getvalue() == '100%\n'
