# views/editor_view.py
import tkinter as tk
from tkinter import scrolledtext

class EditorView(tk.Frame):
    def __init__(self, master, app_controller):
        super().__init__(master)
        self.app_controller = app_controller # Reference to the main AudiobookCreatorApp
        self.pack(fill=tk.BOTH, expand=True)

        self._create_widgets()

    def _create_widgets(self):
        self.info_label = tk.Label(self, text="Step 3: Review and Edit Text", font=("Helvetica", 14, "bold"))
        self.info_label.pack(pady=(0, 10))

        self.text_editor = scrolledtext.ScrolledText(self, wrap=tk.WORD, font=("Arial", 10))
        self.text_editor.pack(expand=True, fill=tk.BOTH, padx=5, pady=5)

        self.button_frame = tk.Frame(self) # Frame for buttons below editor
        self.button_frame.pack(fill=tk.X, pady=5)

        self.save_button = tk.Button(self.button_frame, text="Save Changes", command=self.app_controller.save_edited_text)
        self.save_button.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
        self.back_button = tk.Button(self.button_frame, text="< Back to Start", command=self.app_controller.show_wizard_view)
        self.back_button.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
        self.options_frame = tk.Frame(self)
        self.options_frame.pack(fill=tk.X, padx=5)
        self.single_quote_var = tk.BooleanVar(value=self.app_controller.state.use_single_quotes)
        self.single_quote_checkbox = tk.Checkbutton(
            self.options_frame,
            text="Detect single quotes as dialogue delimiters (use only if book uses 'quotes' for speech)",
            variable=self.single_quote_var,
            command=self._on_single_quote_toggled,
        )
        self.single_quote_checkbox.pack(anchor='w')

        self.analyze_button = tk.Button(self, text="Step 4: Analyze Characters", command=self.app_controller.start_hybrid_analysis)
        self.analyze_button.pack(fill=tk.X, ipady=5, pady=5)

        self.app_controller._themed_tk_labels.append(self.info_label)
        self.app_controller._themed_tk_buttons.extend([self.save_button, self.back_button, self.analyze_button])
        self.app_controller._themed_tk_frames.extend([self, self.button_frame, self.options_frame])
        self.app_controller._themed_tk_checkbuttons = getattr(self.app_controller, '_themed_tk_checkbuttons', [])
        self.app_controller._themed_tk_checkbuttons.append(self.single_quote_checkbox)

    def _on_single_quote_toggled(self):
        self.app_controller.state.use_single_quotes = self.single_quote_var.get()