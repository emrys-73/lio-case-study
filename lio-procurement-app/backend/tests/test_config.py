import re

from app.core.config import Settings

DATED_SNAPSHOT = re.compile(r"-\d{4}-\d{2}-\d{2}$")


def test_default_model_is_a_dated_snapshot():
    assert DATED_SNAPSHOT.search(Settings.model_fields["openai_model"].default)


def test_running_model_is_a_dated_snapshot():
    assert DATED_SNAPSHOT.search(Settings().openai_model)
