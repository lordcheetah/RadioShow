# validators.py
from pathlib import Path
import re
from typing import List, Tuple

class InputValidator:
    SUPPORTED_FORMATS = ['.epub', '.mobi', '.pdf', '.azw3']
    MAX_FILE_SIZE_MB = 500
    MIN_TEXT_LENGTH = 100
    
    @staticmethod
    def validate_ebook_file(file_path: Path) -> Tuple[bool, str]:
        """Validate ebook file"""
        if not file_path.exists():
            return False, "File does not exist"
        
        if file_path.suffix.lower() not in InputValidator.SUPPORTED_FORMATS:
            return False, f"Unsupported format. Use: {', '.join(InputValidator.SUPPORTED_FORMATS)}"
        
        size_mb = file_path.stat().st_size / (1024 * 1024)
        if size_mb > InputValidator.MAX_FILE_SIZE_MB:
            return False, f"File too large ({size_mb:.1f}MB). Max: {InputValidator.MAX_FILE_SIZE_MB}MB"
        
        return True, "Valid"
    
    @staticmethod
    def validate_text_content(text: str) -> Tuple[bool, str]:
        """Validate text content for processing"""
        if len(text.strip()) < InputValidator.MIN_TEXT_LENGTH:
            return False, f"Text too short. Minimum: {InputValidator.MIN_TEXT_LENGTH} characters"
        
        # Check for reasonable text content
        if len(re.findall(r'[a-zA-Z]', text)) / len(text) < 0.5:
            return False, "Text appears to contain mostly non-alphabetic characters"
        
        return True, "Valid"
    
    @staticmethod
    def validate_voice_file(file_path: Path) -> Tuple[bool, str]:
        """Validate voice sample file"""
        if not file_path.exists():
            return False, "Voice file does not exist"
        
        if file_path.suffix.lower() not in ['.wav', '.mp3', '.flac']:
            return False, "Voice file must be .wav, .mp3, or .flac"
        
        size_mb = file_path.stat().st_size / (1024 * 1024)
        if size_mb > 50:
            return False, "Voice file too large (>50MB)"
        
        return True, "Valid"
    
    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """Sanitize filename for safe file operations"""
        # Remove or replace problematic characters
        sanitized = re.sub(r'[<>:"/\\|?*]', '_', filename)
        sanitized = re.sub(r'[^\w\s-.]', '', sanitized)
        return sanitized.strip()[:100]  # Limit length