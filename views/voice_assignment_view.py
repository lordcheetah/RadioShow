# views/voice_assignment_view.py
import tkinter as tk
from tkinter import ttk

class VoiceAssignmentView(tk.Frame):
    def __init__(self, master, app_controller):
        super().__init__(master)
        self.app_controller = app_controller
        self.pack(fill=tk.BOTH, expand=True)
        self.pack_propagate(False)
        self._create_widgets()

    def _create_widgets(self):
        self.top_frame = tk.Frame(self)
        self.top_frame.pack(side=tk.TOP, fill=tk.X, pady=(0, 10))
        self.main_panels_frame = tk.Frame(self)
        self.main_panels_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.bottom_frame = tk.Frame(self)
        self.bottom_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(10, 0), anchor=tk.S)
        
        self.info_label = tk.Label(self.top_frame, text="Step 5: Assign Voices", font=("Helvetica", 14, "bold"))
        self.info_label.pack(anchor='w')
        
        # --- Left Panel: Cast List ---
        self.cast_list_outer_frame = tk.Frame(self.main_panels_frame, width=350)
        self.cast_list_outer_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        self.cast_list_outer_frame.pack_propagate(False)
        
        self.cast_list_label = tk.Label(self.cast_list_outer_frame, text="Cast List", font=("Helvetica", 12, "bold"))
        self.cast_list_label.pack(side=tk.TOP, fill=tk.X)
        
        cast_columns = ('speaker', 'voice')
        self.cast_tree = ttk.Treeview(self.cast_list_outer_frame, columns=cast_columns, show='headings', height=10)
        self.cast_tree.heading('speaker', text='Speaker'); self.cast_tree.column('speaker', width=150, anchor='w')
        self.cast_tree.heading('voice', text='Voice'); self.cast_tree.column('voice', width=150, anchor='w')
        self.cast_tree.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(5,0))

        # --- Right Panel: Voice Controls ---
        self.controls_frame = tk.Frame(self.main_panels_frame)
        self.controls_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.voice_mgmt_labelframe = tk.LabelFrame(self.controls_frame, text="Voice Library", padx=5, pady=5)
        self.voice_mgmt_labelframe.pack(fill=tk.X, pady=(0,10), anchor='n')
        
        self.add_voice_button = tk.Button(self.voice_mgmt_labelframe, text="Add New Voice (.wav)", command=self.app_controller.add_new_voice)
        self.add_voice_button.pack(fill=tk.X)
        self.remove_voice_button = tk.Button(self.voice_mgmt_labelframe, text="Remove Selected Voice", command=self.app_controller.remove_selected_voice)
        self.remove_voice_button.pack(fill=tk.X, pady=(5,0))

        self.assign_voice_labelframe = tk.LabelFrame(self.controls_frame, text="Assign Voice to Selected Speaker", padx=5, pady=5)
        self.assign_voice_labelframe.pack(fill=tk.X, anchor='n')
        
        self.auto_assign_button = tk.Button(self.assign_voice_labelframe, text="Auto-Assign Voices", command=self.app_controller.logic.auto_assign_voices)
        self.auto_assign_button.pack(fill=tk.X, pady=(0,5))
        
        self.clear_assignments_button = tk.Button(self.assign_voice_labelframe, text="Clear All Assignments", command=self.app_controller.clear_all_assignments)
        self.clear_assignments_button.pack(fill=tk.X, pady=(0,5))
        
        voice_selection_frame = tk.Frame(self.assign_voice_labelframe)
        voice_selection_frame.pack(fill=tk.X, pady=(0, 5))
        self.voice_dropdown = ttk.Combobox(voice_selection_frame, state='readonly')
        self.voice_dropdown.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.voice_dropdown.bind('<<ComboboxSelected>>', self.app_controller.on_voice_dropdown_select)
        self.preview_voice_button = tk.Button(voice_selection_frame, text="▶", command=self.app_controller.preview_selected_voice, width=3)
        self.preview_voice_button.pack(side=tk.RIGHT, padx=(5,0))
        
        self.voice_details_label = tk.Label(self.assign_voice_labelframe, text="Details: N/A", wraplength=200, justify=tk.LEFT)
        self.voice_details_label.pack(fill=tk.X, pady=(0,5))

        self.assign_button = tk.Button(self.assign_voice_labelframe, text="Assign Voice", command=self.app_controller.assign_voice)
        self.assign_button.pack(fill=tk.X)
        
        self.set_default_voice_button = tk.Button(self.assign_voice_labelframe, text="Set Selected as Default", command=self.app_controller.set_selected_as_default_voice)
        self.set_default_voice_button.pack(fill=tk.X, pady=(5,0))
        self.default_voice_label = tk.Label(self.assign_voice_labelframe, text="Default: None")
        self.default_voice_label.pack(fill=tk.X, pady=(5,0))

        # --- Bottom Buttons ---
        self.back_button = tk.Button(self.bottom_frame, text="< Back to Refine Cast", command=self.app_controller.show_cast_refinement_view)
        self.back_button.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
        self.tts_button = tk.Button(self.bottom_frame, text="Step 6: Generate Audio Clips", command=self.app_controller.start_audio_generation)
        self.tts_button.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)

        # Register themed widgets
        self.app_controller._themed_tk_labels.extend([
            self.info_label, self.cast_list_label, self.default_voice_label, self.voice_details_label
        ])
        self.app_controller._themed_tk_buttons.extend([
            self.add_voice_button, self.remove_voice_button, self.auto_assign_button,
            self.clear_assignments_button, self.preview_voice_button, self.assign_button,
            self.set_default_voice_button, self.back_button, self.tts_button
        ])
        self.app_controller._themed_tk_labelframes.extend([
            self.voice_mgmt_labelframe, self.assign_voice_labelframe
        ])