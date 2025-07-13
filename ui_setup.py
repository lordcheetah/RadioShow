# ui_setup.py
import tkinter as tk
from tkinter import ttk, simpledialog, filedialog, messagebox, scrolledtext
from pathlib import Path
import threading
import re
import queue
import shutil # For copying files
import os # For opening directory
import subprocess # For opening directory on macOS/Linux
from tkinterdnd2 import DND_FILES, TkinterDnD
import platform # For system detection
import json # For saving/loading voice config
from app_state import AppState

from pydub.playback import play as pydub_play
# Import the logic class from the other file
from dialogs import AddVoiceDialog, ConfirmationDialog
from app_logic import AppLogic
import theming # Import the new theming module
from views.wizard_view import WizardView
from views.editor_view import EditorView
from views.cast_refinement_view import CastRefinementView
from views.voice_assignment_view import VoiceAssignmentView
from views.review_view import ReviewView # Import the new ReviewView

# Constants for post-actions
class PostAction:
    DO_NOTHING = "do_nothing"
    SLEEP = "sleep"
    SHUTDOWN = "shutdown"
    QUIT = "quit"

class RadioShowApp(tk.Frame):
    def __init__(self, root):
        super().__init__(root, padx=10, pady=10)
        self.root = root
        self.pack(fill=tk.BOTH, expand=True)

        # Initialize lists for themed widgets as instance attributes
        self._themed_tk_labels = []
        self._themed_tk_buttons = []
        self._themed_tk_frames = []
        self._themed_tk_labelframes = []

        # Centralized application state
        self.state = AppState()

        self.allowed_extensions = ['.epub', '.mobi', '.pdf', '.azw3']
        self.timer_id = None
        self.timer_seconds = 0
        self.update_queue = queue.Queue()
        self.state.output_dir.mkdir(exist_ok=True)
        (self.state.output_dir / "voices").mkdir(exist_ok=True) # Ensure voices subdirectory exists

        self.current_theme_name = "system" # "light", "dark", "system"
        self.system_actual_theme = "light" # What "system" resolves to
        self._theme_colors = {}
        self.theme_var = tk.StringVar(value=self.current_theme_name) # "light", "dark", "system"
        self.selected_tts_engine_name = "Coqui XTTS" # Default, will be updated by tts_engine_var
        self.tts_engine_var = tk.StringVar(value="Coqui XTTS") # Default TTS engine
        self.post_action_var = tk.StringVar(value=PostAction.DO_NOTHING)

        self.color_palette = [ # List of visually distinct colors
            "#E6194B", "#3CB44B", "#FFE119", "#4363D8", "#F58231", "#911EB4", "#46F0F0", "#F032E6", 
            "#BCF60C", "#FABEBE", "#008080", "#E6BEFF", "#9A6324", "#FFFAC8", "#800000", "#AAFFC3", 
            "#808000", "#FFD8B1", "#000075", "#808080", "#FFFFFF", "#000000" # Added white/black for more options
        ] # Ensure good contrast with theme BG/FG
        
        # Create an instance of the logic class, passing a reference to self
        self.logic = AppLogic(self, self.state)
        # Load voice config after logic is initialized (for logging) but before UI that depends on it

        # Bind the closing event to a cleanup method
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
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
        self.wizard_view = WizardView(self.wizard_frame, self) # Instantiate WizardView
        self.editor_frame = tk.Frame(self.content_frame)
        self.editor_view = EditorView(self.editor_frame, self) # Instantiate EditorView
        self.cast_refinement_frame = tk.Frame(self.content_frame)
        self.cast_refinement_view = CastRefinementView(self.cast_refinement_frame, self)
        self.voice_assignment_frame = tk.Frame(self.content_frame)
        self.voice_assignment_view = VoiceAssignmentView(self.voice_assignment_frame, self)
        self.review_frame = tk.Frame(self.content_frame) 
        self.review_view = ReviewView(self.review_frame, self)
        
        # Register top-level frames for theming
        self._themed_tk_frames.extend([
            self, self.content_frame, self.status_frame,
            self.wizard_frame, self.editor_frame, self.cast_refinement_frame,
            self.voice_assignment_frame, self.review_frame
        ])

        # Bind Drag and Drop to the new target in WizardView
        self.wizard_view.drop_target_frame.drop_target_register(DND_FILES)
        self.wizard_view.drop_target_frame.dnd_bind('<<Drop>>', self.handle_drop)
        # Also bind to the label inside, as it can sometimes capture the drop event
        self.wizard_view.drop_info_label.drop_target_register(DND_FILES)
        self.wizard_view.drop_info_label.dnd_bind('<<Drop>>', self.handle_drop)
        
        # Create all widgets first
        
        # Then initialize theming (which might apply theme if system theme changed during detection)
        theming.initialize_theming(self)
        self.create_menubar()     # Menubar uses theme_var, so initialize_theming should come first

        # Explicitly apply the theme based on current settings after all setup
        theming.apply_theme_settings(self)
        # Schedule TTS initialization with UI feedback

        # Initialize the status label text and color properly (theming.apply_theme_settings will also call update_status_label_color)
        if hasattr(self, 'status_label') and self._theme_colors:
            self.status_label.config(text="", fg=self._theme_colors.get("status_fg", "blue"))
        elif hasattr(self, 'status_label'): # Fallback if theme colors not yet loaded
            self.status_label.config(text="", fg="blue")

        # Ensure the initial status label color is set according to the theme
        theming.update_status_label_color(self)

        self.root.after(200, self.start_tts_initialization_with_ui_feedback)
        
        self.show_wizard_view()

        # Start the main UI update loop to keep the app responsive
        self.check_update_queue()

        # Add a method to handle the window closing event
    def on_closing(self):
        self.logic.on_app_closing() # Call logic cleanup
        self.root.destroy() # Destroy the window
    
    def create_menubar(self):
        self.menubar = tk.Menu(self.root)
        self.root.config(menu=self.menubar) # Set the menubar for the root window

        self.theme_menu = tk.Menu(self.menubar, tearoff=0) # Store as instance variable
        self.menubar.add_cascade(label="View", menu=self.theme_menu) # The menubar itself is often OS-styled and may not fully theme.
                                                                     # Individual menus and their items will be themed.
        # Note: Full menubar styling (the bar itself) is highly OS-dependent with Tkinter.
        # The theme is applied, but the OS may override the appearance of the top-level bar.
        # self._menubar = menubar # Store if needed for more direct styling attempts
        # self._theme_menu = theme_menu # Store if needed

        self.theme_menu.add_radiobutton(label="Light", variable=self.theme_var, value="light", command=self.change_theme)
        self.theme_menu.add_radiobutton(label="Dark", variable=self.theme_var, value="dark", command=self.change_theme)
        self.theme_menu.add_radiobutton(label="System", variable=self.theme_var, value="system", command=self.change_theme)
        
        self.tts_engine_menu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label="TTS Engine", menu=self.tts_engine_menu)

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
                self.tts_engine_menu.add_radiobutton(
                    label=engine_spec["label"],
                    variable=self.tts_engine_var,
                    value=engine_spec["value"],
                    command=self.change_tts_engine
                )
        else:
            self.tts_engine_menu.add_command(label="No TTS engines found/installed.", state=tk.DISABLED)
            self.tts_engine_var.set("") # No engine selected
            self.selected_tts_engine_name = ""
            self.logic.logger.warning("No compatible TTS engines were found installed.")
            # self.root.after(500, lambda: messagebox.showwarning("TTS Engines Missing", "No compatible TTS engines (Coqui XTTS, Chatterbox) found. TTS functionality will be limited.")) # Kept as popup due to importance
            
        self.post_actions_menu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label="Post-Actions", menu=self.post_actions_menu)
        self.post_actions_menu.add_radiobutton(label="Do Nothing", variable=self.post_action_var, value=PostAction.DO_NOTHING)
        self.post_actions_menu.add_radiobutton(label="Sleep on Finish", variable=self.post_action_var, value=PostAction.SLEEP)
        self.post_actions_menu.add_radiobutton(label="Shutdown on Finish", variable=self.post_action_var, value=PostAction.SHUTDOWN)
        self.post_actions_menu.add_radiobutton(label="Quit Program on Finish", variable=self.post_action_var, value=PostAction.QUIT)


        # For future: self.root.bind("<<ThemeChanged>>", self.on_system_theme_change_event)

    def change_theme(self):
        self.current_theme_name = self.theme_var.get()
        # In a real app, save self.current_theme_name to a config file
        theming.apply_theme_settings(self)

    def change_tts_engine(self):
        new_engine_name = self.tts_engine_var.get()
        if not new_engine_name: # Should not happen if menu is populated correctly
            self.logic.logger.warning("Change TTS engine called with no engine selected.")
            return

        self.selected_tts_engine_name = new_engine_name # Update internal tracker
        self.logic.logger.info(f"TTS Engine selection changed to: {new_engine_name}. Re-initializing.")

        # Clear runtime voice list and assignments. Default will be re-evaluated.
        self.state.voices = []
        self.state.default_voice_info = None
        self.state.loaded_default_voice_name_from_config = None # Reset for new load
        self.state.voice_assignments = {}

        # Reload user-defined voices from the configuration file.
        self.load_voice_config() # This populates self.voices and self.default_voice_info from JSON
        self.start_tts_initialization_with_ui_feedback() # This will re-initialize and update UI

    # def on_system_theme_change_event(self, event=None): # For future real-time updates
    #     self.detect_system_theme()
    #     if self.current_theme_name == "system":
    #         theming.apply_theme_settings(self)

    def start_tts_initialization_with_ui_feedback(self):
        self.start_progress_indicator("Initializing TTS Engine...")
        # AppLogic.initialize_tts sets self.ui.last_operation = 'tts_init'
        # and starts the background thread.
        self.logic.initialize_tts()

    # --- NEW METHOD: ADD A VOICE TO THE LIBRARY ---
    def add_new_voice(self):
        dialog = AddVoiceDialog(self.root, self._theme_colors)
        if dialog.result:
            new_voice_data = dialog.result
            if any(v['name'] == new_voice_data['name'] for v in self.state.voices):
                messagebox.showwarning("Duplicate Name", "A voice with this name already exists.")
                return

            filepath_str = filedialog.askopenfilename(
                title=f"Select a 10-30s sample .wav for '{new_voice_data['name']}'",
                filetypes=[("WAV Audio Files", "*.wav")]
            )
            if not filepath_str: return

            source_path = Path(filepath_str)
            if not source_path.exists():
                messagebox.showerror("Error", "File not found.")
                return

            # --- New Logic: Copy file to local app directory ---
            voices_dir = self.state.output_dir / "voices"
            # Sanitize the voice name for use as a filename
            sanitized_name = re.sub(r'[^\w\s-]', '', new_voice_data['name']).strip().replace(' ', '_')
            dest_filename = f"{sanitized_name}_{source_path.stem}.wav"
            dest_path = voices_dir / dest_filename

            if dest_path.exists():
                if not messagebox.askyesno("File Exists", f"A voice file named '{dest_filename}' already exists. Overwrite it?"):
                    return
            
            try:
                shutil.copy2(source_path, dest_path)
                self.logic.logger.info(f"Copied voice file from '{source_path}' to '{dest_path}'")
            except Exception as e:
                messagebox.showerror("File Copy Error", f"Could not copy the voice file to the application directory.\n\nError: {e}")
                self.logic.logger.error(f"Failed to copy voice file to '{dest_path}': {e}")
                return
            
            new_voice_data['path'] = str(dest_path) # Store the path to the *local copy*
            self.state.voices.append(new_voice_data)
            
            if not self.state.default_voice_info: # If no default, make this the new default
                self.state.default_voice_info = new_voice_data
                if self.default_voice_label: self.default_voice_label.config(text=f"Default: {new_voice_data['name']}")
            self.on_voice_dropdown_select() # Update details after adding
                
            self.save_voice_config()
            self.update_voice_dropdown()
            messagebox.showinfo("Success", f"Voice '{new_voice_data['name']}' added successfully.")

    def remove_selected_voice(self):
        selected_voice_name = self.voice_dropdown.get()
        if not selected_voice_name:
            messagebox.showwarning("No Selection", "Please select a voice from the dropdown to remove."); return

        voice_to_delete = next((v for v in self.state.voices if v['name'] == selected_voice_name), None)
        if not voice_to_delete:
            messagebox.showerror("Error", "Could not find the selected voice data."); return

        if not Path(voice_to_delete.get('path', '')).is_file():
            messagebox.showerror("Cannot Remove", "Internal engine voices cannot be removed."); return

        if not messagebox.askyesno("Confirm Deletion", f"Are you sure you want to permanently remove the voice '{selected_voice_name}'?\n\nThis will also delete the associated file and cannot be undone."):
            return

        self.logic.remove_voice(voice_to_delete)
        self.voice_assignment_view.voice_dropdown.set("") # Clear selection after removal

    def set_selected_as_default_voice(self):
        selected_voice_name = self.voice_assignment_view.voice_dropdown.get()
        if not selected_voice_name:
            messagebox.showwarning("No Voice Selected", "Please select a voice from the dropdown to set as default.")
            return

        selected_voice = next((v for v in self.state.voices if v['name'] == selected_voice_name), None)
        if selected_voice:
            self.state.default_voice_info = selected_voice
            self.voice_assignment_view.default_voice_label.config(text=f"Default: {selected_voice['name']}")
            self.save_voice_config()
            messagebox.showinfo("Default Voice Set", f"'{selected_voice['name']}' is now the default voice.")
        else:
            # Should not happen if dropdown is synced with self.voices
            messagebox.showerror("Error", "Could not find the selected voice data.")

    def update_voice_dropdown(self):
        if not hasattr(self.voice_assignment_view, 'voice_dropdown'): return # Guard clause
        voice_names = sorted([v['name'] for v in self.state.voices])
        self.voice_assignment_view.voice_dropdown.config(values=voice_names)
        if voice_names:
            self.voice_assignment_view.voice_dropdown.set(voice_names[0])
        else:
            self.voice_assignment_view.voice_dropdown.set("")
        self.voice_assignment_view.set_default_voice_button.config(state=tk.NORMAL if self.state.voices else tk.DISABLED)
        self.on_voice_dropdown_select() # Update details after dropdown changes

    def on_voice_dropdown_select(self, event=None):
        """Updates the voice details label based on the selected voice in the dropdown."""
        if not self.voice_assignment_view.voice_dropdown or not hasattr(self.voice_assignment_view, 'voice_details_label'): return

        selected_voice_name = self.voice_assignment_view.voice_dropdown.get()
        if not selected_voice_name:
            self.voice_assignment_view.voice_details_label.config(text="Details: N/A")
            return

        selected_voice = next((v for v in self.state.voices if v['name'] == selected_voice_name), None)
        if selected_voice:
            gender = selected_voice.get('gender', 'Unknown')
            age_range = selected_voice.get('age_range', 'Unknown')
            language = selected_voice.get('language', 'Unknown')
            accent = selected_voice.get('accent', 'Unknown')
            details_text = f"Gender: {gender}, Age: {age_range}\nLang: {language}, Accent: {accent}"
            self.voice_assignment_view.voice_details_label.config(text=details_text)
        else:
            self.voice_assignment_view.voice_details_label.config(text="Details: Voice not found")

    def clear_all_assignments(self):
        """Clears all voice assignments from speakers."""
        if not self.state.voice_assignments:
            self.show_status_message("No voice assignments to clear.", "info")
            return

        if messagebox.askyesno("Confirm Clear", "Are you sure you want to clear all voice assignments?"):
            self.state.voice_assignments.clear()
            self.update_cast_list()
            self.show_status_message("All voice assignments have been cleared.", "success")
            self.logic.logger.info("All voice assignments cleared by user.")

    def preview_selected_voice(self):
        """Generates and plays a TTS preview of the selected voice."""
        selected_voice_name = self.voice_assignment_view.voice_dropdown.get()
        if not selected_voice_name:
            self.show_status_message("Select a voice from the dropdown to preview.", "warning")
            return
        
        selected_voice = next((v for v in self.state.voices if v['name'] == selected_voice_name), None)
        if selected_voice:
            self.show_status_message(f"Generating preview for '{selected_voice_name}'...", "info")
            self.logic.start_voice_preview_thread(selected_voice)

    # --- UPDATED METHOD ---
    def assign_voice(self):
        try:
            selected_item_id = self.voice_assignment_view.cast_tree.selection()[0]
            speaker_name = self.voice_assignment_view.cast_tree.item(selected_item_id, 'values')[0]
        except IndexError:
            messagebox.showwarning("No Selection", "Please select a speaker from the cast list first."); return
        
        selected_voice_name = self.voice_assignment_view.voice_dropdown.get()
        if not selected_voice_name:
            messagebox.showwarning("No Voice Selected", "Please select a voice from the dropdown menu.\nYou may need to add one first using the 'Add New Voice' button."); return

        # Find the full voice dictionary
        selected_voice = next((voice for voice in self.state.voices if voice['name'] == selected_voice_name), None)
        if selected_voice is None:
            return messagebox.showerror("Error", "Could not find the selected voice data. It may have been removed.")

        # Store the entire voice dictionary for the selected speaker
        self.state.voice_assignments[speaker_name] = selected_voice
        print(f"Assigned voice '{selected_voice['name']}' to '{speaker_name}'.")
        self.update_cast_list()

    # --- UPDATED METHOD ---
    def _populate_cast_tree(self, tree, speakers, is_full_detail):
        """Helper to populate a cast list treeview."""
        if not tree: return
        selected_item = tree.selection()
        tree.delete(*tree.get_children())
        for i, speaker in enumerate(speakers):
            speaker_color_tag = self.get_speaker_color_tag(speaker)
            assigned_voice_name = self.state.voice_assignments.get(speaker, {}).get('name', "Not Assigned")
            
            if is_full_detail:
                gender = self.state.character_profiles.get(speaker, {}).get('gender', 'N/A')
                age_range = self.state.character_profiles.get(speaker, {}).get('age_range', 'N/A')
                count = sum(1 for item in self.state.analysis_result if item.get('speaker') == speaker)
                values = (speaker, assigned_voice_name, gender, age_range, count)
            else:
                values = (speaker, assigned_voice_name)

            tree.insert('', tk.END, iid=speaker, values=values, tags=(speaker_color_tag,))
        
        if selected_item:
            try: 
                if tree.exists(selected_item[0]): tree.selection_set(selected_item)
            except tk.TclError: pass
        self.update_treeview_item_tags(tree)

    def update_cast_list(self):
        if not self.state.analysis_result: return
        unique_speakers = sorted(list(set(item['speaker'] for item in self.state.analysis_result)))
        self.state.cast_list = unique_speakers
        
        self._populate_cast_tree(self.refinement_cast_tree, self.state.cast_list, is_full_detail=True)
        self._populate_cast_tree(self.assignment_cast_tree, self.state.cast_list, is_full_detail=False)

    # --- END UPDATED METHOD (update_cast_list) ---

    def show_status_message(self, message, msg_type="info"):
        # msg_type: "info", "warning", "error", "success"
        # Ensure _theme_colors is initialized
        if not self._theme_colors:
            self.apply_theme_settings() # Apply theme to populate _theme_colors if not already
            # This call will be theming.apply_theme_settings(self) after refactor
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
            engine_voices = self.logic.current_tts_engine_instance.get_engine_specific_voices() # type: ignore
            for eng_voice in engine_voices:
                ui_voice_format = {'name': eng_voice['name'], 'path': eng_voice['id_or_path']}
                if not any(v['path'] == ui_voice_format['path'] for v in self.state.voices):
                    self.state.voices.append(ui_voice_format)
                
            # Default Voice Resolution:
            # Try to re-establish default based on the name loaded from config,
            # searching within the now complete self.voices list (user + current engine).
            resolved_default_voice = None
            if self.state.loaded_default_voice_name_from_config:
                resolved_default_voice = next((v for v in self.state.voices if v['name'] == self.state.loaded_default_voice_name_from_config), None)

            if resolved_default_voice:
                self.state.default_voice_info = resolved_default_voice
            else:
                # No valid saved default, or saved default not found in current engine's + user voices.
                # Try to set a sensible engine-specific default.
                self.state.default_voice_info = None # Reset before trying engine defaults
                if engine_display_name == "Coqui XTTS":
                    xtts_default = next((v for v in self.state.voices if v['path'] == '_XTTS_INTERNAL_VOICE_'), None)
                    if xtts_default: self.state.default_voice_info = xtts_default
                elif engine_display_name == "Chatterbox":
                    cb_default = next((v for v in self.state.voices if v['path'] == 'chatterbox_default_internal'), None)
                    if cb_default: self.state.default_voice_info = cb_default
                # If still no default, and self.voices is not empty, it will remain None or could pick first.
                # Current logic implies it remains None if no specific engine default matches.

            if self.state.default_voice_info:
                self.default_voice_label.config(text=f"Default: {self.state.default_voice_info['name']}")
            else:
                self.voice_assignment_view.default_voice_label.config(text="Default: None (select or add one)")
        else: # No TTS engine instance (e.g., none available or init failed before instance creation)
            self.show_status_message("TTS Engine not available or failed to initialize.", "error")
            self.voice_assignment_view.default_voice_label.config(text="Default: None")

        self.update_voice_dropdown() # Ensure dropdown is populated, now potentially with internal voice
        # self.update_status_label_color() # show_status_message handles this
    @property
    def refinement_cast_tree(self):
        return self.cast_refinement_view.cast_tree if hasattr(self, 'cast_refinement_view') else None
    @property
    def assignment_cast_tree(self):
        return self.voice_assignment_view.cast_tree if hasattr(self, 'voice_assignment_view') else None
    @property
    def tree(self): # Make tree (main script view) accessible as a property
        return self.cast_refinement_view.tree if hasattr(self, 'cast_refinement_view') else None
    @property
    def voice_dropdown(self):
        return self.voice_assignment_view.voice_dropdown if hasattr(self, 'voice_assignment_view') else None
    @property
    def default_voice_label(self):
        return self.voice_assignment_view.default_voice_label if hasattr(self, 'voice_assignment_view') else None
    @property
    def resolve_button(self):
        return self.cast_refinement_view.resolve_button if hasattr(self, 'cast_refinement_view') else None
    @property
    def refine_speakers_button(self):
        return self.cast_refinement_view.refine_speakers_button if hasattr(self, 'cast_refinement_view') else None
    @property
    def tts_button(self):
        return self.voice_assignment_view.tts_button if hasattr(self, 'voice_assignment_view') else None
    @property
    def rename_button(self):
        return self.cast_refinement_view.rename_button if hasattr(self, 'cast_refinement_view') else None
    @property
    def add_voice_button(self):
        return self.voice_assignment_view.add_voice_button if hasattr(self, 'voice_assignment_view') else None
    @property
    def remove_voice_button(self):
        return self.voice_assignment_view.remove_voice_button if hasattr(self, 'voice_assignment_view') else None
    @property
    def set_default_voice_button(self):
        return self.voice_assignment_view.set_default_voice_button if hasattr(self, 'voice_assignment_view') else None
    @property
    def assign_button(self):
        return self.voice_assignment_view.assign_button if hasattr(self, 'voice_assignment_view') else None
    @property
    def auto_assign_button(self):
        return self.voice_assignment_view.auto_assign_button if hasattr(self, 'voice_assignment_view') else None
    @property
    def clear_assignments_button(self):
        return self.voice_assignment_view.clear_assignments_button if hasattr(self, 'voice_assignment_view') else None
    @property
    def back_button_refinement(self):
        return self.cast_refinement_view.back_button if hasattr(self, 'cast_refinement_view') else None
    
    # Properties for ReviewView widgets
    @property
    def review_tree(self):
        return self.review_view.tree if hasattr(self.review_view, 'tree') else None
    # Add other review_view widget properties if directly accessed from AudiobookCreatorApp
        
    def set_ui_state(self, state, exclude=None):
        if exclude is None: exclude = []
        widgets_to_toggle = [
            self.wizard_view.upload_button, self.wizard_view.next_step_button, self.wizard_view.edit_text_button,
            self.editor_view.save_button, self.editor_view.back_button, self.editor_view.analyze_button,
            self.editor_view.text_editor, self.tree,
            self.back_button_refinement, self.cast_refinement_view.next_button, self.resolve_button, self.refine_speakers_button, self.refinement_cast_tree, self.rename_button,
            self.voice_assignment_view.back_button, self.tts_button, self.assignment_cast_tree,
            self.add_voice_button, self.remove_voice_button, self.auto_assign_button, self.clear_assignments_button,
            self.voice_assignment_view.preview_voice_button, self.assign_button, self.set_default_voice_button, self.voice_dropdown,
            
        ]
        if hasattr(self.review_view, 'play_selected_button'): widgets_to_toggle.append(self.review_view.play_selected_button)
        if hasattr(self.review_view, 'regenerate_selected_button'): widgets_to_toggle.append(self.review_view.regenerate_selected_button)
        if hasattr(self.review_view, 'assemble_audiobook_button'): widgets_to_toggle.append(self.review_view.assemble_audiobook_button)
        if hasattr(self.review_view, 'back_to_analysis_button'): widgets_to_toggle.append(self.review_view.back_to_analysis_button)
        if self.review_tree: widgets_to_toggle.append(self.review_tree)

        for widget in widgets_to_toggle:
            if widget and widget not in exclude:
                try: widget.config(state=state)
                except (tk.TclError, AttributeError): pass
        
        # Only change cursor if colors are available (theme applied)
        if self._theme_colors:
            self.root.config(cursor="watch" if state == tk.DISABLED else "")

    def _update_wizard_button_states(self):
        """ Helper to set states of wizard step buttons based on ebook and txt paths. """
        if self.state.ebook_path:
            if self.state.txt_path:  # Ebook processed and converted
                self.wizard_view.next_step_button.config(state=tk.DISABLED, text="Conversion Complete")
                self.wizard_view.edit_text_button.config(state=tk.NORMAL)
            else:  # Ebook loaded, but not yet converted
                self.wizard_view.next_step_button.config(state=tk.NORMAL, text="Convert to Text")
                self.wizard_view.edit_text_button.config(state=tk.DISABLED)
        else:  # No ebook loaded yet
            self.wizard_view.next_step_button.config(state=tk.DISABLED, text="Convert to Text")
            self.wizard_view.edit_text_button.config(state=tk.DISABLED)


    # --- Other methods are unchanged, but included for completeness ---
    
    def get_speaker_color_tag(self, speaker_name):
        """Gets a color for a speaker and ensures a ttk tag exists for it."""
        if speaker_name not in self.state.speaker_colors:
            color = self.color_palette[self.state._color_palette_index % len(self.color_palette)] # type: ignore
            self.state.speaker_colors[speaker_name] = color
            self.state._color_palette_index += 1
        
        color = self.state.speaker_colors[speaker_name] # type: ignore
        tag_name = f"speaker_{re.sub(r'[^a-zA-Z0-9_]', '', speaker_name)}" # Sanitize name for tag

        # Ensure the tag is configured in all relevant treeviews
        for treeview in [self.tree, self.refinement_cast_tree, self.assignment_cast_tree, self.review_tree]:
            if treeview: # Check if treeview exists (e.g. review_tree might not be fully init early)
                # tag_configure is idempotent: it creates the tag if it doesn't exist,
                # or reconfigures it if it does.
                treeview.tag_configure(tag_name, foreground=color)
        return tag_name

    def _hide_all_main_frames(self):
        self.wizard_frame.pack_forget()
        self.editor_frame.pack_forget()
        self.cast_refinement_frame.pack_forget()
        self.voice_assignment_frame.pack_forget()
        self.review_frame.pack_forget()

    def show_wizard_view(self, resize=True):
        self._hide_all_main_frames()
        if resize: self.root.geometry("800x800")
        self.wizard_frame.pack(fill=tk.BOTH, expand=True)

    def show_editor_view(self, resize=True):
        if self.state.txt_path and self.state.txt_path.exists() and not self.editor_view.text_editor.get("1.0", tk.END).strip():
            try:
                with open(self.state.txt_path, 'r', encoding='utf-8') as f: content = f.read()
                self.editor_view.text_editor.delete('1.0', tk.END); self.editor_view.text_editor.insert('1.0', content)
                self.show_status_message("Text loaded for editing.", "info")
            except Exception as e:
                self.show_status_message(f"Error: Could not load text for editing. Error: {e}", "error")
                
                
        self._hide_all_main_frames()
        if resize: self.root.geometry("800x700")
        self.editor_frame.pack(fill=tk.BOTH, expand=True)
        
    def show_cast_refinement_view(self, resize=True):
        self._hide_all_main_frames()
        if resize:
            self.root.geometry("1000x900")
        self.cast_refinement_frame.pack(fill=tk.BOTH, expand=True)

        # Refresh data and UI elements for analysis view
        # on_analysis_complete will populate tree, cast_list, and update relevant button states
        self.on_analysis_complete() 

        # Set a generic status message for navigation or initial load
        if self.state.analysis_result:
            # If called after Pass 1, _handle_rules_pass_complete_update will set a more specific message.
            # This message is for general navigation to this view.
            if self.state.last_operation != 'rules_pass_analysis':
                self.show_status_message("Refine the script and cast list. Use AI tools if needed.", "info")
        else:
            self.show_status_message("No analysis data to display. Please process text first.", "warning")
        
        self.set_ui_state(tk.NORMAL) # General UI enablement

    def show_voice_assignment_view(self, resize=True):
        self._hide_all_main_frames()
        if resize: self.root.geometry("800x700")
        self.voice_assignment_frame.pack(fill=tk.BOTH, expand=True)
        self.update_cast_list() # Ensure the cast list is populated
        self.update_voice_dropdown()
        self.show_status_message("Assign voices to each speaker.", "info")


    def _handle_pass_2_complete_update(self, update):
        self.stop_progress_indicator()
        self.logic.logger.info("Pass 2 complete. Propagating updated character profiles to all analysis lines.")
        # Propagate character profile info to all lines in analysis_result
        for item in self.state.analysis_result:
            speaker = item['speaker']
            if speaker in self.state.character_profiles:
                profile = self.state.character_profiles[speaker]
                item['gender'] = profile.get('gender', 'Unknown')
                item['age_range'] = profile.get('age_range', 'Unknown')
        self.on_analysis_complete()
        self.show_status_message("Pass 2 (LLM Analysis) complete.", "success")
        self.set_ui_state(tk.NORMAL)
        self.state.active_thread = None
        self.state.last_operation = None

    def _handle_speaker_refinement_complete_update(self, update):
        self.stop_progress_indicator()
        groups = update.get('groups', [])
        if not groups:
            self.show_status_message("Speaker refinement returned no groups.", "warning")
            self.set_ui_state(tk.NORMAL)
            return

        self.logic.logger.info("Applying speaker refinement changes.")
        changes_made = 0
        for group in groups:
            primary_name = group.get('primary_name')
            aliases = group.get('aliases', [])
            if not primary_name or not aliases:
                continue

            best_voice_assignment = self.state.voice_assignments.get(primary_name)
            if not best_voice_assignment:
                for alias in aliases:
                    if alias in self.state.voice_assignments:
                        best_voice_assignment = self.state.voice_assignments[alias]; break
            
            best_profile = self.state.character_profiles.get(primary_name, {})
            if not best_profile or best_profile.get('gender', 'Unknown') == 'Unknown':
                 for alias in aliases:
                    if alias in self.state.character_profiles and self.state.character_profiles[alias].get('gender', 'Unknown') != 'Unknown':
                        best_profile = self.state.character_profiles[alias]; break

            for alias in aliases:
                if alias == primary_name: continue
                self.logic.logger.info(f"Merging '{alias}' into '{primary_name}'.")
                for item in self.state.analysis_result:
                    if item['speaker'] == alias: item['speaker'] = primary_name
                if alias in self.state.voice_assignments: del self.state.voice_assignments[alias]
                if alias in self.state.character_profiles: del self.state.character_profiles[alias]
                changes_made += 1

            if best_voice_assignment: self.state.voice_assignments[primary_name] = best_voice_assignment
            if best_profile: self.state.character_profiles[primary_name] = best_profile

        self.on_analysis_complete()
        self.show_status_message(f"Speaker list refined. Merged {changes_made} aliases.", "success")
        self.set_ui_state(tk.NORMAL)
        self.state.active_thread = None
        self.state.last_operation = None
    def show_review_view(self):
        self._hide_all_main_frames()
        self.root.geometry("900x700")
        self.review_frame.pack(fill=tk.BOTH, expand=True)
        self.populate_review_tree()

    def sanitize_for_tts(self, text):
        """Removes characters/patterns that can cause issues with TTS engines."""
        # Remove text within square brackets (e.g., [laughter])
        text = re.sub(r'\[.*?\]', '', text)
        # Remove text within parentheses (e.g., (whispering))
        text = re.sub(r'\(.*?\)', '', text)
        # Remove asterisks (often used for emphasis or actions)
        text = text.replace('*', ''); text = re.sub(r'\s+', ' ', text)
        # Remove various quote characters
        text = re.sub(r'[“”‘’"\']', '', text) # Remove various quote characters
        text = text.replace('...', '') # Remove ellipses
        text = text.replace('.', '') # Remove periods (except those handled by abbreviation expansion)
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

    def on_analysis_complete(self):
        # This method is now primarily for populating/refreshing the analysis view's content
        if not self.state.analysis_result or not self.refinement_cast_tree or not self.cast_refinement_view.tree:
            if self.cast_refinement_view.tree: self.cast_refinement_view.tree.delete(*self.cast_refinement_view.tree.get_children())
            if self.refinement_cast_tree: self.refinement_cast_tree.delete(*self.refinement_cast_tree.get_children())
            if self.assignment_cast_tree: self.assignment_cast_tree.delete(*self.assignment_cast_tree.get_children())
            self.state.cast_list = []
            if self.resolve_button: self.resolve_button.config(state=tk.DISABLED)
            if self.tts_button: self.tts_button.config(state=tk.DISABLED)
            return
        
        self.cast_refinement_view.tree.delete(*self.cast_refinement_view.tree.get_children())
        for i, item in enumerate(self.state.analysis_result):
            speaker_color_tag = self.get_speaker_color_tag(item.get('speaker', 'N/A'))
            row_tags = (speaker_color_tag, 'evenrow' if i % 2 == 0 else 'oddrow')
            pov_display = item.get('pov', 'Unknown')
            self.cast_refinement_view.tree.insert('', tk.END, 
                             values=(item.get('speaker', 'N/A'), item.get('line', 'N/A'), pov_display), 
                             tags=row_tags)
        self.update_treeview_item_tags(self.cast_refinement_view.tree)
        
        self.update_cast_list() # This populates cast_tree and applies its themes
        
        # Update button states specific to analysis view
        has_ambiguous_speakers = any(item['speaker'] == 'AMBIGUOUS' for item in self.state.analysis_result)
        if self.resolve_button: self.resolve_button.config(state=tk.NORMAL if has_ambiguous_speakers else tk.DISABLED)
        if self.refine_speakers_button: self.refine_speakers_button.config(state=tk.NORMAL if not has_ambiguous_speakers and self.state.cast_list else tk.DISABLED)
        if self.voice_assignment_view.tts_button: self.voice_assignment_view.tts_button.config(state=tk.NORMAL if self.state.analysis_result else tk.DISABLED)

        # Ensure voice dropdown is up-to-date and default voice label is correct
        self.update_voice_dropdown()
        if self.state.default_voice_info: self.voice_assignment_view.default_voice_label.config(text=f"Default: {self.state.default_voice_info['name']}")
        else: self.voice_assignment_view.default_voice_label.config(text="Default: None (select or add one)")

    def rename_speaker(self):
        try:
            if not self.refinement_cast_tree: raise IndexError("Cast tree not available")
            selected_item_id = self.refinement_cast_tree.selection()[0]; original_name = self.refinement_cast_tree.item(selected_item_id, 'values')[0]
        except IndexError:
            self.show_status_message("Please select a speaker from the cast list to rename.", "warning"); return

        new_name = simpledialog.askstring("Rename Speaker", f"Enter new name for '{original_name}':", parent=self.root)
        
        if not new_name or not new_name.strip() or new_name.strip() == original_name: return
        new_name = new_name.strip()

        if original_name in self.state.speaker_colors:
            self.state.speaker_colors[new_name] = self.state.speaker_colors.pop(original_name)

        for item in self.state.analysis_result:
            if item['speaker'] == original_name: item['speaker'] = new_name

        if original_name in self.state.voice_assignments: self.state.voice_assignments[new_name] = self.state.voice_assignments.pop(original_name)
        if original_name in self.state.character_profiles: self.state.character_profiles[new_name] = self.state.character_profiles.pop(original_name)

        self.on_analysis_complete() # This will re-populate tree and cast_list with new colors/tags

    def on_treeview_double_click(self, event):
        if not self.cast_refinement_view.tree: return # Guard clause
        tree_widget = self.cast_refinement_view.tree
        region = tree_widget.identify_region(event.x, event.y);
        if region != "cell": return
        column_id = tree_widget.identify_column(event.x); item_id = tree_widget.identify_row(event.y)
        if column_id != '#1' or not item_id: return
        x, y, width, height = tree_widget.bbox(item_id, column_id)
        try:
            current_speaker = tree_widget.item(item_id, 'values')[0]
        except IndexError: # Should not happen if item_id is valid
            return

        # Style the combobox editor based on the current theme
        # This is tricky as it's a temporary widget. For now, it uses ttk defaults.
        editor = ttk.Combobox(tree_widget, values=self.state.cast_list); editor.set(current_speaker); editor.place(x=x, y=y, width=width, height=height); editor.focus_set()
        editor.after(10, lambda: editor.event_generate('<Alt-Down>'))
        def on_edit_commit(event):
            new_value = editor.get()
            if new_value and new_value != current_speaker:
                tree_widget.set(item_id, column_id, new_value)
                try:
                    item_index = tree_widget.index(item_id)
                    self.state.analysis_result[item_index]['speaker'] = new_value
                    self.update_treeview_item_tags(tree_widget)
                except (ValueError, IndexError): print(f"Warning: Could not find item {item_id} to update master data.")
            editor.destroy()
        def on_edit_cancel(event): editor.destroy()
        editor.bind('<<ComboboxSelected>>', on_edit_commit); editor.bind('<Return>', on_edit_commit); editor.bind('<Escape>', on_edit_cancel)

    def start_hybrid_analysis(self):
        full_text = self.editor_view.text_editor.get('1.0', tk.END)
        if not full_text.strip():
            self.show_status_message("Cannot analyze: Text editor is empty.", "warning")
            return # messagebox.showwarning("Empty Text", "There is no text to analyze.")

        self.start_progress_indicator("Running high-speed analysis (Pass 1)...") 
        # This will now call a method in AppLogic to start the thread
        self.logic.start_rules_pass_thread(full_text)
            
    def _handle_error_update(self, error_message):
        self.stop_progress_indicator()
        messagebox.showerror("Background Task Error", error_message)
        self.set_ui_state(tk.NORMAL)
        self._update_wizard_button_states()
        if self.state.last_operation == 'conversion':
            self.wizard_view.next_step_button.config(state=tk.NORMAL if self.state.ebook_path else tk.DISABLED, text="Convert to Text") # type: ignore
            self.wizard_view.edit_text_button.config(state=tk.DISABLED)
        elif self.state.last_operation in ['generation', 'assembly'] and self.post_action_var.get() != PostAction.DO_NOTHING:
            self.handle_post_generation_action(success=False)
        self.state.last_operation = None

    def _handle_status_update(self, status_message):
        self.show_status_message(status_message, "info")

    def _handle_playback_finished_update(self, update):
        original_index = update['original_index']
        status = update['status']
        item_id = str(original_index) # Assuming IID is string of original_index
        if hasattr(self, 'review_tree') and self.review_tree.exists(item_id):
            self.review_tree.set(item_id, 'status', status)
        
        msg_type = "info"
        if status == 'Error':
            msg_type = "error"
            self.logic.logger.info(f"UI received playback error for index {original_index}")
        
        self.show_status_message(f"Playback {status.lower()} for line {original_index + 1}.", msg_type)

    def _handle_pass_2_resolution_started_update(self, update):
        self.set_ui_state(tk.DISABLED, exclude=[self.back_button_refinement])
        total_items = update['total_items']
        self.progressbar.config(mode='determinate', maximum=total_items, value=0)
        self.progressbar.pack(fill=tk.X, padx=5, pady=(0,5), expand=True)
        self.show_status_message(f"Resolving 0 / {total_items} speakers...", "info")

    def _handle_assembly_started_update(self):
        self.set_ui_state(tk.DISABLED)
        self.progressbar.config(mode='indeterminate', value=0)
        self.progressbar.pack(fill=tk.X, padx=5, pady=(0,5), expand=True)
        self.progressbar.start()
        self.show_status_message("Assembling audiobook... This may take a while.", "info")
        self.root.update_idletasks()

    def _handle_rules_pass_complete_update(self, update):
        self.state.analysis_result = update['results']
        self.stop_progress_indicator()
        # on_analysis_complete will populate the data, then we show the view
        self.show_cast_refinement_view(resize=False)
        self.show_status_message("Pass 1 Complete! Review script and assign voices.", "success")
        self.set_ui_state(tk.NORMAL)
        self.state.active_thread = None
        self.state.last_operation = None

    def _handle_tts_init_complete_update(self):
        self.on_tts_initialization_complete()
        self.state.active_thread = None
        self.state.last_operation = None

    def _handle_generation_for_review_complete_update(self, update):
        self.state.generated_clips_info = update['clips_info']
        self.stop_progress_indicator()
        self.show_status_message("Audio generation complete. Ready for review.", "success")
        self.set_ui_state(tk.NORMAL)
        self.show_review_view()
        self.state.active_thread = None
        self.state.last_operation = None

    def _handle_single_line_regeneration_complete_update(self, update):
        self.on_single_line_regeneration_complete(update)

    def _handle_assembly_complete_update(self, update):
        self.progressbar.pack_forget()
        self.set_ui_state(tk.NORMAL)
        final_audio_path_str = update['final_path']
        # The final_audio_path_str now points to the .m4b file
        self.show_status_message(f"Audiobook assembled successfully! Saved to: {final_audio_path_str}", "success")
        try:
            output_dir = Path(final_audio_path_str).parent
            if messagebox.askyesno("Open Output Directory",
                                   f"Audiobook assembly complete.\n\nOutput directory: {output_dir}\n\nDo you want to open this directory?",
                                   parent=self.root):
                self.open_directory(output_dir)
        except Exception as e:
            self.logic.logger.error(f"Error during 'open directory' prompt or action: {e}")
            self.show_status_message(f"Could not open directory: {e}", "error")
        if self.post_action_var.get() != PostAction.DO_NOTHING:
            self.handle_post_generation_action(success=True)
        self.state.active_thread = None
        self.state.last_operation = None

    def _handle_conversion_complete_update(self, update):
        self.state.txt_path = Path(update['txt_path'])
        self.stop_progress_indicator()
        self.status_label.config(text="Success! Text ready for editing.", fg=self._theme_colors.get("success_fg", "green"))
        self.set_ui_state(tk.NORMAL)
        self._update_wizard_button_states()
        self.wizard_view.next_step_button.config(state=tk.DISABLED, text="Conversion Complete") # type: ignore
        self.wizard_view.edit_text_button.config(state=tk.NORMAL) # type: ignore
        self.state.active_thread = None
        self.state.last_operation = None

    def _handle_progress_update(self, update):
        if update.get('assembly_total_duration'):
            self.progressbar.config(maximum=update['assembly_total_duration'])
        elif update.get('assembly_progress'):
            total_seconds = int(self.progressbar['maximum'] / 1000) # type: ignore
            current_seconds = int(update['assembly_progress'] / 1000)
            self.progressbar.config(value=update['assembly_progress'])
            self.show_status_message(f"Assembling... {current_seconds}s / {total_seconds}s", "info")
        elif update.get('is_generation'):
            total_items = self.progressbar['maximum'] # type: ignore
            items_processed = update['progress'] + 1
            self.progressbar.config(value=items_processed)
            self.show_status_message(f"Generating {items_processed} / {total_items} audio clips...", "info")
        elif 'progress' in update and 'original_index' in update and 'new_speaker' in update: # LLM progress
            total_items = self.progressbar['maximum'] # type: ignore
            items_processed = update['progress'] + 1
            self.state.analysis_result[update['original_index']]['speaker'] = update['new_speaker']
            # Store gender and age in analysis_result and character_profiles
            self.state.analysis_result[update['original_index']]['gender'] = update.get('gender', 'Unknown')
            self.state.analysis_result[update['original_index']]['age_range'] = update.get('age_range', 'Unknown')

            speaker_name_for_profile = update['new_speaker']
            if speaker_name_for_profile and speaker_name_for_profile.upper() not in {"UNKNOWN", "TIMED_OUT", "NARRATOR", "AMBIGUOUS"}:
                if speaker_name_for_profile not in self.state.character_profiles:
                    self.state.character_profiles[speaker_name_for_profile] = {}
                self.state.character_profiles[speaker_name_for_profile]['gender'] = update.get('gender', 'Unknown')
                self.state.character_profiles[speaker_name_for_profile]['age_range'] = update.get('age_range', 'Unknown')
                self.update_cast_list() # Refresh cast list as profiles might have changed
            if self.tree:
                item_id = self.tree.get_children('')[update['original_index']]
                self.tree.set(item_id, '#1', update['new_speaker'])
            self.progressbar.config(value=items_processed)
            self.status_label.config(text=f"Resolving {items_processed} / {total_items} speakers...")
    def check_update_queue(self):
        try:
            # New handlers at the top for quick UI feedback
            while not self.update_queue.empty():
                update = self.update_queue.get_nowait()
                
                # Process all types of updates directly here or delegate.
                # No need for separate loops or putting back, just process everything
                # that's currently in the queue.
                # The order of if/elif matters for priority, but all will be processed.
                # High-priority updates like 'error' should be first.
                if 'file_accepted' in update:
                        self._handle_file_accepted_update(update)
                elif 'metadata_extracted' in update:
                        self._handle_metadata_extracted_update(update)
                elif 'error' in update:
                    self._handle_error_update(update['error'])
                elif update.get('status'):
                    self._handle_status_update(update['status'])
                elif update.get('playback_finished'):
                    self._handle_playback_finished_update(update)
                elif update.get('pass_2_resolution_started'):
                        self._handle_pass_2_resolution_started_update(update)
                elif update.get('pass_2_complete'):
                    self._handle_pass_2_complete_update(update)
                elif update.get('speaker_refinement_complete'):
                    self._handle_speaker_refinement_complete_update(update)
                elif update.get('assembly_started'):
                    self._handle_assembly_started_update()
                elif update.get('rules_pass_complete'):
                    self._handle_rules_pass_complete_update(update)
                elif update.get('tts_init_complete'):
                    self._handle_tts_init_complete_update()
                elif update.get('generation_for_review_complete'):
                    self._handle_generation_for_review_complete_update(update)
                elif update.get('single_line_regeneration_complete'):
                    self._handle_single_line_regeneration_complete_update(update)
                elif update.get('assembly_complete'):
                    self._handle_assembly_complete_update(update)
                elif update.get('conversion_complete'):
                    self._handle_conversion_complete_update(update)
                else: # General progress updates
                    self._handle_progress_update(update)
                
                # If a handler returned (e.g. error), it would have done so already.
                # Otherwise, we continue to process other messages in the queue in this iteration.
        finally:
            # Fallback for a thread that died without sending a completion message
            if self.state.active_thread and not self.state.active_thread.is_alive():
                self.logic.logger.warning(
                    f"Thread for '{self.state.last_operation}' finished or died without a final queue signal. "
                    f"Resetting UI as a fallback."
                )
                if hasattr(self, 'progressbar') and self.progressbar.winfo_ismapped():
                    self.stop_progress_indicator()
                self.set_ui_state(tk.NORMAL)
                self._update_wizard_button_states()
                if self.state.last_operation in ['analysis', 'rules_pass_analysis', 'speaker_refinement']:
                    self.on_analysis_complete() # This refreshes all analysis-related views
                self.show_status_message(f"Operation '{self.state.last_operation}' ended unexpectedly. UI has been reset.", "warning")
                self.state.active_thread = None # Clear the dead thread
                self.state.last_operation = None

            # Always reschedule the queue check to keep the UI responsive
            self.root.after(100, self.check_update_queue)

    def _handle_file_accepted_update(self, update):
        self.state.ebook_path = Path(update['ebook_path'])
        self.state.title = "" # Clear old metadata
        self.state.author = ""
        self.state.cover_path = None
        self.state.txt_path = None # Clear previous text path to reset conversion state
        self.wizard_view.update_metadata_display(None, None, None) # Clear UI display
        self.wizard_view.file_status_label.config(text=f"Selected: {self.state.ebook_path.name}")
        # Manually disable the button while metadata is being fetched.
        self.wizard_view.next_step_button.config(state=tk.DISABLED, text="Extracting Metadata...")
        self.wizard_view.edit_text_button.config(state=tk.DISABLED)
        self.show_status_message("Extracting metadata...", "info")

    def _handle_metadata_extracted_update(self, update):
        self.state.title = update.get('title')
        self.state.author = update.get('author')
        self.state.cover_path = Path(update['cover_path']) if update.get('cover_path') else None
        self.wizard_view.update_metadata_display(self.state.title, self.state.author, self.state.cover_path)
        self.show_status_message("Ebook metadata and cover extracted.", "info")
        self.state.active_thread = None # Metadata extraction thread is complete
        self.state.last_operation = None # Clear the last operation
        # Now that metadata is done, update the button states correctly.
        self._update_wizard_button_states()

    def start_audio_generation(self):
        if not self.state.analysis_result:
            self.show_status_message("Cannot generate audio: No script loaded or analyzed.", "warning")
            return # return messagebox.showwarning("No Script", "There is no script to generate audio from.")
        if not self.state.voices: 
            self.show_status_message("Cannot generate audio: No voices in Voice Library. Please add one.", "warning")
            return # return messagebox.showwarning("No Voices", "You must add at least one voice to the Voice Library before generating audio.")
        if not self.state.default_voice_info and any(item['speaker'] not in self.state.voice_assignments or item['speaker'].upper() in {'AMBIGUOUS', 'UNKNOWN', 'TIMED_OUT'} for item in self.state.analysis_result):
            self.show_status_message("Default voice needed for unassigned/unresolved lines, but none set. Please set one.", "warning")
            return # return messagebox.showwarning("Default Voice Needed", "Some lines will use the default voice, but no default voice has been set. Please set one in the 'Voice Library'.") # type: ignore

        if not self.confirm_proceed_to_tts(): return

        self.set_ui_state(tk.DISABLED, exclude=[self.voice_assignment_view.back_button])
        total_lines = len([item for item in self.state.analysis_result if self.sanitize_for_tts(item['line'])]) # Count non-empty lines
        if total_lines == 0:
            self.show_status_message("No valid lines to generate audio for after sanitization.", "warning")
            self.set_ui_state(tk.NORMAL)
            return
        self.progressbar.config(mode='determinate', maximum=total_lines, value=0); self.progressbar.pack(fill=tk.X, padx=5, pady=(0,5), expand=True) # type: ignore
        self.show_status_message(f"Generating 0 / {total_lines} audio clips...", "info")
        self.state.last_operation = 'generation'

        self.logic._start_background_task(self.logic.run_audio_generation, op_name='generation')

    def populate_review_tree(self):
        if not hasattr(self, 'review_tree'): return
        if self.review_tree: self.review_tree.delete(*self.review_tree.get_children())
        for i, clip_info in enumerate(self.state.generated_clips_info):
            speaker_color_tag = self.get_speaker_color_tag(clip_info['speaker'])
            row_tags = (speaker_color_tag, 'evenrow' if i % 2 == 0 else 'oddrow')
            # Use original_index for display number if available, else i+1
            line_num = clip_info.get('original_index', i) + 1
            
            # The text displayed in the review tree is the *original* text from analysis_result,
            # not the sanitized text used for TTS generation.
            display_text = clip_info['text']
            if len(display_text) > 100:
                display_text = display_text[:100] + "..." # Add ellipsis only if truncated
            # Generate unique IID by combining original_index and chunk_index
            chunk_index = clip_info.get('chunk_index', 0) # Default to 0 if missing
            unique_iid = f"{clip_info['original_index']}_{chunk_index}"
            if self.review_tree:
                self.review_tree.insert('', tk.END, iid=unique_iid,
                                        values=(line_num, clip_info['speaker'], display_text, "Ready"),
                                        tags=row_tags)
        if self.review_tree: self.update_treeview_item_tags(self.review_tree)

    def play_selected_audio_clip(self):
        try:
            if not self.review_tree: raise IndexError("Review tree not available.")
            selected_item_id = self.review_tree.selection()[0] # type: ignore
            # Extract original_index from the combined ID
            original_index = int(selected_item_id.split('_')[0])
            clip_info = next((ci for ci in self.state.generated_clips_info if ci['original_index'] == original_index), None)
            if clip_info and Path(clip_info['clip_path']).exists():
                # Use the new logic method for playback, passing the index
                self.logic.play_audio_clip(Path(clip_info['clip_path']), original_index)
                # Update UI status immediately - logic will send 'playback_finished' later
                self.review_tree.set(selected_item_id, 'status', 'Playing...') 
                self.show_status_message(f"Playing: {Path(clip_info['clip_path']).name}", "info") # Keep this for immediate feedback
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
        unresolved_count = sum(1 for item in self.state.analysis_result if item['speaker'].upper() in unresolved_speakers)
        unassigned_speakers = {item['speaker'] for item in self.state.analysis_result if item['speaker'] not in self.state.voice_assignments}

        message_parts = []

        default_voice_name = self.state.default_voice_info['name'] if self.state.default_voice_info else "NOT SET"

        if unassigned_speakers or unresolved_count > 0:
            if not self.state.default_voice_info:
                # This case is now primarily caught by start_audio_generation's initial checks
                return False # Indicates to start_audio_generation that a pre-condition (default voice) failed
            
            if unassigned_speakers:
                message_parts.append(f"The following speakers have not been assigned a voice and will use the default ('{default_voice_name}'): {', '.join(sorted(list(unassigned_speakers)))}")
            if unresolved_count > 0:
                message_parts.append(f"There are {unresolved_count} unresolved lines (AMBIGUOUS, etc.). These will also use the default voice ('{default_voice_name}').")
        
        if message_parts:
            message = "\n\n".join(message_parts) + "\n\nAre you sure you want to proceed with audio generation?"
        else:
            message = "Are you sure you want to proceed with audio generation?"
        
        return messagebox.askyesno("Confirm Generation", message)

    def request_regenerate_selected_line(self):
        try:
            selected_item_id = self.review_tree.selection()[0] # type: ignore
            original_index = int(selected_item_id)
            clip_info = next((ci for ci in self.state.generated_clips_info if ci['original_index'] == original_index), None)

            if not clip_info:
                self.show_status_message("Error: Could not find clip information for selected line.", "error")
                return # return messagebox.showerror("Error", "Could not find clip information for selected line.")

            # Confirm with user
            if not messagebox.askyesno("Confirm Regeneration", f"Regenerate audio for line:\n'{clip_info['text'][:100]}...'?\n\nThis will use the voice: '{clip_info['voice_used']['name']}'."):
                return

            self.set_ui_state(tk.DISABLED, exclude=[self.review_view.back_to_analysis_button, self.review_view.assemble_audiobook_button]) # Keep some nav enabled
            self.show_status_message(f"Regenerating line {original_index + 1}...", "info")
            self.progressbar.config(mode='indeterminate'); self.progressbar.pack(fill=tk.X, padx=5, pady=(0,5), expand=True); self.progressbar.start()

            self.state.last_operation = 'regeneration' # For error handling or UI state
            # Call the logic method directly. The logic layer will handle the threading.
            self.logic.start_single_line_regeneration(clip_info, clip_info['voice_used'])

        except IndexError:
            self.show_status_message("Please select a line from the review list to regenerate.", "warning")
            # messagebox.showwarning("No Selection", "Please select a line from the review list to regenerate.")
        except Exception as e:
            self.stop_progress_indicator()
            self.set_ui_state(tk.NORMAL)

    def on_single_line_regeneration_complete(self, update_data):
        self.stop_progress_indicator()
        self.set_ui_state(tk.NORMAL)
        original_index = update_data['original_index']
        # Update the clip_path in self.generated_clips_info
        for info in self.state.generated_clips_info:
            if info['original_index'] == original_index: info['clip_path'] = update_data['new_clip_path']; break
        if self.review_tree: self.review_tree.set(str(original_index), 'status', 'Regenerated')
        self.show_status_message(f"Line {original_index + 1} regenerated successfully.", "success")

    def upload_ebook(self):
        filepath_str = filedialog.askopenfilename(title="Select an Ebook File", filetypes=[("Ebook Files", "*.epub *.mobi *.pdf *.azw3"), ("All Files", "*.*")])
        if filepath_str: self.logic.process_ebook_path(filepath_str)

    def handle_drop(self, event):
        filepath_str = event.data.strip('{}'); self.logic.process_ebook_path(filepath_str)
        
    def save_edited_text(self):
        if not self.state.txt_path:
            self.show_status_message("Error: No text file path is set. Cannot save.", "error")
            return # return messagebox.showerror("Error", "No text file path is set.")
        try:
            with open(self.state.txt_path, 'w', encoding='utf-8') as f: f.write(self.editor_view.text_editor.get('1.0', tk.END))
            self.show_status_message("Changes have been saved successfully.", "success")
            # messagebox.showinfo("Success", f"Changes have been saved.")
        except Exception as e:
            self.show_status_message(f"Save Error: Could not save changes. Error: {e}", "error")
            # messagebox.showerror("Save Error", f"Could not save changes.\n\nError: {e}")

    def update_treeview_item_tags(self, treeview_widget):
        # This method is now a wrapper if specific app logic is needed before calling the theming function.
        # Or, it can be removed if all calls go directly to theming.update_treeview_item_tags(self, treeview_widget)
        theming.update_treeview_item_tags(self, treeview_widget)

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
        ConfirmationDialog(self.root, dialog_title, dialog_message, countdown_seconds, perform_actual_action_callback, self._theme_colors if self._theme_colors else theming.LIGHT_THEME)

    def confirm_back_to_analysis_from_review(self):
        if messagebox.askyesno("Confirm Navigation", "Going back will discard current generated audio clips. You'll need to regenerate them. Are you sure?"):
            self.state.generated_clips_info = [] # Clear generated clips
            if self.review_tree: self.review_tree.delete(*self.review_tree.get_children()) # Clear review tree
            # Important: We must clear the stop request flag before navigating
            self.state.stop_requested = False
            self.show_cast_refinement_view()

    def back_to_analysis_button_click(self):
        """Requests the audio generation to stop before navigating back."""
        # Check if the current thread is the generation task
        if (self.state.last_operation == 'generation' and
                self.state.active_thread and
                self.state.active_thread.is_alive()):
            if not messagebox.askyesno("Confirm Cancel & Navigate Back", "Audio generation is in progress. Going back will cancel it and you'll need to regenerate audio later. Are you sure?"):
                return  # User cancelled the back navigation

        # If not generating or user confirms, proceed to stop generation and navigate
        self.logic.stop_audio_generation()  # Request the generation thread to stop
        self.confirm_back_to_analysis_from_review()  # Then handle the navigation
        
    def save_voice_config(self):
        config_path = self.state.output_dir / "voices_config.json"
        
        # Filter self.voices to only include user-added voices (those with actual file paths)
        # and engine-specific internal voices.
        voices_to_save = []
        for v_info in self.state.voices:
            # Check if it's a user-added voice with a real file path
            is_user_file_voice = False
            try:
                if Path(v_info['path']).is_file():
                    is_user_file_voice = True
            except (TypeError, ValueError): # Path might be non-path-like string for internal voices
                pass
            
            if is_user_file_voice:
                voices_to_save.append(v_info)

        config_data = {
            "voices": voices_to_save, # Save only user-added file-based voices
            "default_voice_name": self.state.default_voice_info['name'] if self.state.default_voice_info else None
        }
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=4, ensure_ascii=False)
            self.logic.logger.info(f"Voice configuration saved to {config_path}")
        except Exception as e:
            self.logic.logger.error(f"Error saving voice configuration: {e}")

    def load_voice_config(self):
        config_path = self.state.output_dir / "voices_config.json"
        if config_path.exists():
            needs_resave = False
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)
                
                loaded_voices = config_data.get("voices", [])
                valid_voices = []
                for voice in loaded_voices:
                    if Path(voice.get('path', '')).exists():
                        valid_voices.append(voice)
                    else:
                        self.logic.logger.warning(f"Pruning missing voice file from config: {voice.get('name')} at {voice.get('path')}")
                        needs_resave = True
                
                self.state.voices = valid_voices
                self.state.loaded_default_voice_name_from_config = config_data.get("default_voice_name")

                if self.state.loaded_default_voice_name_from_config:
                    self.state.default_voice_info = next((v for v in self.state.voices if v['name'] == self.state.loaded_default_voice_name_from_config), None)
                else:
                    self.state.default_voice_info = None
                self.logic.logger.info(f"Voice configuration loaded. Found {len(self.state.voices)} valid voices. Saved default: {self.state.loaded_default_voice_name_from_config or 'None'}.")
                if needs_resave: self.save_voice_config() # Clean up the config file
            except Exception as e:
                self.logic.logger.error(f"Error loading voice configuration: {e}. Starting with empty voice list.")
                self.state.voices, self.state.default_voice_info, self.state.loaded_default_voice_name_from_config = [], None, None
        else:
            self.logic.logger.info(f"Voice configuration file not found at {config_path}. Starting with empty voice list.")
            self.state.voices, self.state.default_voice_info, self.state.loaded_default_voice_name_from_config = [], None, None

    def start_final_assembly_process(self):
        if not self.state.generated_clips_info:
            self.show_status_message("No audio clips available to assemble.", "warning")
            return # return messagebox.showwarning("No Audio", "No audio clips have been generated or retained for assembly.")
        self.show_status_message("Preparing for final assembly...", "info")
        self.logic.start_assembly(self.state.generated_clips_info) # Pass the list of clips

    def open_directory(self, path_to_open):
        """Opens the specified directory in the system's file explorer."""
        try:
            path_to_open = Path(path_to_open) # Ensure it's a Path object
            if not path_to_open.exists() or not path_to_open.is_dir():
                self.show_status_message(f"Error: Directory not found: {path_to_open}", "error")
                self.logic.logger.error(f"Attempted to open non-existent directory: {path_to_open}")
                return

            system_os = platform.system()
            self.logic.logger.info(f"Opening directory: {path_to_open} on OS: {system_os}")
            if system_os == "Windows":
                os.startfile(str(path_to_open))
            elif system_os == "Darwin": # macOS
                subprocess.run(['open', str(path_to_open)], check=True)
            else: # Linux and other Unix-like
                subprocess.run(['xdg-open', str(path_to_open)], check=True)
            # self.show_status_message(f"Opened directory: {path_to_open}", "info") # Optional: can be noisy
        except FileNotFoundError as e: # For xdg-open or open if not found
            self.show_status_message(f"Error: Could not open directory. Command not found: {e.filename}", "error")
            self.logic.logger.error(f"Error opening directory {path_to_open}: Command not found - {e}")
        except (subprocess.CalledProcessError, Exception) as e: # For errors from open/xdg-open or other issues
            self.show_status_message(f"Error: Failed to open directory: {e}", "error")
            self.logic.logger.error(f"Error opening directory {path_to_open}: {e}")
