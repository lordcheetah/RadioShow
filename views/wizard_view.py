# views/wizard_view.py
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk

class WizardView(tk.Frame):
    def __init__(self, master, app_controller):
        super().__init__(master)
        self.app_controller = app_controller
        self.cover_image = None # To prevent garbage collection
        self.pack(fill=tk.BOTH, expand=True)
        self.pack_propagate(False)
        self._create_widgets()

    def _create_widgets(self):
        self.info_label = tk.Label(self, text="Step 1: Upload Ebook", font=("Helvetica", 14, "bold"))
        self.info_label.pack(pady=(10, 20), anchor='w', padx=10)

        self.main_frame = tk.Frame(self)
        self.main_frame.pack(pady=20, padx=20, fill=tk.X)

        # --- Left side for upload button and status ---
        self.upload_frame = tk.Frame(self.main_frame)
        self.upload_frame.pack(side=tk.LEFT, fill=tk.Y, anchor='n')

        self.upload_button = tk.Button(self.upload_frame, text="Upload Ebook", command=self.app_controller.upload_ebook)
        self.upload_button.pack(ipady=10, ipadx=10)

        self.file_status_label = tk.Label(self.upload_frame, text="No file selected.", wraplength=200, justify=tk.LEFT)
        self.file_status_label.pack(pady=(10,0), anchor='w')

        # --- Right side for metadata display ---
        self.metadata_frame = tk.Frame(self.main_frame)
        # This frame will be packed by the update method

        self.cover_label = tk.Label(self.metadata_frame)
        self.cover_label.pack(side=tk.LEFT, padx=(0, 10), anchor='n')

        self.info_frame = tk.Frame(self.metadata_frame)
        self.info_frame.pack(side=tk.LEFT, fill=tk.Y, anchor='n')

        self.title_label_header = tk.Label(self.info_frame, text="Title:", font=("Helvetica", 10, "bold"))
        self.title_label_header.pack(anchor='w')
        self.title_label = tk.Label(self.info_frame, text="", wraplength=300, justify=tk.LEFT)
        self.title_label.pack(anchor='w', pady=(0, 5))

        self.author_label_header = tk.Label(self.info_frame, text="Author:", font=("Helvetica", 10, "bold"))
        self.author_label_header.pack(anchor='w')
        self.author_label = tk.Label(self.info_frame, text="", wraplength=300, justify=tk.LEFT)
        self.author_label.pack(anchor='w')

        # --- Bottom navigation buttons ---
        self.bottom_frame = tk.Frame(self)
        self.bottom_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(10, 0), anchor=tk.S, padx=10)
        self.next_step_button = tk.Button(self.bottom_frame, text="Convert to Text", command=self.app_controller.logic.start_conversion_process, state=tk.DISABLED)
        self.next_step_button.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
        self.edit_text_button = tk.Button(self.bottom_frame, text="Edit Text / Skip to Analysis", command=self.app_controller.show_editor_view, state=tk.DISABLED)
        self.edit_text_button.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)

        # Register themed widgets
        self.app_controller._themed_tk_labels.extend([self.info_label, self.file_status_label, self.title_label_header, self.title_label, self.author_label_header, self.author_label])
        self.app_controller._themed_tk_buttons.extend([self.upload_button, self.next_step_button, self.edit_text_button])

    def update_metadata_display(self, title, author, cover_path):
        self.title_label.config(text=title or "N/A")
        self.author_label.config(text=author or "N/A")

        if cover_path:
            try:
                img = Image.open(cover_path)
                img.thumbnail((120, 180))
                self.cover_image = ImageTk.PhotoImage(img)
                self.cover_label.config(image=self.cover_image)
            except Exception as e:
                self.app_controller.logic.logger.error(f"Failed to load cover image for display: {e}")
                self.cover_label.config(image='')
        else:
            self.cover_label.config(image='')

        self.metadata_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(20, 0))