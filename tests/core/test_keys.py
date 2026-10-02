"""Tests for opaque persisted identifiers."""

from muninn.keys import pack_key, problem_key, question_type_key


def test_keys_are_stable_and_namespaced():
    assert pack_key("chemistry") == pack_key("chemistry")
    assert pack_key("chemistry") != pack_key("japanese")
    assert question_type_key("chemistry", "symbols") != question_type_key(
        "chemistry",
        "positions",
    )
    assert problem_key("chemistry", "symbols", "H") != problem_key(
        "chemistry",
        "symbols",
        "He",
    )


def test_component_boundaries_cannot_be_confused():
    assert question_type_key("a", "b::c") != question_type_key("a::b", "c")
    assert problem_key("a", "b", "c::d") != problem_key("a", "b::c", "d")
