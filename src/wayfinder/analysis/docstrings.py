"""Checking a function's docstring against its own code. No model involved.

Parameters, return values and raised exceptions are facts the code states exactly, so a
docstring that disagrees is drift we can find with certainty. Google, Sphinx and NumPy
docstring styles are understood. Precision matters more than recall here: a check only
fires when the docstring makes a clear, checkable claim.
"""

from __future__ import annotations

import ast
import io
import re
import textwrap
import tokenize
from collections.abc import Iterator

from wayfinder.domain.results import DriftFinding

_NESTED = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)
FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef

_HEADERS = {
    "params": re.compile(r"^(Args|Arguments|Parameters|Params|Other Parameters|Keyword Args|Keyword Arguments)\s*:?$", re.I),
    "raises": re.compile(r"^(Raises|Raise)\s*:?$", re.I),
    "returns": re.compile(r"^(Returns?|Yields?)\s*:?$", re.I),
}
_UNDERLINE = re.compile(r"^-{3,}$")
# An entry names something at the start of a line: `x`, `x: desc`, `x (int): desc`, `x : int`.
_PARAM_ENTRY = re.compile(r"^(\*{0,2}[A-Za-z_]\w*)\s*(?:\([^)]*\))?\s*(?::.*)?$")
_RAISES_ENTRY = re.compile(r"^([A-Za-z_][\w.]*)\s*(?::.*)?$")
_SPHINX_PARAM = re.compile(r"^:param\s+(?:[\w\[\], .|]+\s+)?(\*{0,2}[A-Za-z_]\w*)\s*:")
_SPHINX_RAISES = re.compile(r"^:raises?\s+([\w.]+)\s*:")
_SPHINX_RETURNS = re.compile(r"^:(?:returns?|yields?)\s*:")


class _Documented:
    """What a docstring claims. None means no such section (no claim), which is different
    from a section that lists nothing."""

    def __init__(self) -> None:
        self.params: set[str] | None = None
        self.raises: set[str] | None = None
        self.returns = False


def _is_underlined(lines: list[str], i: int) -> bool:
    return i + 1 < len(lines) and bool(_UNDERLINE.match(lines[i + 1].strip()))


def _sections(doc: str) -> Iterator[tuple[str, list[str]]]:
    """(kind, body lines) for each Google- or NumPy-style section. `kind` is 'params',
    'raises' or 'returns'."""
    lines = doc.splitlines()
    i = 0
    while i < len(lines):
        head = lines[i].strip()
        numpy = _is_underlined(lines, i)
        google = head.endswith(":") and lines[i] == lines[i].lstrip()
        kind = next((k for k, pattern in _HEADERS.items() if pattern.match(head)), None) if (numpy or google) else None
        if kind is None:
            i += 1
            continue
        i += 2 if numpy else 1
        body: list[str] = []
        while i < len(lines):
            line = lines[i]
            if numpy:
                ends = bool(line.strip()) and _is_underlined(lines, i)  # the next section's title
            else:
                ends = bool(line.strip()) and line == line.lstrip()  # any unindented text
            if ends:
                break
            body.append(line)
            i += 1
        yield kind, body


def _entries(body: list[str], pattern: re.Pattern[str]) -> set[str]:
    """Names introduced at the section's entry indent; continuation lines sit deeper."""
    lines = [line for line in body if line.strip()]
    if not lines:
        return set()
    indent = min(len(line) - len(line.lstrip()) for line in lines)
    names: set[str] = set()
    for line in lines:
        if len(line) - len(line.lstrip()) == indent and (m := pattern.match(line.strip())):
            names.add(m.group(1))
    return names


def _parse(doc: str) -> _Documented:
    out = _Documented()
    for kind, body in _sections(doc):
        if kind == "params":
            out.params = (out.params or set()) | {n.lstrip("*") for n in _entries(body, _PARAM_ENTRY)}
        elif kind == "raises":
            out.raises = (out.raises or set()) | {n.split(".")[-1] for n in _entries(body, _RAISES_ENTRY)}
        elif any(line.strip() for line in body):
            out.returns = True
    for line in doc.splitlines():  # Sphinx field lists
        line = line.strip()
        if m := _SPHINX_PARAM.match(line):
            out.params = (out.params or set()) | {m.group(1).lstrip("*")}
        elif m := _SPHINX_RAISES.match(line):
            out.raises = (out.raises or set()) | {m.group(1).split(".")[-1]}
        elif _SPHINX_RETURNS.match(line):
            out.returns = True
    return out


def _own_nodes(func: FunctionNode) -> Iterator[ast.AST]:
    """Every node in the function's own body, not descending into nested functions/classes."""
    stack: list[ast.AST] = list(func.body)
    while stack:
        node = stack.pop()
        yield node
        if not isinstance(node, _NESTED):
            stack.extend(ast.iter_child_nodes(node))


def _raised_names(func: FunctionNode) -> set[str]:
    names: set[str] = set()
    for node in _own_nodes(func):
        if not isinstance(node, ast.Raise) or node.exc is None:
            continue
        exc = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
        name = exc.id if isinstance(exc, ast.Name) else exc.attr if isinstance(exc, ast.Attribute) else None
        if name and name[0].isupper():  # `raise error` re-raises a variable; only classes count
            names.add(name)
    return names


def _returns_a_value(func: FunctionNode) -> bool:
    for node in _own_nodes(func):
        if isinstance(node, (ast.Yield, ast.YieldFrom)):
            return True
        if isinstance(node, ast.Return) and node.value is not None:
            if not (isinstance(node.value, ast.Constant) and node.value.value is None):
                return True
    return False


def _is_stub(func: FunctionNode) -> bool:
    """A body that does nothing or only raises: an abstract method or protocol stub."""
    body = func.body[1:] if ast.get_docstring(func) is not None else func.body
    return all(
        isinstance(s, (ast.Pass, ast.Raise)) or (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))
        for s in body
    )


def _signature_params(func: FunctionNode) -> list[str]:
    a = func.args
    names = [p.arg for p in (*a.posonlyargs, *a.args, *a.kwonlyargs)]
    names += [p.arg for p in (a.vararg, a.kwarg) if p is not None]
    return [n for n in names if n not in ("self", "cls")]


def _function(source: str) -> FunctionNode | None:
    try:
        tree = ast.parse(textwrap.dedent(source))
    except SyntaxError:
        return None
    return next((n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))), None)


def has_documentation(source: str) -> bool:
    """Does the function have a docstring or any comment - anything to check?"""
    func = _function(source)
    if func is not None and ast.get_docstring(func):
        return True
    try:
        tokens = tokenize.generate_tokens(io.StringIO(textwrap.dedent(source)).readline)
        return any(t.type == tokenize.COMMENT for t in tokens)
    except (tokenize.TokenError, IndentationError):
        return False


def check_docstring(source: str, def_line: int) -> list[DriftFinding]:
    """Findings for a function's source. `def_line` is the file line of its `def`."""
    func = _function(source)
    doc = ast.get_docstring(func) if func else None
    if func is None or not doc:
        return []

    at = def_line + (func.body[0].lineno - func.lineno)  # the docstring's own line in the file
    documented = _parse(doc)
    signature = _signature_params(func)
    findings: list[DriftFinding] = []

    def add(kind: str, severity: str, message: str) -> None:
        findings.append(DriftFinding(kind=kind, severity=severity, message=message, source="static", line=at))

    if documented.params is not None:
        for name in sorted(documented.params - set(signature)):
            add(
                "param-not-in-signature",
                "high",
                f"the docstring documents parameter '{name}', but the function has no such parameter "
                f"(its parameters are: {', '.join(signature) or 'none'})",
            )
        if documented.params:  # a partial list: the parameters it left out are worth noting
            for name in (p for p in signature if p not in documented.params):
                add("param-undocumented", "low", f"parameter '{name}' is missing from the docstring's parameter list")

    if documented.returns and not _returns_a_value(func) and not _is_stub(func):
        add("returns-without-value", "medium", "the docstring describes a return value, but the function never returns one")

    if documented.raises is not None:
        raised = _raised_names(func)
        for name in sorted(documented.raises - raised):
            add(
                "raises-not-raised",
                "low",
                f"the docstring says it raises {name}, but this function never raises it directly "
                "(it may come from a function it calls)",
            )
        for name in sorted(raised - documented.raises):
            add("raises-undocumented", "low", f"the function raises {name}, which the docstring's Raises section doesn't list")

    return findings
