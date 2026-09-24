"""Find every call in a source file, and what data goes into and out of it.

pyright's call hierarchy says *that* handle_login calls fetch_user. It does not
say what was passed or where the result went. Python's own `ast` module can:
it gives us the argument expressions and the variable a result was assigned to,
plus exact positions we can then hover over to ask pyright for types.

Known limits (deliberate, for now):
- Calls whose target isn't a plain name or attribute (e.g. `fns[0]()`, `f()()`)
  are skipped - there's no callee name to match against the call graph.
- Only `x = call()` and `x: T = call()` count as "assigned". Tuple unpacking
  (`a, b = call()`) is not tracked.
- ast column offsets count UTF-8 bytes, not characters, so a non-ASCII character
  earlier on the same line shifts columns. Same caveat as position.py.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

Pos = tuple[int, int]  # (line, col), both 1-indexed, matching position.py's convention


@dataclass(frozen=True)
class ArgSite:
    text: str  # compact source of the argument, e.g. "uid", "'test'", or "Inner(...)"
    keyword: str | None  # "uid" for the `uid=uid` in User(uid=uid); None for positional
    pos: Pos | None  # hoverable position - only set when the argument is a bare name


@dataclass(frozen=True)
class CallSite:
    caller: str  # enclosing function's name, or "<module>" at top level
    callee: str  # "fetch_user" for fetch_user(...), "method" for obj.method(...)
    pos: Pos  # position of the callee's name token
    args: tuple[ArgSite, ...]
    assigned_to: str | None  # "user" in `user = fetch_user(uid)` or `user = await fetch_user(uid)`
    assigned_pos: Pos | None
    awaited: bool = False  # the call's result is awaited, so its value type isn't a coroutine


class _CallSiteVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.sites: list[CallSite] = []
        self._scope: list[str] = []
        self._awaited: set[int] = set()  # id() of Call nodes that are directly awaited
        # id(Call node) -> (target name, target pos), filled by visit_Assign
        # *before* its child Call is visited, so visit_Call can look it up.
        self._assigned: dict[int, tuple[str, Pos]] = {}

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        # Decorators, default values and annotations run when the `def` statement runs,
        # in the *enclosing* scope - so `@router.get(...)` is a call made by whoever
        # defines the function, not by the function's own body.
        for decorator in node.decorator_list:
            self.visit(decorator)
        self.visit(node.args)
        if node.returns is not None:
            self.visit(node.returns)
        self._scope.append(node.name)
        for statement in node.body:
            self.visit(statement)
        self._scope.pop()

    visit_FunctionDef = _visit_function
    visit_AsyncFunctionDef = _visit_function

    def visit_Assign(self, node: ast.Assign) -> None:
        if len(node.targets) == 1:
            self._remember_assignment(node.targets[0], node.value)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None:
            self._remember_assignment(node.target, node.value)
        self.generic_visit(node)

    def visit_Await(self, node: ast.Await) -> None:
        if isinstance(node.value, ast.Call):
            self._awaited.add(id(node.value))
        self.generic_visit(node)

    def _remember_assignment(self, target: ast.expr, value: ast.expr) -> None:
        if isinstance(value, ast.Await):
            value = value.value  # `x = await f()` assigns f()'s result, same as `x = f()`
        if isinstance(target, ast.Name) and isinstance(value, ast.Call):
            self._assigned[id(value)] = (target.id, (target.lineno, target.col_offset + 1))

    def visit_Call(self, node: ast.Call) -> None:
        site = self._make_site(node)
        if site is not None:
            self.sites.append(site)
        self.generic_visit(node)  # descend: calls can be nested inside arguments

    def _make_site(self, node: ast.Call) -> CallSite | None:
        func = node.func
        if isinstance(func, ast.Name):
            callee, pos = func.id, (func.lineno, func.col_offset + 1)
        elif isinstance(func, ast.Attribute):
            # The Attribute node spans `obj.method`; the method name is its last
            # `len(attr)` characters, so back up from the end of the node.
            assert func.end_lineno is not None and func.end_col_offset is not None
            callee = func.attr
            pos = (func.end_lineno, func.end_col_offset - len(func.attr) + 1)
        else:
            return None

        args = tuple(_arg(a, None) for a in node.args) + tuple(
            _arg(k.value, k.arg) for k in node.keywords
        )
        assigned_to, assigned_pos = self._assigned.get(id(node), (None, None))
        return CallSite(
            caller=self._scope[-1] if self._scope else "<module>",
            callee=callee,
            pos=pos,
            args=args,
            assigned_to=assigned_to,
            assigned_pos=assigned_pos,
            awaited=id(node) in self._awaited,
        )


_MAX_ARG_TEXT = 60


def _summarize(value: ast.expr) -> str:
    """Compact source text for an argument.

    A nested call is shown as `name(...)` - it's already recorded as its own
    CallSite, so repeating its full argument list inside the outer call would
    just duplicate it. Any other expression longer than _MAX_ARG_TEXT is cut off.
    """
    if isinstance(value, ast.Await):
        return f"await {_summarize(value.value)}"
    if isinstance(value, ast.Call):
        callee = ast.unparse(value.func)
        return f"{callee}(...)" if value.args or value.keywords else f"{callee}()"
    text = ast.unparse(value)
    return text if len(text) <= _MAX_ARG_TEXT else text[: _MAX_ARG_TEXT - 3] + "..."


def _arg(value: ast.expr, keyword: str | None) -> ArgSite:
    pos = (value.lineno, value.col_offset + 1) if isinstance(value, ast.Name) else None
    return ArgSite(text=_summarize(value), keyword=keyword, pos=pos)


def find_call_sites(source: str) -> list[CallSite]:
    """Every resolvable call in `source`, in source order."""
    visitor = _CallSiteVisitor()
    visitor.visit(ast.parse(source))
    return sorted(visitor.sites, key=lambda s: s.pos)
