
import sys
import argparse

from . import error, help

#
# ArgumentParser has a nasty habit of exiting, so disable that behavior
#
class CommandParser(argparse.ArgumentParser):
    out = sys.stderr
    def __init__(self, *args, **kwds):
        kwds['add_help'] = False
        argparse.ArgumentParser.__init__(self, *args, **kwds)

    def print_help(self):
        self._print_message(self.format_help(), self.out)
        raise help

    def error(self, message):
        raise error(message)

    def exit(self, status=0, message=None):
        pass
