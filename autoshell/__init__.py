

# exception to raise on parse error
class error(Exception):
    pass

# exception to raise on help message
class help(Exception):
    pass

# exception to raise on early exit
class stop(Exception):
    pass

from .arguments  import CommandParser
from .shell      import Shell
from .decorators import *
