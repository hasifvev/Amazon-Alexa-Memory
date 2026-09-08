"""Tests for the spoken memory tools.

These check the thing that distinguishes this from a notes app: that the answers
are honest about time. Saying "your standup is at nine" when the question was
about March, and it moved in June, is wrong in a way that is worse than saying
nothing.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pytest

from core.store import Memory, MemoryStore
from server.tools import MemoryTools, parse_when

NOW = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)


def ago(days: int) -> str:
    return (NOW - timedelta(days=days)).isoformat(timespec="seconds")


@pytest.fixture
def tools(tmp_path):
    return MemoryTools(MemoryStore(tmp_path / "m.jsonl"))


# -- spoken time parsing ---------------------------------------------------


def test_iso_dates_parse():
    assert parse_when("2026-03-01").month == 3


def test_relative_phrases_parse():
    base = NOW
    assert parse_when("3 months ago", now=base) < base
    assert parse_when("yesterday", now=base) == base - timedelta(days=1)
    assert parse_when("last week", now=base) == base - timedelta(days=7)


def test_now_words_mean_now():
    assert parse_when("now", now=NOW) == NOW
    assert parse_when(None, now=NOW) == NOW


def test_an_unparseable_phrase_raises_rather_than_defaulting_to_now():
    """Silently answering about the wrong date is the failure this prevents."""
    with pytest.raises(ValueError, match="can't work out when"):
        parse_when("sometime around the thing")


# -- remembering and recalling ---------------------------------------------


def test_remember_then_recall(tools):
    tools.remember("the standup is at nine")
    assert "nine" in tools.recall("standup")


def test_recall_of_an_unknown_subject_says_so(tools):
    assert "don't know anything about" in tools.recall("quarterly badgers")


def test_correcting_keeps_the_old_answer_for_history(tools):
    tools.remember("the standup is at nine")
    reply = tools.correct("standup", "the standup is at ten")

    assert "ten" in reply
    assert "nine" in reply, "the spoken confirmation should say what it used to be"
    assert "ten" in tools.recall("standup")


def test_recall_volunteers_the_previous_value(tools):
    """Unprompted history is the product. Say what it was, not only what it is.

    Asserts the previous value is mentioned, not any particular phrasing —
    wording is a design decision that should be free to change without
    reddening a test about behaviour.
    """
    tools.remember("the standup is at nine")
    tools.correct("standup", "the standup is at ten")
    reply = tools.recall("standup")
    assert "ten" in reply, "must give the current answer"
    assert "nine" in reply, "must volunteer what it used to be, unprompted"


def test_recall_at_a_past_date_gives_the_answer_of_that_time(tools):
    store = tools.store
    old = store.add(
        Memory(text="the standup is at nine", asserted_at=ago(200), valid_from=ago(200))
    )
    store.supersede(
        old.id,
        Memory(text="the standup is at ten", asserted_at=ago(10), valid_from=ago(10)),
        at=ago(10),
    )

    assert "nine" in tools.recall("standup", when="100 days ago")
    assert "ten" in tools.recall("standup")


def test_recall_before_anything_was_known_admits_the_gap(tools):
    tools.store.add(
        Memory(text="the standup is at nine", asserted_at=ago(10), valid_from=ago(10))
    )
    reply = tools.recall("standup", when="200 days ago")
    assert "didn't know" in reply
    assert "nine" not in reply, "must not answer a past question with a later fact"


# -- withdrawing -----------------------------------------------------------


def test_forget_withdraws_without_deleting(tools):
    tools.remember("the bundle is twelve megabytes")
    tools.forget("bundle", "measured at 595 megabytes")

    assert len(list(tools.store.all())) == 1, "a retraction must not delete the record"
    reply = tools.recall("bundle")
    assert "withdrew" in reply
    assert "595" in reply


def test_forgetting_something_unknown_says_so(tools):
    assert "don't have anything about" in tools.forget("nonexistent")


def test_an_ambiguous_correction_asks_which_one(tools):
    tools.remember("the standup is at nine")
    tools.remember("the standup room is upstairs")
    assert "Which one?" in tools.correct("standup", "the standup is at ten")


# -- the wake --------------------------------------------------------------


def test_catch_me_up_on_an_empty_memory_is_graceful(tools):
    assert "don't have anything" in tools.catch_me_up()


def test_catch_me_up_reports_a_change(tools):
    tools.remember("the deploy root is app")
    tools.correct("deploy root", "the deploy root is projects")
    assert "projects" in tools.catch_me_up()


def test_what_changed_reports_a_withdrawal(tools):
    tools.remember("the bundle is twelve megabytes")
    tools.forget("bundle", "measured at 595 megabytes")
    assert "withdrew" in tools.what_changed()


def test_what_changed_with_nothing_new_says_nothing_changed(tools):
    assert tools.what_changed() == "Nothing has changed."


# -- voice shape and latency ----------------------------------------------


def test_answers_are_short_enough_to_speak(tools):
    for i in range(30):
        tools.remember(f"fact number {i} about the project")

    for reply in (tools.catch_me_up(), tools.recall("project"), tools.what_changed()):
        assert len(reply) < 400, f"too long to speak aloud: {reply[:120]}..."
        assert "\n" not in reply, "spoken answers must not contain line breaks"


def test_the_tool_path_stays_well_under_the_500ms_budget(tools):
    """Alexa+ requires a sub-500ms round trip. Leave room for the network."""
    for i in range(200):
        tools.remember(f"fact number {i}")

    started = time.perf_counter()
    tools.catch_me_up(named=True)
    tools.recall("fact number 5")
    tools.what_changed()
    elapsed_ms = (time.perf_counter() - started) * 1000

    assert elapsed_ms < 100, f"tools took {elapsed_ms:.0f}ms of the 500ms budget"
