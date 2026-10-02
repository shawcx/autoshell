
import inspect
import typing

from . import error
from .arguments import CommandParser

GROUP   = 1
SHADOW  = 2
INIT    = 3
COMMAND = 4
MEMBER  = 5

__all__ = ['Group', 'Shadow', 'Ignore', 'Member', 'Command', 'GroupInit']

# every @Command, @Group and @Shadow in definition order; a Shell given no
# explicit commands is built from this
registry = []

#
# decorators only mark; build() turns the marks into parsers for one shell
#

def Command(fn):
    'a top-level command'
    check_args(fn)
    fn.__AutoShell__ = COMMAND
    registry.append(fn)
    return fn

def Group(cls):
    'a group of sub-commands made of the methods decorated with @Member'
    cls.__AutoShell__ = GROUP
    registry.append(cls)
    return cls

def Shadow(cls):
    'add the methods decorated with @Member as top-level commands'
    cls.__AutoShell__ = SHADOW
    registry.append(cls)
    return cls

def Member(fn):
    'a sub-command of the enclosing @Group or @Shadow class'
    check_args(fn)
    fn.__AutoShell__ = MEMBER
    return fn

def GroupInit(fn):
    'called when the group is entered without a sub-command; return True to stay in it'
    fn.__AutoShell__ = INIT
    return fn

def Ignore(fn):
    'convenience function for verbose function decorators'
    return fn

#
# building the parser tree
#

# attributes build() sets on group instances; never scanned for commands
_LINKS = ('_parser', '_parent', '_root')

def build(commands, root):
    '''return the root parser for a shell. commands holds @Command functions
    and @Group/@Shadow classes or instances; classes are instantiated with no
    arguments. a group nested inside another is left out of the top level.'''
    parser = CommandParser(prog='')
    parser.add_argument('command')
    parser.handlers = {}
    parser.path = ()

    nested = set()
    groups = {}

    for item in commands:
        kind = getattr(item, '__AutoShell__', None)

        if kind == COMMAND:
            item._root = root
            name = item.__name__.lower()
            parser.handlers[name] = command_parser(item, name, complete=getattr(item, 'complete', None))

        elif kind == GROUP:
            instance = instantiate(item)
            name = type(instance).__name__.lower()
            parser.handlers[name] = group_parser(instance, name, parser, root, root, nested)
            groups[name] = type(instance)

        elif kind == SHADOW:
            instance = instantiate(item)
            for name, fn in members(instance):
                if fn.__AutoShell__ != MEMBER:
                    raise ValueError('Not implemented')
                parser.handlers[name] = command_parser(fn, name, 1, completer(instance, name))
            instance._root = root

        else:
            raise ValueError('not a command, group or shadow: %r' % (item,))

    for name, cls in groups.items():
        if cls in nested:
            del parser.handlers[name]

    return parser

def completer(instance, name):
    'the complete_<name>(text, args) method of instance, if any'
    return getattr(instance, 'complete_' + name, None)

def instantiate(item):
    return item() if isinstance(item, type) else item

def members(instance):
    'yield (name, value) for the marked attributes of instance'
    for name in dir(instance):
        if name.startswith('__') or name in _LINKS:
            continue
        # don't run property getters; the instance isn't linked up yet
        if isinstance(getattr(type(instance), name, None), property):
            continue
        value = getattr(instance, name)
        if hasattr(value, '__AutoShell__'):
            yield name.lower(), value

def group_parser(instance, name, parent_parser, parent, root, nested):
    parser = CommandParser(prog=name)
    parser.add_argument('<command>')
    parser.handlers = {}
    parser.path = parent_parser.path + (name,)
    parser.description = type(instance).__doc__
    parser.instance = instance
    parser.meta_init = None

    for attr, value in members(instance):
        kind = value.__AutoShell__
        if kind == MEMBER:
            parser.handlers[attr] = command_parser(value, attr, 1, completer(instance, attr))
        elif kind == GROUP:
            child = instantiate(value)
            nested.add(type(child))
            parser.handlers[attr] = group_parser(child, attr, parser, instance, root, nested)
        elif kind == INIT:
            parser.meta_init = value
        else:
            raise ValueError('Not implemented')

    instance._parser = parser
    instance._parent = parent
    instance._root   = root
    return parser

def command_parser(fn, name, argoffset=0, complete=None):
    parser = CommandParser(prog=name)
    parser.fn = fn
    parser.complete = complete
    compute_args(fn, parser, argoffset)
    return parser

def check_args(fn):
    spec = inspect.getfullargspec(fn)
    if spec.varkw or spec.kwonlyargs:
        raise error('Keyword arguments not implemented')

# accepted for parameters annotated as bool
TRUE_VALUES  = ('t', 'true',  'y', 'yes', '1', 'on')
FALSE_VALUES = ('f', 'false', 'n', 'no',  '0', 'off')

def boolean(text):
    'argparse type for bool: yes/no, on/off, true/false, y/n, t/f, 1/0'
    value = text.lower()
    if value in TRUE_VALUES:
        return True
    if value in FALSE_VALUES:
        return False
    raise ValueError(text)

def option_name(arg):
    'v -> -v, dry_run -> --dry-run'
    if len(arg) == 1:
        return '-' + arg
    return '--' + arg.replace('_', '-')

def type_hints(fn):
    try:
        return typing.get_type_hints(getattr(fn, '__func__', fn))
    except Exception:
        return {}

def hinted_type(hints, arg):
    'the argparse type for an annotated parameter, or None'
    hint = hints.get(arg)
    if hint is bool:
        return boolean
    if isinstance(hint, type):
        return hint
    return None

def compute_args(fn, parser, argoffset=0):
    parser.description = fn.__doc__
    spec = inspect.getfullargspec(fn)
    hints = type_hints(fn)

    args = spec.args[argoffset:]

    if spec.defaults:
        posargs = args[:-len(spec.defaults)]
        optargs = args[-len(spec.defaults):]
    else:
        posargs = args
        optargs = []

    parser.order = []

    for arg in posargs:
        kind = hinted_type(hints, arg)
        if kind:
            parser.add_argument(arg, metavar='<'+arg+'>', type=kind)
        else:
            parser.add_argument(arg, metavar='<'+arg+'>')
        parser.order.append(arg)

    if spec.defaults:
        for arg,val in zip(optargs, spec.defaults):
            parser.order.append(arg)
            kind = hinted_type(hints, arg)
            if val is True:
                # on by default, so the flag turns it off
                parser.add_argument('--no-' + arg.replace('_', '-'), dest=arg,
                                    action='store_false', default=True)
            elif val is False:
                parser.add_argument(option_name(arg), dest=arg, action='store_true', default=False)
            elif val is None:
                if kind:
                    parser.add_argument(option_name(arg), dest=arg, type=kind, metavar=hints[arg].__name__)
                else:
                    parser.add_argument(option_name(arg), dest=arg)
            else:
                kind = kind or type(val)
                hint = hints.get(arg, type(val))
                parser.add_argument(option_name(arg), dest=arg, type=kind,
                                    metavar=getattr(hint, '__name__', 'value'), default=val)

    parser.varargs = True if spec.varargs else False

    check_args(fn)
