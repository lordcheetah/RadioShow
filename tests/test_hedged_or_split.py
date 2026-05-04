"""Tests for hedged-OR group splitting in speaker refinement."""
import pytest
from app_state import AppState
from text_processing import TextProcessor
import logging
from queue import Queue


@pytest.fixture
def text_processor():
    """Create a TextProcessor instance for testing."""
    state = AppState()
    state.output_dir = "/tmp"
    queue = Queue()
    logger = logging.getLogger("test")
    processor = TextProcessor(state, queue, logger, "Coqui XTTS")
    return processor


def test_split_hedged_or_groups_basic(text_processor):
    """Test that 'X Or Y' primary names are split into separate groups."""
    input_groups = [
        {"primary_name": "Wedge Or Tycho", "aliases": ["Antilles", "Wedge", "Tycho"]},
        {"primary_name": "Kirk", "aliases": ["James Kirk"]},
    ]

    result = text_processor._split_hedged_or_groups(input_groups)

    # Should have 3 groups now: Wedge, Tycho, Kirk
    assert len(result) == 3
    primary_names = [g["primary_name"] for g in result]
    assert "Wedge" in primary_names
    assert "Tycho" in primary_names
    assert "Kirk" in primary_names


def test_split_hedged_or_groups_case_insensitive(text_processor):
    """Test that OR detection is case-insensitive."""
    input_groups = [
        {"primary_name": "Luke or Leia", "aliases": []},
    ]

    result = text_processor._split_hedged_or_groups(input_groups)

    assert len(result) == 2
    primary_names = [g["primary_name"] for g in result]
    assert "Luke" in primary_names
    assert "Leia" in primary_names


def test_split_hedged_or_groups_no_or(text_processor):
    """Test that groups without OR are left unchanged."""
    input_groups = [
        {"primary_name": "Commander Wedge Antilles", "aliases": ["Wedge", "Antilles"]},
        {"primary_name": "Kirk", "aliases": []},
    ]

    result = text_processor._split_hedged_or_groups(input_groups)

    # No OR present, so should have same number of groups
    assert len(result) == 2
    assert result[0]["primary_name"] == "Commander Wedge Antilles"
    assert result[1]["primary_name"] == "Kirk"


def test_split_hedged_or_groups_with_diagnostics(text_processor):
    """Test that diagnostics are logged when groups are split."""
    input_groups = [
        {"primary_name": "Wedge Or Tycho", "aliases": ["Antilles", "Wedge", "Tycho"]},
    ]

    diag_messages = []

    def capture_diag(msg):
        diag_messages.append(msg)

    result = text_processor._split_hedged_or_groups(input_groups, _diag_fn=capture_diag)

    # Should have logged the split
    assert len(diag_messages) > 0
    assert any("Hedged-OR split" in msg for msg in diag_messages)
    assert any("Wedge" in msg for msg in diag_messages)
    assert any("Tycho" in msg for msg in diag_messages)


def test_split_multiple_or_parts(text_processor):
    """Test splitting when there are more than 2 parts."""
    input_groups = [
        {"primary_name": "X Or Y Or Z", "aliases": []},
    ]

    result = text_processor._split_hedged_or_groups(input_groups)

    assert len(result) == 3
    primary_names = [g["primary_name"] for g in result]
    assert "X" in primary_names
    assert "Y" in primary_names
    assert "Z" in primary_names


def test_split_preserves_unaffected_groups(text_processor):
    """Test that groups without OR are preserved exactly."""
    input_groups = [
        {"primary_name": "Kirk", "aliases": ["James Kirk", "Captain Kirk"]},
        {"primary_name": "Spock Or McCoy", "aliases": []},
        {"primary_name": "Uhura", "aliases": []},
    ]

    result = text_processor._split_hedged_or_groups(input_groups)

    # Kirk should be unchanged
    kirk_group = [g for g in result if g["primary_name"] == "Kirk"]
    assert len(kirk_group) == 1
    assert kirk_group[0]["aliases"] == ["James Kirk", "Captain Kirk"]

    # Uhura should be unchanged
    uhura_group = [g for g in result if g["primary_name"] == "Uhura"]
    assert len(uhura_group) == 1
    assert uhura_group[0]["aliases"] == []

    # Spock and McCoy should be separate
    spock_group = [g for g in result if g["primary_name"] == "Spock"]
    mccoy_group = [g for g in result if g["primary_name"] == "McCoy"]
    assert len(spock_group) == 1
    assert len(mccoy_group) == 1
