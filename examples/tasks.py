#!/usr/bin/env python3
'''
A small task tracker built with autoshell.

    $ python examples/tasks.py [--demo]     --demo adds some tasks to start with
    $ help                                  list groups and commands
    $ tasks                                 enter the tasks group
    tasks $ add "write docs" --priority 2 --estimate 1.5
    tasks $ add -- "-v flag is broken"      -- ends options, so the title can start with -
    tasks $ list --no-show-tags
    tasks $ tags add 1 docs                 nested group
    tasks $ done 1
    tasks $ !verbose yes                    ! runs a top-level command from inside a group
    tasks $ ..                              leave the group
    $ help tasks add                        help for one command
    $ exit

Tab completes commands, --options, task numbers, tags and greet names.
History is kept in ~/.autoshell_tasks_history.
'''

import sys

from rich import print
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

import autoshell
from autoshell import Command, Group, GroupInit, Member, Shadow


class Store:
    'the task list, handed to the Tasks group through its constructor'
    def __init__(self):
        self.tasks = {}
        self.next_id = 1

    def numbers(self):
        return [str(n) for n in self.tasks]

    def all_tags(self):
        return sorted(set().union(*[t['tags'] for t in self.tasks.values()]))

    def get(self, num):
        if num not in self.tasks:
            print(f'[red]no task {num}[/]')
            # error: abandon the command quietly
            raise autoshell.error(num)
        return self.tasks[num]


#
# top-level commands
#

@Command
def greet(name, shout=False, times=1):
    'say hello; --shout for capitals, --times N to repeat'
    text = f'hello, {escape(name)}!'
    for _ in range(times):
        print(text.upper() if shout else text)

# a plain @Command gets tab completion through a .complete attribute
greet.complete = lambda text, args: ['world', 'team', 'everyone'] if not args else []


@Command
def echo(*words):
    'print the arguments back'
    if not words:
        # help: print this command's help instead
        raise autoshell.help
    print(escape(' '.join(words)))


@Command
def verbose(enabled: bool):
    'show more detail; takes yes/no, on/off, true/false or 1/0'
    # _root is one object per shell, shared by every command and group
    verbose._root.verbose = enabled
    print(f'verbose is {"on" if enabled else "off"}')


#
# groups
#

@Group
class Tags:
    'label tasks'

    # declared as a class attribute of Tasks below, so the shell creates it
    # and sets _parent to the Tasks instance

    @property
    def store(self):
        return self._parent.store

    @Member
    def add(self, num: int, *tags):
        'tag a task'
        task = self.store.get(num)
        task['tags'].update(tags)
        print(f'task {num}: {escape(", ".join(sorted(task["tags"])))}')

    @Member
    def clear(self, num: int):
        'remove all tags from a task'
        self.store.get(num)['tags'].clear()

    # tab completion: complete_<command>(text, args) returns candidates, and
    # args holds the words already typed after the command
    def complete_add(self, text, args):
        return self.store.numbers() if not args else self.store.all_tags()

    def complete_clear(self, text, args):
        return self.store.numbers() if not args else []


@Group
class Tasks:
    'add, finish and list tasks'

    tags = Tags

    def __init__(self, store):
        self.store = store

    @GroupInit
    def enter(self):
        'runs when "tasks" is typed alone; returning True stays in the group'
        print(f'[dim]{len(self.store.tasks)} tasks; help for commands, .. to leave[/]')
        return True

    @Member
    def add(self, title, priority=1, estimate: float = None):
        'add a task; --priority takes an int, --estimate a number of hours'
        num = self.store.next_id
        self.store.next_id += 1
        self.store.tasks[num] = dict(title=title, priority=priority, estimate=estimate,
                                     done=False, tags=set())
        print(f'added task [bold]{num}[/]')
        if getattr(self._root, 'verbose', False):
            print(f'[dim]priority={priority} estimate={estimate}[/]')

    @Member
    def done(self, num: int, undo=False):
        'mark a task done, or not done with --undo'
        self.store.get(num)['done'] = not undo

    @Member
    def remove(self, num: int):
        'delete a task'
        self.store.get(num)
        del self.store.tasks[num]

    @Member
    def clear(self, done_only=True, yes=False):
        'remove finished tasks; --no-done-only removes every task; needs --yes'
        doomed = [n for n, t in self.store.tasks.items() if t['done'] or not done_only]
        if not yes:
            print(f'[yellow]would remove {len(doomed)} tasks; add --yes to do it[/]')
            # stop: abandon the command quietly
            raise autoshell.stop
        for num in doomed:
            del self.store.tasks[num]
        print(f'removed {len(doomed)} tasks')

    @Member
    def list(self, all=False, tag=None, show_tags=True):
        'list open tasks; --all includes done ones, --tag filters, --no-show-tags hides tags'
        table = Table('#', 'task', 'priority', 'hours', *(['tags'] if show_tags else []))
        rows = sorted(self.store.tasks.items(), key=lambda kv: -kv[1]['priority'])
        for num, task in rows:
            if task['done'] and not all:
                continue
            if tag and tag not in task['tags']:
                continue
            title = escape(task['title'])
            if task['done']:
                title = f'[strike dim]{title}[/]'
            hours = '' if task['estimate'] is None else f'{task["estimate"]:g}'
            tags = [escape(' '.join(sorted(task['tags'])))] if show_tags else []
            table.add_row(str(num), title, str(task['priority']), hours, *tags)
        # the shell's console, which writes to the shell's stdout
        self._root.console.print(table)

    def complete_done(self, text, args):
        return self.store.numbers() if not args else []

    complete_remove = complete_done

    def complete_list(self, text, args):
        return self.store.all_tags() if args[-1:] == ['--tag'] else []


#
# shadow: members become top-level commands
#

@Shadow
class System:
    'general commands'

    @Member
    def about(self):
        'what this is'
        print(Panel('[bold cyan]tasks[/] - an autoshell example\n'
                    'type [bold]help[/] to see what it can do', expand=False))

    @Member
    def quit(self):
        'leave the shell'
        raise SystemExit


if __name__ == '__main__':
    store = Store()
    # pass an instance to give a group constructor arguments; classes are
    # instantiated with none
    shell = autoshell.Shell(commands=[greet, echo, verbose, Tasks(store), System],
                            history_file='~/.autoshell_tasks_history')

    if '--demo' in sys.argv[1:]:
        # One() runs a command line without the interactive loop
        for line in ['tasks add "write the docs" --priority 3 --estimate 2',
                     'tasks add "fix the parser bug" --priority 5 --estimate 0.5',
                     'tasks add "tidy up"',
                     'tasks tags add 1 docs',
                     'tasks tags add 2 bug urgent']:
            shell.One(line)

    shell.Start()
