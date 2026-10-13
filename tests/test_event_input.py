"""Tests for ui.widgets.event_input: the recurrence wording shared by the
calendar's delete card and the event manager's delete dialog."""
import jdatetime
import pytest

from ui.widgets.event_input import delete_confirmation_message, recurrence_label
from utils.event_io import RECURRENCE_MODES, RECURRENCE_NONE, make_event_key

ONE_TIME_KEY = "1404-05-10"
MONTHLY_KEY = "0000-00-10"
YEARLY_KEY = "0000-05-10"


def test_a_one_time_key_asks_the_plain_question():
    assert delete_confirmation_message([ONE_TIME_KEY]) == "این رویداد حذف شود؟"


@pytest.mark.parametrize("key,label", [(MONTHLY_KEY, "ماهانه"), (YEARLY_KEY, "سالانه")])
def test_a_recurring_key_names_its_recurrence_and_the_whole_series(key, label):
    """The card previews one occurrence, the answer removes the series: the
    question has to say so rather than read like a single-event deletion."""
    message = delete_confirmation_message([key])
    assert label in message
    assert "تمام تکرارهای آن حذف خواهند شد" in message
    assert message != "این رویداد حذف شود؟"


@pytest.mark.parametrize("mode", RECURRENCE_MODES)
def test_every_recurrence_mode_the_store_can_build_reads_as_itself(mode):
    """The wording is driven by the key model, so a mode added to the store
    cannot end up with another mode's label (``recurrence_label`` falls back to
    the first row for anything it does not know)."""
    key = make_event_key(jdatetime.date(1404, 5, 10), mode)
    message = delete_confirmation_message([key])
    if mode == RECURRENCE_NONE:
        assert message == "این رویداد حذف شود؟"
    else:
        assert recurrence_label(mode) in message
        assert "تمام تکرارهای آن حذف خواهند شد" in message


def test_several_keys_are_counted_and_their_kinds_named():
    """A date-level delete covers the day's whole key set, so the ask counts it
    in Persian digits and lists what is being lost."""
    message = delete_confirmation_message([ONE_TIME_KEY, MONTHLY_KEY, YEARLY_KEY])
    assert "۳ رویداد" in message
    for label in ("بدون تکرار", "ماهانه", "سالانه"):
        assert label in message
    assert "تکرار" in message


def test_an_unparseable_key_reads_as_one_time():
    """Fail closed: a key the model cannot read must never promise that a whole
    series is about to go."""
    assert delete_confirmation_message(["not-a-key"]) == "این رویداد حذف شود؟"


def test_no_keys_still_asks_the_plain_question():
    """The empty set is the store-moved-under-the-card edge: the ask stays a
    valid question instead of rendering a count of zero or an empty list."""
    assert delete_confirmation_message([]) == "این رویداد حذف شود؟"
