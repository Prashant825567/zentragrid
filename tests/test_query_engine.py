"""Offline unit tests for the document query engine.

Pure functions only — no storage, no Telegram, no app wiring.
"""

from __future__ import annotations

import pytest

from app.utils import query as q


# ------------------------------------------------------------- path lookup
def test_resolve_path_top_level():
    assert q.resolve_path({"a": 1}, "a") == 1


def test_resolve_path_nested():
    assert q.resolve_path({"a": {"b": {"c": 7}}}, "a.b.c") == 7


def test_resolve_path_list_index():
    assert q.resolve_path({"tags": ["x", "y"]}, "tags.1") == "y"


def test_resolve_path_missing_returns_sentinel():
    assert q.resolve_path({"a": 1}, "b") is q.MISSING


def test_resolve_path_through_scalar_is_missing():
    assert q.resolve_path({"a": 5}, "a.b") is q.MISSING


def test_resolve_path_explicit_null_is_not_missing():
    assert q.resolve_path({"a": None}, "a") is None


# ---------------------------------------------------------------- matching
@pytest.mark.parametrize(
    "op,stored,expected,result",
    [
        ("eq", 5, 5, True),
        ("eq", 5, 6, False),
        ("ne", 5, 6, True),
        ("lt", 3, 5, True),
        ("lte", 5, 5, True),
        ("gt", 9, 5, True),
        ("gte", 4, 5, False),
        ("in", "b", ["a", "b"], True),
        ("in", "z", ["a", "b"], False),
        ("nin", "z", ["a", "b"], True),
        ("contains", "Hello World", "world", True),
        ("contains", ["a", "b"], "b", True),
        ("starts_with", "ZentraGrid", "zentra", True),
        ("ends_with", "note.md", ".md", True),
    ],
)
def test_operators(op, stored, expected, result):
    assert q.matches({"f": stored}, "f", op, expected) is result


def test_true_does_not_equal_one():
    """``True == 1`` in Python, but a datastore must keep types distinct."""
    assert q.matches({"f": True}, "f", "eq", 1) is False
    assert q.matches({"f": 1}, "f", "eq", True) is False


def test_comparison_across_types_does_not_raise():
    assert q.matches({"f": "abc"}, "f", "gt", 5) is False
    assert q.matches({"f": None}, "f", "lt", "x") is False


def test_missing_field_never_matches_eq():
    assert q.matches({}, "nope", "eq", 1) is False


def test_missing_field_matches_ne():
    assert q.matches({}, "nope", "ne", 1) is True


def test_exists_operator():
    assert q.matches({"a": None}, "a", "exists", True) is True
    assert q.matches({}, "a", "exists", True) is False
    assert q.matches({}, "a", "exists", False) is True


def test_unknown_operator_never_matches():
    assert q.matches({"a": 1}, "a", "regex", ".*") is False


def test_matches_all_requires_every_filter():
    body = {"age": 30, "city": "Delhi"}
    assert q.matches_all(body, [("age", "gte", 18), ("city", "eq", "Delhi")]) is True
    assert q.matches_all(body, [("age", "gte", 18), ("city", "eq", "Mumbai")]) is False


# ----------------------------------------------------------------- sorting
def test_sort_key_orders_mixed_types_without_raising():
    values = [None, 5, "apple", True, [1], {"a": 1}]
    assert sorted(values, key=q.sort_key)  # must not raise


def test_missing_sorts_before_null():
    assert q.sort_key(q.MISSING) < q.sort_key(None)


def test_numbers_sort_numerically_not_lexically():
    values = [10, 9, 100]
    assert sorted(values, key=q.sort_key) == [9, 10, 100]


def test_document_sort_key_breaks_ties_by_id():
    a = q.document_sort_key({"n": 1}, "n", "aaa")
    b = q.document_sort_key({"n": 1}, "n", "bbb")
    assert a < b


# -------------------------------------------------------------- pagination
def test_cursor_roundtrip():
    token = q.encode_cursor("2026-01-01", "doc_1")
    assert q.decode_cursor(token) == ("2026-01-01", "doc_1")


def test_cursor_roundtrip_with_number():
    token = q.encode_cursor(42, "doc_x")
    assert q.decode_cursor(token) == (42, "doc_x")


def test_cursor_is_url_safe():
    token = q.encode_cursor("a/b+c==", "doc_1")
    assert "/" not in token and "+" not in token and "=" not in token


def test_garbage_cursor_decodes_to_none():
    assert q.decode_cursor("!!!not-base64!!!") is None
    assert q.decode_cursor("") is None


def test_cursor_without_id_is_rejected():
    import base64 as b64
    import json as js

    raw = b64.urlsafe_b64encode(js.dumps({"v": 1}).encode()).decode().rstrip("=")
    assert q.decode_cursor(raw) is None


# ------------------------------------------------------------ where parser
def test_parse_where_infers_json_types():
    assert q.parse_where(["age:gte:30"]) == [("age", "gte", 30)]
    assert q.parse_where(["done:eq:true"]) == [("done", "eq", True)]
    assert q.parse_where(['tag:in:["a","b"]']) == [("tag", "in", ["a", "b"])]


def test_parse_where_falls_back_to_string():
    assert q.parse_where(["city:eq:Delhi"]) == [("city", "eq", "Delhi")]


def test_parse_where_quoted_number_stays_string():
    assert q.parse_where(['zip:eq:"110001"']) == [("zip", "eq", "110001")]


def test_parse_where_two_part_defaults_to_eq():
    assert q.parse_where(["city:Delhi"]) == [("city", "eq", "Delhi")]


def test_parse_where_value_may_contain_colons():
    assert q.parse_where(["at:eq:2026-01-01T10:00:00Z"]) == [
        ("at", "eq", "2026-01-01T10:00:00Z")
    ]


def test_parse_where_rejects_unknown_operator():
    with pytest.raises(ValueError, match="Unknown operator"):
        q.parse_where(["a:regex:b"])


def test_parse_where_rejects_empty_field():
    with pytest.raises(ValueError, match="empty field"):
        q.parse_where([":eq:1"])


def test_parse_where_skips_blank_entries():
    assert q.parse_where(["", "a:eq:1"]) == [("a", "eq", 1)]
