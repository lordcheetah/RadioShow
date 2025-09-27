# progress_tracker.py
import json
from pathlib import Path
from datetime import datetime
from enum import Enum

class ProcessingStage(Enum):
    METADATA_EXTRACTION = "metadata_extraction"
    TEXT_CONVERSION = "text_conversion"
    SPEAKER_ANALYSIS = "speaker_analysis"
    VOICE_ASSIGNMENT = "voice_assignment"
    AUDIO_GENERATION = "audio_generation"
    ASSEMBLY = "assembly"
    COMPLETED = "completed"

class ProgressTracker:
    def __init__(self, project_path: Path):
        self.progress_file = project_path.with_suffix('.progress')
        self.progress_data = {
            'stage': ProcessingStage.METADATA_EXTRACTION.value,
            'completed_lines': 0,
            'total_lines': 0,
            'last_updated': None,
            'errors': []
        }
        self.load_progress()
    
    def load_progress(self):
        if self.progress_file.exists():
            try:
                with open(self.progress_file, 'r') as f:
                    self.progress_data.update(json.load(f))
            except Exception:
                pass
    
    def save_progress(self):
        self.progress_data['last_updated'] = datetime.now().isoformat()
        with open(self.progress_file, 'w') as f:
            json.dump(self.progress_data, f, indent=2)
    
    def update_stage(self, stage: ProcessingStage):
        self.progress_data['stage'] = stage.value
        self.save_progress()
    
    def update_progress(self, completed: int, total: int = None):
        self.progress_data['completed_lines'] = completed
        if total is not None:
            self.progress_data['total_lines'] = total
        self.save_progress()
    
    def add_error(self, error_msg: str):
        self.progress_data['errors'].append({
            'timestamp': datetime.now().isoformat(),
            'message': error_msg
        })
        self.save_progress()
    
    def get_progress_percentage(self):
        if self.progress_data['total_lines'] == 0:
            return 0
        return (self.progress_data['completed_lines'] / self.progress_data['total_lines']) * 100
    
    def cleanup(self):
        if self.progress_file.exists():
            self.progress_file.unlink()