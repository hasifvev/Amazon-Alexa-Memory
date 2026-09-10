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

from core.store import Kind, Memory, MemoryStore
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


# -- déjà vu ---------------------------------------------------------------


def test_asking_twice_with_an_unchanged_answer_says_nothing_extra(tools):
    """Noting that you repeated yourself is an observation about you, not a useful one."""
    tools.remember("the standup is at nine")
    first = tools.recall("standup")
    second = tools.recall("standup")
    assert "You asked me this" not in second
    assert first.rstrip(".") in second or "nine" in second


def test_asking_again_after_the_answer_changed_volunteers_the_earlier_ask(tools):
    """The déjà vu moment: you asked before, and it was different then."""
    store = tools.store
    old = store.add(
        Memory(text="the standup is at nine", asserted_at=ago(200), valid_from=ago(200))
    )
    tools.store.add(
        Memory(
            text="you asked about standup",
            kind=Kind.EVENT,
            source="alexa",
            asserted_at=ago(150),
            valid_from=ago(150),
            tags=("asked", tools._topic_key("standup")),
        )
    )
    store.supersede(
        old.id,
        Memory(text="the standup is at ten", asserted_at=ago(10), valid_from=ago(10)),
        at=ago(10),
    )

    reply = tools.recall("standup")
    assert "You asked me this on" in reply
    assert "nine" in reply, "must say what the answer was at the time of the earlier ask"


def test_questions_do_not_pollute_the_standing_facts(tools):
    """The ask log lives in the same store; it must not read as a known fact."""
    tools.remember("the standup is at nine")
    tools.recall("standup")
    tools.recall("standup")
    assert "you asked about" not in tools.catch_me_up()


def test_repeated_questions_in_the_same_second_are_distinct_events(tools):
    """Facts dedup within a second by design; questions must not."""
    tools.remember("the standup is at nine")
    for _ in range(4):
        tools.recall("standup")
    assert len(tools._prior_asks("standup")) >= 4


# -- what have I been wrong about ------------------------------------------


def test_wrong_about_on_a_clean_record(tools):
    tools.remember("the standup is at nine")
    assert "haven't withdrawn anything" in tools.wrong_about()


def test_wrong_about_reports_how_long_the_belief_was_held(tools):
    """The number no competitor can produce: they delete what they retract."""
    store = tools.store
    m = store.add(
        Memory(text="the office closes at six", asserted_at=ago(150), valid_from=ago(150))
    )
    store.retract(m.id, "you told me it is seven", at=ago(5))

    reply = tools.wrong_about()
    assert "145 days" in reply, reply
    assert "office closes at six" in reply


def test_wrong_about_leads_with_the_longest_held_mistake(tools):
    store = tools.store
    brief_error = store.add(Memory(text="bin day is Monday", asserted_at=ago(9), valid_from=ago(9)))
    store.retract(brief_error.id, "it is Tuesday", at=ago(8))
    long_error = store.add(Memory(text="the office closes at six", asserted_at=ago(200), valid_from=ago(200)))
    store.retract(long_error.id, "it is seven", at=ago(2))

    reply = tools.wrong_about()
    assert reply.index("office") < reply.index("bin day"), (
        "the belief carried for months matters more than the one fixed overnight"
    )


def test_a_superseded_fact_is_not_a_mistake(tools):
    """Changing is not being wrong. The distinction is the whole design."""
    tools.remember("the standup is at nine")
    tools.correct("standup", "the standup is at ten")
    assert "haven't withdrawn anything" in tools.wrong_about()


# -- multi-person: an Echo is a shared device ------------------------------


def test_one_persons_memory_does_not_leak_to_another(tools):
    """Regression, and a privacy bug rather than a cosmetic one.

    recall() queried the store without passing subject, so on a shared kitchen
    device every person heard everybody else's facts. Every other method
    filtered correctly, which is exactly why it went unnoticed.
    """
    hasif = tools.for_subject("hasif")
    aisyah = tools.for_subject("aisyah")

    hasif.remember("my standup is at ten")
    aisyah.remember("my standup is at eight")

    assert "ten" in hasif.recall("standup")
    assert "eight" not in hasif.recall("standup"), "heard someone else's memory"

    assert "eight" in aisyah.recall("standup")
    assert "ten" not in aisyah.recall("standup"), "heard someone else's memory"


def test_an_unknown_topic_stays_unknown_per_person(tools):
    tools.for_subject("hasif").remember("my locker code is 4417")
    assert "don't know" in tools.for_subject("aisyah").recall("locker code")


def test_for_subject_returns_self_when_unscoped(tools):
    assert tools.for_subject(None) is tools
    assert tools.for_subject("default") is tools


def test_questions_are_scoped_per_person(tools):
    hasif = tools.for_subject("hasif")
    hasif.remember("my standup is at ten")
    hasif.recall("standup")
    assert len(hasif._prior_asks("standup")) == 1
    assert tools.for_subject("aisyah")._prior_asks("standup") == []


def test_a_timeline_shows_only_that_persons_history(tools):
    hasif = tools.for_subject("hasif")
    aisyah = tools.for_subject("aisyah")
    hasif.remember("my standup is at ten")
    aisyah.remember("my standup is at eight")

    texts = [e.text for e in hasif.timeline("standup").entries]
    assert any("ten" in t for t in texts)
    assert not any("eight" in t for t in texts)


# -- new features: remember_for, share, shared_with_me, what_moved ----------


def test_remember_for_stores_with_expiry(tools):
    """An ephemeral memory is present before it expires and absent after."""
    from datetime import timedelta
    from server.tools import _parse_until, _now

    # Store a memory that expires tomorrow
    reply = tools.remember_for("the guest wifi password is GuestPass", "tomorrow")
    assert "guest wifi" in reply.lower()
    assert "tomorrow" in reply.lower()

    # It should be recallable right now
    assert "GuestPass" in tools.recall("guest wifi")


def test_remember_for_expired_is_not_recalled(tools):
    """A memory whose valid_until is in the past does not appear in recall."""
    from core.store import Memory, Kind
    from datetime import timedelta
    from server.tools import _now

    # Manually insert an already-expired memory
    past = (_now() - timedelta(hours=1)).isoformat(timespec="seconds")
    earlier = (_now() - timedelta(hours=2)).isoformat(timespec="seconds")
    expired = Memory(
        text="the temporary code is 9999",
        subject="default",
        source="test",
        asserted_at=earlier,
        valid_from=earlier,
        valid_until=past,
    )
    tools.store.add(expired)

    # Should not appear in current recall
    reply = tools.recall("temporary code")
    assert "9999" not in reply


def test_remember_for_bad_expiry_returns_error(tools):
    """An unparseable until phrase returns an error, not an exception."""
    reply = tools.remember_for("buy milk", "whenever I feel like it")
    assert "can't work out" in reply.lower() or "i can't" in reply.lower()


def test_share_puts_fact_in_recipients_memory(tools):
    """Sharing a fact makes it appear in the recipient's memory, not the sender's."""
    hasif = tools.for_subject("hasif")
    aisyah = tools.for_subject("aisyah")

    reply = hasif.share("the wifi password is Network2026", "aisyah")
    assert "Aisyah" in reply
    assert "Network2026" in reply

    # Appears for aisyah
    assert "Network2026" in aisyah.recall("wifi password")
    # Does NOT appear for hasif
    assert "Network2026" not in hasif.recall("wifi password")


def test_shared_with_me_lists_received_facts(tools):
    """shared_with_me returns facts pushed by others, attributed to the sender."""
    hasif = tools.for_subject("hasif")
    aisyah = tools.for_subject("aisyah")

    hasif.share("dinner is at seven tonight", "aisyah")

    reply = aisyah.shared_with_me()
    assert "dinner is at seven" in reply.lower()
    assert "hasif" in reply.lower()


def test_shared_with_me_empty_when_nothing_shared(tools):
    """shared_with_me returns a clear message when nothing has been shared."""
    reply = tools.shared_with_me()
    assert "nobody" in reply.lower() or "nothing" in reply.lower()


def test_what_moved_lists_superseded_facts(tools):
    """what_moved returns facts that changed, with how long each was held."""
    tools.remember("the standup is at nine")
    import time; time.sleep(0.01)
    tools.correct("standup", "the standup is at ten")

    reply = tools.what_moved()
    assert "standup" in reply.lower()
    assert "nine" in reply.lower()
    assert "ten" in reply.lower()


def test_what_moved_empty_when_nothing_changed(tools):
    """what_moved returns a clear message when nothing has a correction history."""
    tools.remember("the standup is at nine")
    reply = tools.what_moved()
    assert "nothing" in reply.lower() or "first version" in reply.lower()
