# voice_analyzer.py
from pathlib import Path
from pydub import AudioSegment
import numpy as np

class VoiceAnalyzer:
    @staticmethod
    def analyze_voice_sample(audio_path: Path) -> dict:
        """Analyze voice sample for quality metrics"""
        try:
            audio = AudioSegment.from_file(audio_path)
            
            # Convert to numpy array for analysis
            samples = np.array(audio.get_array_of_samples())
            if audio.channels == 2:
                samples = samples.reshape((-1, 2)).mean(axis=1)
            
            # Calculate metrics
            duration_ms = len(audio)
            sample_rate = audio.frame_rate
            rms = np.sqrt(np.mean(samples**2))
            peak = np.max(np.abs(samples))
            
            # Quality assessment
            quality_score = VoiceAnalyzer._calculate_quality_score(
                duration_ms, sample_rate, rms, peak
            )
            
            return {
                'duration_ms': duration_ms,
                'sample_rate': sample_rate,
                'rms_level': float(rms),
                'peak_level': float(peak),
                'quality_score': quality_score,
                'is_suitable': quality_score > 0.6,
                'recommendations': VoiceAnalyzer._get_recommendations(
                    duration_ms, sample_rate, rms, peak
                )
            }
        except Exception as e:
            return {
                'error': str(e),
                'is_suitable': False,
                'quality_score': 0.0
            }
    
    @staticmethod
    def _calculate_quality_score(duration_ms, sample_rate, rms, peak):
        """Calculate overall quality score (0-1)"""
        score = 1.0
        
        # Duration check (prefer 10-30 seconds)
        if duration_ms < 5000 or duration_ms > 60000:
            score *= 0.7
        
        # Sample rate check (prefer 22kHz+)
        if sample_rate < 16000:
            score *= 0.6
        elif sample_rate < 22050:
            score *= 0.8
        
        # Audio level checks
        if rms < 1000 or peak < 5000:  # Too quiet
            score *= 0.7
        elif peak > 30000:  # Too loud/clipped
            score *= 0.8
        
        return min(score, 1.0)
    
    @staticmethod
    def _get_recommendations(duration_ms, sample_rate, rms, peak):
        """Get improvement recommendations"""
        recommendations = []
        
        if duration_ms < 5000:
            recommendations.append("Voice sample too short - use 10-30 seconds")
        elif duration_ms > 60000:
            recommendations.append("Voice sample too long - trim to 10-30 seconds")
        
        if sample_rate < 22050:
            recommendations.append("Low sample rate - use 22kHz or higher")
        
        if rms < 1000:
            recommendations.append("Audio too quiet - increase recording level")
        elif peak > 30000:
            recommendations.append("Audio may be clipped - reduce recording level")
        
        return recommendations