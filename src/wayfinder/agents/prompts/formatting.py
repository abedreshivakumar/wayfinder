"""How the agents describe code to a model - shared, so every agent describes a call the
same way."""

from __future__ import annotations

from wayfinder.domain.labels import ArgLabel, CallLabel

KIND_WORDS = {5: "class", 6: "method", 9: "constructor", 12: "function"}  # LSP SymbolKind -> word

_MAX_ARGS_SHOWN = 6  # a call with 18 keyword arguments would spend tokens on noise


def _literal_base(first_value: str) -> str:
    v = first_value.strip()
    if v[:1] in ("'", '"'):
        return "str"
    if v[:2] in ("b'", 'b"'):
        return "bytes"
    if v in ("True", "False"):
        return "bool"
    if v.lstrip("-").isdigit():
        return "int"
    return "Literal[...]"  # e.g. an enum member: no value to protect, but nothing useful to say


def clean_type(type_: str | None) -> str | None:
    """A type as it may appear in a prompt.

    pyright narrows a variable assigned a constant to `Literal['the value']`, which would
    put the value itself in front of the model - a password, for instance. Each Literal[...]
    is replaced by its plain base type, which is what the model needs. The scan is aware of
    quotes, so a value containing ']' can't leave part of itself behind."""
    if type_ is None:
        return None
    out: list[str] = []
    i = 0
    while i < len(type_):
        if not type_.startswith("Literal[", i):
            out.append(type_[i])
            i += 1
            continue
        j, depth, quote = i + len("Literal["), 1, ""
        while j < len(type_) and depth:
            ch = type_[j]
            if quote:
                if ch == "\\":
                    j += 1  # skip the escaped character
                elif ch == quote:
                    quote = ""
            elif ch in ("'", '"'):
                quote = ch
            elif ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
            j += 1
        inner = type_[i + len("Literal[") : j - 1]
        out.append(_literal_base(inner))
        i = j
    return "".join(out)


def _arg(a: ArgLabel) -> str:
    # pyright says "Unknown" when it can't resolve a type (e.g. a package it can't see);
    # that tells the model nothing, so it's left out rather than passed along.
    typed = clean_type(a.type) if a.type and a.type != "Unknown" else None
    return (f"{a.keyword}=" if a.keyword else "") + a.text + (f": {typed}" if typed else "")


def format_args(args: tuple[ArgLabel, ...]) -> str:
    shown = ", ".join(_arg(a) for a in args[:_MAX_ARGS_SHOWN])
    hidden = len(args) - _MAX_ARGS_SHOWN
    return f"{shown}, ... {hidden} more" if hidden > 0 else shown


def format_call(label: CallLabel, callee_name: str) -> str:
    """One call as `callee(arg: Type, ...) -> what comes back`."""
    returns_type = clean_type(label.returns_type)
    if label.returns_var:
        returns = f" -> stored in `{label.returns_var}: {returns_type}`"
    elif returns_type:
        returns = f" -> returns {returns_type}"
    else:
        returns = ""
    return f"{callee_name}({format_args(label.args)}){returns}"
