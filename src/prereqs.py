"""Prerequisite expressions: ``CPSC 2120 AND (MATH 1060 OR MATH 1070)``.

Grammar, lowest precedence first::

    or_expr  := and_expr ("OR" and_expr)*
    and_expr := atom ("AND" atom)*
    atom     := COURSE | "(" or_expr ")"
"""

import re

# Course codes are 2-5 letters + 4 digits, with the space optional: "CH 1010", "CPSC2120".
_TOKEN = re.compile(r"\(|\)|\bAND\b|\bOR\b|[A-Z]{2,5} ?\d{4}")
_CODE = re.compile(r"\s*([A-Za-z]{2,5}) ?(\d{4})\s*")
_OPERATORS = frozenset({"AND", "OR", "(", ")"})


def normalize(code):
    """Canonical form for a course code: ``cpsc2120`` -> ``CPSC 2120``."""
    match = _CODE.fullmatch(code)
    return f"{match.group(1).upper()} {match.group(2)}" if match else code.strip().upper()


def courses_in(expression):
    """Every course code mentioned in an expression, in order, normalized."""
    if not expression:
        return []
    return [normalize(t) for t in _TOKEN.findall(expression.upper()) if t not in _OPERATORS]


def satisfied(expression, taken):
    """True if ``taken`` satisfies ``expression``. No prerequisites means satisfied.

    Raises ValueError on a malformed expression rather than silently passing or
    failing the course -- bad catalog data should be loud, not quietly let a
    student register for something they are not eligible for.
    """
    if not expression or not expression.strip():
        return True

    tokens = _TOKEN.findall(expression.upper())
    if not tokens:
        raise ValueError(f"no course codes or operators in prerequisite {expression!r}")

    have = {normalize(code) for code in taken}
    tokens.reverse()  # pop() takes from the end, so reversing reads left to right
    value = _or_expr(tokens, have, expression)
    if tokens:
        raise ValueError(f"trailing tokens in prerequisite {expression!r}: {tokens[::-1]}")
    return value


def _or_expr(tokens, have, source):
    value = _and_expr(tokens, have, source)
    while tokens and tokens[-1] == "OR":
        tokens.pop()
        right = _and_expr(tokens, have, source)  # parse before combining, never short-circuit
        value = value or right
    return value


def _and_expr(tokens, have, source):
    value = _atom(tokens, have, source)
    while tokens and tokens[-1] == "AND":
        tokens.pop()
        right = _atom(tokens, have, source)
        value = value and right
    return value


def _atom(tokens, have, source):
    if not tokens:
        raise ValueError(f"prerequisite {source!r} ended early")

    token = tokens.pop()
    if token == "(":
        value = _or_expr(tokens, have, source)
        if not tokens or tokens.pop() != ")":
            raise ValueError(f"unbalanced parentheses in prerequisite {source!r}")
        return value
    if token in _OPERATORS:
        raise ValueError(f"unexpected {token!r} in prerequisite {source!r}")
    return normalize(token) in have
