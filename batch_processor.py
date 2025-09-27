# batch_processor.py
from pathlib import Path
from typing import List, Dict, Callable
import json
from datetime import datetime

class BatchProcessor:
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.batch_report_path = output_dir / "batch_report.json"
        
    def create_batch_report(self, results: List[Dict]):
        """Create a detailed batch processing report"""
        report = {
            'timestamp': datetime.now().isoformat(),
            'total_books': len(results),
            'successful': len([r for r in results if r['success']]),
            'failed': len([r for r in results if not r['success']]),
            'results': results,
            'summary': self._generate_summary(results)
        }
        
        with open(self.batch_report_path, 'w') as f:
            json.dump(report, f, indent=2)
        
        return report
    
    def _generate_summary(self, results: List[Dict]) -> Dict:
        """Generate processing summary statistics"""
        total_duration = sum(r.get('duration_seconds', 0) for r in results)
        avg_duration = total_duration / len(results) if results else 0
        
        error_types = {}
        for result in results:
            if not result['success'] and 'error_type' in result:
                error_type = result['error_type']
                error_types[error_type] = error_types.get(error_type, 0) + 1
        
        return {
            'total_duration_seconds': total_duration,
            'average_duration_seconds': avg_duration,
            'error_breakdown': error_types
        }
    
    def validate_batch_input(self, file_paths: List[Path]) -> Dict:
        """Validate batch input files"""
        valid_files = []
        invalid_files = []
        
        for path in file_paths:
            if path.exists() and path.suffix.lower() in ['.epub', '.mobi', '.pdf', '.azw3']:
                valid_files.append(path)
            else:
                invalid_files.append(path)
        
        return {
            'valid': valid_files,
            'invalid': invalid_files,
            'total_size_mb': sum(f.stat().st_size for f in valid_files) / (1024 * 1024)
        }