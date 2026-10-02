# autoshell

Build interactive command shells from plain Python functions. Decorate a function and its
signature becomes the command line: parameters turn into arguments and options, the docstring
becomes the help text, and the shell gives you tab completion, history, and nested command
groups.

```console
$ greet world --times 2
hello, world!
hello, world!
$ tasks add "write docs" --priority 2
added task 1
$ tasks list
2 write docs
$ help tasks
tasks
manage tasks

Commands
  add   add a task
  list  list tasks
```

## Install

```sh
pip install git+https://github.com/shawcx/autoshell
```

Requires Python 3.9+ and [rich](https://github.com/Textualize/rich).

## Quick start

```python
from rich import print

import autoshell
from autoshell import Command, Group, GroupInit, Member


@Command
def greet(name, shout=False, times=1):
    'say hello'
    for _ in range(times):
        print(f'hello, {name}!'.upper() if shout else f'hello, {name}!')


@Group
class Tasks:
    'manage tasks'

    def __init__(self):
        self.tasks = []

    @GroupInit
    def enter(self):
        return True     # typing "tasks" alone enters the group

    @Member
    def add(self, title, priority: int = 1):
        'add a task'
        self.tasks.append((priority, title))
        print(f'added task {len(self.tasks)}')

    @Member
    def list(self):
        'list tasks'
        for priority, title in sorted(self.tasks, reverse=True):
            print(f'[bold]{priority}[/] {title}')


autoshell.Shell(commands=[greet, Tasks], history_file='~/.myshell_history').Start()
```

[`examples/tasks.py`](examples/tasks.py) is a fuller example that uses every feature. Run it with
`python examples/tasks.py --demo`.

## Commands and arguments

| Decorator    | Use                                                                            |
|--------------|--------------------------------------------------------------------------------|
| `@Command`   | A function that becomes a top-level command.                                   |
| `@Group`     | A class whose `@Member` methods become sub-commands, as in `tasks add`.        |
| `@Member`    | A method that becomes a sub-command of its `@Group` or `@Shadow` class.        |
| `@GroupInit` | Runs when the group is typed on its own. Return `True` to stay inside it.     |
| `@Shadow`    | A class whose `@Member` methods become top-level commands.                     |

Parameters map to arguments like this:

| Signature                     | Command line                                              |
|-------------------------------|-----------------------------------------------------------|
| `name`                        | required positional `<name>`                              |
| `*words`                      | any number of extra arguments                             |
| `shout=False`                 | flag `--shout`                                            |
| `color=True`                  | flag `--no-color`                                         |
| `label=None`                  | option `--label LABEL`                                    |
| `times=1`                     | option `--times int`, typed from the default              |
| `dry_run=False`               | flag `--dry-run`, with underscores as dashes              |
| `v=False`                     | single-letter names give a short flag, `-v`               |
| `count: int`, `ratio: float`  | positional, converted to the annotated type               |
| `enabled: bool`               | positional accepting yes/no, on/off, true/false, 1/0      |

Put `*args` last, after the parameters with defaults. Parameters after `*args` are
keyword-only, and keyword-only parameters and `**kwargs` aren't supported.

`--` ends the options, so `add -- "-v is broken"` passes `-v is broken` as the title. A bad
value prints the command's usage.

A command can raise `autoshell.error` or `autoshell.stop` to give up quietly, or
`autoshell.help` to print its own help. Any other exception prints a traceback, and the shell
keeps running.

## Groups

- **Nested groups:** a group class or instance stored as an attribute of another group becomes a
  nested group, as in `tasks tags add`.
- **Constructor arguments:** pass an instance, such as `Shell(commands=[Tasks(store)])`, to give a
  group constructor arguments. A class is instantiated with no arguments.
- **Shared state:** every command and group can reach a per-shell `_root` object. Groups also get
  `_parent`, the enclosing group.

## Using the shell

| Input                      | Effect                                                             |
|----------------------------|--------------------------------------------------------------------|
| `tasks`                    | enter a group; the prompt shows the path, as in `tasks › tags $`   |
| `..`                       | leave the current group                                            |
| `cd`                       | return to the top level                                            |
| `!greet world`             | run a top-level command from inside a group                        |
| `help`, `?`                | list groups and commands with their docstrings                     |
| `help tasks add`           | full help for one command                                          |
| `# ...`                    | comment                                                            |
| `exit`                     | leave the group, or quit at the top level                          |
| Tab                        | complete commands, groups, `--options` and argument values         |

To complete argument values, add a `complete_<command>(self, text, args)` method to the group, or
set `fn.complete = lambda text, args: [...]` on a `@Command`. `args` holds the words already
typed after the command.

## Output

Commands print with rich: `from rich import print`, or the shell's own `self._root.console`.
Output goes to the shell's `stdout`. Colour is used only on a terminal and respects `NO_COLOR`.

## Scripting and testing

`Shell.One("tasks add x")` runs a single command line without the interactive loop. Pass
`stdin` and `stdout` streams to drive a whole session:

```python
import io

out = io.StringIO()
autoshell.Shell(stdin=io.StringIO('greet world\n'), stdout=out, commands=[greet]).Start()
assert 'hello, world!' in out.getvalue()
```

## Development

```sh
python3 -m venv .venv
.venv/bin/pip install -e '.[test]'
.venv/bin/pytest
```

## License

MIT. See [LICENSE](LICENSE).
