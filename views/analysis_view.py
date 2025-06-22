# views/analysis_view.py
import tkinter as tk
from tkinter import ttk

class AnalysisView(tk.Frame):
    def __init__(self, master, app_controller):
        super().__init__(master)
        self.app_controller = app_controller # Reference to the main AudiobookCreatorApp
        self.pack(fill=tk.BOTH, expand=True)
        self.pack_propagate(False) # Prevent child widgets from resizing this frame

        self._create_widgets()

    def _create_widgets(self):
        self.top_frame = tk.Frame(self); self.top_frame.pack(side=tk.TOP, fill=tk.X, pady=(0, 10))
        self.main_panels_frame = tk.Frame(self); self.main_panels_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.bottom_frame = tk.Frame(self); self.bottom_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(10, 0), anchor=tk.S)
        
        self.info_label = tk.Label(self.top_frame, text="Step 4 & 5: Review Script and Assign Voices", font=("Helvetica", 14, "bold")); self.info_label.pack(anchor='w')
        
        # --- Left Panel for Cast List and Voice Controls ---
        self.cast_list_outer_frame = tk.Frame(self.main_panels_frame, width=400); self.cast_list_outer_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10)); self.cast_list_outer_frame.pack_propagate(False)
        
        # Pack non-expanding widgets first, starting from the top and bottom edges.
        self.cast_list_label = tk.Label(self.cast_list_outer_frame, text="Cast List", font=("Helvetica", 12, "bold"))
        self.cast_list_label.pack(side=tk.TOP, fill=tk.X)

        # Pack control sections from the bottom up
        self.assign_voice_labelframe = tk.LabelFrame(self.cast_list_outer_frame, text="Assign Voice to Selected Speaker", padx=5, pady=5)
        self.assign_voice_labelframe.pack(side=tk.BOTTOM, fill=tk.X, pady=(5,0))

        self.voice_mgmt_labelframe = tk.LabelFrame(self.cast_list_outer_frame, text="Voice Library", padx=5, pady=5)
        self.voice_mgmt_labelframe.pack(side=tk.BOTTOM, fill=tk.X, pady=(10,0))

        self.resolve_button = tk.Button(self.cast_list_outer_frame, text="Resolve Ambiguous (AI)", command=self.app_controller.logic.start_pass_2_resolution)
        self.resolve_button.pack(side=tk.BOTTOM, fill=tk.X)

        self.refine_speakers_button = tk.Button(self.cast_list_outer_frame, text="Refine Speaker List (AI)", command=self.app_controller.logic.start_speaker_refinement_pass)
        self.refine_speakers_button.pack(side=tk.BOTTOM, fill=tk.X)

        self.rename_button = tk.Button(self.cast_list_outer_frame, text="Rename Selected Speaker", command=self.app_controller.rename_speaker)
        self.rename_button.pack(side=tk.BOTTOM, fill=tk.X, pady=(5,0))

        # Now, pack the expanding Treeview to fill the remaining space in the middle
        cast_columns = ('speaker', 'voice', 'gender', 'age_range', 'count'); self.cast_tree = ttk.Treeview(self.cast_list_outer_frame, columns=cast_columns, show='headings', height=10)
        self.cast_tree.heading('speaker', text='Speaker'); self.cast_tree.column('speaker', width=90, anchor='w')
        self.cast_tree.heading('voice', text='Voice'); self.cast_tree.column('voice', width=90, anchor='w')
        self.cast_tree.heading('gender', text='Gender'); self.cast_tree.column('gender', width=60, anchor='w')
        self.cast_tree.heading('age_range', text='Age'); self.cast_tree.column('age_range', width=60, anchor='w')
        self.cast_tree.heading('count', text='Count'); self.cast_tree.column('count', width=50, anchor='e')
        self.cast_tree.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(5,0))
        
        # --- Create and pack widgets that go inside the labelframes ---
        self.add_voice_button = tk.Button(self.voice_mgmt_labelframe, text="Add New Voice (.wav)", command=self.app_controller.add_new_voice)
        self.add_voice_button.pack(fill=tk.X)
        self.remove_voice_button = tk.Button(self.voice_mgmt_labelframe, text="Remove Selected Voice", command=self.app_controller.remove_selected_voice)
        self.remove_voice_button.pack(fill=tk.X, pady=(5,0))
        
        self.auto_assign_button = tk.Button(self.assign_voice_labelframe, text="Auto-Assign Voices", command=self.app_controller.logic.auto_assign_voices)
        self.auto_assign_button.pack(fill=tk.X, pady=(0,5))
        
        self.clear_assignments_button = tk.Button(self.assign_voice_labelframe, text="Clear All Assignments", command=self.app_controller.clear_all_assignments)
        self.clear_assignments_button.pack(fill=tk.X, pady=(0,5))
        
        # Frame for the dropdown and preview button to sit side-by-side
        voice_selection_frame = tk.Frame(self.assign_voice_labelframe)
        voice_selection_frame.pack(fill=tk.X, pady=(0, 5))
        self.voice_dropdown = ttk.Combobox(self.assign_voice_labelframe, state='readonly')
        self.voice_dropdown.pack(in_=voice_selection_frame, side=tk.LEFT, fill=tk.X, expand=True)
        self.voice_dropdown.bind('<<ComboboxSelected>>', self.app_controller.on_voice_dropdown_select)
        self.preview_voice_button = tk.Button(voice_selection_frame, text="▶", command=self.app_controller.preview_selected_voice, width=3)
        self.preview_voice_button.pack(in_=voice_selection_frame, side=tk.RIGHT, padx=(5,0))
        self.voice_details_label = tk.Label(self.assign_voice_labelframe, text="Details: N/A", wraplength=200, justify=tk.LEFT)
        self.voice_details_label.pack(fill=tk.X, pady=(0,5))

        self.assign_button = tk.Button(self.assign_voice_labelframe, text="Assign Voice", command=self.app_controller.assign_voice)
        self.assign_button.pack(fill=tk.X)
        
        self.set_default_voice_button = tk.Button(self.assign_voice_labelframe, text="Set Selected as Default", command=self.app_controller.set_selected_as_default_voice)
        self.set_default_voice_button.pack(fill=tk.X, pady=(5,0))
        self.default_voice_label = tk.Label(self.assign_voice_labelframe, text="Default: None")
        self.default_voice_label.pack(fill=tk.X, pady=(5,0))

        # --- Right Panel for Script Lines ---
        self.results_frame = tk.Frame(self.main_panels_frame); self.results_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        columns = ('speaker', 'line', 'pov'); self.tree = ttk.Treeview(self.results_frame, columns=columns, show='headings')
        self.tree.heading('speaker', text='Speaker'); self.tree.column('speaker', width=150, anchor='n')
        self.tree.heading('line', text='Line'); self.tree.column('line', width=800)
        self.tree.heading('pov', text='POV'); self.tree.column('pov', width=100, anchor='n')
        self.vsb = ttk.Scrollbar(self.results_frame, orient="vertical", command=self.tree.yview); self.hsb = ttk.Scrollbar(self.results_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=self.vsb.set, xscrollcommand=self.hsb.set)
        self.vsb.pack(side='right', fill='y'); self.hsb.pack(side='bottom', fill='x'); self.tree.pack(side=tk.LEFT, expand=True, fill='both')
        self.tree.bind('<Double-1>', self.app_controller.on_treeview_double_click)
        
        # --- Bottom Buttons ---
        self.back_button = tk.Button(self.bottom_frame, text="< Back to Editor", command=self.app_controller.confirm_back_to_editor); self.back_button.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
        self.tts_button = tk.Button(self.bottom_frame, text="Step 6: Generate Audio Clips", command=self.app_controller.start_audio_generation); self.tts_button.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)

        # Register themed widgets
        self.app_controller._themed_tk_labels.extend([self.info_label, self.cast_list_label, self.default_voice_label, self.voice_details_label]) # Added voice_details_label
        self.app_controller._themed_tk_buttons.extend([self.rename_button, self.resolve_button, self.refine_speakers_button, self.add_voice_button,
                                   self.remove_voice_button, self.auto_assign_button, self.clear_assignments_button, self.preview_voice_button, self.assign_button, # Added refine_speakers_button
                                   self.set_default_voice_button,
                                   self.back_button, self.tts_button])
        self.app_controller._themed_tk_labelframes.extend([self.voice_mgmt_labelframe, self.assign_voice_labelframe])        