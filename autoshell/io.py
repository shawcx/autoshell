
import sys
import builtins

# where printf/writeln/hexdump write; Shell points this at its own stream
stdout = None

def _out():
    return stdout or sys.stdout

class Colors:
    def white(self, fmt='', *args):
        fmt = '\x1b[1;37m' + fmt + '\x1b[0m'
        self(fmt, *args)

    def black(self, fmt='', *args):
        fmt = '\x1b[1;30m' + fmt + '\x1b[0m'
        self(fmt, *args)

    def red(self, fmt='', *args):
        fmt = '\x1b[1;31m' + fmt + '\x1b[0m'
        self(fmt, *args)

    def yellow(self, fmt='', *args):
        fmt = '\x1b[1;33m' + fmt + '\x1b[0m'
        self(fmt, *args)

    def green(self, fmt='', *args):
        fmt = '\x1b[1;32m' + fmt + '\x1b[0m'
        self(fmt, *args)

    def blue(self, fmt='', *args):
        fmt = '\x1b[1;34m' + fmt + '\x1b[0m'
        self(fmt, *args)

    def cyan(self, fmt='', *args):
        fmt = '\x1b[1;36m' + fmt + '\x1b[0m'
        self(fmt, *args)

    def purple(self, fmt='', *args):
        fmt = '\x1b[1;35m' + fmt + '\x1b[0m'
        self(fmt, *args)

class PrintF(Colors):
    def __call__(self, fmt, *args):
        if args:
            fmt = fmt % args
        out = _out()
        out.write(fmt)
        out.flush()

class WriteLn(Colors):
    def __call__(self, fmt='', *args):
        if args:
            fmt = fmt % args
        _out().write(fmt + '\n')

def hexdump(data, offset=0):
    if isinstance(data, str):
        data = data.encode('utf-8')
    fmt = '%%.%dx: ' % len('%.x' % len(data))
    while data:
        line = data[:16]
        data = data[16:]
        printf.black(fmt, offset)
        printf.blue(' '.join(['%.2x' % c for c in line]))
        printf(' ' * (50 - len(line) * 3))
        for c in line:
            if c < 32 or c > 126:
                printf.black('.')
            else:
                printf.white('%c', c)
        writeln()
        offset += 16

printf  = builtins.printf  = PrintF()
writeln = builtins.writeln = WriteLn()
builtins.hexdump = hexdump
