
import sys
import shlex
import traceback
from contextlib import contextmanager

import os
import re

import rich
from rich.console import Console
from rich.text import Text

try:
    import readline
except ImportError:
    readline = None

from . import error, help, stop
from .arguments import CommandParser
from .decorators import build, registry

class Root:
    'shared object handed to every command and group as _root'
    pass

# names the shell handles itself, offered by tab completion
BUILTINS = ('help', 'exit')

# prompt colours for each group depth, repeating if nested deeper
GROUP_STYLES = ('bold cyan', 'bold magenta', 'bold yellow', 'bold green')

_ansi = re.compile(r'(\x1b\[[0-9;]*m)')

def _libedit():
    'true for the libedit readline emulation (macOS), false for GNU readline'
    return readline is not None and (getattr(readline, 'backend', None) == 'editline'
                                     or 'libedit' in (readline.__doc__ or ''))

class Shell:
    def __init__(self, prompt='$ ', stdin=None, stdout=None, commands=None, history_file=None,
                 separator=' › '):
        '''commands is a list of @Command functions and @Group/@Shadow classes
        or instances; by default, everything decorated so far. history_file
        keeps readline history between sessions.'''
        self.root = Root()
        self.parser = build(registry if commands is None else commands, self.root)

        self.stop = False
        self.parsers = [self.parser]
        self.prompt = prompt
        self.separator = separator
        self.stdin  = stdin  if stdin  is not None else sys.stdin
        self.stdout = stdout if stdout is not None else sys.stdout

        # commands print with rich; on the process stdout that is rich's own
        # global console, otherwise a console on this shell's stream
        if self.stdout is sys.stdout:
            self.console = rich.get_console()
        else:
            self.console = Console(file=self.stdout)
        self.root.console = self.console

        self.history_file = os.path.expanduser(history_file) if history_file else None

    def _bind(self):
        # route argparse output to this shell
        CommandParser.out = self.stdout

    @contextmanager
    def _redirect(self):
        'point rich.print and friends at this shell while a command runs'
        glob = rich.get_console()
        if self.console is glob:
            yield
            return
        # the same swap rich.reconfigure() does, undone afterwards
        saved = glob.__dict__
        glob.__dict__ = self.console.__dict__
        try:
            yield
        finally:
            glob.__dict__ = saved

    def _interactive(self):
        # input() gives readline editing, but only works on the process streams
        return self.stdin is sys.stdin and self.stdout is sys.stdout

    @contextmanager
    def _readline_session(self):
        'install tab completion and load history for the duration of Start()'
        if readline is None or not self._interactive():
            yield
            return

        old_completer = readline.get_completer()
        old_delims = readline.get_completer_delims()
        readline.set_completer(self._complete)
        # keep - so --options complete as one word
        readline.set_completer_delims(' \t\n')
        if _libedit():
            readline.parse_and_bind('bind ^I rl_complete')
        else:
            readline.parse_and_bind('tab: complete')

        if self.history_file:
            try:
                readline.read_history_file(self.history_file)
            except OSError:
                pass
        try:
            yield
        finally:
            if self.history_file:
                try:
                    readline.write_history_file(self.history_file)
                except OSError:
                    pass
            readline.set_completer(old_completer)
            readline.set_completer_delims(old_delims)

    def _complete(self, text, state):
        'readline completer; see completions()'
        if state == 0:
            line = readline.get_line_buffer()[:readline.get_begidx()]
            self._matches = self.completions(line, text)
        try:
            return self._matches[state]
        except IndexError:
            return None

    def completions(self, line, text):
        '''tab completion candidates for the word text, where line is
        everything typed before it'''
        try:
            words = shlex.split(line)
        except ValueError:
            return []

        parser = self.parsers[-1]
        bang = ''
        rooted = False
        if words and words[0].startswith('!'):
            parser, rooted = self.parsers[0], True
            words[0] = words[0][1:]
            if not words[0]:
                words.pop(0)
        elif not words and text.startswith('!'):
            parser, rooted = self.parsers[0], True
            bang, text = '!', text[1:]

        # help <group> <command> completes group and command names only
        helping = bool(words) and words[0] in ('help', '?') and 'help' not in parser.handlers
        if helping:
            words = words[1:]

        for i, word in enumerate(words):
            child = parser.handlers.get(word)
            if child is None:
                return []
            if hasattr(child, 'handlers'):
                parser = child
                continue
            if helping:
                return []
            return self._complete_args(child, words[i+1:], text)

        names = sorted(parser.handlers)
        if not words and not helping:
            # exit, .. and cd are handled before ! dispatch, so only help works after it
            builtins = ['help'] if rooted else list(BUILTINS)
            if not rooted and len(self.parsers) > 1:
                builtins.append('..')
            names += [b for b in builtins if b not in parser.handlers]
        return [bang + n + ' ' for n in names if n.startswith(text)]

    def _complete_args(self, parser, args, text):
        if text.startswith('-'):
            options = [o for a in parser._actions for o in a.option_strings if o not in args]
            return [o + ' ' for o in sorted(options) if o.startswith(text)]
        if parser.complete is None:
            return []
        try:
            values = parser.complete(text, args)
        except Exception:
            return []
        return [str(v) + ' ' for v in values if str(v).startswith(text)]

    def path_text(self, path):
        'a group path as rich Text, coloured by depth'
        text = Text()
        for depth, name in enumerate(path):
            if depth:
                text.append(self.separator, style='dim')
            text.append(name, style=GROUP_STYLES[depth % len(GROUP_STYLES)])
        return text

    def render_prompt(self):
        '''the prompt for the current group, with colour codes when the
        console is a terminal'''
        path = self.parsers[-1].path
        text = self.path_text(path)
        if path:
            text.append(' ')
        text.append(self.prompt)
        with self.console.capture() as capture:
            self.console.print(text, end='', soft_wrap=True)
        rendered = capture.get()
        if self._interactive() and readline is not None and not _libedit():
            # GNU readline must not count colour codes towards the prompt
            # width; libedit prints the \001/\002 markers wrongly, so it
            # gets the codes unmarked
            rendered = _ansi.sub('\x01\\1\x02', rendered)
        return rendered

    def _readline(self, prompt):
        if self._interactive():
            return input(prompt)
        self.stdout.write(prompt)
        self.stdout.flush()
        line = self.stdin.readline()
        if not line:
            raise EOFError
        return line.rstrip('\n')

    def Start(self):
        with self._readline_session():
            self._loop()

    def _loop(self):
        echo = not self.stdin.isatty()

        while not self.stop:
            self._bind()
            try:
                self.stdout.write('\n')
                line = self._readline(self.render_prompt())
            except KeyboardInterrupt:
                continue
            except EOFError:
                self.OnEOF()
                break

            if echo:
                self.stdout.write(line + '\n')

            if not line:
                continue

            # ^C during a command abandons it, including any groups it entered
            depth = len(self.parsers)
            try:
                self.One(line)
            except KeyboardInterrupt:
                del self.parsers[depth:]
                self.stdout.write('\n')

    def OnEOF(self):
        self.stdout.write('\n')

    def One(self, cmd):
        self._bind()

        if cmd.__class__ is str:
            try:
                cmd = shlex.split(cmd)
            except ValueError as e:
                self.stdout.write('Parse error: %s\n' % e)
                return

        if not cmd:
            return

        # bare cd returns to the top level
        if cmd == ['cd']:
            del self.parsers[1:]
            return

        # .. leaves the current group
        if cmd[0] == 'exit' or cmd == ['..']:
            if 1 == len(self.parsers):
                self.stop = True
                return
            self.parsers.pop()
            return

        with self._redirect():
            self.Run(cmd)

    def Run(self, cmd, parser=None):
        # use the last parser on the stack
        if parser is None:
            parser = self.parsers[-1]

        # ! says to execute from the first parser on the stack
        if cmd[0].startswith('!'):
            parser = self.parsers[0]

            # trim the bang
            cmd[0] = cmd[0][1:]
            # support bang space command
            if not cmd[0]:
                cmd = cmd[1:]
            # if no cmd, print help
            if not cmd:
                cmd = ['help']

        # ignore comments
        if cmd[0].startswith('#'):
            return

        # print help, unless a command is itself called help
        if cmd[0] in ('?', '--help') or (cmd[0] == 'help' and 'help' not in parser.handlers):
            self.Help(cmd[1:], parser)
            return

        # load the handler for the given command
        try:
            parser = parser.handlers[cmd[0]]
        except KeyError:
            self.stdout.write('Unknown command: "%s"\n' % cmd[0])
            return

        # is it a sub-command?
        if hasattr(parser, 'handlers'):
            self.parsers.append(parser)

            if len(cmd) == 1: # only group specified
                if parser.meta_init:
                    try:
                        keep = parser.meta_init()
                    except error:
                        keep = False
                    except Exception:
                        traceback.print_exc(file=self.stdout)
                        keep = False
                else:
                    return True
            else:
                keep = self.Run(cmd[1:], parser)

            if keep != True:
                self.parsers.pop()

            return keep

        # is it a function?
        elif hasattr(parser, 'fn'):
            varargs = None
            try:
                if not parser.varargs:
                    args = parser.parse_args(cmd[1:])
                else:
                    (args, varargs) = parser.parse_known_args(cmd[1:])
                    # TODO: if useful add "smart" parsing of varargs
            except help:
                return
            except error as e:
                usage = parser.format_usage()
                self.stdout.write(usage)
                return

            fnargs = []
            for name in parser.order:
                fnargs.append(getattr(args, name))
            if parser.varargs:
                fnargs += varargs

            try:
                parser.fn(*fnargs)
            except help:
                self.stdout.write('\n%s\n' % parser.format_help())
            except stop:
                return # a command can raise this to stop processing
            except error:
                return
            except Exception:
                traceback.print_exc(file=self.stdout)

    def Help(self, path=(), parser=None):
        '''show help for the group or command at path, relative to parser
        (by default the current group)'''
        if parser is None:
            parser = self.parsers[-1]

        for i, name in enumerate(path):
            child = parser.handlers.get(name)
            if child is None:
                self.stdout.write('Unknown command: "%s"\n' % ' '.join(path[:i+1]))
                return
            if not hasattr(child, 'handlers'):
                self.stdout.write(child.format_help())
                return
            parser = child

        def summary(p):
            lines = (p.description or '').strip().splitlines()
            return lines[0] if lines else ''

        groups   = [(n, p) for n, p in sorted(parser.handlers.items()) if hasattr(p, 'handlers')]
        commands = [(n, p) for n, p in sorted(parser.handlers.items()) if not hasattr(p, 'handlers')]
        width = max([len(n) for n in parser.handlers] + [0])

        if parser.path:
            self.console.print(self.path_text(parser.path))
            if parser.description:
                self.console.print(Text(parser.description.strip()))
            self.console.print()
        for title, entries in (('Groups', groups), ('Commands', commands)):
            if not entries:
                continue
            self.console.print(Text(title, style='bold blue'))
            for name, p in entries:
                line = Text('  ' + name, style='bold')
                if summary(p):
                    line.append(' ' * (width - len(name)) + '  ' + summary(p))
                self.console.print(line)
            self.console.print()
