"""Turn pyright's hover markdown into structured type info.

pyright doesn't return types as data - it returns a markdown string it rendered
for humans, e.g. "```python\\n(variable) user: User\\n```". This file is the one
place that string gets parsed, so if pyright's format ever changes, only this
file breaks.

Known limit: signatures pyright wraps across multiple lines (very long parameter
lists) are not parsed yet - parse_hover returns None for those rather than guess.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from wayfinder.languages import LanguageDriver

_FENCE = re.compile(r"```python\n(.*?)\n```", re.DOTALL)
_VARIABLE = re.compile(r"^\((variable|parameter|constant)\) (\w+): (.+)$")
_FUNCTION = re.compile(r"^\((?:function|method)\) def (\w+)\((.*)\) -> (.+)$")
_CLASS = re.compile(r"^\(class\) (\w+)$")
# Hovering a constructor *call* gives the class's __init__ parameters, laid out over
# several lines: "class User(\n    uid: str,\n    name: str\n)". Only the name matters.
_CLASS_CALL = re.compile(r"^class (\w+)\(")


@dataclass(frozen=True)
class HoverInfo:
    kind: str  # "variable" | "parameter" | "constant" | "function" | "class"
    name: str
    # variable/parameter/constant: its type. function: its return type.
    # class: the class name itself (calling a class produces an instance of it).
    type: str
    params: str | None = None  # functions only: raw parameter list, e.g. "uid: str"


def parse_hover(markdown: str | None) -> HoverInfo | None:
    if not markdown:
        return None
    fenced = _FENCE.search(markdown)
    text = (fenced.group(1) if fenced else markdown).strip()

    if m := _VARIABLE.match(text):
        return HoverInfo(kind=m.group(1), name=m.group(2), type=m.group(3))
    if m := _FUNCTION.match(text):
        return HoverInfo(kind="function", name=m.group(1), params=m.group(2), type=m.group(3))
    if m := _CLASS.match(text) or _CLASS_CALL.match(text):
        return HoverInfo(kind="class", name=m.group(1), type=m.group(1))
    return None


def resolve_type(driver: LanguageDriver, file: Path, line: int, col: int) -> HoverInfo | None:
    """line, col are 1-indexed. Ask pyright what's at this position, parsed."""
    return parse_hover(driver.hover(file, line, col))
