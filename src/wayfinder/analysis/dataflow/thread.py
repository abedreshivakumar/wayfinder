"""Link a value's producer to its consumer: where a result is stored, then reused.

In:
    user = fetch_user(uid)
    process(user)
the call graph shows handle_login -> fetch_user and handle_login -> process, but
the interesting fact is that fetch_user's *result* flows into process. That's a
relationship between two calls, not either call alone - this file finds it.

Known limits (deliberate, for now):
- Only bare-name arguments are followed. `process(user.name)` or `process(f(user))`
  don't count as consuming `user`.
- Scopes are grouped by the enclosing function's *name*, so two methods with the
  same name in different classes would be mixed together.
"""

from __future__ import annotations

from dataclasses import dataclass

from wayfinder.analysis.dataflow.ast_pass import ArgSite, CallSite


@dataclass(frozen=True)
class DataFlowLink:
    var: str  # the variable carrying the value, e.g. "user"
    producer: CallSite  # the call whose result was assigned to `var`
    consumer: CallSite  # the later call that received `var` as an argument
    arg: ArgSite  # which of the consumer's arguments carried it


def thread_variables(sites: list[CallSite]) -> list[DataFlowLink]:
    """`sites` must be in source order (find_call_sites already returns them that way)."""
    by_caller: dict[str, list[CallSite]] = {}
    for site in sites:
        by_caller.setdefault(site.caller, []).append(site)

    links: list[DataFlowLink] = []
    for caller_sites in by_caller.values():
        live: dict[str, CallSite] = {}  # variable name -> the call that last assigned it

        for site in caller_sites:
            # Consume first: in `x = f(x)`, the argument is read before x is rebound.
            for arg in site.args:
                if arg.pos is not None and arg.text in live:
                    links.append(
                        DataFlowLink(var=arg.text, producer=live[arg.text], consumer=site, arg=arg)
                    )
            if site.assigned_to is not None:
                live[site.assigned_to] = site  # rebinding replaces any earlier producer

    return links
