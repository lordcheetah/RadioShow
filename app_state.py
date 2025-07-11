# app_state.py
from pathlib import Path
import threading # For active_thread type hint

class AppState:
    """A dedicated class to hold the application's shared state."""
    def __init__(self):
        # --- File and Path State ---
        self.ebook_path: Path | None = None
        self.txt_path: Path | None = None
        self.calibre_exec_path: Path | None = None
        self.output_dir: Path = Path.cwd() / "Audiobook_Output"
        self.cover_path: Path | None = None # Path to the cover image file

        # --- Metadata State ---
        self.title: str = ""
        self.author: str = ""
        
        # --- Analysis and Script State ---
        self.analysis_result: list = []
        self.cast_list: list = []
        self.character_profiles: dict = {}
        self.pass_2_run_or_skipped: bool = False

        # --- Voice and Assignment State ---
        self.voices: list = []
        self.default_voice_info: dict | None = None
        self.loaded_default_voice_name_from_config: str | None = None
        self.voice_assignments: dict = {}
        self.speaker_colors: dict = {}
        self._color_palette_index: int = 0

        # --- Generation and Review State ---
        self.generated_clips_info: list[dict] = []

        # --- Background Task State ---
        self.active_thread: threading.Thread | None = None
        self.last_operation: str | None = None