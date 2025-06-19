# ui_setup.py
import tkinter as tk
from tkinter import ttk, simpledialog, filedialog, messagebox, scrolledtext
from pathlib import Path
import threading
import re
import queue
from tkinterdnd2 import DND_FILES, TkinterDnD
import platform # For system detection
import json # For saving/loading voice config

from pydub.playback import play as pydub_play
# Import the logic class from the other file
from app_logic import AppLogic

LIGHT_THEME = {
    "bg": "#ECECEC", "fg": "#000000", "frame_bg": "#F0F0F0", "text_bg": "#FFFFFF", "text_fg": "#000000",
    "button_bg": "#D9D9D9", "button_fg": "#000000", "button_active_bg": "#C0C0C0",
    "select_bg": "#0078D7", "select_fg": "#FFFFFF", "tree_heading_bg": "#D9D9D9",
    "tree_even_row_bg": "#FFFFFF", "tree_odd_row_bg": "#F0F0F0", "disabled_fg": "#A0A0A0",
    "progressbar_trough": "#E0E0E0", "progressbar_bar": "#0078D7",
    "status_fg": "blue", "error_fg": "red", "success_fg": "green", "cursor_color": "#000000",
    "scrollbar_bg": "#D9D9D9", "scrollbar_trough": "#F0F0F0", "labelframe_fg": "#000000"
}

DARK_THEME = {
    "bg": "#2E2E2E", "fg": "#E0E0E0", "frame_bg": "#3C3C3C", "text_bg": "#252525", "text_fg": "#E0E0E0",
    "button_bg": "#505050", "button_fg": "#E0E0E0", "button_active_bg": "#6A6A6A",
    "select_bg": "#005A9E", "select_fg": "#E0E0E0", "tree_heading_bg": "#424242",
    "tree_even_row_bg": "#3C3C3C", "tree_odd_row_bg": "#333333", "disabled_fg": "#707070",
    "progressbar_trough": "#404040", "progressbar_bar": "#0078D7",
    "status_fg": "#ADD8E6", "error_fg": "#FF7B7B", "success_fg": "#90EE90", "cursor_color": "#FFFFFF",
    "scrollbar_bg": "#505050", "scrollbar_trough": "#3C3C3C", "labelframe_fg": "#E0E0E0"
}

# Store references to all created tk.Label and tk.Button widgets for easier theming
_themed_tk_labels = []
_themed_tk_buttons = []

# Store references to LabelFrames for easier theming
_themed_tk_labelframes = []

# Constants for post-actions
class PostAction:
    DO_NOTHING = "do_nothing"
    SLEEP = "sleep"
    SHUTDOWN = "shutdown"
    QUIT = "quit"

class AudiobookCreatorApp(tk.Frame):
    def __init__(self, root):
        super().__init__(root, padx=10, pady=10)
        self.root = root
        self.pack(fill=tk.BOTH, expand=True)

        # State variables that the UI needs to manage
        self.ebook_path = None
        self.txt_path = None
        self.calibre_exec_path = None
        self.cast_list = []
        self.allowed_extensions = ['.epub', '.mobi', '.pdf', '.azw3']
        self.active_thread = None
        self.last_operation = None
        self.timer_id = None
        self.timer_seconds = 0
        self.update_queue = queue.Queue()
        self.output_dir = Path.cwd() / "Audiobook_Output"
        self.output_dir.mkdir(exist_ok=True)

        self.current_theme_name = "system" # "light", "dark", "system"
        self.system_actual_theme = "light" # What "system" resolves to
        self._theme_colors = {}
        self.theme_var = tk.StringVar(value=self.current_theme_name) # "light", "dark", "system"
        self.selected_tts_engine_name = "Coqui XTTS" # Default, will be updated by tts_engine_var
        self.tts_engine_var = tk.StringVar(value="Coqui XTTS") # Default TTS engine
        self.post_action_var = tk.StringVar(value=PostAction.DO_NOTHING)

        self.analysis_result = [] # Stores results from text analysis
        
        # TTS Engine and Voice Data (will be populated by the logic class)
        self.generated_clips_info = [] # For the new review step: [{'text':..., 'speaker':..., 'clip_path':..., 'original_index':..., 'voice_used':...}]
        self.speaker_colors = {}
        self.color_palette = [ # List of visually distinct colors
            "#E6194B", "#3CB44B", "#FFE119", "#4363D8", "#F58231", "#911EB4", "#46F0F0", "#F032E6", 
            "#BCF60C", "#FABEBE", "#008080", "#E6BEFF", "#9A6324", "#FFFAC8", "#800000", "#AAFFC3", 
            "#808000", "#FFD8B1", "#000075", "#808080", "#FFFFFF", "#000000" # Added white/black for more options
        ] # Ensure good contrast with theme BG/FG
        self._color_palette_index = 0

        # self.tts_engine = None # This will be managed by AppLogic now
        self.voices = [] # This will now be a list of dicts: [{'name': str, 'path': str}]
        # Initialize voices list and default_voice_info before loading config
        self.default_voice_info = None # Stores the dict {'name': str, 'path': str} for the default voice
        self.voice_assignments = {} # Maps speaker name to a voice dict
        self.loaded_default_voice_name_from_config = None # Temp store for name from JSON
        
        # Create an instance of the logic class, passing a reference to self
        self.logic = AppLogic(self)
        # Load voice config after logic is initialized (for logging) but before UI that depends on it
        self.load_voice_config() # Load saved voices before UI creation that depends on it

        # UI Frames and Widgets
        self.content_frame = tk.Frame(self)
        self.content_frame.pack(fill=tk.BOTH, expand=True)
        self.status_frame = tk.Frame(self)
        self.status_frame.pack(fill=tk.X, pady=(5,0))
        self.progressbar = ttk.Progressbar(self.status_frame, mode='indeterminate')
        self.progressbar.pack(fill=tk.X, padx=5, pady=(0,5), expand=True)
        self.progressbar.pack_forget()
        self.status_label = tk.Label(self.status_frame, text="", fg="blue")
        self.status_label.pack(fill=tk.X, expand=True)
        self.wizard_frame = tk.Frame(self.content_frame)
        self.editor_frame = tk.Frame(self.content_frame)
        self.analysis_frame = tk.Frame(self.content_frame)
        self.review_frame = tk.Frame(self.content_frame) # New review frame
        
        # Create all widgets first
        self.create_wizard_widgets()
        self.create_editor_widgets()
        self.create_analysis_widgets()
        self.create_review_widgets() # New review widgets
        
        # Then initialize theming (which might apply theme if system theme changed during detection)
        self.initialize_theming() 
        self.create_menubar()     # Menubar uses theme_var, so initialize_theming should come first

        # Explicitly apply the theme based on current settings after all setup
        self.apply_theme_settings() 
        # Schedule TTS initialization with UI feedback

        # Initialize the status label text and color properly
        if hasattr(self, 'status_label') and self._theme_colors:
            self.status_label.config(text="", fg=self._theme_colors.get("status_fg", "blue"))
        elif hasattr(self, 'status_label'): # Fallback if theme colors not yet loaded
            self.status_label.config(text="", fg="blue")

        # Ensure the initial status label color is set according to the theme
        self.update_status_label_color()


        self.root.after(200, self.start_tts_initialization_with_ui_feedback)
        
        self.show_wizard_view()
    
    def create_menubar(self):
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar) # Set the menubar for the root window

        self.theme_menu = tk.Menu(menubar, tearoff=0) # Store as instance variable
        menubar.add_cascade(label="View", menu=self.theme_menu)
        # Note: Full menubar styling is highly OS-dependent with Tkinter
        # self._menubar = menubar # Store if needed for more direct styling attempts
        # self._theme_menu = theme_menu # Store if needed

        self.theme_menu.add_radiobutton(label="Light", variable=self.theme_var, value="light", command=self.change_theme)
        self.theme_menu.add_radiobutton(label="Dark", variable=self.theme_var, value="dark", command=self.change_theme)
        self.theme_menu.add_radiobutton(label="System", variable=self.theme_var, value="system", command=self.change_theme)

        tts_engine_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="TTS Engine", menu=tts_engine_menu)

        possible_engines = [
            {"label": "Coqui XTTS", "value": "Coqui XTTS", "check_module": "TTS.api"},
            {"label": "Chatterbox", "value": "Chatterbox", "check_module": "chatterbox.tts"}
        ]

        available_engines = []
        for engine_spec in possible_engines:
            try:
                __import__(engine_spec["check_module"])
                available_engines.append(engine_spec)
                self.logic.logger.info(f"TTS Engine available: {engine_spec['label']}")
            except ImportError:
                self.logic.logger.info(f"TTS Engine {engine_spec['label']} (module {engine_spec['check_module']}) not found. It will not be listed.")

        if available_engines:
            # Set default tts_engine_var to the first available one
            self.tts_engine_var.set(available_engines[0]["value"])
            self.selected_tts_engine_name = available_engines[0]["value"] # Update internal tracker
            for engine_spec in available_engines:
                tts_engine_menu.add_radiobutton(
                    label=engine_spec["label"],
                    variable=self.tts_engine_var,
                    value=engine_spec["value"],
                    command=self.change_tts_engine
                )
        else:
            tts_engine_menu.add_command(label="No TTS engines found/installed.", state=tk.DISABLED)
            self.tts_engine_var.set("") # No engine selected
            self.selected_tts_engine_name = ""
            self.logic.logger.warning("No compatible TTS engines were found installed.")
            # self.root.after(500, lambda: messagebox.showwarning("TTS Engines Missing", "No compatible TTS engines (Coqui XTTS, Chatterbox) found. TTS functionality will be limited.")) # Kept as popup due to importance
            
        post_actions_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Post-Actions", menu=post_actions_menu)
        post_actions_menu.add_radiobutton(label="Do Nothing", variable=self.post_action_var, value=PostAction.DO_NOTHING)
        post_actions_menu.add_radiobutton(label="Sleep on Finish", variable=self.post_action_var, value=PostAction.SLEEP)
        post_actions_menu.add_radiobutton(label="Shutdown on Finish", variable=self.post_action_var, value=PostAction.SHUTDOWN)
        post_actions_menu.add_radiobutton(label="Quit Program on Finish", variable=self.post_action_var, value=PostAction.QUIT)


        # For future: self.root.bind("<<ThemeChanged>>", self.on_system_theme_change_event)

    def initialize_theming(self):
        self.detect_system_theme() 
        # In a real app, you might load saved theme preference here
        # self.current_theme_name = saved_preference or "system"
        # self.theme_var.set(self.current_theme_name)

    def detect_system_theme(self):
        system_os = platform.system()
        original_system_theme = self.system_actual_theme
        try:
            if system_os == "Windows":
                import winreg
                key_path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path)
                value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
                winreg.CloseKey(key)
                self.system_actual_theme = "light" if value == 1 else "dark"
            elif system_os == "Darwin": # macOS
                import subprocess
                cmd = 'defaults read -g AppleInterfaceStyle'
                # Use shell=False for security with specific commands
                p = subprocess.run(cmd.split(), capture_output=True, text=True, check=False)
                if p.stdout and p.stdout.strip() == 'Dark':
                    self.system_actual_theme = "dark"
                else:
                    self.system_actual_theme = "light" # Default if not 'Dark' or command fails
            else: # Linux or other
                self.system_actual_theme = "light" # Default for now, can be expanded
        except Exception as e:
            self.logic.logger.warning(f"Could not detect system theme on {system_os}: {e}. Defaulting to light.")
            self.system_actual_theme = "light"
        
        if original_system_theme != self.system_actual_theme:
            self.logic.logger.info(f"System theme changed to: {self.system_actual_theme}")
            if self.current_theme_name == "system":
                 self.apply_theme_settings() # Re-apply if system theme is active and changed

    def change_theme(self):
        self.current_theme_name = self.theme_var.get()
        # In a real app, save self.current_theme_name to a config file
        self.apply_theme_settings()

    def change_tts_engine(self):
        new_engine_name = self.tts_engine_var.get()
        if not new_engine_name: # Should not happen if menu is populated correctly
            self.logic.logger.warning("Change TTS engine called with no engine selected.")
            return

        self.selected_tts_engine_name = new_engine_name # Update internal tracker
        self.logic.logger.info(f"TTS Engine selection changed to: {new_engine_name}. Re-initializing.")

        # Clear runtime voice list and assignments. Default will be re-evaluated.
        self.voices = []
        self.default_voice_info = None
        self.loaded_default_voice_name_from_config = None # Reset for new load
        self.voice_assignments = {}

        # Reload user-defined voices from the configuration file.
        self.load_voice_config() # This populates self.voices and self.default_voice_info from JSON
        self.start_tts_initialization_with_ui_feedback() # This will re-initialize and update UI

    # def on_system_theme_change_event(self, event=None): # For future real-time updates
    #     self.detect_system_theme()
    #     if self.current_theme_name == "system":
    #         self.apply_theme_settings()

    def apply_theme_settings(self):
        if not hasattr(self, 'status_label'): # Widgets not created yet
            return

        theme_to_apply = self.current_theme_name
        if theme_to_apply == "system":
            self.detect_system_theme() # Ensure system_actual_theme is up-to-date
            theme_to_apply = self.system_actual_theme
        
        self._theme_colors = LIGHT_THEME if theme_to_apply == "light" else DARK_THEME
        
        self.root.config(background=self._theme_colors["bg"])
        self.config(background=self._theme_colors["bg"]) 
        
        # Styling the menubar's background/foreground directly is often problematic
        # and OS-dependent. Individual menu items (like radiobuttons) might be stylable
        # via their own configurations or ttk styles if they were ttk widgets.
        # For now, we'll rely on the OS to handle menubar appearance.
        # Attempt to style items within the theme_menu
        if hasattr(self, 'theme_menu') and self.theme_menu:
            try:
                for i in range(self.theme_menu.index(tk.END) + 1):
                    self.theme_menu.entryconfigure(i, 
                                                   background=self._theme_colors["bg"], 
                                                   foreground=self._theme_colors["fg"],
                                                   activebackground=self._theme_colors["select_bg"],
                                                   activeforeground=self._theme_colors["select_fg"],
                                                   selectcolor=self._theme_colors["fg"] # Color of the radiobutton indicator
                                                  )
            except tk.TclError as e:
                self.logic.logger.debug(f"Note: Could not fully style menu items (OS limitations likely): {e}")
                # This might still fail on some options depending on OS and Tk version
            pass


        self.apply_standard_tk_styles()
        self.apply_ttk_styles()

        self.update_treeview_item_tags(self.tree)
        self.update_treeview_item_tags(self.cast_tree)
        self.update_status_label_color()
        self.text_editor.config( # Ensure ScrolledText is themed
            background=self._theme_colors["text_bg"], foreground=self._theme_colors["text_fg"],
            insertbackground=self._theme_colors["cursor_color"],
            selectbackground=self._theme_colors["select_bg"], selectforeground=self._theme_colors["select_fg"]
        )

    def start_tts_initialization_with_ui_feedback(self):
        self.start_progress_indicator("Initializing TTS Engine...")
        # AppLogic.initialize_tts sets self.ui.last_operation = 'tts_init'
        # and starts the background thread.
        self.logic.selected_tts_engine_name = self.selected_tts_engine_name # Ensure logic uses current selection
        self.logic.initialize_tts()

    def create_wizard_widgets(self):
        self.wizard_frame.drop_target_register(DND_FILES)
        self.wizard_frame.dnd_bind('<<Drop>>', self.handle_drop)
        self.wizard_info_label = tk.Label(self.wizard_frame, text="Step 1 & 2: Upload and Convert", font=("Helvetica", 14, "bold"))
        self.wizard_info_label.pack(pady=(0, 10))
        self.upload_frame = tk.Frame(self.wizard_frame) # Made instance attribute
        self.upload_frame.pack(fill=tk.X)
        self.upload_button = tk.Button(self.upload_frame, text="Upload Ebook", command=self.upload_ebook)
        self.upload_button.pack(side=tk.LEFT, expand=True, fill=tk.X, ipady=5)
        self.drop_info_label = tk.Label(self.upload_frame, text="<-- or Drag & Drop File Here", fg="grey")
        self.drop_info_label.pack(side=tk.LEFT, padx=10)
        self.file_status_label = tk.Label(self.wizard_frame, text="No ebook selected.", wraplength=580, justify=tk.CENTER)
        self.file_status_label.pack(pady=5)
        self.next_step_button = tk.Button(self.wizard_frame, text="Convert to Text", state=tk.DISABLED, command=self.logic.start_conversion_process)
        self.next_step_button.pack(fill=tk.X, ipady=5, pady=5)
        self.edit_text_button = tk.Button(self.wizard_frame, text="Step 3: Edit Text", state=tk.DISABLED, command=self.show_editor_view)
        self.edit_text_button.pack(fill=tk.X, ipady=5, pady=5)
        _themed_tk_labels.extend([self.wizard_info_label, self.drop_info_label, self.file_status_label])
        _themed_tk_buttons.extend([self.upload_button, self.next_step_button, self.edit_text_button])

    def create_editor_widgets(self):
        self.editor_info_label = tk.Label(self.editor_frame, text="Step 3: Review and Edit Text", font=("Helvetica", 14, "bold"))
        self.editor_info_label.pack(pady=(0, 10))
        self.text_editor = scrolledtext.ScrolledText(self.editor_frame, wrap=tk.WORD, font=("Arial", 10))
        self.text_editor.pack(expand=True, fill=tk.BOTH, padx=5, pady=5)
        self.editor_button_frame = tk.Frame(self.editor_frame) # Made instance attribute
        self.editor_button_frame.pack(fill=tk.X, pady=5)
        self.save_button = tk.Button(self.editor_button_frame, text="Save Changes", command=self.save_edited_text)
        self.save_button.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
        self.back_button_editor = tk.Button(self.editor_button_frame, text="< Back to Start", command=self.show_wizard_view)
        self.back_button_editor.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
        self.analyze_button = tk.Button(self.editor_frame, text="Step 4: Analyze Characters", command=self.start_hybrid_analysis)
        self.analyze_button.pack(fill=tk.X, ipady=5, pady=5)
        _themed_tk_labels.append(self.editor_info_label)
        _themed_tk_buttons.extend([self.save_button, self.back_button_editor, self.analyze_button])
    
    def create_analysis_widgets(self):
        self.analysis_frame.pack_propagate(False)
        self.analysis_top_frame = tk.Frame(self.analysis_frame); self.analysis_top_frame.pack(side=tk.TOP, fill=tk.X, pady=(0, 10))
        self.analysis_main_panels_frame = tk.Frame(self.analysis_frame); self.analysis_main_panels_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.analysis_bottom_frame = tk.Frame(self.analysis_frame); self.analysis_bottom_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(10, 0), anchor=tk.S)
        
        self.analysis_info_label = tk.Label(self.analysis_top_frame, text="Step 4 & 5: Review Script and Assign Voices", font=("Helvetica", 14, "bold")); self.analysis_info_label.pack(anchor='w')
        
        self.cast_list_outer_frame = tk.Frame(self.analysis_main_panels_frame, width=280); self.cast_list_outer_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10)); self.cast_list_outer_frame.pack_propagate(False)
        self.cast_list_label = tk.Label(self.cast_list_outer_frame, text="Cast List", font=("Helvetica", 12, "bold")); self.cast_list_label.pack(fill=tk.X)
        cast_columns = ('speaker', 'voice'); self.cast_tree = ttk.Treeview(self.cast_list_outer_frame, columns=cast_columns, show='headings', height=10)
        self.cast_tree.heading('speaker', text='Speaker'); self.cast_tree.heading('voice', text='Assigned Voice')
        self.cast_tree.column('speaker', width=130); self.cast_tree.column('voice', width=130)
        self.cast_tree.pack(fill=tk.BOTH, expand=True, pady=(5,0)) # self.cast_tree is already an instance attr
        self.rename_button = tk.Button(self.cast_list_outer_frame, text="Rename Selected Speaker", command=self.rename_speaker); self.rename_button.pack(fill=tk.X, pady=(5,0))
        self.resolve_button = tk.Button(self.cast_list_outer_frame, text="Resolve Ambiguous (AI)", command=self.logic.start_pass_2_resolution); self.resolve_button.pack(fill=tk.X)
        
        # --- NEW & IMPROVED VOICE MANAGEMENT WIDGETS ---
        self.voice_mgmt_labelframe = tk.LabelFrame(self.cast_list_outer_frame, text="Voice Library", padx=5, pady=5)
        self.voice_mgmt_labelframe.pack(fill=tk.X, pady=(10,0))
        _themed_tk_labelframes.append(self.voice_mgmt_labelframe)

        self.add_voice_button = tk.Button(self.voice_mgmt_labelframe, text="Add New Voice (.wav)", command=self.add_new_voice)
        self.add_voice_button.pack(fill=tk.X)
        self.set_default_voice_button = tk.Button(self.voice_mgmt_labelframe, text="Set Selected as Default", command=self.set_selected_as_default_voice)
        self.set_default_voice_button.pack(fill=tk.X, pady=(5,0))
        self.default_voice_label = tk.Label(self.voice_mgmt_labelframe, text="Default: None")
        self.default_voice_label.pack(fill=tk.X, pady=(5,0))

        self.assign_voice_labelframe = tk.LabelFrame(self.cast_list_outer_frame, text="Assign Voice to Selected Speaker", padx=5, pady=5)
        self.assign_voice_labelframe.pack(fill=tk.X, pady=(5,0))
        _themed_tk_labelframes.append(self.assign_voice_labelframe)

        self.voice_dropdown = ttk.Combobox(self.assign_voice_labelframe, state='readonly'); self.voice_dropdown.pack(fill=tk.X, pady=(0, 5))
        self.assign_button = tk.Button(self.assign_voice_labelframe, text="Assign Voice", command=self.assign_voice); self.assign_button.pack(fill=tk.X)
        # --- END WIDGET CHANGES ---

        self.results_frame = tk.Frame(self.analysis_main_panels_frame); self.results_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        columns = ('speaker', 'line'); self.tree = ttk.Treeview(self.results_frame, columns=columns, show='headings')
        self.tree.heading('speaker', text='Speaker'); self.tree.heading('line', text='Line')
        self.tree.column('speaker', width=150, anchor='n'); self.tree.column('line', width=1000)
        vsb = ttk.Scrollbar(self.results_frame, orient="vertical", command=self.tree.yview); hsb = ttk.Scrollbar(self.results_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side='right', fill='y'); hsb.pack(side='bottom', fill='x'); self.tree.pack(side=tk.LEFT, expand=True, fill='both')
        self.tree.bind('<Double-1>', self.on_treeview_double_click)
        self.back_button_analysis = tk.Button(self.analysis_bottom_frame, text="< Back to Editor", command=self.confirm_back_to_editor); self.back_button_analysis.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
        self.tts_button = tk.Button(self.analysis_bottom_frame, text="Step 6: Generate Audiobook", command=self.start_audio_generation); self.tts_button.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)

        _themed_tk_labels.extend([self.analysis_info_label, self.cast_list_label, self.default_voice_label])
        _themed_tk_buttons.extend([self.rename_button, self.resolve_button, self.add_voice_button, 
                                   self.set_default_voice_button, self.assign_button, 
                                   self.back_button_analysis, self.tts_button])

    # --- NEW METHOD: ADD A VOICE TO THE LIBRARY ---
    def add_new_voice(self):
        voice_name = simpledialog.askstring("Add Voice", "Enter a name for this new voice (e.g., 'Narrator', 'Hero'):", parent=self.root)
        if not voice_name or not voice_name.strip():
            return
        voice_name = voice_name.strip()
        if any(v['name'] == voice_name for v in self.voices):
            messagebox.showwarning("Duplicate Name", "A voice with this name already exists.")
            return

        filepath_str = filedialog.askopenfilename(
            title=f"Select a 10-30 second sample .wav file for '{voice_name}'",
            filetypes=[("WAV Audio Files", "*.wav")]
        )
        if not filepath_str:
            return

        voice_path = Path(filepath_str)
        if not voice_path.exists():
            messagebox.showerror("Error", "File not found.")
            return
        
        new_voice = {'name': voice_name, 'path': str(voice_path)}
        self.voices.append(new_voice)
        
        # If this is the first voice added, or no default is set, make it the default
        if not self.default_voice_info:
            self.default_voice_info = new_voice
            self.default_voice_label.config(text=f"Default: {new_voice['name']}")
            
        self.save_voice_config()
        self.update_voice_dropdown()
        messagebox.showinfo("Success", f"Voice '{voice_name}' added successfully.")

    def set_selected_as_default_voice(self):
        selected_voice_name = self.voice_dropdown.get()
        if not selected_voice_name:
            messagebox.showwarning("No Voice Selected", "Please select a voice from the dropdown to set as default.")
            return

        selected_voice = next((v for v in self.voices if v['name'] == selected_voice_name), None)
        if selected_voice:
            self.default_voice_info = selected_voice
            self.default_voice_label.config(text=f"Default: {selected_voice['name']}")
            self.save_voice_config()
            messagebox.showinfo("Default Voice Set", f"'{selected_voice['name']}' is now the default voice.")
        else:
            # Should not happen if dropdown is synced with self.voices
            messagebox.showerror("Error", "Could not find the selected voice data.")

    # --- NEW METHOD: UPDATE THE VOICE DROPDOWN ---
    def update_voice_dropdown(self):
        voice_names = sorted([v['name'] for v in self.voices])
        self.voice_dropdown.config(values=voice_names)
        if voice_names:
            self.voice_dropdown.set(voice_names[0])
        else:
            self.voice_dropdown.set("")
        self.set_default_voice_button.config(state=tk.NORMAL if self.voices else tk.DISABLED)

    # --- UPDATED METHOD ---
    def assign_voice(self):
        try:
            selected_item_id = self.cast_tree.selection()[0]
            speaker_name = self.cast_tree.item(selected_item_id, 'values')[0]
        except IndexError:
            return messagebox.showwarning("No Selection", "Please select a speaker from the cast list first.")
        
        selected_voice_name = self.voice_dropdown.get()
        if not selected_voice_name:
            return messagebox.showwarning("No Voice Selected", "Please select a voice from the dropdown menu.\nYou may need to add one first using the 'Add New Voice' button.")

        # Find the full voice dictionary
        selected_voice = next((voice for voice in self.voices if voice['name'] == selected_voice_name), None)
        if selected_voice is None:
            return messagebox.showerror("Error", "Could not find the selected voice data. It may have been removed.")

        # Store the entire voice dictionary for the selected speaker
        self.voice_assignments[speaker_name] = selected_voice
        print(f"Assigned voice '{selected_voice['name']}' to '{speaker_name}'.")
        self.update_cast_list()

    # --- UPDATED METHOD ---
    def update_cast_list(self):
        if not self.analysis_result: return
        unique_speakers = sorted(list(set(item['speaker'] for item in self.analysis_result)))
        self.cast_list = unique_speakers
        
        selected_item = self.cast_tree.selection()
        self.cast_tree.delete(*self.cast_tree.get_children())
        
        c = self._theme_colors # Get current theme colors
        for i, speaker in enumerate(self.cast_list):
            speaker_color_tag = self.get_speaker_color_tag(speaker) # Get or assign color tag
            assigned_voice_name = "Not Assigned"
            if speaker in self.voice_assignments:
                # We now store the whole dict, so get the name from it
                assigned_voice_name = self.voice_assignments[speaker]['name']
            self.cast_tree.insert('', tk.END, iid=speaker, values=(speaker, assigned_voice_name), tags=(speaker_color_tag,))
        
        if selected_item:
            try: 
                if self.cast_tree.exists(selected_item[0]): self.cast_tree.selection_set(selected_item)
            except tk.TclError: pass
        self.update_treeview_item_tags(self.cast_tree) # Apply odd/even row bg

    # --- END UPDATED METHOD ---

    def show_status_message(self, message, msg_type="info"):
        # msg_type: "info", "warning", "error", "success"
        # Ensure _theme_colors is initialized
        if not self._theme_colors:
            self.apply_theme_settings() # Apply theme to populate _theme_colors if not already

        fg_color = self._theme_colors.get("status_fg", "blue") # Default
        if msg_type == "success":
            fg_color = self._theme_colors.get("success_fg", "green")
        elif msg_type == "error" or msg_type == "warning": # Treat warnings as errors for visibility
            fg_color = self._theme_colors.get("error_fg", "red")
        
        self.status_label.config(text=message, fg=fg_color)
    # --- UPDATED METHOD ---
    def on_tts_initialization_complete(self):
        self.stop_progress_indicator() # Stop indicator on successful completion
        self.set_ui_state(tk.NORMAL) # Enable general UI elements
        self._update_wizard_button_states() # Set specific button states

        engine_display_name = "TTS" # Default if something unexpected happens
        if self.logic.current_tts_engine_instance:
            engine_display_name = self.logic.current_tts_engine_instance.get_engine_name()
            status_msg = f"{engine_display_name} engine initialized. Add/manage voices before generation."
            self.show_status_message(status_msg, "success")


            # Get engine-specific voices (like internal defaults)
            # self.voices already contains user-loaded voices from load_voice_config (called in __init__ or change_tts_engine)
            engine_voices = self.logic.current_tts_engine_instance.get_engine_specific_voices()
            for eng_voice in engine_voices:
                ui_voice_format = {'name': eng_voice['name'], 'path': eng_voice['id_or_path']}
                if not any(v['path'] == ui_voice_format['path'] for v in self.voices):
                    self.voices.append(ui_voice_format)
                
            # Default Voice Resolution:
            # Try to re-establish default based on the name loaded from config,
            # searching within the now complete self.voices list (user + current engine).
            resolved_default_voice = None
            if self.loaded_default_voice_name_from_config:
                resolved_default_voice = next((v for v in self.voices if v['name'] == self.loaded_default_voice_name_from_config), None)

            if resolved_default_voice:
                self.default_voice_info = resolved_default_voice
            else:
                # No valid saved default, or saved default not found in current engine's + user voices.
                # Try to set a sensible engine-specific default.
                self.default_voice_info = None # Reset before trying engine defaults
                if engine_display_name == "Coqui XTTS":
                    xtts_default = next((v for v in self.voices if v['path'] == '_XTTS_INTERNAL_VOICE_'), None)
                    if xtts_default: self.default_voice_info = xtts_default
                elif engine_display_name == "Chatterbox":
                    cb_default = next((v for v in self.voices if v['path'] == 'chatterbox_default_internal'), None)
                    if cb_default: self.default_voice_info = cb_default
                # If still no default, and self.voices is not empty, it will remain None or could pick first.
                # Current logic implies it remains None if no specific engine default matches.

            if self.default_voice_info:
                self.default_voice_label.config(text=f"Default: {self.default_voice_info['name']}")
            else:
                self.default_voice_label.config(text="Default: None (select or add one)")
        else: # No TTS engine instance (e.g., none available or init failed before instance creation)
            self.show_status_message("TTS Engine not available or failed to initialize.", "error")
            self.default_voice_label.config(text="Default: None")

        self.update_voice_dropdown() # Ensure dropdown is populated, now potentially with internal voice
        # self.update_status_label_color() # show_status_message handles this

    def set_ui_state(self, state, exclude=None):
        if exclude is None: exclude = []
        widgets_to_toggle = [
            self.upload_button, self.next_step_button, self.edit_text_button, 
            self.save_button, self.back_button_editor, self.analyze_button, 
            self.back_button_analysis, self.tts_button, self.text_editor, self.tree, 
            self.resolve_button, self.cast_tree, self.rename_button, self.add_voice_button, # Added self.rename_button
            self.set_default_voice_button, self.voice_dropdown, self.assign_button,
            self.play_selected_button, self.regenerate_selected_button, self.assemble_audiobook_button, self.back_to_analysis_button_review, self.review_tree # New review widgets
        ]
        for widget in widgets_to_toggle:
            if widget and widget not in exclude:
                try: widget.config(state=state)
                except (tk.TclError, AttributeError): pass
        
        # Only change cursor if colors are available (theme applied)
        if self._theme_colors:
            self.root.config(cursor="watch" if state == tk.DISABLED else "")

    def _update_wizard_button_states(self):
        """ Helper to set states of wizard step buttons based on ebook and txt paths. """
        if self.ebook_path:
            if self.txt_path: # Ebook processed and converted
                self.next_step_button.config(state=tk.DISABLED, text="Conversion Complete")
                self.edit_text_button.config(state=tk.NORMAL)
            else: # Ebook loaded, but not yet converted
                self.next_step_button.config(state=tk.NORMAL, text="Convert to Text")
                self.edit_text_button.config(state=tk.DISABLED)
        else: # No ebook loaded yet
            self.next_step_button.config(state=tk.DISABLED, text="Convert to Text")
            self.edit_text_button.config(state=tk.DISABLED)


    # --- Other methods are unchanged, but included for completeness ---
    
    def get_speaker_color_tag(self, speaker_name):
        """Gets a color for a speaker and ensures a ttk tag exists for it."""
        if speaker_name not in self.speaker_colors:
            color = self.color_palette[self._color_palette_index % len(self.color_palette)]
            self.speaker_colors[speaker_name] = color
            self._color_palette_index += 1
        
        color = self.speaker_colors[speaker_name]
        tag_name = f"speaker_{re.sub(r'[^a-zA-Z0-9_]', '', speaker_name)}" # Sanitize name for tag

        # Ensure the tag is configured in all relevant treeviews
        for treeview in [self.tree, self.cast_tree, self.review_tree]:
            if treeview: # Check if treeview exists (e.g. review_tree might not be fully init early)
                try:
                    # Check if tag exists by trying to get its configuration
                    # If it doesn't exist, TclError is raised by cget if tag unknown.
                    # A more robust way is to check if tag_names() includes it, but configure is idempotent.
                    treeview.tag_configure(tag_name, foreground=color)
                except tk.TclError: # Should not happen if configure is idempotent
                     treeview.tag_configure(tag_name, foreground=color)
        return tag_name

    def create_review_widgets(self):
        self.review_frame.pack_propagate(False)
        review_top_frame = tk.Frame(self.review_frame); review_top_frame.pack(side=tk.TOP, fill=tk.X, pady=(0,10))
        self.review_info_label = tk.Label(review_top_frame, text="Step 6: Review Generated Audio & Assemble", font=("Helvetica", 14, "bold"))
        self.review_info_label.pack(anchor='w')
        _themed_tk_labels.append(self.review_info_label)

        review_main_frame = tk.Frame(self.review_frame); review_main_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        
        # Treeview for generated lines
        review_columns = ('num', 'speaker', 'line_text', 'status')
        self.review_tree = ttk.Treeview(review_main_frame, columns=review_columns, show='headings')
        self.review_tree.heading('num', text='#'); self.review_tree.column('num', width=50, anchor='n')
        self.review_tree.heading('speaker', text='Speaker'); self.review_tree.column('speaker', width=150, anchor='n')
        self.review_tree.heading('line_text', text='Line Text'); self.review_tree.column('line_text', width=500)
        self.review_tree.heading('status', text='Status'); self.review_tree.column('status', width=100, anchor='n')
        
        vsb_review = ttk.Scrollbar(review_main_frame, orient="vertical", command=self.review_tree.yview)
        hsb_review = ttk.Scrollbar(review_main_frame, orient="horizontal", command=self.review_tree.xview)
        self.review_tree.configure(yscrollcommand=vsb_review.set, xscrollcommand=hsb_review.set)
        vsb_review.pack(side='right', fill='y'); hsb_review.pack(side='bottom', fill='x')
        self.review_tree.pack(side=tk.LEFT, expand=True, fill='both')

        review_bottom_frame = tk.Frame(self.review_frame); review_bottom_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(10,0), anchor=tk.S)
        review_controls_frame = tk.Frame(review_bottom_frame) # Frame for playback/regen buttons
        review_controls_frame.pack(fill=tk.X, pady=(0,5))

        self.play_selected_button = tk.Button(review_controls_frame, text="Play Selected Line", command=self.play_selected_audio_clip)
        self.play_selected_button.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        self.regenerate_selected_button = tk.Button(review_controls_frame, text="Regenerate Selected Line", command=self.request_regenerate_selected_line)
        self.regenerate_selected_button.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        
        self.back_to_analysis_button_review = tk.Button(review_bottom_frame, text="< Back to Analysis/Voice Assignment", command=self.confirm_back_to_analysis_from_review)
        self.back_to_analysis_button_review.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
        self.assemble_audiobook_button = tk.Button(review_bottom_frame, text="Assemble Audiobook (Final Step)", command=self.start_final_assembly_process)
        self.assemble_audiobook_button.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)

        _themed_tk_buttons.extend([self.play_selected_button, self.regenerate_selected_button, self.back_to_analysis_button_review, self.assemble_audiobook_button])

    def show_wizard_view(self, resize=True):
        self.editor_frame.pack_forget(); self.analysis_frame.pack_forget(); self.review_frame.pack_forget()
        if resize: self.root.geometry("600x400")
        self.wizard_frame.pack(fill=tk.BOTH, expand=True)
        
    def show_editor_view(self, resize=True):
        if self.txt_path and self.txt_path.exists() and not self.text_editor.get("1.0", tk.END).strip():
            try:
                with open(self.txt_path, 'r', encoding='utf-8') as f: content = f.read()
                self.text_editor.delete('1.0', tk.END); self.text_editor.insert('1.0', content)
            except Exception as e:
                self.show_status_message(f"Error: Could not load text for editing. Error: {e}", "error")
                # messagebox.showerror("Error Reading File", f"Could not load text.\n\nError: {e}")

        self.wizard_frame.pack_forget(); self.analysis_frame.pack_forget(); self.review_frame.pack_forget()
        if resize: self.root.geometry("800x700")
        self.editor_frame.pack(fill=tk.BOTH, expand=True)
        
    def show_analysis_view(self):
        self.editor_frame.pack_forget(); self.wizard_frame.pack_forget()
        self.root.geometry("800x700")
        self.analysis_frame.pack(fill=tk.BOTH, expand=True)

    def show_review_view(self):
        self.wizard_frame.pack_forget(); self.editor_frame.pack_forget(); self.analysis_frame.pack_forget()
        self.root.geometry("900x700") # Potentially wider for review tree
        self.review_frame.pack(fill=tk.BOTH, expand=True)
        self.populate_review_tree()

    def sanitize_for_tts(self, text):
        text = re.sub(r'\[.*?\]', '', text); text = re.sub(r'\(.*?\)', '', text)
        text = text.replace('*', ''); text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def update_timer(self):
        self.timer_seconds += 1; self.status_label.config(text=f"Working... Please wait. ({self.timer_seconds}s elapsed)")
        self.timer_id = self.root.after(1000, self.update_timer)
        
    def start_progress_indicator(self, status_text="Working..."):
        self.set_ui_state(tk.DISABLED); self.progressbar.pack(fill=tk.X, padx=5, pady=(0,5), expand=True); self.progressbar.start()
        self.timer_seconds = 0; self.status_label.config(text=status_text); self.update_timer()

    def stop_progress_indicator(self):
        if self.timer_id: self.root.after_cancel(self.timer_id); self.timer_id = None
        self.progressbar.stop(); self.progressbar.pack_forget(); self.status_label.config(text="")

    def start_conversion_process(self):
        if not self.logic.find_calibre_executable():
            self.show_status_message("Error: Calibre's 'ebook-convert.exe' not found. Conversion disabled.", "error")
            return # messagebox.showerror("Calibre Not Found", "Could not find Calibre's 'ebook-convert.exe'.")
        self.start_progress_indicator("Converting, please wait...")
        self.last_operation = 'conversion'
        self.active_thread = threading.Thread(target=self.logic.run_calibre_conversion); self.active_thread.daemon = True; self.active_thread.start()
        self.root.after(100, self.check_update_queue) # Use queue for completion

    def on_analysis_complete(self):
        self.set_ui_state(tk.NORMAL)
        if not self.analysis_result: return
        c = self._theme_colors # Get current theme colors
        self.tree.delete(*self.tree.get_children()); self.cast_tree.delete(*self.cast_tree.get_children())
        for i, item in enumerate(self.analysis_result):
            speaker_color_tag = self.get_speaker_color_tag(item.get('speaker', 'N/A'))
            row_tags = (speaker_color_tag, 'evenrow' if i % 2 == 0 else 'oddrow')
            self.tree.insert('', tk.END, values=(item.get('speaker', 'N/A'), item.get('line', 'N/A')), tags=row_tags)
        self.update_cast_list(); self.show_analysis_view()
        self.show_status_message("Pass 1 Complete! Review the results and assign voices.", "success")

    def rename_speaker(self):
        try:
            selected_item_id = self.cast_tree.selection()[0]; original_name = self.cast_tree.item(selected_item_id, 'values')[0]
        except IndexError:
            self.show_status_message("Please select a speaker from the cast list to rename.", "warning")
            return # messagebox.showwarning("No Selection", "Please select a speaker from the cast list to rename.")
        new_name = simpledialog.askstring("Rename Speaker", f"Enter new name for '{original_name}':", parent=self.root)
        
        if not new_name or not new_name.strip() or new_name.strip() == original_name: return
        new_name = new_name.strip()

        # Update speaker_colors mapping
        if original_name in self.speaker_colors:
            self.speaker_colors[new_name] = self.speaker_colors.pop(original_name)
            # Re-configure the tag for the new name with the old color, or get new if it was a merge
            self.get_speaker_color_tag(new_name) 

        for item in self.analysis_result:
            if item['speaker'] == original_name: item['speaker'] = new_name
        for item_id in self.tree.get_children():
            values = self.tree.item(item_id, 'values')
            if values[0] == original_name: self.tree.item(item_id, values=(new_name, values[1]))
        if original_name in self.voice_assignments: self.voice_assignments[new_name] = self.voice_assignments.pop(original_name)
        self.on_analysis_complete() # This will re-populate tree and cast_list with new colors/tags

    def on_treeview_double_click(self, event):
        region = self.tree.identify_region(event.x, event.y);
        if region != "cell": return
        column_id = self.tree.identify_column(event.x); item_id = self.tree.identify_row(event.y)
        if column_id != '#1' or not item_id: return
        x, y, width, height = self.tree.bbox(item_id, column_id)
        try:
            current_speaker = self.tree.item(item_id, 'values')[0]
        except IndexError: # Should not happen if item_id is valid
            return

        # Style the combobox editor based on the current theme
        # This is tricky as it's a temporary widget. For now, it uses ttk defaults.
        editor = ttk.Combobox(self.tree, values=self.cast_list); editor.set(current_speaker); editor.place(x=x, y=y, width=width, height=height); editor.focus_set()
        editor.after(10, lambda: editor.event_generate('<Alt-Down>'))
        def on_edit_commit(event):
            new_value = editor.get()
            if new_value and new_value != current_speaker:
                self.tree.set(item_id, column_id, new_value)
                try:
                    all_item_ids = self.tree.get_children(''); item_index = all_item_ids.index(item_id)
                    self.analysis_result[item_index]['speaker'] = new_value
                    # Update color tag for the edited cell/row
                    speaker_color_tag = self.get_speaker_color_tag(new_value)
                    base_tags = [t for t in self.tree.item(item_id, 'tags') if t not in self.speaker_colors.keys() and not t.startswith("speaker_")] # Keep odd/even
                    self.tree.item(item_id, tags=tuple(base_tags + [speaker_color_tag]))
                except (ValueError, IndexError): print(f"Warning: Could not find item {item_id} to update master data.")
            editor.destroy()
        def on_edit_cancel(event): editor.destroy()
        editor.bind('<<ComboboxSelected>>', on_edit_commit); editor.bind('<Return>', on_edit_commit); editor.bind('<Escape>', on_edit_cancel)

    def start_hybrid_analysis(self):
        full_text = self.text_editor.get('1.0', tk.END)
        if not full_text.strip():
            self.show_status_message("Cannot analyze: Text editor is empty.", "warning")
            return # messagebox.showwarning("Empty Text", "There is no text to analyze.")

        self.start_progress_indicator("Running high-speed analysis (Pass 1)...") 
        # This will now call a method in AppLogic to start the thread
        self.logic.start_rules_pass_thread(full_text)
            
    def check_update_queue(self):
        try:
            while not self.update_queue.empty():
                update = self.update_queue.get_nowait()
                if 'error' in update:
                    self.stop_progress_indicator()
                    # For critical background errors, a messagebox might still be appropriate
                    messagebox.showerror("Background Task Error", update['error']) # Keeping this as a modal popup
                    self.set_ui_state(tk.NORMAL) # Ensure UI is re-enabled
                    self._update_wizard_button_states() # Re-apply specific button states
                    if self.last_operation == 'conversion': 
                        self.next_step_button.config(state=tk.NORMAL if self.ebook_path else tk.DISABLED, text="Convert to Text") # type: ignore
                        self.edit_text_button.config(state=tk.DISABLED)
                    elif self.last_operation in ['generation', 'assembly'] and self.post_action_var.get() != "do_nothing":
                        self.handle_post_generation_action(success=False) # Trigger post-action on critical error
                    self.last_operation = None # Clear operation on error
                    return

                if update.get('status'): # Handler for generic status updates
                    # Determine message type if possible, or default to 'info'
                    self.show_status_message(update['status'], "info")
                    # Do not return, as this might be an intermediate status

                if update.get('pass_2_resolution_started'):
                    self.set_ui_state(tk.DISABLED, exclude=[self.back_button_analysis])
                    total_items = update['total_items']
                    self.progressbar.config(mode='determinate', maximum=total_items, value=0)
                    self.progressbar.pack(fill=tk.X, padx=5, pady=(0,5), expand=True)
                    self.show_status_message(f"Resolving 0 / {total_items} speakers...", "info")
                    return

                if update.get('assembly_started'):
                    self.set_ui_state(tk.DISABLED)
                    self.progressbar.config(mode='indeterminate', value=0)
                    self.progressbar.pack(fill=tk.X, padx=5, pady=(0,5), expand=True)
                    self.progressbar.start()
                    self.show_status_message("Assembling audiobook... This may take a while.", "info")
                    self.root.update_idletasks() # Ensure UI updates before blocking thread starts
                    return
    
                if update.get('rules_pass_complete'):
                    self.analysis_result = update['results'] 
                    self.stop_progress_indicator() 
                    self.on_analysis_complete()    
                    self.set_ui_state(tk.NORMAL)
                    self.last_operation = None # Clear after successful handling
                    return 
    
                if update.get('tts_init_complete'):
                    self.on_tts_initialization_complete()
                    self.last_operation = None # Clear after successful handling
                    return
                
                if update.get('generation_for_review_complete'):
                    self.generated_clips_info = update['clips_info']
                    self.stop_progress_indicator()
                    self.show_status_message("Audio generation complete. Ready for review.", "success")
                    self.set_ui_state(tk.NORMAL)
                    self.show_review_view() # Switch to the new review screen
                    self.last_operation = None
                    return
                if update.get('single_line_regeneration_complete'): self.on_single_line_regeneration_complete(update); return

                if update.get('assembly_complete'):
                    self.progressbar.pack_forget(); self.set_ui_state(tk.NORMAL)
                    self.show_status_message(f"Audiobook assembled successfully! Saved to: {update['final_path']}", "success")
                    # messagebox.showinfo("Success!", f"Audiobook assembled successfully!\n\nSaved to: {update['final_path']}") # Replaced
                    if self.post_action_var.get() != PostAction.DO_NOTHING:
                        self.handle_post_generation_action(success=True)
                    self.last_operation = None # Clear after successful handling
                    return

                if update.get('conversion_complete'):
                    self.txt_path = update['txt_path']
                    self.stop_progress_indicator() # Handled here now
                    self.status_label.config(text="Success! Text ready for editing.", fg=self._theme_colors.get("success_fg", "green"))
                    self.set_ui_state(tk.NORMAL) # General enable
                    self._update_wizard_button_states() # Specific enable/disable
                    self.next_step_button.config(state=tk.DISABLED, text="Conversion Complete"); self.edit_text_button.config(state=tk.NORMAL) # type: ignore
                    self.last_operation = None # Clear after successful handling
                    return
                if update.get('assembly_total_duration'): self.progressbar.config(maximum=update['assembly_total_duration'])
                elif update.get('assembly_progress'):
                    total_seconds = int(self.progressbar['maximum'] / 1000); current_seconds = int(update['assembly_progress'] / 1000) # type: ignore
                    self.progressbar.config(value=update['assembly_progress']); self.show_status_message(f"Assembling... {current_seconds}s / {total_seconds}s", "info")
                elif update.get('is_generation'):
                    total_items = self.progressbar['maximum']; items_processed = update['progress'] + 1 # type: ignore
                    self.progressbar.config(value=items_processed); self.show_status_message(f"Generating {items_processed} / {total_items} audio clips...", "info")
                elif 'progress' in update:
                    total_items = self.progressbar['maximum']; items_processed = update['progress'] + 1 # type: ignore
                    self.analysis_result[update['original_index']]['speaker'] = update['new_speaker']
                    item_id = self.tree.get_children('')[update['original_index']]; self.tree.set(item_id, '#1', update['new_speaker'])
                    # Color update handled by on_treeview_double_click or full refresh
                    self.progressbar.config(value=items_processed); self.status_label.config(text=f"Resolving {items_processed} / {total_items} speakers...")
        finally:
            if self.active_thread and self.active_thread.is_alive():
                self.root.after(100, self.check_update_queue)
            else:
                # This block runs if the active_thread has finished or was never started/died.
                # It's a fallback to ensure UI is reset if an operation completes/fails
                # without its final queue message being processed or if the queue polling stops.
                # For 'tts_init', the specific handlers (on_tts_initialization_complete or error handler)
                # are responsible for UI state, so we exclude it from this generic fallback's UI enabling.
                if self.last_operation in ['analysis', 'generation', 'assembly', 'conversion', 'rules_pass_analysis']:
                    # Ensure progress indicator is stopped and UI is enabled
                    self.logic.logger.warning(
                        f"Thread for '{self.last_operation}' finished or died without a final queue signal. "
                        f"Resetting UI as a fallback. This might indicate an issue if not an error."
                    )
                    if hasattr(self, 'progressbar') and self.progressbar.winfo_ismapped(): # Check if progressbar is visible
                        self.stop_progress_indicator()
                    self.set_ui_state(tk.NORMAL)
                    self._update_wizard_button_states() # Also apply specific states in this fallback
                    if self.last_operation in ['analysis', 'rules_pass_analysis']:
                        self.update_cast_list() 
                        self.update_treeview_item_tags(self.tree); self.update_treeview_item_tags(self.cast_tree)
                    if self.last_operation == 'analysis': 
                        self.show_status_message(f"Operation '{self.last_operation}' ended, possibly unexpectedly. UI has been reset.", "warning")
                        # messagebox.showinfo("Operation Ended", f"Operation '{self.last_operation}' ended, possibly unexpectedly. UI has been reset.")
                self.last_operation = None # Clear last_operation if thread died or after specific handling

    def start_audio_generation(self):
        if not self.analysis_result:
            self.show_status_message("Cannot generate audio: No script loaded or analyzed.", "warning")
            return # return messagebox.showwarning("No Script", "There is no script to generate audio from.")
        if not self.voices: 
            self.show_status_message("Cannot generate audio: No voices in Voice Library. Please add one.", "warning")
            return # return messagebox.showwarning("No Voices", "You must add at least one voice to the Voice Library before generating audio.")
        if not self.default_voice_info and any(item['speaker'] not in self.voice_assignments or item['speaker'].upper() in {'AMBIGUOUS', 'UNKNOWN', 'TIMED_OUT'} for item in self.analysis_result):
            self.show_status_message("Default voice needed for unassigned/unresolved lines, but none set. Please set one.", "warning")
            return # return messagebox.showwarning("Default Voice Needed", "Some lines will use the default voice, but no default voice has been set. Please set one in the 'Voice Library'.") # type: ignore

        if not self.confirm_proceed_to_tts(): return

        self.set_ui_state(tk.DISABLED, exclude=[self.back_button_analysis])
        total_lines = len([item for item in self.analysis_result if self.sanitize_for_tts(item['line'])]) # Count non-empty lines
        if total_lines == 0:
            self.show_status_message("No valid lines to generate audio for after sanitization.", "warning")
            self.set_ui_state(tk.NORMAL)
            return
        self.progressbar.config(mode='determinate', maximum=total_lines, value=0); self.progressbar.pack(fill=tk.X, padx=5, pady=(0,5), expand=True) # type: ignore
        self.show_status_message(f"Generating 0 / {total_lines} audio clips...", "info")
        self.last_operation = 'generation'
        self.active_thread = threading.Thread(target=self.logic.run_audio_generation); self.active_thread.daemon = True; self.active_thread.start()
        self.root.after(100, self.check_update_queue)
    
    def populate_review_tree(self):
        if not hasattr(self, 'review_tree'): return
        self.review_tree.delete(*self.review_tree.get_children())
        for i, clip_info in enumerate(self.generated_clips_info):
            speaker_color_tag = self.get_speaker_color_tag(clip_info['speaker'])
            row_tags = (speaker_color_tag, 'evenrow' if i % 2 == 0 else 'oddrow')
            # Use original_index for display number if available, else i+1
            line_num = clip_info.get('original_index', i) + 1 
            self.review_tree.insert('', tk.END, iid=str(clip_info['original_index']), 
                                    values=(line_num, clip_info['speaker'], clip_info['text'][:100] + "...", "Ready"), # Truncate line
                                    tags=row_tags)
        self.update_treeview_item_tags(self.review_tree)

    def play_selected_audio_clip(self):
        try:
            selected_item_id = self.review_tree.selection()[0]
            original_index = int(selected_item_id) # IID is original_index
            clip_info = next((ci for ci in self.generated_clips_info if ci['original_index'] == original_index), None)
            if clip_info and Path(clip_info['clip_path']).exists():
                self.show_status_message(f"Playing: {Path(clip_info['clip_path']).name}", "info")
                # Run playback in a thread to avoid UI freeze
                audio_segment = self.logic.load_audio_segment(clip_info['clip_path'])
                if audio_segment:
                    threading.Thread(target=pydub_play, args=(audio_segment,), daemon=True).start()
                    self.review_tree.set(selected_item_id, 'status', 'Played')
                else:
                    self.show_status_message(f"Playback Error: Could not load audio file: {clip_info['clip_path']}", "error")
                    # messagebox.showerror("Playback Error", f"Could not load audio file: {clip_info['clip_path']}")
            elif clip_info:
                self.show_status_message(f"Playback Error: Audio file not found: {clip_info['clip_path']}", "error")
                # messagebox.showerror("Playback Error", f"Audio file not found: {clip_info['clip_path']}")
        except IndexError:
            self.show_status_message("Please select a line from the review list to play.", "warning")
            # messagebox.showwarning("No Selection", "Please select a line from the review list to play.")
        except Exception as e:
            self.show_status_message(f"Playback Error: Could not play audio: {e}", "error")
            # messagebox.showerror("Playback Error", f"Could not play audio: {e}")

    def confirm_back_to_editor(self):
        if messagebox.askyesno("Confirm Navigation", "Any analysis edits will be lost. Are you sure you want to go back?"): self.show_editor_view()
        
    def confirm_proceed_to_tts(self):
        unresolved_speakers = {'AMBIGUOUS', 'UNKNOWN', 'TIMED_OUT'}
        unresolved_count = sum(1 for item in self.analysis_result if item['speaker'].upper() in unresolved_speakers)
        unassigned_speakers = {item['speaker'] for item in self.analysis_result if item['speaker'] not in self.voice_assignments}

        message = ""
        default_voice_name = self.default_voice_info['name'] if self.default_voice_info else "NOT SET"

        if unassigned_speakers or unresolved_count > 0:
            if not self.default_voice_info:
                # This case is now primarily caught by start_audio_generation's initial checks
                return False # Indicates to start_audio_generation that a pre-condition (default voice) failed
            
            if unassigned_speakers:
                message += f"The following speakers have not been assigned a voice and will use the default ('{default_voice_name}'): {', '.join(sorted(list(unassigned_speakers)))}\n\n"
            if unresolved_count > 0:
                message += f"There are {unresolved_count} unresolved lines (AMBIGUOUS, etc.). These will also use the default voice ('{default_voice_name}').\n\n"
        
        message += "Are you sure you want to proceed with audio generation?"
        
        return messagebox.askyesno("Confirm Generation", message)

    def request_regenerate_selected_line(self):
        try:
            selected_item_id = self.review_tree.selection()[0]
            original_index = int(selected_item_id)
            clip_info = next((ci for ci in self.generated_clips_info if ci['original_index'] == original_index), None)

            if not clip_info:
                self.show_status_message("Error: Could not find clip information for selected line.", "error")
                return # return messagebox.showerror("Error", "Could not find clip information for selected line.")

            # Confirm with user
            if not messagebox.askyesno("Confirm Regeneration", f"Regenerate audio for line:\n'{clip_info['text'][:100]}...'?\n\nThis will use the voice: '{clip_info['voice_used']['name']}'."):
                return

            self.set_ui_state(tk.DISABLED, exclude=[self.back_to_analysis_button_review, self.assemble_audiobook_button]) # Keep some nav enabled
            self.show_status_message(f"Regenerating line {original_index + 1}...", "info")
            self.progressbar.config(mode='indeterminate'); self.progressbar.pack(fill=tk.X, padx=5, pady=(0,5), expand=True); self.progressbar.start()

            self.last_operation = 'regeneration' # For error handling or UI state
            # Call logic method in a thread
            self.active_thread = threading.Thread(target=self.logic.start_single_line_regeneration_thread, 
                                                  args=(clip_info, clip_info['voice_used']), daemon=True)
            self.active_thread.start()
            self.root.after(100, self.check_update_queue)
        except IndexError:
            self.show_status_message("Please select a line from the review list to regenerate.", "warning")
            # messagebox.showwarning("No Selection", "Please select a line from the review list to regenerate.")
        except Exception as e:
            self.show_status_message(f"Regeneration Error: {e}", "error")
            # messagebox.showerror("Regeneration Error", f"An error occurred: {e}")
            self.stop_progress_indicator()
            self.set_ui_state(tk.NORMAL)

    def on_single_line_regeneration_complete(self, update_data):
        self.stop_progress_indicator()
        self.set_ui_state(tk.NORMAL)
        original_index = update_data['original_index']
        # Update the clip_path in self.generated_clips_info
        for info in self.generated_clips_info:
            if info['original_index'] == original_index: info['clip_path'] = update_data['new_clip_path']; break
        self.review_tree.set(str(original_index), 'status', 'Regenerated')
        self.show_status_message(f"Line {original_index + 1} regenerated successfully.", "success")

    def upload_ebook(self):
        filepath_str = filedialog.askopenfilename(title="Select an Ebook File", filetypes=[("Ebook Files", "*.epub *.mobi *.pdf *.azw3"), ("All Files", "*.*")])
        if filepath_str: self.logic.process_ebook_path(filepath_str)

    def handle_drop(self, event):
        filepath_str = event.data.strip('{}'); self.logic.process_ebook_path(filepath_str)
        
    def save_edited_text(self):
        if not self.txt_path:
            self.show_status_message("Error: No text file path is set. Cannot save.", "error")
            return # return messagebox.showerror("Error", "No text file path is set.")
        try:
            with open(self.txt_path, 'w', encoding='utf-8') as f: f.write(self.text_editor.get('1.0', tk.END))
            self.show_status_message("Changes have been saved successfully.", "success")
            # messagebox.showinfo("Success", f"Changes have been saved.")
        except Exception as e:
            self.show_status_message(f"Save Error: Could not save changes. Error: {e}", "error")
            # messagebox.showerror("Save Error", f"Could not save changes.\n\nError: {e}")

    def apply_standard_tk_styles(self):
        """Applies theme to standard Tkinter widgets."""
        c = self._theme_colors
        
        # Frames
        frames_to_style = [ # Add new frames here
            self.content_frame, self.status_frame, self.wizard_frame, self.editor_frame, 
            self.analysis_frame, self.upload_frame, self.editor_button_frame,
            self.analysis_top_frame, self.analysis_main_panels_frame, 
            self.analysis_bottom_frame, self.cast_list_outer_frame, self.results_frame,
            self.review_frame # Add review_frame and its sub-frames if any
        ]
        for frame in frames_to_style:
            if frame: frame.config(background=c["frame_bg"])

        # Labels
        for label in _themed_tk_labels:
            if label:
                # Special handling for status_label's dynamic color is in update_status_label_color
                if label == self.status_label:
                    label.config(background=c["frame_bg"]) # update_status_label_color handles fg
                elif hasattr(self, 'drop_info_label') and label == self.drop_info_label: # Special grey color
                     label.config(background=c["frame_bg"], foreground="#808080" if c == LIGHT_THEME else "#A0A0A0")
                else:
                    label.config(background=c["frame_bg"], foreground=c["fg"])
        
        # Buttons (standard tk.Button)
        for button in _themed_tk_buttons:
            if button:
                button.config(
                    background=c["button_bg"], foreground=c["button_fg"],
                    activebackground=c["button_active_bg"], activeforeground=c["button_fg"],
                    disabledforeground=c["disabled_fg"]
                )
        
        # LabelFrames (standard tk.LabelFrame)
        for labelframe in _themed_tk_labelframes:
            if labelframe:
                labelframe.config(background=c["frame_bg"], foreground=c["labelframe_fg"])
                # Children of LabelFrames (like internal labels)
                for child in labelframe.winfo_children():
                    if isinstance(child, tk.Label):
                        child.config(background=c["frame_bg"], foreground=c["fg"])
                    # Buttons inside are ttk, handled separately

    def apply_ttk_styles(self):
        """Applies theme to TTK widgets using ttk.Style."""
        style = ttk.Style(self.root)
        c = self._theme_colors

        # Configure a base theme if desired, e.g., 'clam', 'alt'
        style.theme_use('clam') 

        style.configure(".", background=c["bg"], foreground=c["fg"], fieldbackground=c["text_bg"])
        style.map(".",
                  background=[('disabled', c["frame_bg"]), ('active', c["button_active_bg"])],
                  foreground=[('disabled', c["disabled_fg"])])

        style.configure("TFrame", background=c["frame_bg"])
        style.configure("TLabel", background=c["frame_bg"], foreground=c["fg"])
        
        # Note: Standard tk.Buttons are styled in apply_standard_tk_styles.
        # If you switch to ttk.Button, style "TButton" here.

        style.configure("Treeview", background=c["text_bg"], foreground=c["text_fg"], fieldbackground=c["text_bg"])
        style.map("Treeview", background=[('selected', c["select_bg"])], foreground=[('selected', c["select_fg"])])
        style.configure("Treeview.Heading", background=c["tree_heading_bg"], foreground=c["fg"], relief=tk.FLAT)
        style.map("Treeview.Heading", background=[('active', c["button_active_bg"])])

        style.configure("TCombobox", fieldbackground=c["text_bg"], background=c["button_bg"], foreground=c["text_fg"],
                        selectbackground=c["select_bg"], selectforeground=c["select_fg"], insertcolor=c["cursor_color"],
                        arrowcolor=c["fg"])
        style.map("TCombobox",
                  fieldbackground=[('readonly', c["text_bg"]), ('disabled', c["frame_bg"])],
                  foreground=[('disabled', c["disabled_fg"])],
                  arrowcolor=[('disabled', c["disabled_fg"])])
        
        self.root.option_add("*TCombobox*Listbox.background", c["text_bg"])
        self.root.option_add("*TCombobox*Listbox.foreground", c["text_fg"])
        self.root.option_add("*TCombobox*Listbox.selectBackground", c["select_bg"])
        self.root.option_add("*TCombobox*Listbox.selectForeground", c["select_fg"])

        style.configure("TProgressbar", troughcolor=c["progressbar_trough"], background=c["progressbar_bar"], thickness=15)
        style.configure("Horizontal.TProgressbar", troughcolor=c["progressbar_trough"], background=c["progressbar_bar"], thickness=15)
        style.configure("Vertical.TProgressbar", troughcolor=c["progressbar_trough"], background=c["progressbar_bar"], thickness=15)
        
        # Explicitly apply to the instance if general styling isn't enough (might be redundant but can help)
        if hasattr(self, 'progressbar'):
             self.progressbar.configure(style="Horizontal.TProgressbar")


        style.configure("TScrollbar", background=c["scrollbar_bg"], troughcolor=c["scrollbar_trough"], relief=tk.FLAT, arrowcolor=c["fg"])
        style.map("TScrollbar", background=[('active', c["button_active_bg"])])
        
        # For ttk.LabelFrame if used (currently using tk.LabelFrame)
        # style.configure("TLabelFrame", background=c["frame_bg"], relief=tk.GROOVE)
        # style.configure("TLabelFrame.Label", background=c["frame_bg"], foreground=c["fg"])

    def update_treeview_item_tags(self, treeview_widget):
        if not treeview_widget or not self._theme_colors: return
        c = self._theme_colors
        treeview_widget.tag_configure('oddrow', background=c["tree_odd_row_bg"])
        treeview_widget.tag_configure('evenrow', background=c["tree_even_row_bg"])

        # Ensure speaker color tags are configured (might be redundant if get_speaker_color_tag does it)
        for speaker, color in self.speaker_colors.items():
            tag_name = f"speaker_{re.sub(r'[^a-zA-Z0-9_]', '', speaker)}"
            treeview_widget.tag_configure(tag_name, foreground=color)

        children = treeview_widget.get_children('')
        for i, item_id in enumerate(children):
            current_tags = list(treeview_widget.item(item_id, 'tags'))
             # Add or update odd/even tags, keep speaker tags
            current_tags = [t for t in current_tags if not t.startswith('speaker_') and t not in ('oddrow', 'evenrow')]
            current_tags.append('evenrow' if i % 2 == 0 else 'oddrow') # Add odd/even
            # Re-fetch speaker tag from values if necessary, or assume it's already in current_tags if applied during insert
            try:
                speaker_val = treeview_widget.item(item_id, 'values')[0 if treeview_widget == self.cast_tree else (1 if treeview_widget == self.review_tree else 0)] # Speaker column index
                speaker_color_tag = self.get_speaker_color_tag(speaker_val) # Ensures tag is configured
                if speaker_color_tag not in current_tags: current_tags.append(speaker_color_tag)
            except (IndexError, tk.TclError): pass # In case values are not as expected or item is gone
            treeview_widget.item(item_id, tags=tuple(current_tags))

    def update_status_label_color(self):
        if not hasattr(self, 'status_label') or not self._theme_colors: return
        c = self._theme_colors
        current_text = self.status_label.cget("text")
        current_fg_str = str(self.status_label.cget("fg")) # Ensure it's a string for comparison

        # Determine if current color is one of the special state colors from ANY theme
        is_error = current_fg_str == LIGHT_THEME["error_fg"] or current_fg_str == DARK_THEME["error_fg"]
        is_success = current_fg_str == LIGHT_THEME["success_fg"] or current_fg_str == DARK_THEME["success_fg"]

        if "error" in current_text.lower() or "fail" in current_text.lower() or is_error:
            self.status_label.config(foreground=c["error_fg"])
        elif "success" in current_text.lower() or "complete" in current_text.lower() or is_success:
            self.status_label.config(foreground=c["success_fg"])
        else:
            self.status_label.config(foreground=c["status_fg"])
        self.status_label.config(background=c["frame_bg"])

    def save_voice_config(self):
        config_path = self.output_dir / "voices_config.json"
        
        # Filter self.voices to only include user-added voices (those with actual file paths)
        # Internal engine voices have special paths like '_XTTS_INTERNAL_VOICE_'
        user_added_voices_to_save = [
            v for v in self.voices if Path(v['path']).is_file()
        ]

        config_data = {
            "voices": user_added_voices_to_save,
            "default_voice_name": self.default_voice_info['name'] if self.default_voice_info else None
        }
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=4)
            print(f"Voice configuration saved to {config_path}")
        except Exception as e:
            print(f"Error saving voice configuration: {e}")

    def load_voice_config(self):
        config_path = self.output_dir / "voices_config.json"
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)
                
                # Load only user-added voices from the JSON
                self.voices = config_data.get("voices", []) 
                
                # Store the name of the default voice from config.
                # self.default_voice_info itself will be fully resolved after engine init.
                self.loaded_default_voice_name_from_config = config_data.get("default_voice_name")

                if self.loaded_default_voice_name_from_config:
                    # Attempt to find it among user-added voices for now
                    self.default_voice_info = next((v for v in self.voices if v['name'] == self.loaded_default_voice_name_from_config), None)
                else:
                    self.default_voice_info = None # Explicitly None if no default name in config
                self.logic.logger.info(f"Voice configuration loaded from {config_path}. Found {len(self.voices)} user-added voices. Saved default name: {self.loaded_default_voice_name_from_config or 'None'}.")
            except Exception as e:
                print(f"Error loading voice configuration: {e}. Starting with empty voice list.")
                self.voices = []
                self.default_voice_info = None
                self.loaded_default_voice_name_from_config = None

    def handle_post_generation_action(self, success):
        action = self.post_action_var.get()
        if action == PostAction.DO_NOTHING:
            return

        action_word_map = {PostAction.SLEEP: "sleep", PostAction.SHUTDOWN: "shut down", PostAction.QUIT: "quit program"}
        action_desc = action_word_map.get(action, "perform an action")
        
        outcome_message = "completed successfully" if success else "failed with errors (check log)"
        dialog_message = f"Audiobook generation has {outcome_message}.\n\nDo you want to proceed with system {action_desc}?"
        dialog_title = f"Confirm {action_desc.title()}"
        countdown_seconds = 15 # Increased delay

        def perform_actual_action_callback(confirmed):
            if confirmed:
                self.logic.logger.info(f"User confirmed post-generation action: {action}")
                if action == PostAction.QUIT:
                    self.logic.logger.info("Quitting application as per post-action.")
                    self.root.quit() 
                elif action in [PostAction.SLEEP, PostAction.SHUTDOWN]:
                    self.logic.perform_system_action(action, success)
                # Optionally reset post_action_var to PostAction.DO_NOTHING after action is taken or confirmed
                # self.post_action_var.set(PostAction.DO_NOTHING)
            else:
                self.logic.logger.info(f"User cancelled post-generation action: {action}")
                self.status_label.config(text=f"Post-generation action ({action_desc}) cancelled by user.", 
                                         fg=self._theme_colors.get("status_fg", "blue"))
        # Ensure _theme_colors is populated before calling ConfirmationDialog
        ConfirmationDialog(self.root, dialog_title, dialog_message, countdown_seconds, perform_actual_action_callback, self._theme_colors if self._theme_colors else LIGHT_THEME)

    def confirm_back_to_analysis_from_review(self):
        if messagebox.askyesno("Confirm Navigation", "Going back will discard current generated audio clips. You'll need to regenerate them. Are you sure?"):
            self.generated_clips_info = [] # Clear generated clips
            self.review_tree.delete(*self.review_tree.get_children()) # Clear review tree
            self.show_analysis_view()

    def start_final_assembly_process(self):
        if not self.generated_clips_info:
            self.show_status_message("No audio clips available to assemble.", "warning")
            return # return messagebox.showwarning("No Audio", "No audio clips have been generated or retained for assembly.")
        self.show_status_message("Preparing for final assembly...", "info")
        # self.logic.start_assembly now takes self.generated_clips_info implicitly via self.ui
        self.logic.start_assembly(self.generated_clips_info) # Pass the list of clips

class ConfirmationDialog(tk.Toplevel):
    def __init__(self, parent, title, message, countdown_seconds, action_callback, theme_colors):
        super().__init__(parent)
        self.transient(parent)
        self.title(title)
        self.action_callback = action_callback
        self.countdown_remaining = countdown_seconds
        self.grab_set() # Make modal
        self.theme_colors = theme_colors # Store the passed theme colors

        bg_color = self.theme_colors.get("frame_bg", "#F0F0F0")
        fg_color = self.theme_colors.get("fg", "#000000")
        button_bg = self.theme_colors.get("button_bg", "#D9D9D9")
        self.config(bg=bg_color)

        main_frame = tk.Frame(self, bg=bg_color, padx=20, pady=20)
        main_frame.pack(expand=True, fill=tk.BOTH)

        self.message_label = tk.Label(main_frame, text=message, wraplength=350, justify=tk.CENTER, bg=bg_color, fg=fg_color)
        self.message_label.pack(pady=(0, 10))

        self.countdown_label = tk.Label(main_frame, text=f"Action in {self.countdown_remaining}s", font=("Helvetica", 10, "italic"), bg=bg_color, fg=fg_color)
        self.countdown_label.pack(pady=(0, 15))

        button_frame = tk.Frame(main_frame, bg=bg_color)
        button_frame.pack()

        self.proceed_button = tk.Button(button_frame, text="Proceed Now", command=self._proceed, bg=button_bg, fg=fg_color, activebackground=self.theme_colors.get("button_active_bg", "#C0C0C0"))
        self.proceed_button.pack(side=tk.LEFT, padx=10)

        self.cancel_button = tk.Button(button_frame, text="Cancel", command=self._cancel, bg=button_bg, fg=fg_color, activebackground=self.theme_colors.get("button_active_bg", "#C0C0C0"))
        self.cancel_button.pack(side=tk.LEFT, padx=10)

        self.protocol("WM_DELETE_WINDOW", self._cancel) 
        self.geometry(f"+{parent.winfo_rootx()+int(parent.winfo_width()/2 - 200)}+{parent.winfo_rooty()+int(parent.winfo_height()/2 - 100)}") # Center on parent
        self._update_countdown()

    def _update_countdown(self):
        if self.countdown_remaining > 0:
            self.countdown_label.config(text=f"Action in {self.countdown_remaining}s")
            self.countdown_remaining -= 1
            self.timer_id = self.after(1000, self._update_countdown)
        else:
            self.countdown_label.config(text="Proceeding...")
            self._proceed() 

    def _proceed(self):
        if hasattr(self, 'timer_id'): self.after_cancel(self.timer_id)
        self.destroy()
        self.action_callback(True)

    def _cancel(self):
        if hasattr(self, 'timer_id'): self.after_cancel(self.timer_id)
        self.destroy()
        self.action_callback(False)
