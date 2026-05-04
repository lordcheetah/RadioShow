import logging
import queue

from app_state import AppState, VoicingMode
from text_processing import TextProcessor


def test_pass1_resolves_tagged_name_from_extracted_cast():
    state = AppState()
    state.extracted_cast_list_metadata = {
        "characters": [
            {"name": "Wedge Antilles", "role": "Rogue Squadron leader"},
            {"name": "Tycho Celchu", "role": "Rogue pilot"},
        ],
        "confidence": 0.92,
    }

    tp = TextProcessor(state, queue.Queue(), logging.getLogger("test"), "Chatterbox")
    text = '"Hold this line," Wedge said.\n"Copy," Tycho replied.'

    results = tp.run_rules_pass(text, VoicingMode.CAST, use_single_quotes=False)
    assert results is not None

    dialogue_speakers = [
        item["speaker"]
        for item in results
        if str(item.get("speaker_source", "")).startswith("dialogue_")
    ]

    assert "Wedge Antilles" in dialogue_speakers
    assert "Tycho Celchu" in dialogue_speakers
