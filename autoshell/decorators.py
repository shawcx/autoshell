
import inspect

from . import error
from .arguments import CommandParser
from .shell import Shell

GROUP   = 1
HIDDEN  = 2
INIT    = 3
COMMAND = 4
MEMBER  = 5

__all__ = ['Group', 'Shadow', 'Ignore', 'Member', 'Command', 'GroupInit']

#
#
#

def Group(cls):
    'add member functions decorated with @Member as sub-commands'

    cls.__AutoShell__ = GROUP
    action = cls.__name__.lower()
    instance = cls()

    groupparser = CommandParser(prog=action)
    groupparser.add_argument('<command>')
    groupparser.handlers = {}
    groupparser.prefix = action + ' '
    groupparser.instance = instance
    groupparser.meta_init = None
    groupparser.instance._parser = groupparser
    groupparser.instance._parent = Shell.root
    groupparser.instance._root   = Shell.root

    Shell.parser.handlers[action] = groupparser

    for name in dir(instance):
        if name.startswith('__'):
            continue
        fn = getattr(instance, name)
        if not hasattr(fn, '__AutoShell__'):
            continue

        name = name.lower()

        if fn.__AutoShell__ == MEMBER:
            parser = CommandParser(prog=name)
            parser.fn = fn
            compute_args(fn, parser, 1)
        elif fn.__AutoShell__ == GROUP:
            parser = Shell.parser.handlers[name]
            parser.instance._parent = instance
            parser.prefix = groupparser.prefix + parser.prefix
            del Shell.parser.handlers[name]
        elif fn.__AutoShell__ == INIT:
            groupparser.meta_init = fn
            continue
        else:
            raise ValueError('Not implemented')

        groupparser.handlers[name] = parser

    return cls

#
#
#

def Shadow(cls):
    cls.__AutoShell__ = GROUP
    instance = cls()
    instance._root = Shell.root

    for name in dir(instance):
        if name.startswith('__'):
            continue
        fn = getattr(instance, name)
        if not hasattr(fn, '__AutoShell__'):
            continue

        name = name.lower()

        if fn.__AutoShell__ == MEMBER:
            parser = CommandParser(prog=name)
            parser.fn = fn
            compute_args(fn, parser, 1)
        else:
            raise ValueError('Not implemented')

        Shell.parser.handlers[name] = parser

    return cls

def Command(fn):
    'add the command to the base parser'
    # mark the function for when we iterate the class
    fn.__AutoShell__ = COMMAND
    fn._root = Shell.root

    action = fn.__name__.lower()

    parser = CommandParser(prog=action)
    parser.fn = fn
    Shell.parser.handlers[action] = parser

    compute_args(fn, parser)

    return fn

def Member(fn):
    'mark the function, will be processed when the class is decorated'
    fn.__AutoShell__ = MEMBER
    return fn

def GroupInit(fn):
    'mark the function, will be processed when the class is decorated'
    fn.__AutoShell__ = INIT
    return fn

def Ignore(fn):
    'convenience function for verbose function decorators'
    return fn


def compute_args(fn, parser, argoffset=0):
    parser.description = fn.__doc__
    spec = inspect.getfullargspec(fn)

    args = spec.args[argoffset:]

    if spec.defaults:
        posargs = args[:-len(spec.defaults)]
        optargs = args[-len(spec.defaults):]
    else:
        posargs = args
        optargs = []

    parser.order = []

    for arg in posargs:
        parser.add_argument(arg, metavar='<'+arg+'>')
        parser.order.append(arg)

    if spec.defaults:
        for arg,val in zip(optargs, spec.defaults):
            parser.order.append(arg)
            prefix = '-' if 1 == len(arg) else '--'
            arg = prefix+arg
            if val is None:
                parser.add_argument(arg)
            elif val is True:
                parser.add_argument(arg, action='store_false', default=val)
            elif val is False:
                parser.add_argument(arg, action='store_true', default=val)
            else:
                parser.add_argument(arg, type=val.__class__, metavar=type(val).__name__, default=val)

    parser.varargs = True if spec.varargs else False

    if spec.varkw or spec.kwonlyargs:
        raise error('Keyword arguments not implemented')
