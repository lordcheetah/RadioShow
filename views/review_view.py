# views/review_view.py
import tkinter as tk
from tkinter import ttk

class ReviewView(tk.Frame):
    def __init__(self, master, app_controller):
        super().__init__(master)
        self.app_controller = app_controller # Reference to the main AudiobookCreatorApp
        self.pack(fill=tk.BOTH, expand=True)
        self.pack_propagate(False) # Prevent child widgets from resizing this frame

        self._create_widgets()

    def _create_widgets(self):
        self.top_frame = tk.Frame(self); self.top_frame.pack(side=tk.TOP, fill=tk.X, pady=(0,10))
        self.info_label = tk.Label(self.top_frame, text="Step 6: Review Generated Audio & Assemble", font=("Helvetica", 14, "bold"))
        self.info_label.pack(anchor='w')

        self.main_frame = tk.Frame(self); self.main_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        
        review_columns = ('num', 'speaker', 'line_text', 'audio_file', 'status') # Added 'audio_file'
        self.tree = ttk.Treeview(self.main_frame, columns=review_columns, show='headings')
        self.tree.heading('num', text='#'); self.tree.column('num', width=50, anchor='n')
        self.tree.heading('speaker', text='Speaker'); self.tree.column('speaker', width=150, anchor='n')
        self.tree.heading('line_text', text='Line Text'); self.tree.column('line_text', width=500)
        self.tree.heading('audio_file', text='Audio File'); self.tree.column('audio_file', width=100, anchor='w') # New Column
        self.tree.heading('status', text='Status'); self.tree.column('status', width=100, anchor='n')
        
        self.vsb = ttk.Scrollbar(self.main_frame, orient="vertical", command=self.tree.yview)
        self.hsb = ttk.Scrollbar(self.main_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=self.vsb.set, xscrollcommand=self.hsb.set)
        self.vsb.pack(side='right', fill='y'); self.hsb.pack(side='bottom', fill='x')
        self.tree.pack(side=tk.LEFT, expand=True, fill='both')

        self.bottom_frame = tk.Frame(self); self.bottom_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(10,0), anchor=tk.S)
        self.controls_frame = tk.Frame(self.bottom_frame) 
        self.controls_frame.pack(fill=tk.X, pady=(0,5))

        self.play_selected_button = tk.Button(self.controls_frame, text="Play Selected Line", command=self.app_controller.play_selected_audio_clip)
        self.play_selected_button.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        self.regenerate_selected_button = tk.Button(self.controls_frame, text="Regenerate Selected Line", command=self.app_controller.request_regenerate_selected_line)
        self.regenerate_selected_button.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        
        self.back_to_analysis_button = tk.Button(self.bottom_frame, text="< Back to Analysis/Voice Assignment", command=self.app_controller.confirm_back_to_analysis_from_review)
        self.back_to_analysis_button.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
        self.assemble_audiobook_button = tk.Button(self.bottom_frame, text="Assemble Audiobook (Final Step)", command=lambda: self.app_controller._start_background_task(self.app_controller.file_op.assemble_audiobook, args=(self.app_controller.state.generated_clips_info,), op_name='assembly'))
        self.assemble_audiobook_button.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)


        self.app_controller._themed_tk_labels.append(self.info_label)
        self.app_controller._themed_tk_buttons.extend([self.play_selected_button, self.regenerate_selected_button, self.back_to_analysis_button, self.assemble_audiobook_button])
        self.app_controller._themed_tk_frames.extend([
            self, self.top_frame, self.main_frame, self.bottom_frame,
            self.controls_frame
        ])