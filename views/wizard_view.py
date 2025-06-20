# views/wizard_view.py
import tkinter as tk
from tkinterdnd2 import DND_FILES

class WizardView(tk.Frame):
    def __init__(self, master, app_controller):
        super().__init__(master)
        self.app_controller = app_controller # Reference to the main AudiobookCreatorApp
        self.pack(fill=tk.BOTH, expand=True) # Pack self into the master frame

        self._create_widgets()

    def _create_widgets(self):
        # Register DND for this frame
        self.drop_target_register(DND_FILES)
        self.dnd_bind('<<Drop>>', self.app_controller.handle_drop)

        self.info_label = tk.Label(self, text="Step 1 & 2: Upload and Convert", font=("Helvetica", 14, "bold"))
        self.info_label.pack(pady=(0, 10))

        # Keep upload_frame as an attribute if other methods in WizardView might need it,
        # or if app_controller needs to access it directly (though less ideal).
        # For now, it's local to _create_widgets if not accessed elsewhere.
        self.upload_frame = tk.Frame(self)
        self.upload_frame.pack(fill=tk.X)

        self.upload_button = tk.Button(self.upload_frame, text="Upload Ebook", command=self.app_controller.upload_ebook)
        self.upload_button.pack(side=tk.LEFT, expand=True, fill=tk.X, ipady=5)

        self.drop_info_label = tk.Label(self.upload_frame, text="<-- or Drag & Drop File Here", fg="grey")
        self.drop_info_label.pack(side=tk.LEFT, padx=10)

        self.file_status_label = tk.Label(self, text="No ebook selected.", wraplength=580, justify=tk.CENTER)
        self.file_status_label.pack(pady=5)

        self.next_step_button = tk.Button(self, text="Convert to Text", state=tk.DISABLED, command=self.app_controller.logic.start_conversion_process)
        self.next_step_button.pack(fill=tk.X, ipady=5, pady=5)

        self.edit_text_button = tk.Button(self, text="Step 3: Edit Text", state=tk.DISABLED, command=self.app_controller.show_editor_view)
        self.edit_text_button.pack(fill=tk.X, ipady=5, pady=5)

        # Register themed widgets with the app_controller
        self.app_controller._themed_tk_labels.extend([self.info_label, self.drop_info_label, self.file_status_label])
        self.app_controller._themed_tk_buttons.extend([self.upload_button, self.next_step_button, self.edit_text_button])