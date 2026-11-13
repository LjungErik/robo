"""Small, safe expressions for character files.

Anything in a character file that should move can be written as an
expression instead of a number, e.g. ``"sin(t * 3) * 6"`` or
``"-34 + trail * 0.5"``. They are plain Python syntax, but only a tiny,
harmless subset is allowed: numbers, strings, variables, arithmetic,
comparisons, ``and``/``or``/``not``, ``x if cond else y``, ``in``, tuples
and calls to the functions in FUNCTIONS. No attributes, indexing, imports
or anything else, so a character file can never run real code.

    compile_expr("sin(t * 3)")  ->  Expr;  expr(env) -> value
"""
import ast
import math
import random

MAX_POW = 64                       # pow(a, b): b is capped so files can't hang Robo


def _clamp(x, lo=0.0, hi=1.0):
    return min(max(x, lo), hi)


def _smooth(k):
    k = _clamp(k)
    return k * k * (3 - 2 * k)


def _pick(i, *values):
    """pick(i, a, b, c): the i-th value, wrapping around (i may be any number)."""
    return values[int(i) % len(values)] if values else 0


def _pow(a, b):
    b = min(b, MAX_POW)
    if a < 0 and b != int(b):
        return 0.0                 # would be a complex number
    try:
        return float(a) ** b
    except (OverflowError, ZeroDivisionError):
        return 0.0


def _sign(x):
    return (x > 0) - (x < 0)


def _mul(a, b):
    if isinstance(a, (str, tuple, list)) or isinstance(b, (str, tuple, list)):
        raise ExprError('only numbers can be multiplied')
    return a * b


class _SafeMul(ast.NodeTransformer):
    """a * b  ->  _mul(a, b), so "text" * 10**9 can't eat all the memory."""
    def visit_BinOp(self, node):
        self.generic_visit(node)
        if isinstance(node.op, ast.Mult):
            return ast.copy_location(
                ast.Call(ast.Name('_mul', ast.Load()), [node.left, node.right], []), node)
        return node


FUNCTIONS = {
    'sin': math.sin, 'cos': math.cos, 'tan': math.tan, 'atan2': math.atan2,
    'sqrt': lambda x: math.sqrt(max(0.0, x)), 'abs': abs, 'min': min, 'max': max,
    'floor': math.floor, 'ceil': math.ceil, 'round': round, 'int': int, 'float': float,
    'sign': _sign, 'pow': _pow, 'clamp': _clamp, 'smooth': _smooth,
    'lerp': lambda a, b, k: a + (b - a) * k, 'pick': _pick,
    'hypot': math.hypot,
    # random numbers: in particle spawns these use Robo's own random generator
    'rand': random.uniform, 'choice': lambda *v: random.choice(v),
}
CONSTANTS = {'pi': math.pi, 'tau': 2 * math.pi, 'true': True, 'false': False,
             'True': True, 'False': False, 'None': None}

_ALLOWED = (
    ast.Expression, ast.BoolOp, ast.BinOp, ast.UnaryOp, ast.Compare, ast.IfExp, ast.Call,
    ast.Name, ast.Load, ast.Constant, ast.Tuple, ast.List,
    ast.And, ast.Or, ast.Not, ast.USub, ast.UAdd,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn,
)


class ExprError(ValueError):
    pass


class Expr:
    """A compiled expression; call it with a dict of variables."""
    __slots__ = ('source', 'code', 'names', 'const')

    def __init__(self, source, code, names, const=None):
        self.source = source
        self.code = code
        self.names = names            # variable names it reads
        self.const = const            # set when it doesn't depend on anything

    def __call__(self, env):
        if self.code is None:
            return self.const
        try:
            return eval(self.code, _GLOBALS, env)          # noqa: S307 (checked AST)
        except ZeroDivisionError:
            return 0.0

    def __repr__(self):
        return f'Expr({self.source!r})'


_GLOBALS = {'__builtins__': {}, '_mul': _mul, **FUNCTIONS, **CONSTANTS}


def _check(tree, source):
    names = set()
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED):
            raise ExprError(f'{source!r}: {type(node).__name__} is not allowed in expressions')
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in FUNCTIONS:
                raise ExprError(f'{source!r}: unknown function')
            if node.keywords:
                raise ExprError(f'{source!r}: keyword arguments are not allowed')
        elif isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Constant) and not isinstance(node.value, (int, float, str, bool,
                                                                             type(None))):
            raise ExprError(f'{source!r}: unsupported constant')
    called = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call)}
    return frozenset(names - called - set(CONSTANTS))


def compile_expr(value):
    """Number, bool or expression string -> Expr. Anything else is an error."""
    if isinstance(value, Expr):
        return value
    if isinstance(value, bool) or value is None:
        return Expr(repr(value), None, frozenset(), value)
    if isinstance(value, (int, float)):
        return Expr(repr(value), None, frozenset(), float(value))
    if not isinstance(value, str):
        raise ExprError(f'expected a number or an expression, got {value!r}')
    source = value.strip()
    if len(source) > 2000:
        raise ExprError('expression too long')
    try:
        tree = ast.parse(source, mode='eval')
    except SyntaxError as e:
        raise ExprError(f'{source!r}: {e.msg}') from None
    names = _check(tree, source)
    tree = ast.fix_missing_locations(_SafeMul().visit(tree))
    code = compile(tree, '<character file>', 'eval')
    if not names and not _uses_random(tree):
        return Expr(source, None, frozenset(), eval(code, _GLOBALS, {}))  # noqa: S307
    return Expr(source, code, names)


def _uses_random(tree):
    return any(isinstance(n, ast.Call) and n.func.id in ('rand', 'choice') for n in ast.walk(tree))


def evaluate(value, env):
    """Evaluate a number / expression string right away (no caching)."""
    return compile_expr(value)(env)
