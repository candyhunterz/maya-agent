import pytest
from tests.eval.matchers import assert_calls_match, MatchError


def test_bare_string_positional_exact():
    assert_calls_match(
        [("a", {}), ("b", {})], ["a", "b"], allow_extra=False,
    )


def test_bare_string_in_wrong_order_fails():
    with pytest.raises(MatchError):
        assert_calls_match([("b", {}), ("a", {})], ["a", "b"], allow_extra=False)


def test_args_contain_partial_match():
    assert_calls_match(
        [("fix", {"obj": "x", "extra": 1})],
        [{"tool": "fix", "args_contain": {"obj": "x"}}],
        allow_extra=False,
    )


def test_args_contain_mismatch_fails():
    with pytest.raises(MatchError, match="args"):
        assert_calls_match(
            [("fix", {"obj": "y"})],
            [{"tool": "fix", "args_contain": {"obj": "x"}}],
            allow_extra=False,
        )


def test_any_order_block_matches_either_order():
    assert_calls_match(
        [("a", {}), ("b", {}), ("c", {})],
        ["a", {"any_order": ["b", "c"]}],
        allow_extra=False,
    )
    assert_calls_match(
        [("a", {}), ("c", {}), ("b", {})],
        ["a", {"any_order": ["b", "c"]}],
        allow_extra=False,
    )


def test_allow_extra_calls_lets_unmatched_intermediates_pass():
    assert_calls_match(
        [("a", {}), ("noise", {}), ("b", {})],
        ["a", "b"],
        allow_extra=True,
    )


def test_allow_extra_false_rejects_extras():
    with pytest.raises(MatchError, match="extra"):
        assert_calls_match(
            [("a", {}), ("noise", {}), ("b", {})],
            ["a", "b"],
            allow_extra=False,
        )
