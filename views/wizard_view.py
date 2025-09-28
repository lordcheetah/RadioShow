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
        # Pack bottom frame first to reserve its space at the bottom of the view
        self.bottom_frame = tk.Frame(self)
        self.bottom_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=10, padx=20)

        # Main container for a more guided, vertical layout
        container = tk.Frame(self)
        container.pack(pady=20, padx=20, fill=tk.BOTH, expand=True)

        self.info_label = tk.Label(container, text="Step 1: Upload Ebook", font=("Helvetica", 14, "bold"))
        self.info_label.pack(pady=(0, 20), anchor='w')

        # --- Drag and Drop Area ---
        self.drop_target_frame = tk.Frame(container, relief=tk.SUNKEN, borderwidth=2, height=100)
        self.drop_target_frame.pack(fill=tk.X, pady=10)
        self.drop_target_frame.pack_propagate(False) # Prevent it from shrinking
        self.drop_info_label = tk.Label(self.drop_target_frame, text="Drag and Drop Ebook File Here")
        self.drop_info_label.pack(expand=True)

        # --- Upload Button and Status ---
        self.upload_button = tk.Button(container, text="...or click to Upload Ebook", command=self.app_controller.upload_ebook)
        self.upload_button.pack(pady=(5, 10))

        # New button for folder selection
        self.select_folder_button = tk.Button(container, text="...or select a folder with Ebooks", command=self.app_controller.select_ebook_folder, state=tk.DISABLED)
        self.select_folder_button.pack(pady=(0, 10))

        self.file_status_label = tk.Label(container, text="No file selected.", wraplength=400, justify=tk.LEFT)
        self.file_status_label.pack(pady=(5, 10), anchor='w')

        # --- Metadata Display Area (initially hidden) ---
        self.metadata_display_frame = tk.Frame(container)
        # This frame is packed later by update_metadata_display

        self.cover_label = tk.Label(self.metadata_display_frame)
        self.cover_label.pack(side=tk.LEFT, padx=(0, 15), anchor='n')

        self.info_frame = tk.Frame(self.metadata_display_frame)
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
        self.next_step_button = tk.Button(self.bottom_frame, text="Convert to Text", command=self.app_controller.logic.start_conversion_process, state=tk.DISABLED)
        self.next_step_button.pack(side=tk.TOP, fill=tk.X, ipady=8, pady=(0, 5))
        self.edit_text_button = tk.Button(self.bottom_frame, text="Edit Text / Skip to Analysis", command=self.app_controller.show_editor_view, state=tk.DISABLED)
        self.edit_text_button.pack(side=tk.TOP, fill=tk.X, ipady=8)

        # Register themed widgets
        self.app_controller._themed_tk_labels.extend([self.info_label, self.drop_info_label, self.file_status_label, self.title_label_header, self.title_label, self.author_label_header, self.author_label])
        self.app_controller._themed_tk_buttons.extend([self.upload_button, self.select_folder_button, self.next_step_button, self.edit_text_button])
        # Register frames for theming
        self.app_controller._themed_tk_frames.extend([self, container, self.drop_target_frame, self.metadata_display_frame, self.info_frame, self.bottom_frame])

    def update_metadata_display(self, title, author, cover_path):
        # If no title, hide the metadata frame
        if not title:
            self.metadata_display_frame.pack_forget()
            return

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

        # Pack the frame to make it visible
        self.metadata_display_frame.pack(pady=10, anchor='w')