"""What a file defines, read with `ast`: its functions with their parameters, its classes,
and which of those classes are schemas (data shapes) with their fields.

Exact and fast, so the UI can show every function's inputs and every schema's fields
without asking pyright, and without running any of the code.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field

_SCHEMA_BASES = {
    "BaseModel": "pydantic", "RootModel": "pydantic", "SQLModel": "orm", "DeclarativeBase": "orm",
    "TypedDict": "typeddict", "NamedTuple": "namedtuple", "Struct": "struct", "Schema": "schema",
    "Enum": "enum", "IntEnum": "enum", "StrEnum": "enum", "Flag": "enum", "IntFlag": "enum",
}
_SCHEMA_DECORATORS = {"dataclass": "dataclass", "define": "attrs", "frozen": "attrs", "s": "attrs", "attrs": "attrs"}
_MAX_FIELDS = 24


@dataclass(frozen=True)
class Param:
    name: str
    type: str | None = None  # the annotation as written, when there is one


@dataclass(frozen=True)
class FunctionInfo:
    qualname: str  # "Engine.run" for a method
    name: str
    line: int
    params: list[Param] = field(default_factory=list)  # without self / cls
    returns: str | None = None
    doc: str | None = None  # first line of the docstring
    is_async: bool = False


@dataclass(frozen=True)
class SchemaInfo:
    name: str
    kind: str  # dataclass | pydantic | typeddict | namedtuple | enum | orm | attrs | struct | schema
    line: int
    fields: list[Param] = field(default_factory=list)
    doc: str | None = None


@dataclass(frozen=True)
class Outline:
    functions: list[FunctionInfo]
    classes: list[str]
    schemas: list[SchemaInfo]
    has_main_guard: bool  # `if __name__ == "__main__":` - it is meant to be run


def _first_line(node: ast.AST) -> str | None:
    doc = ast.get_docstring(node)  # type: ignore[arg-type]
    return doc.strip().splitlines()[0] if doc and doc.strip() else None


def _text(node: ast.AST | None) -> str | None:
    return ast.unparse(node) if node is not None else None


def _last_name(node: ast.AST) -> str:
    """`pydantic.BaseModel` -> "BaseModel", `dataclass(frozen=True)` -> "dataclass"."""
    if isinstance(node, ast.Call):
        node = node.func
    if isinstance(node, ast.Subscript):
        node = node.value
    if isinstance(node, ast.Attribute):
        return node.attr
    return node.id if isinstance(node, ast.Name) else ""


def _params(fn: ast.FunctionDef | ast.AsyncFunctionDef, method: bool) -> list[Param]:
    a = fn.args
    ordered = [*a.posonlyargs, *a.args]
    out = [Param(p.arg, _text(p.annotation)) for p in ordered]
    if method and out and out[0].name in ("self", "cls"):
        out = out[1:]
    if a.vararg:
        out.append(Param("*" + a.vararg.arg, _text(a.vararg.annotation)))
    out += [Param(p.arg, _text(p.annotation)) for p in a.kwonlyargs]
    if a.kwarg:
        out.append(Param("**" + a.kwarg.arg, _text(a.kwarg.annotation)))
    return out


def _schema_kind(cls: ast.ClassDef) -> str | None:
    for d in cls.decorator_list:
        kind = _SCHEMA_DECORATORS.get(_last_name(d))
        if kind:
            return kind
    for b in cls.bases:
        kind = _SCHEMA_BASES.get(_last_name(b))
        if kind:
            return kind
    return None


def _fields(cls: ast.ClassDef, kind: str) -> list[Param]:
    out: list[Param] = []
    for stmt in cls.body:
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            annotation = _text(stmt.annotation) or ""
            if not annotation.startswith(("ClassVar", "typing.ClassVar")):
                out.append(Param(stmt.target.id, annotation))
        elif kind == "enum" and isinstance(stmt, ast.Assign):
            out += [Param(t.id) for t in stmt.targets if isinstance(t, ast.Name) and not t.id.startswith("_")]
    return out[:_MAX_FIELDS]


def outline(source: str) -> Outline:
    tree = ast.parse(source)
    functions: list[FunctionInfo] = []
    classes: list[str] = []
    schemas: list[SchemaInfo] = []
    schema_names: set[str] = set()

    def visit(body: list[ast.stmt], prefix: str, in_class: bool) -> None:
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(
                    FunctionInfo(
                        qualname=prefix + node.name,
                        name=node.name,
                        line=node.lineno,
                        params=_params(node, in_class),
                        returns=_text(node.returns),
                        doc=_first_line(node),
                        is_async=isinstance(node, ast.AsyncFunctionDef),
                    )
                )
            elif isinstance(node, ast.ClassDef):
                classes.append(prefix + node.name)
                kind = _schema_kind(node)
                # A class that inherits from a schema defined in this same file is one too.
                if kind is None and any(_last_name(b) in schema_names for b in node.bases):
                    kind = next(s.kind for s in schemas if s.name in {_last_name(b) for b in node.bases})
                if kind:
                    schema_names.add(node.name)
                    schemas.append(SchemaInfo(prefix + node.name, kind, node.lineno, _fields(node, kind), _first_line(node)))
                visit(node.body, f"{prefix}{node.name}.", True)

    visit(tree.body, "", False)
    main_guard = any(
        isinstance(n, ast.If) and "__name__" in ast.unparse(n.test) and "__main__" in ast.unparse(n.test)
        for n in tree.body
    )
    return Outline(functions, classes, schemas, main_guard)
