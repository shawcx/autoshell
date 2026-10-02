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

Runtime dependency: `rich`.

```sh
pytest                                              # run all tests
pytest tests/test_shell.py::test_nested_group       # run one test
pip install -e '.[test]'                            # editable install with pytest
.venv/bin/python examples/tasks.py                  # example interactive shell
```

`pyproject.toml` sets `pythonpath = ["."]`, so `pytest` works without installing the package.

## Tests

`tests/conftest.py` has two helpers. `run_one("cmd", commands=[...])` runs a single command, and
`run_script(*lines, commands=[...])` runs a whole session through `Start()`. Both return what the
shell wrote. `test_complete.py` tests `completions()` directly, and drives `Start()` with a fake
`readline` module and a patched `input()`. `test_shell.py` wraps them in the `one` and `script` fixtures, which use its `COMMANDS`
list. Pass `commands` explicitly so each test only sees the commands it means to.

## Architecture

- **`__init__.py`** defines three control-flow exceptions. `error` is a parse error. `help` means
  help was printed, so stop. `stop` lets a command abort quietly. It then re-exports
  `CommandParser`, `Shell`, and the decorators.
- **`arguments.py`** defines `CommandParser`, an `argparse.ArgumentParser` that never exits. It
  raises `AutoShell.error` or `AutoShell.help` instead, writes to the class attribute `out`, and has
  `add_help=False`.
- **`decorators.py`** decorators only mark things (`__AutoShell__`). `@Command`, `@Group` and
  `@Shadow` also append to the module-level `registry` list. `build(commands, root)` turns marked
  items into a fresh tree of `CommandParser`s for one shell:
  - A `@Command` function becomes a top-level command.
  - A `@Group` class or instance becomes a sub-parser (`handlers`, `path`, `instance`,
    `meta_init`) made of its `@Member` methods. Classes are instantiated with no arguments, so pass
    an instance to give it constructor arguments. Each shell built from a class gets its own
    instance. An attribute holding another `@Group` class or instance becomes a nested group,
    keyed and prompted by the attribute name. A group that gets nested is dropped from the top
    level, even when it is also listed. The instance's `_parser`, `_parent` (the enclosing group,
    or the shell's root) and `_root` are set after its members are scanned.
  - A `@Shadow` class or instance contributes its `@Member` methods as top-level commands.
  - Tab-completion hooks are attached as `parser.complete`. For a group or shadow member, the hook
    is the instance's `complete_<name>(text, args)` method. For an `@Command` function, it is a
    `.complete` attribute set on the function. A group's class docstring becomes its parser
    `description`, which `help` shows.
  - `@GroupInit` marks the method that runs when the user enters a group with no sub-command. If it
    returns `True`, the shell stays "inside" the group.
  - `members()` skips dunders, because `__class__` would otherwise look like a nested group. It
    also skips the `_parser`, `_parent` and `_root` links, which would otherwise recurse when an
    instance is reused. It doesn't evaluate properties, because their getters may rely on links
    that aren't set yet.
  - `compute_args` maps the function signature to CLI arguments, always setting `dest` to the
    parameter name:
    - Positional params become `<name>`.
    - Keyword params become `-x` (one letter) or `--name`, with underscores turned into dashes
      (`dry_run` becomes `--dry-run`).
    - A `False` default gives a `store_true` flag. A `True` default gives `--no-name`
      (`store_false`).
    - A `None` default is a plain string option. Any other default sets `type=type(default)`.
    - A type annotation that is a class (`count: int`) sets the type for both positionals and
      options, found through `typing.get_type_hints`. A `bool` annotation uses `boolean()`, which
      accepts yes/no, on/off, true/false, y/n, t/f and 1/0.
    - `--` ends the options, which argparse handles itself. `*args` collects unknown args through
      `parse_known_args`.
    - `**kwargs` and keyword-only params are rejected at decoration time by `check_args`.
    - The docstring becomes the parser description. `parser.order` records the parameter order,
      which is used to rebuild the call.
- **`shell.py`**: `Shell(commands=None)` builds `self.parser` from `commands`, or from
  `decorators.registry` when that is `None`, and gives each command and group a fresh
  `self.root`. `Shell` keeps a stack of parsers (`self.parsers`), which works as the current
  "directory". In the input syntax, `exit` or `..` pops the stack (or quits at the root), bare
  `cd` returns to the top level, a leading `!` dispatches from the root, and `#` starts a comment.
  `help [group...] [command]`, `?` and `--help` call `Help()`, which lists groups and commands with
  the first line of each docstring, or prints one command's argparse help. A user command named
  `help` takes precedence. A group name with no sub-command pushes onto the stack.
  Entry points: `Shell(...).Start()` runs the interactive loop, and `Shell().One("cmd args")` runs
  a single command.
- **I/O:** `Shell(stdin=, stdout=)` streams are used for everything. Commands print with rich
  (`from rich import print`, or `rich.get_console()`). When `stdout` is `sys.stdout`,
  `shell.console` is rich's global console. Otherwise it is a `Console(file=stdout)`, and
  `_redirect()` swaps it into the global console's `__dict__` while `One()` runs a command, the
  same trick `rich.reconfigure` uses, then restores it. `shell.root.console` exposes it to
  commands. `_bind()` points `CommandParser.out` at the shell's stdout. `input()`, and so
  readline, is used only when both streams are the process's own. Otherwise `_readline` reads
  `stdin` directly, which is how to drive a shell from `StringIO` in tests.
- **Prompt:** `render_prompt()` builds the prompt from the current parser's `path`, a tuple of
  group names, as rich `Text`. Each depth gets the next of `GROUP_STYLES`, joined by
  `Shell(separator=' › ')` in dim, followed by `prompt`. It renders through `console.capture()`, so
  colour follows rich's terminal detection and `NO_COLOR`. For GNU readline, colour codes are
  wrapped in `\001`/`\002` so the prompt width is right. macOS's libedit prints those markers
  wrongly, so `_libedit()` skips them there. `help <group>` titles use the same `path_text()`.
- **Completion and history:** `Start()` runs inside `_readline_session()`, but only when both
  streams are the process's own and `readline` imported. It installs `_complete`, sets the word
  delimiters to whitespace so `--options` complete as one word, and binds Tab. On macOS's libedit
  the binding is `bind ^I rl_complete`. It loads and saves `history_file`, then restores the
  previous completer and delimiters. `completions(line, text)` is the pure, testable logic:
  - It walks groups from the current stack, or from the root after `!`.
  - It offers names at a group level, plus `help`, `exit` and, inside a group, `..` (only `help` after `!`).
  - It offers unused option strings when `text` starts with `-`, and otherwise calls the
    command's hook, which receives the words already typed after the command.
- **Errors:** an exception from a command or `@GroupInit` prints a traceback to the shell's stdout
  and the loop continues. A shlex quoting error prints `Parse error`. Ctrl-C during a command
  abandons it and restores the group stack to its earlier depth.
