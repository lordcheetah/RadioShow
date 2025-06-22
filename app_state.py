# app_state.py
from pathlib import Path

class AppState:
    """A dedicated class to hold the application's shared state."""
    def __init__(self):
        # --- File and Path State ---
        self.ebook_path = None
        self.txt_path = None
        self.calibre_exec_path = None
        self.output_dir = Path.cwd() / "Audiobook_Output"
        self.cover_path = None # Path to the cover image file

        # --- Metadata State ---
        self.title = ""
        self.author = ""
        
        # --- Analysis and Script State ---
        self.analysis_result = []
        self.cast_list = []
        self.character_profiles = {}

        # --- Voice and Assignment State ---
        self.voices = []
        self.default_voice_info = None
        self.loaded_default_voice_name_from_config = None
        self.voice_assignments = {}
        self.speaker_colors = {}
        self._color_palette_index = 0

        # --- Generation and Review State ---
        self.generated_clips_info = []

        # --- Background Task State ---
        self.active_thread = None
        self.last_operation = None