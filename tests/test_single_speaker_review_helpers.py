import logging
import tempfile
from queue import Queue
from pathlib import Path

from app_state import AppState
from text_processing import TextProcessor


def _make_processor():
    state = AppState()
    state.output_dir = Path(tempfile.gettempdir())
    queue = Queue()
    logger = logging.getLogger("test_single_speaker_review")
    return TextProcessor(state, queue, logger, "Chatterbox")


def test_parse_single_speaker_review_response_array():
    processor = _make_processor()
    raw = (
        "```json\n"
        "[{\"index\": 12, \"action\": \"mark_narration\", \"suggested_speaker\": \"Narrator\"}]\n"
        "```"
    )
    parsed = processor._parse_single_speaker_review_response(raw)
    assert len(parsed) == 1
    assert parsed[0]["index"] == 12


def test_parse_single_speaker_review_response_object_wrapper():
    processor = _make_processor()
    raw = (
        "{\"suggestions\": ["
        "{\"index\": 7, \"action\": \"reassign\", \"suggested_speaker\": \"Kevin\"}"
        "]}"
    )
    parsed = processor._parse_single_speaker_review_response(raw)
    assert len(parsed) == 1
    assert parsed[0]["suggested_speaker"] == "Kevin"


def test_is_obvious_narration_candidate_true_for_action_line():
    processor = _make_processor()
    assert processor._is_obvious_narration_candidate("He turned to look at Kevin.") is True


def test_is_obvious_narration_candidate_false_for_quoted_dialogue():
    processor = _make_processor()
    assert processor._is_obvious_narration_candidate('"I did," Kevin said.') is False
