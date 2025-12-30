# dialogs.py
import tkinter as tk
from tkinter import simpledialog, messagebox, scrolledtext, ttk, filedialog
from pathlib import Path
from app_state import VoicingMode

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


class MetadataEditorDialog(simpledialog.Dialog):
    """Dialog to create or edit a metadata CSV for XTTS training.

    The dialog accepts an optional list of WAV filenames to help auto-populate the left column.
    On success, `self.result` is set to the path of a temporary metadata CSV file.
    """
    def __init__(self, parent, theme_colors, wav_filenames: list[str] | None = None, initial_metadata_path: str | None = None):
        self.theme_colors = theme_colors
        self.wav_filenames = list(wav_filenames) if wav_filenames else []
        self.initial_metadata_path = initial_metadata_path
        self.result = None
        super().__init__(parent, "Metadata Editor")

    def body(self, master):
        bg_color = self.theme_colors.get("frame_bg", "#F0F0F0")
        fg_color = self.theme_colors.get("fg", "#000000")
        master.config(bg=bg_color)

        tk.Label(master, text="Metadata CSV (format: filename|transcript)", bg=bg_color, fg=fg_color).pack(pady=(5,0))

        # Instruction label
        tk.Label(master, text="One entry per line. Use the WAV filename (basename) in the left column.", bg=bg_color, fg=fg_color, font=(None, 9, "italic")).pack(pady=(0,5))

        self.text = scrolledtext.ScrolledText(master, width=80, height=12, bg=self.theme_colors.get("text_bg"), fg=self.theme_colors.get("text_fg"))
        self.text.pack(padx=5, pady=5, fill=tk.BOTH, expand=True)

        button_frame = tk.Frame(master, bg=bg_color)
        button_frame.pack(fill=tk.X, pady=(0,5))

        tk.Button(button_frame, text="Auto-Populate Filenames", command=self._auto_populate, bg=self.theme_colors.get("button_bg"), fg=fg_color).pack(side=tk.LEFT, padx=(5,0))
        tk.Button(button_frame, text="Fill Missing Transcripts", command=self._on_fill_missing_clicked, bg=self.theme_colors.get("button_bg"), fg=fg_color).pack(side=tk.LEFT, padx=(5,0))
        tk.Button(button_frame, text="Load CSV", command=self._load_csv, bg=self.theme_colors.get("button_bg"), fg=fg_color).pack(side=tk.LEFT, padx=(5,0))
        tk.Button(button_frame, text="Save As...", command=self._save_as, bg=self.theme_colors.get("button_bg"), fg=fg_color).pack(side=tk.RIGHT, padx=(0,5))

        # If initial metadata path provided, load it
        if self.initial_metadata_path:
            try:
                with open(self.initial_metadata_path, 'r', encoding='utf-8') as f:
                    self.text.delete('1.0', tk.END)
                    self.text.insert(tk.END, f.read())
            except Exception as e:
                tk.messagebox.showwarning("Load Error", f"Could not load initial metadata: {e}")

        # If wav filenames provided, auto-populate a basic template
        if self.wav_filenames and not self.initial_metadata_path:
            self._auto_populate()

        return self.text

    def _auto_populate(self):
        # Add any filenames that are not already present in the editor, with empty transcripts
        existing = set()
        for line in self.text.get('1.0', tk.END).splitlines():
            if not line.strip():
                continue
            parts = line.split('|', 1)
            existing.add(parts[0].strip())

        lines_to_add = []
        for fname in self.wav_filenames:
            b = Path(fname).name
            if b not in existing:
                lines_to_add.append(f"{b}| ")

        if lines_to_add:
            self.text.insert(tk.END, "\n".join(lines_to_add) + "\n")

    def _fill_missing_transcripts(self):
        """Fill blank transcripts or add missing filenames with placeholder transcripts."""
        lines = self.text.get('1.0', tk.END).splitlines()
        out_lines = []
        blanks = 0
        for line in lines:
            if not line.strip():
                continue
            parts = line.split('|', 1)
            fname = parts[0].strip()
            transcript = parts[1].strip() if len(parts) > 1 else ''
            if not transcript:
                blanks += 1
                # Default fill uses filename without extension as a plausible transcript
                transcript = Path(fname).stem
            out_lines.append(f"{fname}|{transcript}")

        # Ensure all selected wavs are present
        present = {Path(l.split('|',1)[0].strip()).name for l in out_lines}
        for fname in self.wav_filenames:
            b = Path(fname).name
            if b not in present:
                out_lines.append(f"{b}|{Path(b).stem}")

        # Replace editor contents
        self.text.delete('1.0', tk.END)
        self.text.insert(tk.END, '\n'.join(out_lines) + ('\n' if out_lines else ''))
        return blanks, len(self.wav_filenames) - len(present) if self.wav_filenames else 0

    def _load_csv(self):
        path = filedialog.askopenfilename(title="Select metadata CSV", filetypes=[("CSV Files", "*.csv;*.txt")])
        if not path:
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                self.text.delete('1.0', tk.END)
                self.text.insert(tk.END, f.read())
        except Exception as e:
            messagebox.showerror("Load Error", f"Failed to load CSV: {e}")

    def _on_fill_missing_clicked(self):
        blanks, missing = self._fill_missing_transcripts()
        msg_parts = []
        if blanks:
            msg_parts.append(f"Filled {blanks} blank transcript(s) using filenames as text.")
        if missing:
            msg_parts.append(f"Added {missing} missing filename entry(ies) with filename-based transcripts.")
        if msg_parts:
            messagebox.showinfo("Auto-Fill Complete", "\n".join(msg_parts))
        else:
            messagebox.showinfo("Nothing To Fill", "No missing filenames or blank transcripts found.")

    def _save_as(self):
        path = filedialog.asksaveasfilename(title="Save metadata CSV", defaultextension='.csv', filetypes=[("CSV Files", "*.csv")])
        if not path:
            return
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(self.text.get('1.0', tk.END))
            tk.messagebox.showinfo("Saved", f"Metadata saved to {path}")
        except Exception as e:
            tk.messagebox.showerror("Save Error", f"Could not save metadata: {e}")

    def validate(self):
        # Basic validation: ensure each non-empty line contains a '|' and a filename
        lines = [l for l in self.text.get('1.0', tk.END).splitlines() if l.strip()]
        filenames_in_metadata = set()
        blanks = []
        for i, line in enumerate(lines, start=1):
            if '|' not in line:
                messagebox.showwarning("Validation Error", f"Line {i} is missing a '|' separator: {line}")
                return False
            fname = line.split('|', 1)[0].strip()
            transcript = line.split('|', 1)[1].strip() if '|' in line else ''
            if not fname:
                messagebox.showwarning("Validation Error", f"Line {i} is missing a filename: {line}")
                return False
            filenames_in_metadata.add(fname)
            if not transcript:
                blanks.append((i, fname))

        # Check for missing selected WAVs
        missing_selected = [Path(f).name for f in (self.wav_filenames or []) if Path(f).name not in filenames_in_metadata]
        if missing_selected:
            resp = messagebox.askyesno("Missing Files", f"The following selected WAVs are missing from the metadata:\n\n{', '.join(missing_selected)}\n\nWould you like to auto-add them with placeholder transcripts? (You can edit before saving)")
            if resp:
                self._auto_populate()
                return self.validate()  # Re-validate after auto-populating
            else:
                return False

        if blanks:
            resp = messagebox.askyesno("Blank Transcripts", f"{len(blanks)} blank transcript(s) detected.\nWould you like to auto-fill blanks using the filename (without extension)?")
            if resp:
                self._fill_missing_transcripts()
                return self.validate()
            else:
                # Let user edit manually
                return False

        return True

    def apply(self):
        # On OK, write to a temporary file and set self.result
        import tempfile
        if not self.validate():
            return False
        try:
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.csv', mode='w', encoding='utf-8')
            tmp.write(self.text.get('1.0', tk.END))
            tmp.close()
            self.result = tmp.name
        except Exception as e:
            tk.messagebox.showerror("Save Error", f"Could not write temp metadata file: {e}")
            self.result = None
            return False
        return True


class TrainingOptionsDialog(simpledialog.Dialog):
    """Dialog to collect training hyperparameters for XTTS.

    Returns a dict in `self.result` on success, like:
      {'epochs': 50, 'batch_size': 8, 'learning_rate':0.0005, 'device': 'auto', 'num_workers': 2}
    """
    def __init__(self, parent, theme_colors, defaults: dict | None = None):
        self.theme_colors = theme_colors
        self.defaults = defaults or {}
        self.result = None
        super().__init__(parent, "Training Options")

    def body(self, master):
        bg_color = self.theme_colors.get("frame_bg", "#F0F0F0")
        fg_color = self.theme_colors.get("fg", "#000000")
        master.config(bg=bg_color)

        # Defaults
        epochs = self.defaults.get('epochs', 30)
        batch_size = self.defaults.get('batch_size', 8)
        lr = self.defaults.get('learning_rate', 0.0005)
        device = self.defaults.get('device', 'auto') # 'auto'|'cpu'|'gpu'
        num_workers = self.defaults.get('num_workers', 2)

        # Rows
        row = 0
        tk.Label(master, text="Epochs:", bg=bg_color, fg=fg_color).grid(row=row, column=0, sticky='w', padx=5, pady=3)
        self.epochs_var = tk.IntVar(value=epochs)
        tk.Entry(master, textvariable=self.epochs_var, width=10).grid(row=row, column=1, sticky='w', padx=5, pady=3)
        row += 1

        tk.Label(master, text="Batch Size:", bg=bg_color, fg=fg_color).grid(row=row, column=0, sticky='w', padx=5, pady=3)
        self.batch_var = tk.IntVar(value=batch_size)
        tk.Entry(master, textvariable=self.batch_var, width=10).grid(row=row, column=1, sticky='w', padx=5, pady=3)
        row += 1

        tk.Label(master, text="Learning Rate:", bg=bg_color, fg=fg_color).grid(row=row, column=0, sticky='w', padx=5, pady=3)
        self.lr_var = tk.DoubleVar(value=lr)
        tk.Entry(master, textvariable=self.lr_var, width=10).grid(row=row, column=1, sticky='w', padx=5, pady=3)
        row += 1

        tk.Label(master, text="Device:", bg=bg_color, fg=fg_color).grid(row=row, column=0, sticky='w', padx=5, pady=3)
        self.device_var = tk.StringVar(value=device)
        tk.OptionMenu(master, self.device_var, 'auto', 'cpu', 'gpu').grid(row=row, column=1, sticky='w', padx=5, pady=3)
        row += 1

        tk.Label(master, text="Num Workers:", bg=bg_color, fg=fg_color).grid(row=row, column=0, sticky='w', padx=5, pady=3)
        self.workers_var = tk.IntVar(value=num_workers)
        tk.Entry(master, textvariable=self.workers_var, width=10).grid(row=row, column=1, sticky='w', padx=5, pady=3)
        row += 1

        return None

    def validate(self):
        if self.epochs_var.get() <= 0:
            messagebox.showwarning("Invalid Value", "Epochs must be a positive integer.")
            return False
        if self.batch_var.get() <= 0:
            messagebox.showwarning("Invalid Value", "Batch size must be a positive integer.")
            return False
        if not (0 < self.lr_var.get() < 1):
            messagebox.showwarning("Invalid Value", "Learning rate must be between 0 and 1.")
            return False
        if self.workers_var.get() < 0:
            messagebox.showwarning("Invalid Value", "Num workers must be 0 or greater.")
            return False
        return True

    def apply(self):
        self.result = {
            'epochs': int(self.epochs_var.get()),
            'batch_size': int(self.batch_var.get()),
            'learning_rate': float(self.lr_var.get()),
            'device': self.device_var.get(),
            'num_workers': int(self.workers_var.get())
        }
        return True


class EnvironmentSelectionDialog(simpledialog.Dialog):
    """Dialog to select a Python executable (virtualenv) to use for training.

    Expects env_options as a list of tuples (label, python_executable_path).
    On success, `self.result` is set to the selected python executable path.
    """
    def __init__(self, parent, theme_colors, env_options: list | None = None, default_selected: str | None = None):
        self.theme_colors = theme_colors
        self.env_options = list(env_options) if env_options else []
        self.default_selected = default_selected
        self.result = None
        super().__init__(parent, "Select Training Environment")

    def body(self, master):
        bg_color = self.theme_colors.get("frame_bg", "#F0F0F0")
        fg_color = self.theme_colors.get("fg", "#000000")
        master.config(bg=bg_color)

        tk.Label(master, text="Select a Python executable to run training in:", bg=bg_color, fg=fg_color).pack(pady=(8,4))

        # Build display values
        self.mapping = {}
        display_values = []
        for label, exe in self.env_options:
            display = f"{label} ({exe})"
            display_values.append(display)
            self.mapping[display] = exe

        # Allow a 'Browse...' option to choose a custom python executable
        display_values.append("Browse...")

        self.selection_var = tk.StringVar(master)
        if display_values:
            # Pick a default if possible
            if self.default_selected:
                default_display = next((k for k, v in self.mapping.items() if v == self.default_selected), display_values[0])
                self.selection_var.set(default_display)
            else:
                self.selection_var.set(display_values[0])

        self.combo = ttk.Combobox(master, values=display_values, textvariable=self.selection_var, state="readonly", width=100)
        self.combo.pack(padx=8, pady=6)

        browse_frame = tk.Frame(master, bg=bg_color)
        browse_frame.pack(fill=tk.X, padx=8, pady=(0,8))
        tk.Button(browse_frame, text="Browse for Python...", command=self._on_browse, bg=self.theme_colors.get("button_bg"), fg=fg_color).pack(side=tk.LEFT)
        tk.Label(browse_frame, text="(You can select an existing environment or browse for a Python executable)", bg=bg_color, fg=fg_color).pack(side=tk.LEFT, padx=(8,0))

        return self.combo

    def _on_browse(self):
        path = filedialog.askopenfilename(title="Select Python executable", filetypes=[("Python", "python.exe;python")])
        if not path:
            return
        display = f"Custom ({path})"
        vals = list(self.combo['values'])
        if display not in vals:
            vals.insert(0, display)
            self.combo.config(values=vals)
        self.selection_var.set(display)
        self.mapping[display] = path

    def validate(self):
        sel = self.selection_var.get()
        if not sel:
            messagebox.showwarning("Select Environment", "Please select a training environment or cancel.", parent=self)
            return False
        exe = self.mapping.get(sel)
        if not exe:
            messagebox.showwarning("Invalid Selection", "The selected option does not point to a valid Python executable.", parent=self)
            return False
        if not Path(exe).is_file():
            messagebox.showwarning("Not Found", f"Python executable not found: {exe}", parent=self)
            return False
        self.result = exe
        return True


class InstallLogWindow(tk.Toplevel):
    """A simple log window used for showing pip install output during dependency installs."""
    def __init__(self, parent, theme_colors, title="Installer Log"):
        super().__init__(parent)
        self.transient(parent)
        self.title(title)
        self.theme_colors = theme_colors
        self.closed = False

        bg_color = self.theme_colors.get("frame_bg", "#F0F0F0")
        fg_color = self.theme_colors.get("text_fg", "#000000")
        self.config(bg=bg_color)

        self.text = scrolledtext.ScrolledText(self, width=100, height=20, bg=self.theme_colors.get("text_bg"), fg=fg_color)
        self.text.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.text.config(state=tk.DISABLED)

        btn_frame = tk.Frame(self, bg=bg_color)
        btn_frame.pack(fill=tk.X, padx=8, pady=(0,8))
        tk.Button(btn_frame, text="Save Log", command=self._save_log, bg=self.theme_colors.get("button_bg"), fg=fg_color).pack(side=tk.LEFT)
        tk.Button(btn_frame, text="Close", command=self._close, bg=self.theme_colors.get("button_bg"), fg=fg_color).pack(side=tk.RIGHT)
        self.protocol("WM_DELETE_WINDOW", self._close)

    def append_line(self, line: str):
        if self.closed:
            return
        def _append():
            try:
                self.text.config(state=tk.NORMAL)
                self.text.insert(tk.END, line + "\n")
                self.text.see(tk.END)
                self.text.config(state=tk.DISABLED)
            except Exception:
                pass
        try:
            self.after(0, _append)
        except Exception:
            pass

    def _save_log(self):
        path = filedialog.asksaveasfilename(title="Save installer log", defaultextension='.txt', filetypes=[("Text Files", "*.txt")])
        if not path:
            return
        try:
            content = self.text.get('1.0', tk.END)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            messagebox.showinfo("Saved", f"Installer log saved to {path}")
        except Exception as e:
            messagebox.showerror("Save Error", f"Could not save log: {e}")

    def _close(self):
        self.closed = True
        try:
            self.destroy()
        except Exception:
            pass


class DependencyInstallDialog(simpledialog.Dialog):
    """Dialog to show missing dependencies and optionally install them.

    The dialog accepts an optional `engine_context` to indicate whether the
    check was scoped to a particular TTS engine and an `all_candidates` list
    to enable the "Show all packages (advanced)" view. The user may check which
    packages to install.
    """
    def __init__(self, parent, theme_colors, missing: list[tuple], engine_context: str | None = None, all_candidates: list[tuple] | None = None):
        # missing: list of tuples (display_name, module_name, pip_spec)
        self.theme_colors = theme_colors
        self.missing = list(missing)
        self.engine_context = engine_context
        self.all_candidates = list(all_candidates) if all_candidates else []
        self._check_vars: dict[str, tk.BooleanVar] = {}
        self._displaying_all = False
        self.result = False
        super().__init__(parent, "Dependencies Missing")

    def _render_candidates(self, parent_frame, candidates: list[tuple]):
        # Clear any previous widgets
        try:
            children = parent_frame.winfo_children()
        except Exception:
            return
        for w in children:
            try:
                w.destroy()
            except Exception:
                pass
        self._check_vars.clear()

        if not candidates:
            tk.Label(parent_frame, text="No dependencies to show.", bg=self.theme_colors.get('frame_bg')).pack(anchor='w', padx=6)
            return

        for disp, mod, spec in candidates:
            key = f"{disp}||{mod}||{spec}"
            var = tk.BooleanVar(value=True if (disp,mod,spec) in self.missing else False)
            self._check_vars[key] = var
            cb = tk.Checkbutton(parent_frame, variable=var, text=f"{disp} — pip: {spec}", anchor='w', justify='left', bg=self.theme_colors.get('frame_bg'), fg=self.theme_colors.get('fg'))
            cb.pack(fill='x', anchor='w', padx=6, pady=1)

    def _on_toggle_show_all(self):
        self._displaying_all = bool(self.show_all_var.get())
        try:
            if not hasattr(self, 'candidates_frame') or not getattr(self.candidates_frame, 'winfo_exists', lambda: False)():
                return
        except Exception:
            return
        if self._displaying_all:
            self._render_candidates(self.candidates_frame, self.all_candidates)
        else:
            self._render_candidates(self.candidates_frame, self.missing)

    def body(self, master):
        bg_color = self.theme_colors.get("frame_bg", "#F0F0F0")
        fg_color = self.theme_colors.get("fg", "#000000")
        master.config(bg=bg_color)

        header_text = "Dependencies available for installation"
        tk.Label(master, text=header_text, bg=bg_color, fg=fg_color).pack(pady=(8,2), anchor='w', padx=8)

        # Candidate list frame (scroll if needed)
        frame_holder = tk.Frame(master, bg=bg_color)
        frame_holder.pack(fill='both', expand=False, padx=8)

        self.candidates_frame = tk.Frame(frame_holder, bg=bg_color)
        self.candidates_frame.pack(fill='both', expand=True)

        # Initially render only the missing set
        self._render_candidates(self.candidates_frame, self.missing)

        # Show a concise contextual note about scope
        if self.engine_context:
            note = f"Note: These suggestions are scoped for the selected engine/environment: {self.engine_context}."
        else:
            note = "Note: Suggestions are based on detected packages in the active Python environment."
        tk.Label(master, text=note, bg=bg_color, fg=fg_color, font=(None,9,"italic")).pack(pady=(6,4), padx=8, anchor='w')

        # Toggle to show all packages (advanced)
        self.show_all_var = tk.IntVar(value=0)
        tk.Checkbutton(master, text="Show all packages (advanced)", variable=self.show_all_var, command=self._on_toggle_show_all, bg=bg_color, fg=fg_color).pack(anchor='w', padx=8, pady=(0,6))

        tk.Label(master, text="Select which packages to install and click 'Install'. (Requires internet access)", bg=bg_color, fg=fg_color, font=(None,9)).pack(pady=(2,6), padx=8, anchor='w')

        return None
    def buttonbox(self):
        box = tk.Frame(self)
        bg_color = self.theme_colors.get("frame_bg", "#F0F0F0")
        button_bg = self.theme_colors.get("button_bg", "#D9D9D9")
        fg_color = self.theme_colors.get("fg", "#000000")
        tk.Button(box, text="Install", command=self._install, bg=button_bg, fg=fg_color).pack(side=tk.LEFT, padx=6, pady=8)
        tk.Button(box, text="Skip", command=self._skip, bg=button_bg, fg=fg_color).pack(side=tk.LEFT, padx=6, pady=8)
        box.pack()

    def _gather_selected_candidates(self) -> list[tuple]:
        """Return a list of selected candidate tuples (disp, mod, spec) based on checkbox state."""
        selected = []
        # iterate over either all_candidates or missing to find matching keys
        pool = self.all_candidates if self._displaying_all else self.missing
        for disp, mod, spec in pool:
            key = f"{disp}||{mod}||{spec}"
            var = self._check_vars.get(key)
            if var and var.get():
                selected.append((disp, mod, spec))
        return selected

    def _install(self):
        selected = self._gather_selected_candidates()
        if not selected:
            tk.messagebox.showinfo("Nothing Selected", "No packages selected for installation.", parent=self)
            return
        # Launch installer window and start background install for only selected packages
        installer = InstallLogWindow(self, self.theme_colors, title="Dependency Installer")
        import threading, subprocess, sys
        def _worker():
            for disp, mod, spec in selected:
                installer.append_line(f"Installing {spec}...")
                try:
                    proc = subprocess.Popen([sys.executable, '-m', 'pip', 'install', spec], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                    for line in proc.stdout:
                        installer.append_line(line.rstrip('\n'))
                    proc.wait()
                    if proc.returncode == 0:
                        installer.append_line(f"Installed {spec} successfully.")
                    else:
                        installer.append_line(f"Failed to install {spec} (exit {proc.returncode}).")
                except Exception as e:
                    installer.append_line(f"Exception installing {spec}: {e}")
            installer.append_line("Installation complete. Please restart the application if needed.")
        threading.Thread(target=_worker, daemon=True).start()
        self.result = True
        self.destroy()

    def _install(self):
        # Launch installer window and start background install
        installer = InstallLogWindow(self, self.theme_colors, title="Dependency Installer")
        import threading, subprocess, sys
        def _worker():
            for disp, mod, spec in self.missing:
                installer.append_line(f"Installing {spec}...")
                try:
                    proc = subprocess.Popen([sys.executable, '-m', 'pip', 'install', spec], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                    for line in proc.stdout:
                        installer.append_line(line.rstrip('\n'))
                    proc.wait()
                    if proc.returncode == 0:
                        installer.append_line(f"Installed {spec} successfully.")
                    else:
                        installer.append_line(f"Failed to install {spec} (exit {proc.returncode}).")
                except Exception as e:
                    installer.append_line(f"Exception installing {spec}: {e}")
            installer.append_line("Installation complete. Please restart the application if needed.")
        threading.Thread(target=_worker, daemon=True).start()
        self.result = True
        self.destroy()

    def _skip(self):
        self.result = False
        self.destroy()


class TrainingLogWindow(tk.Toplevel):
    """A live training log window with progress reporting and an appended log area."""
    def __init__(self, parent, theme_colors):
        super().__init__(parent)
        self.transient(parent)
        self.title("Training Log")
        self.theme_colors = theme_colors
        self.closed = False

        bg_color = self.theme_colors.get("frame_bg", "#F0F0F0")
        fg_color = self.theme_colors.get("text_fg", "#000000")
        self.config(bg=bg_color)

        # Progress bar and summary label at the top
        summary_frame = tk.Frame(self, bg=bg_color)
        summary_frame.pack(fill=tk.X, padx=8, pady=(8,0))

        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress_bar = ttk.Progressbar(summary_frame, orient='horizontal', mode='determinate', maximum=100.0, variable=self.progress_var)
        self.progress_bar.pack(fill=tk.X, padx=(0,6), expand=True, side=tk.LEFT)

        self.progress_summary = tk.Label(summary_frame, text="Progress: 0%", bg=bg_color, fg=fg_color, width=35, anchor='e')
        self.progress_summary.pack(side=tk.RIGHT)

        # Compact info labels beneath the progress bar
        info_frame = tk.Frame(self, bg=bg_color)
        info_frame.pack(fill=tk.X, padx=8, pady=(2,6))
        self.epoch_label = tk.Label(info_frame, text="Epoch: -", bg=bg_color, fg=fg_color)
        self.epoch_label.pack(side=tk.LEFT, padx=(0,10))
        self.step_label = tk.Label(info_frame, text="Step: -", bg=bg_color, fg=fg_color)
        self.step_label.pack(side=tk.LEFT, padx=(0,10))
        self.loss_label = tk.Label(info_frame, text="Loss: -", bg=bg_color, fg=fg_color)
        self.loss_label.pack(side=tk.LEFT, padx=(0,10))
        self.eta_label = tk.Label(info_frame, text="ETA: -", bg=bg_color, fg=fg_color)
        self.eta_label.pack(side=tk.LEFT)

        # The main scrolling text area for raw logs
        self.text = scrolledtext.ScrolledText(self, width=100, height=24, bg=self.theme_colors.get("text_bg"), fg=fg_color)
        self.text.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.text.config(state=tk.DISABLED)

        btn_frame = tk.Frame(self, bg=bg_color)
        btn_frame.pack(fill=tk.X, padx=8, pady=(0,8))
        tk.Button(btn_frame, text="Save Log", command=self._save_log, bg=self.theme_colors.get("button_bg"), fg=fg_color).pack(side=tk.LEFT)
        tk.Button(btn_frame, text="Clear", command=self._clear, bg=self.theme_colors.get("button_bg"), fg=fg_color).pack(side=tk.LEFT, padx=(5,0))
        tk.Button(btn_frame, text="Close", command=self._close, bg=self.theme_colors.get("button_bg"), fg=fg_color).pack(side=tk.RIGHT)

        # Track last progress to limit UI churn
        self._last_percent = None
        self._last_epoch = None

        # When the user closes the window via window manager
        self.protocol("WM_DELETE_WINDOW", self._close)

    def append_line(self, line: str):
        """Thread-safe append: schedule using `after` to run in the main thread."""
        if self.closed:
            return
        def _append():
            try:
                self.text.config(state=tk.NORMAL)
                self.text.insert(tk.END, line + "\n")
                self.text.see(tk.END)
                self.text.config(state=tk.DISABLED)
            except Exception:
                pass
        try:
            self.after(0, _append)
        except Exception:
            # If `after` can't be used (window destroyed), ignore
            pass

    def update_progress(self, info: dict):
        """Thread-safe update of the progress bar / labels. `info` is a parsed trainer dict."""
        if self.closed:
            return
        def _update():
            try:
                percent = info.get('percent')
                epoch = info.get('epoch')
                epoch_total = info.get('epoch_total')
                step = info.get('step')
                step_total = info.get('step_total')
                loss = info.get('loss')
                eta = info.get('eta')

                # Update percent if present
                if percent is not None:
                    try:
                        p = float(percent)
                        self.progress_var.set(max(0.0, min(100.0, p)))
                        self.progress_summary.config(text=f"Progress: {p:.1f}%")
                        self._last_percent = p
                    except Exception:
                        pass

                # Update epoch/step/loss/eta labels
                if epoch is not None and epoch_total is not None:
                    self.epoch_label.config(text=f"Epoch: {epoch}/{epoch_total}")
                    self._last_epoch = epoch
                elif epoch is not None:
                    self.epoch_label.config(text=f"Epoch: {epoch}")

                if step is not None and step_total is not None:
                    self.step_label.config(text=f"Step: {step}/{step_total}")
                elif step is not None:
                    self.step_label.config(text=f"Step: {step}")

                if loss is not None:
                    try:
                        self.loss_label.config(text=f"Loss: {float(loss):.4f}")
                    except Exception:
                        self.loss_label.config(text=f"Loss: {loss}")

                if eta is not None:
                    self.eta_label.config(text=f"ETA: {eta}")

                # Optionally append a short summary to the log for important milestones
                try:
                    summary_parts = []
                    if epoch is not None and epoch_total is not None:
                        summary_parts.append(f"Epoch {epoch}/{epoch_total}")
                    if step is not None and step_total is not None:
                        summary_parts.append(f"{step}/{step_total}")
                    if loss is not None:
                        summary_parts.append(f"loss={loss}")
                    if eta is not None:
                        summary_parts.append(f"ETA={eta}")
                    if summary_parts:
                        short = " | ".join(summary_parts)
                        # Append instead of always writing to avoid flooding
                        if (self._last_percent is None) or (info.get('percent') is not None and abs(info.get('percent') - (self._last_percent or 0)) >= 1) or (epoch is not None and epoch != self._last_epoch):
                            self.append_line(f"[PROGRESS] {short}")
                except Exception:
                    pass

            except Exception:
                pass
        try:
            self.after(0, _update)
        except Exception:
            pass

    def _save_log(self):
        path = filedialog.asksaveasfilename(title="Save training log", defaultextension='.txt', filetypes=[("Text Files", "*.txt")])
        if not path:
            return
        try:
            content = self.text.get('1.0', tk.END)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            messagebox.showinfo("Saved", f"Training log saved to {path}")
        except Exception as e:
            messagebox.showerror("Save Error", f"Could not save log: {e}")

    def _clear(self):
        self.text.config(state=tk.NORMAL)
        self.text.delete('1.0', tk.END)
        self.text.config(state=tk.DISABLED)

    def _close(self):
        self.closed = True
        try:
            self.destroy()
        except Exception:
            pass

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

        if self.app_controller.state.voicing_mode == VoicingMode.CAST:
            self.cast_warning_label = tk.Label(master, text="Warning: 'Cast' mode is not advised for batch processing as it requires individual voice assignments. Unassigned characters will be skipped.", fg="red", wraplength=400, justify=tk.LEFT, bg=bg_color)
            self.cast_warning_label.pack(anchor='w', padx=5, pady=(5,10))

        # Narrator/Speaker Voice Selection
        if self.app_controller.state.voicing_mode in [VoicingMode.NARRATOR, VoicingMode.NARRATOR_AND_SPEAKER]:
            voice_config_frame = tk.LabelFrame(master, text="Default Voices", padx=5, pady=5, bg=bg_color, fg=fg_color)
            voice_config_frame.pack(fill=tk.X, padx=5, pady=10)

            narrator_set = bool(self.app_controller.state.narrator_voice_info)
            speaker_set = bool(self.app_controller.state.speaker_voice_info) if self.app_controller.state.voicing_mode == VoicingMode.NARRATOR_AND_SPEAKER else True # Speaker not required for NARRATOR mode

            if narrator_set and speaker_set:
                confirm_message = "Default voices are already assigned. Do you want to use them for this batch?"
                if messagebox.askyesno("Confirm Default Voices", confirm_message, parent=self):
                    pass # User confirmed to use existing defaults
                else:
                    messagebox.showinfo("Change Voices", "You can change the voices below.", parent=self)
            elif not narrator_set or (self.app_controller.state.voicing_mode == VoicingMode.NARRATOR_AND_SPEAKER and not speaker_set):
                messagebox.showinfo("Assign Voices", "Please assign default voices for this batch.", parent=self)

            # Narrator Voice
            self.narrator_voice_display_label = tk.Label(voice_config_frame, text=f"Narrator: {self.app_controller.state.narrator_voice_info['name'] if self.app_controller.state.narrator_voice_info else 'None'}", bg=bg_color, fg=fg_color)
            self.narrator_voice_display_label.pack(anchor='w', pady=(0,5))
            tk.Button(voice_config_frame, text="Change Narrator Voice", command=lambda: self._change_voice("narrator"), bg=self.theme_colors.get("button_bg"), fg=self.theme_colors.get("fg")).pack(fill=tk.X, pady=(0,5))

            # Speaker Voice (only for Narrator & Speaker mode)
            if self.app_controller.state.voicing_mode == VoicingMode.NARRATOR_AND_SPEAKER:
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
        if self.app_controller.state.voicing_mode in [VoicingMode.NARRATOR, VoicingMode.NARRATOR_AND_SPEAKER]:
            if not self.app_controller.state.narrator_voice_info:
                messagebox.showwarning("Missing Voice", "Please select a Narrator voice before proceeding.", parent=self)
                return False
            if self.app_controller.state.voicing_mode == VoicingMode.NARRATOR_AND_SPEAKER and not self.app_controller.state.speaker_voice_info:
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
