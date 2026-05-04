import queue

from app_logic import AppLogic
from app_state import AppState


class _DummyUI:
    def __init__(self):
        self.update_queue = queue.Queue()

    def update_cast_list(self):
        return None


def test_auto_assign_prefers_voice_alias_match(tmp_path):
    state = AppState()
    state.output_dir = tmp_path
    state.character_profiles = {
        "Wedge Antilles": {"gender": "Unknown", "age_range": "Unknown", "accent": "Unknown"},
        "Tycho Celchu": {"gender": "Unknown", "age_range": "Unknown", "accent": "Unknown"},
    }
    state.cast_list = ["Tycho Celchu", "Wedge Antilles"]
    state.voices = [
        {
            "name": "Marc Thompson",
            "path": str(tmp_path / "voice1.wav"),
            "gender": "Unknown",
            "age_range": "Unknown",
            "aliases": ["Wedge", "Wedge Antilles", "Corran"],
        },
        {
            "name": "Generic Voice",
            "path": str(tmp_path / "voice2.wav"),
            "gender": "Unknown",
            "age_range": "Unknown",
            "aliases": ["Tycho"],
        },
    ]
    state.voice_assignments = {}

    ui = _DummyUI()
    logic = AppLogic(ui, state, "Chatterbox")

    logic.auto_assign_voices()

    assert state.voice_assignments["Wedge Antilles"]["name"] == "Marc Thompson"
    assert state.voice_assignments["Tycho Celchu"]["name"] == "Generic Voice"
