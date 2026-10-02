
import sys
import shlex
import traceback

try:
    import readline
except ImportError:
    pass

from . import error, help, stop
from . import io
from .arguments import CommandParser

class Root:
    pass

class Shell:
    # the root command parser
    parser = CommandParser(prog='')
    parser.handlers = {}
    parser.prefix = ''
    parser.add_argument('command')

    root = Root()

    def __init__(self, prompt='$ ', stdin=None, stdout=None):
        self.stop = False
        self.parsers = [Shell.parser]
        self.prompt = prompt
        self.stdin  = stdin  if stdin  is not None else sys.stdin
        self.stdout = stdout if stdout is not None else sys.stdout

        self.history = []

    def _bind(self):
        # route printf/writeln/hexdump and argparse output to this shell
        io.stdout = self.stdout
        CommandParser.out = self.stdout

    def _readline(self, prompt):
        # input() gives readline editing, but only works on the process streams
        if self.stdin is sys.stdin and self.stdout is sys.stdout:
            return input(prompt)
        self.stdout.write(prompt)
        self.stdout.flush()
        line = self.stdin.readline()
        if not line:
            raise EOFError
        return line.rstrip('\n')

    def Start(self):
        echo = not self.stdin.isatty()

        while not self.stop:
            self._bind()
            prefix = self.parsers[-1].prefix
            try:
                self.stdout.write('\n')
                line = self._readline(prefix + self.prompt)
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

        if cmd[0] == 'exit' or cmd[:2] == ['cd', '..']:
            if 1 == len(self.parsers):
                self.stop = True
                return
            self.parsers.pop()
            return

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
                cmd = ['?']

        # ignore comments
        if cmd[0].startswith('#'):
            return

        # print help
        if cmd[0] == '--help' or cmd[0] == '?':
            self.stdout.write('\n')
            commands = sorted(parser.handlers)
            for command in commands:
                self.stdout.write(parser.handlers[command].format_usage())
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
                writeln('\n%s', parser.format_help())
            except stop:
                return # a command can raise this to stop processing
            except error:
                return
            except Exception:
                traceback.print_exc(file=self.stdout)
