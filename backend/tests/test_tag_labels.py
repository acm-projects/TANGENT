"""Tag colour names per case: defaults, overrides, and the colours allowed (no database)."""
import os
from types import SimpleNamespace

import pytest

# dummies only for the import (as test_nodes_messages does): real-DB modules skip when these are unset
_dummies = {"DATABASE_URL": "postgresql://dummy@localhost/dummy", "JWT_SECRET_KEY": "test-secret"}
_added = [k for k in _dummies if k not in os.environ]
os.environ.update({k: _dummies[k] for k in _added})
from pydantic import ValidationError  # noqa: E402

from app.context.schemas import DEFAULT_TAG_LABELS, TAG_COLORS  # noqa: E402
from app.routers.projects_router import TagLabelsIn, tag_labels_of  # noqa: E402

for _k in _added:
    del os.environ[_k]


def test_every_colour_has_a_default_and_some_are_left_blank():
    assert set(DEFAULT_TAG_LABELS) == set(TAG_COLORS)
    assert DEFAULT_TAG_LABELS["ochre"] == "Key finding"
    assert sum(1 for v in DEFAULT_TAG_LABELS.values() if not v) == 3


def test_a_case_s_own_names_go_over_the_defaults():
    labels = tag_labels_of(SimpleNamespace(tag_labels={"teal": "Methods", "ochre": ""}))
    assert labels["teal"] == "Methods" and labels["ochre"] == "" and labels["sage"] == "Supported"
    assert tag_labels_of(SimpleNamespace(tag_labels=None)) == DEFAULT_TAG_LABELS


def test_names_are_trimmed_short_and_only_for_known_colours():
    assert TagLabelsIn(labels={"rose": "  Quote  "}).labels == {"rose": "Quote"}
    with pytest.raises(ValidationError):
        TagLabelsIn(labels={"mauve": "x"})
    with pytest.raises(ValidationError):
        TagLabelsIn(labels={"rose": "x" * 33})
