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
        self.theme_var = tk.StringVar(value=self.current_theme_name)
        self.post_action_var = tk.StringVar(value="do_nothing") # "do_nothing", "sleep", "shutdown", "quit"

        self.analysis_result = [] # Stores results from text analysis
        
        # TTS Engine and Voice Data (will be populated by the logic class)
        self.tts_engine = None
        self.voices = [] # This will now be a list of dicts: [{'name': str, 'path': str}]
        self.default_voice_info = None # Stores the dict {'name': str, 'path': str} for the default voice
        self.voice_assignments = {} # Maps speaker name to a voice dict
        
        # Create an instance of the logic class, passing a reference to self
        self.logic = AppLogic(self)
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
        
        # Create all widgets first
        self.create_wizard_widgets()
        self.create_editor_widgets()
        self.create_analysis_widgets()
        
        # Then initialize theming (which might apply theme if system theme changed during detection)
        self.initialize_theming() 
        self.create_menubar()     # Menubar uses theme_var, so initialize_theming should come first

        # Explicitly apply the theme based on current settings after all setup
        self.apply_theme_settings() 
        # Schedule TTS initialization with UI feedback
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

        post_actions_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Post-Actions", menu=post_actions_menu)
        post_actions_menu.add_radiobutton(label="Do Nothing", variable=self.post_action_var, value="do_nothing")
        post_actions_menu.add_radiobutton(label="Sleep on Finish", variable=self.post_action_var, value="sleep")
        post_actions_menu.add_radiobutton(label="Shutdown on Finish", variable=self.post_action_var, value="shutdown")
        post_actions_menu.add_radiobutton(label="Quit Program on Finish", variable=self.post_action_var, value="quit")


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
            assigned_voice_name = "Not Assigned"
            if speaker in self.voice_assignments:
                # We now store the whole dict, so get the name from it
                assigned_voice_name = self.voice_assignments[speaker]['name']
            self.cast_tree.insert('', tk.END, iid=speaker, values=(speaker, assigned_voice_name))
        
        if selected_item:
            try: 
                if self.cast_tree.exists(selected_item[0]): self.cast_tree.selection_set(selected_item)
            except tk.TclError: pass

    # --- UPDATED METHOD ---
    def on_tts_initialization_complete(self):
        self.stop_progress_indicator() # Stop indicator on successful completion
        self.status_label.config(text="TTS engine initialized successfully.")
        self.update_voice_dropdown() # Will be empty initially
        self.default_voice_label.config(text="Default: None") # Initialize label
        self.set_ui_state(tk.NORMAL) # Enable general UI elements

        # After TTS engine is ready, and after attempting to load config,
        # add its internal voice if no voices (user-added or loaded) exist.
        # Also, ensure a default voice is set.
        if self.tts_engine:
            internal_xtts_voice = {'name': "Default XTTS Voice", 'path': '_XTTS_INTERNAL_VOICE_'}
            # Ensure internal voice is in the list if it's the default or no other voices exist
            if not self.voices or (self.default_voice_info and self.default_voice_info['path'] == '_XTTS_INTERNAL_VOICE_' and not any(v['path'] == '_XTTS_INTERNAL_VOICE_' for v in self.voices)):
                if not any(v['path'] == '_XTTS_INTERNAL_VOICE_' for v in self.voices):
                    self.voices.append(internal_xtts_voice)
            
            if not self.default_voice_info and internal_xtts_voice in self.voices:
                self.default_voice_info = internal_xtts_voice
                self.default_voice_label.config(text=f"Default: {internal_xtts_voice['name']}")
                self.save_voice_config() # Save if we just set the internal as default

        self.update_voice_dropdown() # Ensure dropdown is populated, now potentially with internal voice

        # Set specific button states BEFORE showing the modal messagebox
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
        
        self.update_status_label_color() # Ensure status label uses themed color
        messagebox.showinfo("TTS Ready", "Coqui TTS Engine is ready.\n\nPlease add your voices using the 'Add New Voice' button before generating the audiobook.")

    def set_ui_state(self, state, exclude=None):
        if exclude is None: exclude = []
        widgets_to_toggle = [
            self.upload_button, self.next_step_button, self.edit_text_button, 
            self.save_button, self.back_button_editor, self.analyze_button, 
            self.back_button_analysis, self.tts_button, self.text_editor, self.tree, # Added self.tree
            self.resolve_button, self.cast_tree, self.rename_button, self.add_voice_button, # Added self.rename_button
            self.set_default_voice_button, self.voice_dropdown, self.assign_button # Added self.assign_button
        ]
        for widget in widgets_to_toggle:
            if widget and widget not in exclude:
                try: widget.config(state=state)
                except (tk.TclError, AttributeError): pass
        
        # Only change cursor if colors are available (theme applied)
        if self._theme_colors:
            self.root.config(cursor="watch" if state == tk.DISABLED else "")


    # --- Other methods are unchanged, but included for completeness ---
    
    def show_wizard_view(self, resize=True):
        self.editor_frame.pack_forget(); self.analysis_frame.pack_forget()
        if resize: self.root.geometry("600x400")
        self.wizard_frame.pack(fill=tk.BOTH, expand=True)
        
    def show_editor_view(self, resize=True):
        if self.txt_path and self.txt_path.exists() and not self.text_editor.get("1.0", tk.END).strip():
            try:
                with open(self.txt_path, 'r', encoding='utf-8') as f: content = f.read()
                self.text_editor.delete('1.0', tk.END); self.text_editor.insert('1.0', content)
            except Exception as e: messagebox.showerror("Error Reading File", f"Could not load text.\n\nError: {e}")
        self.wizard_frame.pack_forget(); self.analysis_frame.pack_forget()
        if resize: self.root.geometry("800x700")
        self.editor_frame.pack(fill=tk.BOTH, expand=True)
        
    def show_analysis_view(self):
        self.editor_frame.pack_forget(); self.wizard_frame.pack_forget()
        self.root.geometry("800x700")
        self.analysis_frame.pack(fill=tk.BOTH, expand=True)
        
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
            messagebox.showerror("Calibre Not Found", "Could not find Calibre's 'ebook-convert.exe'.")
            return
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
            tags = ('evenrow',) if i % 2 == 0 else ('oddrow',)
            self.tree.insert('', tk.END, values=(item.get('speaker', 'N/A'), item.get('line', 'N/A')), tags=tags)
        self.update_cast_list(); self.show_analysis_view()
        self.status_label.config(text="Pass 1 Complete! Review the results.", fg=self._theme_colors.get("success_fg", "green"))

    def rename_speaker(self):
        try:
            selected_item_id = self.cast_tree.selection()[0]; original_name = self.cast_tree.item(selected_item_id, 'values')[0]
        except IndexError: return messagebox.showwarning("No Selection", "Please select a speaker from the cast list to rename.")
        new_name = simpledialog.askstring("Rename Speaker", f"Enter new name for '{original_name}':", parent=self.root)
        if not new_name or not new_name.strip() or new_name.strip() == original_name: return
        new_name = new_name.strip()
        for item in self.analysis_result:
            if item['speaker'] == original_name: item['speaker'] = new_name
        for item_id in self.tree.get_children():
            values = self.tree.item(item_id, 'values')
            if values[0] == original_name: self.tree.item(item_id, values=(new_name, values[1]))
        if original_name in self.voice_assignments: self.voice_assignments[new_name] = self.voice_assignments.pop(original_name)
        self.update_cast_list()
        self.update_treeview_item_tags(self.tree) # Re-apply tags after modification

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
                    # self.update_treeview_item_tags(self.tree) # Update row colors if needed - can be slow if many edits
                    # Consider a bulk update or update on view change if performance is an issue
                except (ValueError, IndexError): print(f"Warning: Could not find item {item_id} to update master data.")
            editor.destroy()
        def on_edit_cancel(event): editor.destroy()
        editor.bind('<<ComboboxSelected>>', on_edit_commit); editor.bind('<Return>', on_edit_commit); editor.bind('<Escape>', on_edit_cancel)

    def start_hybrid_analysis(self):
        full_text = self.text_editor.get('1.0', tk.END)
        if not full_text.strip():
            messagebox.showwarning("Empty Text", "There is no text to analyze.")
            return

        self.start_progress_indicator("Running high-speed analysis (Pass 1)...") 
        # This will now call a method in AppLogic to start the thread
        self.logic.start_rules_pass_thread(full_text)
            
    def check_update_queue(self):
        try:
            while not self.update_queue.empty():
                update = self.update_queue.get_nowait()
                if 'error' in update:
                    self.stop_progress_indicator()
                    messagebox.showerror("Background Task Error", update['error'])
                    self.set_ui_state(tk.NORMAL)
                    if self.last_operation == 'conversion': 
                        self.next_step_button.config(state=tk.NORMAL if self.ebook_path else tk.DISABLED, text="Convert to Text")
                        self.edit_text_button.config(state=tk.DISABLED)
                    elif self.last_operation in ['generation', 'assembly'] and self.post_action_var.get() != "do_nothing":
                        self.handle_post_generation_action(success=False) # Trigger post-action on critical error
                    self.last_operation = None # Clear operation on error
                    return

                if update.get('status'): # Handler for generic status updates
                    self.status_label.config(text=update['status'], fg=self._theme_colors.get("status_fg", "blue"))
                    self.update_status_label_color() # Ensure correct theme color
                    # Do not return, as this might be an intermediate status

                if update.get('pass_2_resolution_started'):
                    self.set_ui_state(tk.DISABLED, exclude=[self.back_button_analysis])
                    total_items = update['total_items']
                    self.progressbar.config(mode='determinate', maximum=total_items, value=0)
                    self.progressbar.pack(fill=tk.X, padx=5, pady=(0,5), expand=True)
                    self.status_label.config(text=f"Resolving 0 / {total_items} speakers...")
                    return

                if update.get('assembly_started'):
                    self.set_ui_state(tk.DISABLED)
                    self.progressbar.config(mode='indeterminate', value=0)
                    self.progressbar.pack(fill=tk.X, padx=5, pady=(0,5), expand=True)
                    self.progressbar.start()
                    self.status_label.config(text="Assembling audiobook... This may take a while.")
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
                
                if update.get('generation_complete'): self.logic.on_audio_generation_complete(update['clips_dir']); return
                
                if update.get('assembly_complete'):
                    self.status_label.config(text="Assembly Complete!"); self.progressbar.pack_forget(); self.set_ui_state(tk.NORMAL)
                    messagebox.showinfo("Success!", f"Audiobook assembled successfully!\n\nSaved to: {update['final_path']}") # Show before dialog
                    if self.post_action_var.get() != "do_nothing":
                        self.handle_post_generation_action(success=True)
                    self.last_operation = None # Clear after successful handling
                    return
                
                if update.get('conversion_complete'):
                    self.txt_path = update['txt_path']
                    self.stop_progress_indicator() # Handled here now
                    self.status_label.config(text="Success! Text ready for editing.", fg=self._theme_colors.get("success_fg", "green"))
                    self.set_ui_state(tk.NORMAL)
                    self.next_step_button.config(state=tk.DISABLED, text="Conversion Complete"); self.edit_text_button.config(state=tk.NORMAL)
                    self.last_operation = None # Clear after successful handling
                    return
                if update.get('assembly_total_duration'): self.progressbar.config(maximum=update['assembly_total_duration'])
                elif update.get('assembly_progress'):
                    total_seconds = int(self.progressbar['maximum'] / 1000); current_seconds = int(update['assembly_progress'] / 1000)
                    self.progressbar.config(value=update['assembly_progress']); self.status_label.config(text=f"Assembling... {current_seconds}s / {total_seconds}s")
                elif update.get('is_generation'):
                    total_items = self.progressbar['maximum']; items_processed = update['progress'] + 1
                    self.progressbar.config(value=items_processed); self.status_label.config(text=f"Generating {items_processed} / {total_items} audio clips...")
                elif 'progress' in update:
                    total_items = self.progressbar['maximum']; items_processed = update['progress'] + 1
                    self.analysis_result[update['original_index']]['speaker'] = update['new_speaker']
                    item_id = self.tree.get_children('')[update['original_index']]; self.tree.set(item_id, '#1', update['new_speaker'])
                    # self.update_treeview_item_tags(self.tree) # Could update here, but might be too frequent
                    self.progressbar.config(value=items_processed); self.status_label.config(text=f"Resolving {items_processed} / {total_items} speakers...")
        finally:
            if self.active_thread and self.active_thread.is_alive():
                self.root.after(100, self.check_update_queue)
            else:
                # This block runs if the active_thread has finished or was never started/died.
                # It's a fallback to ensure UI is reset if an operation completes/fails
                # without its final queue message being processed or if the queue polling stops.
                if self.last_operation in ['analysis', 'tts_init', 'generation', 'assembly', 'conversion', 'rules_pass_analysis']:
                    # Ensure progress indicator is stopped and UI is enabled
                    if self.progressbar.winfo_ismapped(): # Check if progressbar is visible
                        self.stop_progress_indicator()
                    self.set_ui_state(tk.NORMAL)
                    if self.last_operation in ['analysis', 'rules_pass_analysis']:
                        self.update_cast_list() 
                        self.update_treeview_item_tags(self.tree); self.update_treeview_item_tags(self.cast_tree)
                    if self.last_operation == 'analysis': # 'analysis' here refers to the LLM pass (Pass 2)
                        messagebox.showinfo("Complete", "Pass 2 (LLM) resolution is complete.")
                self.last_operation = None # Clear last_operation after handling

    def start_audio_generation(self):
        if not self.analysis_result: return messagebox.showwarning("No Script", "There is no script to generate audio from.")
        if not self.voices: 
            return messagebox.showwarning("No Voices", "You must add at least one voice to the Voice Library before generating audio.")
        if not self.default_voice_info and any(item['speaker'] not in self.voice_assignments or item['speaker'].upper() in {'AMBIGUOUS', 'UNKNOWN', 'TIMED_OUT'} for item in self.analysis_result):
            return messagebox.showwarning("Default Voice Needed", "Some lines will use the default voice, but no default voice has been set. Please set one in the 'Voice Library'.")

        if not self.confirm_proceed_to_tts(): return
        self.set_ui_state(tk.DISABLED, exclude=[self.back_button_analysis])
        total_lines = len(self.analysis_result)
        self.progressbar.config(mode='determinate', maximum=total_lines, value=0); self.progressbar.pack(fill=tk.X, padx=5, pady=(0,5), expand=True)
        self.status_label.config(text=f"Generating 0 / {total_lines} audio clips...")
        self.last_operation = 'generation'
        self.active_thread = threading.Thread(target=self.logic.run_audio_generation); self.active_thread.daemon = True; self.active_thread.start()
        self.root.after(100, self.check_update_queue)
    
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
                # This case is now caught by start_audio_generation, but as a fallback:
                return messagebox.showerror("Error", "A default voice is needed for unassigned/unresolved lines, but no default voice is set.")
            
            if unassigned_speakers:
                message += f"The following speakers have not been assigned a voice and will use the default ('{default_voice_name}'): {', '.join(sorted(list(unassigned_speakers)))}\n\n"
            if unresolved_count > 0:
                message += f"There are {unresolved_count} unresolved lines (AMBIGUOUS, etc.). These will also use the default voice ('{default_voice_name}').\n\n"
        
        message += "Are you sure you want to proceed with audio generation?"
        
        return messagebox.askyesno("Confirm Generation", message)

    def upload_ebook(self):
        filepath_str = filedialog.askopenfilename(title="Select an Ebook File", filetypes=[("Ebook Files", "*.epub *.mobi *.pdf *.azw3"), ("All Files", "*.*")])
        if filepath_str: self.logic.process_ebook_path(filepath_str)

    def handle_drop(self, event):
        filepath_str = event.data.strip('{}'); self.logic.process_ebook_path(filepath_str)
        
    def save_edited_text(self):
        if not self.txt_path: return messagebox.showerror("Error", "No text file path is set.")
        try:
            with open(self.txt_path, 'w', encoding='utf-8') as f: f.write(self.text_editor.get('1.0', tk.END))
            messagebox.showinfo("Success", f"Changes have been saved.")
        except Exception as e: messagebox.showerror("Save Error", f"Could not save changes.\n\nError: {e}")

    def apply_standard_tk_styles(self):
        """Applies theme to standard Tkinter widgets."""
        c = self._theme_colors
        
        # Frames
        frames_to_style = [
            self.content_frame, self.status_frame, self.wizard_frame, self.editor_frame, 
            self.analysis_frame, self.upload_frame, self.editor_button_frame,
            self.analysis_top_frame, self.analysis_main_panels_frame, 
            self.analysis_bottom_frame, self.cast_list_outer_frame, self.results_frame
        ]
        for frame in frames_to_style:
            if frame: frame.config(background=c["frame_bg"])

        # Labels
        for label in _themed_tk_labels:
            if label:
                # Special handling for status_label's dynamic color is in update_status_label_color
                if label == self.status_label:
                    label.config(background=c["frame_bg"]) # update_status_label_color handles fg
                elif label == self.drop_info_label: # Special grey color
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
        treeview_widget.tag_configure('oddrow', background=c["tree_odd_row_bg"], foreground=c["fg"])
        treeview_widget.tag_configure('evenrow', background=c["tree_even_row_bg"], foreground=c["fg"])
        children = treeview_widget.get_children('')
        for i, item_id in enumerate(children):
            current_tags = list(treeview_widget.item(item_id, 'tags'))
            current_tags = [t for t in current_tags if t not in ('oddrow', 'evenrow')]
            current_tags.append('evenrow' if i % 2 == 0 else 'oddrow')
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
        config_data = {
            "voices": self.voices,
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
                self.voices = config_data.get("voices", [])
                default_voice_name = config_data.get("default_voice_name")
                if default_voice_name:
                    self.default_voice_info = next((v for v in self.voices if v['name'] == default_voice_name), None)
                print(f"Voice configuration loaded from {config_path}")
            except Exception as e:
                print(f"Error loading voice configuration: {e}. Starting with empty voice list.")
                self.voices = []
                self.default_voice_info = None
        # update_voice_dropdown and default_voice_label will be called later,
        # typically after TTS init or when UI is fully set up.

    def handle_post_generation_action(self, success):
        action = self.post_action_var.get()
        if action == "do_nothing":
            return

        action_word_map = {"sleep": "sleep", "shutdown": "shut down", "quit": "quit program"}
        action_desc = action_word_map.get(action, "perform an action")
        
        outcome_message = "completed successfully" if success else "failed with errors (check log)"
        dialog_message = f"Audiobook generation has {outcome_message}.\n\nDo you want to proceed with system {action_desc}?"
        dialog_title = f"Confirm {action_desc.title()}"
        countdown_seconds = 15 # Increased delay

        def perform_actual_action_callback(confirmed):
            if confirmed:
                self.logic.logger.info(f"User confirmed post-generation action: {action}")
                if action == "quit":
                    self.logic.logger.info("Quitting application as per post-action.")
                    self.root.quit() 
                elif action in ["sleep", "shutdown"]:
                    self.logic.perform_system_action(action, success)
                # Optionally reset post_action_var to "do_nothing" after action is taken or confirmed
                # self.post_action_var.set("do_nothing") 
            else:
                self.logic.logger.info(f"User cancelled post-generation action: {action}")
                self.status_label.config(text=f"Post-generation action ({action_desc}) cancelled by user.", 
                                         fg=self._theme_colors.get("status_fg", "blue"))

        ConfirmationDialog(self.root, dialog_title, dialog_message, countdown_seconds, perform_actual_action_callback, self._theme_colors)

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
