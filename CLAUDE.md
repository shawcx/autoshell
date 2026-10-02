# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

AutoShell is a small library for building interactive command shells (REPLs) from plain Python
functions. Decorators inspect a function's signature and generate an `argparse` parser for it, and
`Shell` dispatches each typed line to the matching function. The project has no tests, packaging,
README, or build tooling. It is just the `autoshell/` package.

## Python 3

The package is imported as `autoshell` and uses relative imports internally. `__init__.py` defines
the exceptions before it imports the submodules, which import them with `from . import error`.
Keep that order.

## Commands

```sh
pytest                                              # run all tests
pytest tests/test_shell.py::test_nested_group       # run one test
pip install -e '.[test]'                            # editable install with pytest
```

`pyproject.toml` sets `pythonpath = ["."]`, so `pytest` works without installing the package.

## Tests

`tests/conftest.py` provides two fixtures. `one("cmd")` runs a single command, and
`script(*lines)` runs a whole session through `Start()`. Both return what the shell wrote.
Commands register into one process-wide tree when they're decorated, so every command name must be
unique across all test files, and no test may rely on a command defined in another file.

## Architecture

- **`__init__.py`** defines three control-flow exceptions. `error` is a parse error. `help` means
  help was printed, so stop. `stop` lets a command abort quietly. It then re-exports
  `CommandParser`, `Shell`, and the decorators. It also does `from . import io`, which loads the
  local `io.py`.
- **`io.py`** is imported for its side effects. It injects `printf`, `writeln`, and `hexdump` into
  `builtins`. `hexdump` accepts `bytes`, or `str`, which it encodes as UTF-8. `printf.red(...)`,
  `writeln.green(...)` and the other colour methods emit ANSI bold colours. Other modules call
  `writeln` without importing it. Output goes to the module global `io.stdout`, falling back to
  `sys.stdout`. A format string is applied with `%` only when arguments are passed.
- **`arguments.py`** defines `CommandParser`, an `argparse.ArgumentParser` that never exits. It
  raises `AutoShell.error` or `AutoShell.help` instead, writes to the class attribute `out`, and has
  `add_help=False`.
- **`decorators.py`** registers commands into a global tree at import/decoration time:
  - `@Command` adds a top-level command to `Shell.parser.handlers`.
  - `@Group` on a class instantiates it, then makes a sub-parser (`handlers`, `prefix`, `instance`,
    `meta_init`) out of its `@Member` methods. Dunder names are skipped when it scans the instance,
    because `__class__` would otherwise look like a nested group. When a class decorated with `@Group` is referenced
    as an attribute of another `@Group` class, it is moved out of the root and nested under that
    group. Its `prefix` is then the concatenated group names, which the prompt displays.
  - `@Shadow` on a class registers its `@Member` methods directly as top-level commands.
  - `@GroupInit` marks the method that runs when the user enters a group with no sub-command. If it
    returns `True`, the shell stays "inside" the group.
  - `compute_args` maps the function signature to CLI arguments. Positional params become
    `<name>`. Keyword params become `-x` (one letter) or `--name`. A `None` default is a plain
    option, `True` gives `store_false`, `False` gives `store_true`, and any other default sets
    `type=type(default)`. `*args` collects unknown args through `parse_known_args`. `**kwargs` and
    keyword-only params are rejected. The docstring becomes the parser description. `parser.order` records the parameter
    order, which is used to rebuild the call.
- **`shell.py`** holds the class-level root parser and `root` object, shared by every decorator,
  so registration is global per process. `Shell` keeps a stack of parsers (`self.parsers`), which
  works as the current "directory". In the input syntax, `exit` or `cd ..` pops the stack (or quits
  at the root), a leading `!` dispatches from the root, `#` starts a comment, and `?` or `--help`
  lists usages. A group name with no sub-command pushes onto the stack.
  Entry points: `Shell(...).Start()` runs the interactive loop, and `Shell().One("cmd args")` runs
  a single command. Bare `cd` returns to the top level.
- **I/O:** `Shell(stdin=, stdout=)` streams are used for everything. `_bind()` points `io.stdout`
  and `CommandParser.out` at the shell's stdout on every `Start` iteration and every `One` call.
  `input()`, and so readline, is used only when both streams are the process's own. Otherwise
  `_readline` reads `stdin` directly, which is how to drive a shell from `StringIO` in tests.
- **Errors:** an exception from a command or `@GroupInit` prints a traceback to the shell's stdout
  and the loop continues. A shlex quoting error prints `Parse error`. Ctrl-C during a command
  abandons it and restores the group stack to its earlier depth.
