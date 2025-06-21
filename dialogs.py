# dialogs.py
import tkinter as tk
from tkinter import simpledialog, messagebox

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