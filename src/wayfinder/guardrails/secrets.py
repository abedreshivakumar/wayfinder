"""Finding and blanking out secrets in text.

Source code sometimes contains real credentials. Anything we send to a hosted model, and
anything it sends back, passes through here first. The patterns are the well-known token
shapes plus "a secret-looking name assigned a string"; they favour redacting too much
over leaking, because a placeholder costs the explanation almost nothing.
"""

from __future__ import annotations

import re

# (kind, pattern). A group named `value` limits the replacement to just the secret, so the
# surrounding code (the variable name, the URL host) stays readable.
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----")),
    ("aws-key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("google-key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b|\bAQ\.[A-Za-z0-9_-]{30,}")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b|\bgithub_pat_[A-Za-z0-9_]{50,}\b")),
    ("slack-token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("stripe-key", re.compile(r"\b[sr]k_(?:live|test)_[A-Za-z0-9]{16,}\b")),
    ("api-key", re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_-]{20,}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")),
    ("bearer-token", re.compile(r"(?i)\bBearer\s+(?P<value>[A-Za-z0-9._~+/=-]{20,})")),
    ("url-credentials", re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s:/@]+:(?P<value>[^\s/@]+)@")),
    (
        "assigned-secret",
        re.compile(
            r"""(?ix)
            \b[\w.]*(?:password|passwd|pwd|secret|api[_-]?key|access[_-]?key|auth[_-]?token|token|private[_-]?key)\w*
            ['"]?                                   # a dict key's closing quote
            (?:\s*:\s*[\w\[\]., |]+)?               # an optional type annotation
            \s*[:=]\s*
            (?P<q>['"])(?P<value>[^'"\n]{8,})(?P=q)
            """
        ),
    ),
]


def redact_secrets(text: str) -> tuple[str, int]:
    """(text with secrets replaced by [REDACTED:kind], how many were replaced)."""
    count = 0
    for kind, pattern in _PATTERNS:

        def replace(match: re.Match[str], kind: str = kind) -> str:
            nonlocal count
            count += 1
            marker = f"[REDACTED:{kind}]"
            if "value" not in pattern.groupindex:
                return marker
            start, end = match.span("value")
            whole = match.group(0)
            offset = match.start()
            return whole[: start - offset] + marker + whole[end - offset :]

        text = pattern.sub(replace, text)
    return text, count
