"""A tiny, dependency-free query engine for the document store.

Everything here is pure: it operates on plain dicts and never touches storage.
That keeps it fully unit-testable without Telegram and makes it reusable if the
index is ever moved behind Redis or a real search engine.

Design notes
------------
*   Field paths are dotted (``author.name``) and resolve through nested dicts.
    A missing path is *not* an error — it simply never matches, which is how
    schemaless stores are expected to behave.
*   Comparisons across incompatible types never raise. Python happily refuses
    to order ``3 < "a"``, and a document store must not 500 because one record
    in a collection has a string where the others have numbers.
*   Sorting uses a total order built from a type rank, so a heterogeneous
    collection still produces a stable, paginatable sequence.
"""

from __future__ import annotations

import base64
import binascii
import json
from typing import Any, Callable, Iterable, Optional

MISSING = object()

#: Ordering between different JSON types, so sorts are total and stable.
_TYPE_RANK = {
    type(None): 0,
    bool: 1,
    int: 2,
    float: 2,
    str: 3,
    list: 4,
    dict: 5,
}


def resolve_path(data: dict[str, Any], path: str) -> Any:
    """Return the value at a dotted ``path``, or :data:`MISSING`."""
    current: Any = data
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.lstrip("-").isdigit():
            index = int(part)
            if -len(current) <= index < len(current):
                current = current[index]
            else:
                return MISSING
        else:
            return MISSING
    return current


# --------------------------------------------------------------- operators
def _eq(actual: Any, expected: Any) -> bool:
    # ``True == 1`` is true in Python but surprising in a datastore.
    if isinstance(actual, bool) != isinstance(expected, bool):
        return False
    return actual == expected


def _cmp(actual: Any, expected: Any, relate: Callable[[Any, Any], bool]) -> bool:
    try:
        return bool(relate(actual, expected))
    except TypeError:
        return False


def _contains(actual: Any, expected: Any) -> bool:
    if isinstance(actual, str) and isinstance(expected, str):
        return expected.lower() in actual.lower()
    if isinstance(actual, (list, tuple)):
        return any(_eq(item, expected) for item in actual)
    if isinstance(actual, dict):
        return expected in actual
    return False


def _in(actual: Any, expected: Any) -> bool:
    if not isinstance(expected, (list, tuple)):
        return False
    return any(_eq(actual, item) for item in expected)


OPERATORS: dict[str, Callable[[Any, Any], bool]] = {
    "eq": _eq,
    "ne": lambda a, e: not _eq(a, e),
    "lt": lambda a, e: _cmp(a, e, lambda x, y: x < y),
    "lte": lambda a, e: _cmp(a, e, lambda x, y: x <= y),
    "gt": lambda a, e: _cmp(a, e, lambda x, y: x > y),
    "gte": lambda a, e: _cmp(a, e, lambda x, y: x >= y),
    "in": _in,
    "nin": lambda a, e: not _in(a, e),
    "contains": _contains,
    "starts_with": lambda a, e: isinstance(a, str)
    and isinstance(e, str)
    and a.lower().startswith(e.lower()),
    "ends_with": lambda a, e: isinstance(a, str)
    and isinstance(e, str)
    and a.lower().endswith(e.lower()),
}

#: Operators that are satisfied by the *absence* of a field and therefore must
#: still be evaluated when the path does not resolve.
_MISSING_AWARE = {"ne", "nin", "exists"}


def matches(data: dict[str, Any], field: str, op: str, expected: Any) -> bool:
    """Evaluate a single filter against one document body."""
    actual = resolve_path(data, field)

    if op == "exists":
        present = actual is not MISSING
        return present if bool(expected) else not present

    if actual is MISSING:
        # A document that lacks the field cannot equal a value, but it *is*
        # "not equal" to it — matching how schemaless stores usually read.
        return op in _MISSING_AWARE

    handler = OPERATORS.get(op)
    if handler is None:
        return False
    return handler(actual, expected)


def matches_all(data: dict[str, Any], filters: Iterable[tuple[str, str, Any]]) -> bool:
    return all(matches(data, field, op, value) for field, op, value in filters)


# ----------------------------------------------------------------- sorting
def sort_key(value: Any) -> tuple[int, Any]:
    """Build a totally-ordered key for a heterogeneous JSON value."""
    if value is MISSING:
        # Missing sorts before everything, including explicit nulls.
        return (-1, 0)
    rank = _TYPE_RANK.get(type(value))
    if rank is None:
        return (6, str(value))
    if rank in (4, 5):  # list / dict are not orderable -> compare serialised
        return (rank, json.dumps(value, sort_keys=True, default=str))
    if rank == 0:
        return (0, 0)
    if rank == 1:
        return (1, int(value))
    return (rank, value)


def document_sort_key(data: dict[str, Any], path: Optional[str], doc_id: str):
    """Sort key for a whole document; ``doc_id`` breaks ties deterministically."""
    if not path:
        return ((3, doc_id), doc_id)
    return (sort_key(resolve_path(data, path)), doc_id)


# -------------------------------------------------------------- pagination
def encode_cursor(value: Any, doc_id: str) -> str:
    """Opaque, URL-safe continuation token."""
    try:
        payload = json.dumps({"v": value, "i": doc_id}, default=str)
    except (TypeError, ValueError):
        payload = json.dumps({"v": None, "i": doc_id})
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")


def decode_cursor(cursor: str) -> Optional[tuple[Any, str]]:
    """Return ``(value, doc_id)`` or ``None`` when the cursor is unusable."""
    if not cursor:
        return None
    padded = cursor + "=" * (-len(cursor) % 4)
    try:
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        parsed = json.loads(raw.decode("utf-8"))
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return None
    if not isinstance(parsed, dict) or "i" not in parsed:
        return None
    return parsed.get("v"), str(parsed["i"])


def parse_where(expressions: Iterable[str]) -> list[tuple[str, str, Any]]:
    """Parse ``field:op:value`` query-string filters.

    The value is parsed as JSON when possible so ``age:gte:30`` compares
    numerically while ``name:eq:30`` can still be expressed as ``name:eq:"30"``.
    """
    filters: list[tuple[str, str, Any]] = []
    for raw in expressions:
        if not raw:
            continue
        parts = raw.split(":", 2)
        if len(parts) == 2:
            field, op, literal = parts[0], "eq", parts[1]
        elif len(parts) == 3:
            field, op, literal = parts
        else:
            raise ValueError(f"Malformed filter '{raw}'. Expected field:op:value.")

        field = field.strip()
        op = (op or "eq").strip().lower()
        if not field:
            raise ValueError(f"Malformed filter '{raw}': empty field.")
        if op not in OPERATORS and op != "exists":
            raise ValueError(
                f"Unknown operator '{op}'. Supported: "
                + ", ".join(sorted(set(OPERATORS) | {"exists"}))
            )

        try:
            value: Any = json.loads(literal)
        except json.JSONDecodeError:
            value = literal
        filters.append((field, op, value))
    return filters
