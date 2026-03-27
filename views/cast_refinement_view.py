# views/cast_refinement_view.py
import tkinter as tk
from tkinter import ttk

class CastRefinementView(tk.Frame):
    def __init__(self, master, app_controller):
        super().__init__(master)
        self.app_controller = app_controller
        self.pack(fill=tk.BOTH, expand=True)
        self.pack_propagate(False)
        self._create_widgets()

    def _create_widgets(self):
        self.top_frame = tk.Frame(self)
        self.top_frame.pack(side=tk.TOP, fill=tk.X, pady=(0, 10))
        self.bottom_frame = tk.Frame(self)
        self.bottom_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(10, 0), anchor=tk.S)
        self.main_panels_frame = tk.Frame(self)
        self.main_panels_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        
        self.info_label = tk.Label(self.top_frame, text="Step 4: Refine Script and Cast", font=("Helvetica", 14, "bold"))
        self.info_label.pack(anchor='w')

        self.filters_frame = tk.Frame(self.top_frame)
        self.filters_frame.pack(fill=tk.X, pady=(8, 0))

        self.filter_label = tk.Label(self.filters_frame, text="Review Filter:")
        self.filter_label.pack(side=tk.LEFT)

        self.filter_dropdown = ttk.Combobox(
            self.filters_frame,
            textvariable=self.app_controller.step4_filter_var,
            state='readonly',
            width=22,
            values=[
                'All Lines',
                'Issues Only',
                'Ambiguous Speakers',
                'Low Confidence',
                'Quote Warnings',
                'Long Lines',
            ]
        )
        self.filter_dropdown.pack(side=tk.LEFT, padx=(8, 12))
        self.filter_dropdown.bind('<<ComboboxSelected>>', self.app_controller.on_step4_filter_changed)

        self.prev_flagged_button = tk.Button(self.filters_frame, text="< Prev Flagged", command=self.app_controller.select_previous_step4_flagged)
        self.prev_flagged_button.pack(side=tk.LEFT, padx=(0, 4))

        self.next_flagged_button = tk.Button(self.filters_frame, text="Next Flagged >", command=self.app_controller.select_next_step4_flagged)
        self.next_flagged_button.pack(side=tk.LEFT, padx=(0, 12))

        self.filter_summary_label = tk.Label(self.filters_frame, text="Showing all lines")
        self.filter_summary_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # --- Left Panel for Cast List and Refinement Controls ---
        self.cast_list_outer_frame = tk.Frame(self.main_panels_frame, width=400)
        self.cast_list_outer_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        self.cast_list_outer_frame.pack_propagate(False)
        
        self.cast_list_label = tk.Label(self.cast_list_outer_frame, text="Cast List", font=("Helvetica", 12, "bold"))
        self.cast_list_label.pack(side=tk.TOP, fill=tk.X)

        # Controls packed from the bottom up
        self.refine_speakers_button = tk.Button(self.cast_list_outer_frame, text="Refine Speaker List (AI)", command=self.app_controller.logic.start_speaker_refinement_pass)
        self.refine_speakers_button.pack(side=tk.BOTTOM, fill=tk.X, pady=(5,0)) # Moved up

        self.llm_test_button = tk.Button(
            self.cast_list_outer_frame,
            text="LLM Self-Test",
            command=self.app_controller.logic.start_llm_compatibility_check
        )
        self.llm_test_button.pack(side=tk.BOTTOM, fill=tk.X, pady=(5,0))

        self.resolve_button = tk.Button(self.cast_list_outer_frame, text="Resolve Ambiguous (AI)", command=self.app_controller.logic.start_pass_2_resolution)
        self.resolve_button.pack(side=tk.BOTTOM, fill=tk.X) # Moved down

        self.edit_profile_button = tk.Button(self.cast_list_outer_frame, text="Edit Selected Profile", command=self.app_controller.edit_selected_speaker_profile)
        self.edit_profile_button.pack(side=tk.BOTTOM, fill=tk.X, pady=(5,0))

        self.rename_button = tk.Button(self.cast_list_outer_frame, text="Rename Selected Speaker", command=self.app_controller.rename_speaker)
        self.rename_button.pack(side=tk.BOTTOM, fill=tk.X, pady=(5,0))

        # The expanding Treeview for the cast list
        cast_columns = ('speaker', 'voice', 'gender', 'age_range', 'accent', 'count')
        self.cast_tree = ttk.Treeview(self.cast_list_outer_frame, columns=cast_columns, show='headings', height=10)
        self.cast_tree.heading('speaker', text='Speaker'); self.cast_tree.column('speaker', width=90, anchor='w')
        self.cast_tree.heading('voice', text='Voice'); self.cast_tree.column('voice', width=90, anchor='w')
        self.cast_tree.heading('gender', text='Gender'); self.cast_tree.column('gender', width=60, anchor='w')
        self.cast_tree.heading('age_range', text='Age'); self.cast_tree.column('age_range', width=60, anchor='w')
        self.cast_tree.heading('accent', text='Accent'); self.cast_tree.column('accent', width=85, anchor='w')
        self.cast_tree.heading('count', text='Count'); self.cast_tree.column('count', width=50, anchor='e')
        self.cast_tree.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(5,0))
        
        # --- Right Panel for Script Lines ---
        self.results_frame = tk.Frame(self.main_panels_frame)
        self.results_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        columns = ('speaker', 'confidence', 'issue', 'line', 'pov')
        self.tree = ttk.Treeview(self.results_frame, columns=columns, show='headings')
        self.tree.heading('speaker', text='Speaker'); self.tree.column('speaker', width=150, anchor='n')
        self.tree.heading('confidence', text='Confidence'); self.tree.column('confidence', width=90, anchor='center')
        self.tree.heading('issue', text='Issue'); self.tree.column('issue', width=180, anchor='w')
        self.tree.heading('line', text='Line'); self.tree.column('line', width=800)
        self.tree.heading('pov', text='POV'); self.tree.column('pov', width=100, anchor='n')
        self.vsb = ttk.Scrollbar(self.results_frame, orient="vertical", command=self.tree.yview)
        self.hsb = ttk.Scrollbar(self.results_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=self.vsb.set, xscrollcommand=self.hsb.set)
        self.vsb.pack(side='right', fill='y'); self.hsb.pack(side='bottom', fill='x')
        self.tree.pack(side=tk.LEFT, expand=True, fill='both')
        self.tree.bind('<Double-1>', self.app_controller.on_treeview_double_click)
        
        # --- Bottom Buttons ---
        self.back_button = tk.Button(self.bottom_frame, text="< Back to Editor", command=self.app_controller.confirm_back_to_editor)
        self.back_button.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
        self.next_button = tk.Button(self.bottom_frame, text="Next: Assign Voices >", command=self.app_controller.show_voice_assignment_view)
        self.next_button.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)

        # Register themed widgets
        self.app_controller._themed_tk_labels.extend([self.info_label, self.cast_list_label, self.filter_label, self.filter_summary_label])
        self.app_controller._themed_tk_buttons.extend([
            self.rename_button, self.edit_profile_button, self.resolve_button, self.llm_test_button, self.refine_speakers_button,
            self.back_button, self.next_button, self.prev_flagged_button, self.next_flagged_button
        ])
        # Register frames for theming
        self.app_controller._themed_tk_frames.extend([
            self, self.top_frame, self.main_panels_frame, self.bottom_frame,
            self.cast_list_outer_frame, self.results_frame, self.filters_frame
        ])