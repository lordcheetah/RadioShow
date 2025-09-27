# audio_effects.py
from pydub import AudioSegment
from pydub.effects import normalize, compress_dynamic_range
import numpy as np

class AudioProcessor:
    @staticmethod
    def normalize_audio(audio_segment):
        """Normalize audio levels"""
        return normalize(audio_segment)
    
    @staticmethod
    def add_silence_padding(audio_segment, start_ms=100, end_ms=200):
        """Add silence padding around audio"""
        silence_start = AudioSegment.silent(duration=start_ms)
        silence_end = AudioSegment.silent(duration=end_ms)
        return silence_start + audio_segment + silence_end
    
    @staticmethod
    def adjust_speed(audio_segment, speed_factor=1.0):
        """Adjust playback speed without changing pitch"""
        if speed_factor == 1.0:
            return audio_segment
        return audio_segment.speedup(playback_speed=speed_factor)
    
    @staticmethod
    def compress_audio(audio_segment):
        """Apply dynamic range compression"""
        return compress_dynamic_range(audio_segment)