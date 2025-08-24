# dialogs.py
import tkinter as tk
from tkinter import simpledialog, messagebox, scrolledtext, ttk
from pathlib import Path

class AddVoiceDialog(simpledialog.Dialog):
    def __init__(self, parent, theme_colors):
        self.theme_colors = theme_colors
        self.result = None
        super().__init__(parent, "Add New Voice")

    def body(self, master):
        bg_color = self.theme_colors.get("frame_bg", "#F0F0F0")
        fg_color = self.theme_colors.get("fg", "#000000")
        master.config(bg=bg_color)

        tk.Label(master, text="Voice Name:", bg=bg_color, fg=fg_color).grid(row=0, column=0, sticky="w", padx=5, pady=2)
        self.name_entry = tk.Entry(master, width=30)
        self.name_entry.grid(row=0, column=1, padx=5, pady=2)

        tk.Label(master, text="Gender:", bg=bg_color, fg=fg_color).grid(row=1, column=0, sticky="w", padx=5, pady=2)
        self.gender_var = tk.StringVar(master); self.gender_var.set("Unknown")
        tk.OptionMenu(master, self.gender_var, "Unknown", "Male", "Female", "Neutral").grid(row=1, column=1, sticky="ew", padx=5, pady=2)

        tk.Label(master, text="Age Range:", bg=bg_color, fg=fg_color).grid(row=2, column=0, sticky="w", padx=5, pady=2)
        self.age_range_var = tk.StringVar(master); self.age_range_var.set("Unknown")
        tk.OptionMenu(master, self.age_range_var, "Unknown", "Child", "Teenager", "Young Adult", "Adult", "Elderly").grid(row=2, column=1, sticky="ew", padx=5, pady=2)

        tk.Label(master, text="Language (e.g., en):", bg=bg_color, fg=fg_color).grid(row=3, column=0, sticky="w", padx=5, pady=2)
        self.language_entry = tk.Entry(master, width=30); self.language_entry.insert(0, "en")
        self.language_entry.grid(row=3, column=1, padx=5, pady=2)

        tk.Label(master, text="Accent (e.g., American, British):", bg=bg_color, fg=fg_color).grid(row=4, column=0, sticky="w", padx=5, pady=2)
        self.accent_entry = tk.Entry(master, width=30) 
        self.accent_entry.grid(row=4, column=1, padx=5, pady=2)

        # Add tooltips/help text in a real app
        # ToolTip(self.language_entry, "e.g., en, fr, es")
        # ToolTip(self.accent_entry, "e.g., American, British, Canadian")
        
        return self.name_entry # Initial focus

    def apply(self):
        voice_name = self.name_entry.get().strip()
        if not voice_name:
            messagebox.showwarning("Name Required", "Voice name cannot be empty.", parent=self) # Ensure parent is set for modality
            return
        # Path is handled in the add_new_voice method after dialog closes
        self.result = {
            'name': voice_name,
            'gender': self.gender_var.get(),
            'age_range': self.age_range_var.get(),
            'language': self.language_entry.get().strip() or "Unknown", # Default if empty
            'accent': self.accent_entry.get().strip() or "Unknown"      # Default if empty
        }

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

class VoiceSelectionDialog(simpledialog.Dialog):
    def __init__(self, parent, app_controller, theme_colors, voice_type: str): # voice_type: "narrator" or "speaker"
        self.app_controller = app_controller
        self.theme_colors = theme_colors
        self.voice_type = voice_type
        self.selected_voice = None
        super().__init__(parent, f"Select {voice_type.title()} Voice")

    def body(self, master):
        bg_color = self.theme_colors.get("frame_bg", "#F0F0F0")
        fg_color = self.theme_colors.get("fg", "#000000")
        master.config(bg=bg_color)

        tk.Label(master, text=f"Select a voice for the {self.voice_type}:", bg=bg_color, fg=fg_color).pack(pady=10)

        # Dropdown for existing voices
        voice_names = sorted([v['name'] for v in self.app_controller.state.voices])
        self.voice_var = tk.StringVar(master)
        if voice_names:
            self.voice_var.set(voice_names[0])
        
        self.voice_dropdown = ttk.Combobox(master, textvariable=self.voice_var, values=voice_names, state="readonly")
        self.voice_dropdown.pack(pady=5)

        tk.Button(master, text="Add New Voice", command=self._add_new_voice, bg=self.theme_colors.get("button_bg"), fg=self.theme_colors.get("fg")).pack(pady=10)

        return self.voice_dropdown # initial focus

    def _add_new_voice(self):
        dialog = AddVoiceDialog(self, self.theme_colors)
        if dialog.result:
            # Add the new voice to the app_controller's state
            new_voice_data = dialog.result
            
            filepath_str = filedialog.askopenfilename(
                title=f"Select a 10-30s sample .wav for '{new_voice_data['name']}'",
                filetypes=[("WAV Audio Files", "*.wav")])
            if not filepath_str: return

            if self.app_controller.add_voice_from_dialog_data(new_voice_data, filepath_str):
                # Update dropdown values only if voice was successfully added
                voice_names = sorted([v['name'] for v in self.app_controller.state.voices])
                self.voice_dropdown.config(values=voice_names)
                self.voice_var.set(new_voice_data['name']) # Select the newly added voice

    def apply(self):
        selected_name = self.voice_var.get()
        self.selected_voice = next((v for v in self.app_controller.state.voices if v['name'] == selected_name), None)
        if not self.selected_voice:
            messagebox.showwarning("No Voice Selected", "Please select a voice.", parent=self)
            return False
        return True

class PreflightDialog(simpledialog.Dialog):
    def __init__(self, parent, app_controller, ebook_queue, theme_colors):
        self.app_controller = app_controller
        self.ebook_queue = ebook_queue
        self.theme_colors = theme_colors
        self.result = False # Default to not proceeding
        super().__init__(parent, "Batch Conversion Pre-flight")

    def body(self, master):
        bg_color = self.theme_colors.get("frame_bg", "#F0F0F0")
        fg_color = self.theme_colors.get("fg", "#000000")
        master.config(bg=bg_color)

        tk.Label(master, text="Review Batch Conversion Settings", font=("Helvetica", 12, "bold"), bg=bg_color, fg=fg_color).pack(pady=10)

        # Ebook List
        tk.Label(master, text=f"Ebooks to process ({len(self.ebook_queue)}):", bg=bg_color, fg=fg_color).pack(anchor='w', padx=5, pady=(5,0))
        ebook_list_frame = tk.Frame(master, bg=bg_color)
        ebook_list_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        ebook_list_text = scrolledtext.ScrolledText(ebook_list_frame, width=60, height=10, wrap=tk.WORD, bg=self.theme_colors.get("text_bg"), fg=self.theme_colors.get("text_fg"))
        ebook_list_text.pack(fill=tk.BOTH, expand=True)
        for ebook_path in self.ebook_queue:
            ebook_list_text.insert(tk.END, f"- {ebook_path.name}\n")
        ebook_list_text.config(state=tk.DISABLED)

        # Voicing Mode Warning
        self.voicing_mode_label = tk.Label(master, text=f"Voicing Mode: {self.app_controller.state.voicing_mode.value}", bg=bg_color, fg=fg_color)
        self.voicing_mode_label.pack(anchor='w', padx=5, pady=(10,0))

        if self.app_controller.state.voicing_mode == self.app_controller.state.VoicingMode.CAST:
            self.cast_warning_label = tk.Label(master, text="Warning: 'Cast' mode is not advised for batch processing as it requires individual voice assignments. Unassigned characters will be skipped.", fg="red", wraplength=400, justify=tk.LEFT, bg=bg_color)
            self.cast_warning_label.pack(anchor='w', padx=5, pady=(5,10))

        # Narrator/Speaker Voice Selection
        if self.app_controller.state.voicing_mode in [self.app_controller.state.VoicingMode.NARRATOR, self.app_controller.state.VoicingMode.NARRATOR_AND_SPEAKER]:
            voice_config_frame = tk.LabelFrame(master, text="Default Voices", padx=5, pady=5, bg=bg_color, fg=fg_color)
            voice_config_frame.pack(fill=tk.X, padx=5, pady=10)

            narrator_set = bool(self.app_controller.state.narrator_voice_info)
            speaker_set = bool(self.app_controller.state.speaker_voice_info) if self.app_controller.state.voicing_mode == self.app_controller.state.VoicingMode.NARRATOR_AND_SPEAKER else True # Speaker not required for NARRATOR mode

            if narrator_set and speaker_set:
                confirm_message = "Default voices are already assigned. Do you want to use them for this batch?"
                if messagebox.askyesno("Confirm Default Voices", confirm_message, parent=self):
                    pass # User confirmed to use existing defaults
                else:
                    messagebox.showinfo("Change Voices", "You can change the voices below.", parent=self)
            elif not narrator_set or (self.app_controller.state.voicing_mode == self.app_controller.state.VoicingMode.NARRATOR_AND_SPEAKER and not speaker_set):
                messagebox.showinfo("Assign Voices", "Please assign default voices for this batch.", parent=self)

            # Narrator Voice
            self.narrator_voice_display_label = tk.Label(voice_config_frame, text=f"Narrator: {self.app_controller.state.narrator_voice_info['name'] if self.app_controller.state.narrator_voice_info else 'None'}", bg=bg_color, fg=fg_color)
            self.narrator_voice_display_label.pack(anchor='w', pady=(0,5))
            tk.Button(voice_config_frame, text="Change Narrator Voice", command=lambda: self._change_voice("narrator"), bg=self.theme_colors.get("button_bg"), fg=self.theme_colors.get("fg")).pack(fill=tk.X, pady=(0,5))

            # Speaker Voice (only for Narrator & Speaker mode)
            if self.app_controller.state.voicing_mode == self.app_controller.state.VoicingMode.NARRATOR_AND_SPEAKER:
                self.speaker_voice_display_label = tk.Label(voice_config_frame, text=f"Speaker: {self.app_controller.state.speaker_voice_info['name'] if self.app_controller.state.speaker_voice_info else 'None'}", bg=bg_color, fg=fg_color)
                self.speaker_voice_display_label.pack(anchor='w', pady=(0,5))
                tk.Button(voice_config_frame, text="Change Speaker Voice", command=lambda: self._change_voice("speaker"), bg=self.theme_colors.get("button_bg"), fg=self.theme_colors.get("fg")).pack(fill=tk.X, pady=(0,5))

        return ebook_list_text # Initial focus

    def _change_voice(self, voice_type: str):
        dialog = VoiceSelectionDialog(self, self.app_controller, self.theme_colors, voice_type)
        if dialog.selected_voice:
            if voice_type == "narrator":
                self.app_controller.state.narrator_voice_info = dialog.selected_voice
                self.narrator_voice_display_label.config(text=f"Narrator: {dialog.selected_voice['name']}")
            elif voice_type == "speaker":
                self.app_controller.state.speaker_voice_info = dialog.selected_voice
                self.speaker_voice_display_label.config(text=f"Speaker: {dialog.selected_voice['name']}")
            self.app_controller.save_voice_config() # Save changes immediately

    def apply(self):
        # Check if required voices are set before proceeding
        if self.app_controller.state.voicing_mode in [self.app_controller.state.VoicingMode.NARRATOR, self.app_controller.state.VoicingMode.NARRATOR_AND_SPEAKER]:
            if not self.app_controller.state.narrator_voice_info:
                messagebox.showwarning("Missing Voice", "Please select a Narrator voice before proceeding.", parent=self)
                return False
            if self.app_controller.state.voicing_mode == self.app_controller.state.VoicingMode.NARRATOR_AND_SPEAKER and not self.app_controller.state.speaker_voice_info:
                messagebox.showwarning("Missing Voice", "Please select a Speaker voice before proceeding.", parent=self)
                return False
        self.result = True
        return True

    def buttonbox(self):
        box = tk.Frame(self)
        bg_color = self.theme_colors.get("frame_bg", "#F0F0F0")
        button_bg = self.theme_colors.get("button_bg", "#D9D9D9")
        fg_color = self.theme_colors.get("fg", "#000000")
        box.config(bg=bg_color)

        w = tk.Button(box, text="Start Batch Conversion", width=20, command=self.ok, default=tk.ACTIVE, bg=button_bg, fg=fg_color)
        w.pack(side=tk.LEFT, padx=5, pady=5)
        w = tk.Button(box, text="Cancel", width=10, command=self.cancel, bg=button_bg, fg=fg_color)
        w.pack(side=tk.LEFT, padx=5, pady=5)

        self.bind("<Return>", self.ok)
        self.bind("<Escape>", self.cancel)

        box.pack()
