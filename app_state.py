# app_state.py
from enum import Enum
from pathlib import Path
import threading # For active_thread type hint

class VoicingMode(Enum):
    NARRATOR = "Narrator"
    NARRATOR_AND_SPEAKER = "Narrator & Speaker"
    CAST = "Cast"

class PostAction:
    DO_NOTHING = "Do Nothing"
    SLEEP = "Sleep"
    SHUTDOWN = "Shutdown"
    QUIT = "Quit"

class AppState:
    """A dedicated class to hold the application's shared state."""
    def __init__(self):
        # --- File and Path State ---
        self.ebook_path: Path | None = None
        self.txt_path: Path | None = None
        self.calibre_exec_path: Path | None = None
        self.output_dir: Path = Path.cwd() / "Audiobook_Output"
        self.project_path: Path | None = None
        self.cover_path: Path | None = None # Path to the cover image file

        # --- Batch Processing State ---
        self.ebook_queue: list[Path] = []
        self.batch_errors: dict[str, str] = {}
        self.is_batch_processing: bool = False

        # --- Metadata State ---
        self.title: str = ""
        self.author: str = ""
        
        # --- Analysis and Script State ---
        self.analysis_result: list = []
        self.cast_list: list = []
        self.character_profiles: dict = {}
        self.pass_2_run_or_skipped: bool = False

        # --- Voice and Assignment State ---
        self.voicing_mode: VoicingMode = VoicingMode.CAST # Default to Cast
        self.voices: list = []
        self.narrator_voice_info: dict | None = None
        self.speaker_voice_info: dict | None = None
        self.loaded_narrator_voice_name_from_config: str | None = None
        self.loaded_speaker_voice_name_from_config: str | None = None
        self.voice_assignments: dict = {}
        self.speaker_colors: dict = {}
        self._color_palette_index: int = 0

        # --- Generation and Review State ---
        self.generated_clips_info: list[dict] = []
        self.max_line_chunk_length: int = 800

        # --- Background Task State ---
        self.active_thread: threading.Thread | None = None
        self.last_operation: str | None = None
        self.stop_requested = False # Flag to request a thread to stop

    def to_dict(self):
        return {
            "ebook_path": str(self.ebook_path) if self.ebook_path else None,
            "txt_path": str(self.txt_path) if self.txt_path else None,
            "title": self.title,
            "author": self.author,
            "analysis_result": self.analysis_result,
            "cast_list": self.cast_list,
            "character_profiles": self.character_profiles,
            "voice_assignments": self.voice_assignments,
            "narrator_voice_name": self.narrator_voice_info['name'] if self.narrator_voice_info else None,
            "speaker_voice_name": self.speaker_voice_info['name'] if self.speaker_voice_info else None,
            "voicing_mode": self.voicing_mode.value,
            "ebook_queue": [str(p) for p in self.ebook_queue],
            "batch_errors": self.batch_errors
        }

    def from_dict(self, data):
        self.ebook_path = Path(data["ebook_path"]) if data.get("ebook_path") else None
        self.txt_path = Path(data["txt_path"]) if data.get("txt_path") else None
        self.title = data.get("title", "")
        self.author = data.get("author", "")
        self.analysis_result = data.get("analysis_result", [])
        self.cast_list = data.get("cast_list", [])
        self.character_profiles = data.get("character_profiles", {})
        self.voice_assignments = data.get("voice_assignments", {})
        self.loaded_narrator_voice_name_from_config = data.get("narrator_voice_name")
        self.loaded_speaker_voice_name_from_config = data.get("speaker_voice_name")
        self.voicing_mode = VoicingMode(data.get("voicing_mode", VoicingMode.CAST.value))
        self.ebook_queue = [Path(p) for p in data.get("ebook_queue", [])]
        self.batch_errors = data.get("batch_errors", {})