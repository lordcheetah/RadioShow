# tts_engines.py
import os
import traceback
from abc import ABC, abstractmethod
from pathlib import Path

import torch

# Need to handle potential ModuleNotFoundError for TTS and Chatterbox
try:
    from TTS.api import TTS
    from TTS.tts.configs.xtts_config import XttsConfig
    from TTS.tts.models.xtts import XttsAudioConfig, XttsArgs
    from TTS.config.shared_configs import BaseDatasetConfig
    TTS_AVAILABLE = True
except ImportError:
    TTS, XttsConfig, XttsAudioConfig, XttsArgs, BaseDatasetConfig = None, None, None, None, None
    TTS_AVAILABLE = False

try:
    from chatterbox.tts import ChatterboxTTS as ChatterboxTTSModule
    import torchaudio
    CHATTERBOX_AVAILABLE = True
except ImportError:
    ChatterboxTTSModule, torchaudio = None, None
    CHATTERBOX_AVAILABLE = False

class TTSEngine(ABC):
    """Abstract Base Class for TTS Engines."""
    def __init__(self, ui, logger):
        self.ui = ui
        self.logger = logger
        self.engine = None # The actual TTS library engine instance

    @abstractmethod
    def initialize(self):
        """Initializes the TTS engine. Should set self.engine."""
        pass

    @abstractmethod
    def tts_to_file(self, text: str, file_path: str, **kwargs):
        """Synthesizes text to an audio file."""
        pass

    @abstractmethod
    def get_engine_specific_voices(self) -> list:
        """Returns a list of voice-like objects specific to this engine."""
        pass

    @abstractmethod
    def get_engine_name(self) -> str:
        """Returns the display name of the TTS engine."""
        pass

class CoquiXTTS(TTSEngine):
    """Wrapper for Coqui XTTS engine."""
    def get_engine_name(self) -> str:
        return "Coqui XTTS"

    def initialize(self):
        if not TTS_AVAILABLE:
            self.logger.error("Coqui TTS library not found. Please install it to use this engine.")
            self.ui.update_queue.put({'error': "Coqui TTS library not found. Please install it."})
            return False

        user_local_model_dir = self.ui.state.output_dir / "XTTS_Model"
        try:
            torch.serialization.add_safe_globals([XttsConfig, XttsAudioConfig, BaseDatasetConfig, XttsArgs])
            os.environ["COQUI_TOS_AGREED"] = "1"
            self.logger.info("Initializing Coqui XTTS engine.")
            gpu_available = torch.cuda.is_available()
            self.engine = TTS("tts_models/multilingual/multi-dataset/xtts_v2", progress_bar=False, gpu=gpu_available)
            if gpu_available:
                self.logger.info("XTTS initialized with GPU support")
            else:
                self.logger.info("XTTS initialized with CPU (no GPU available)")
            self.ui.update_queue.put({'status': "Default XTTSv2 model loaded/downloaded successfully."})
            self.logger.info("Default XTTSv2 model loaded/downloaded successfully.")
            return True
        except Exception as e:
            detailed_error = traceback.format_exc()
            self.logger.error(f"Coqui XTTS Initialization failed: {detailed_error}")
            self.ui.update_queue.put({'error': f"Could not initialize Coqui XTTS.\n\nDETAILS:\n{detailed_error}"})
            return False

    def tts_to_file(self, text: str, file_path: str, **kwargs):
        if not self.engine:
            raise RuntimeError("Coqui XTTS engine not initialized.")
        coqui_kwargs = {}
        if 'speaker_wav_path' in kwargs and kwargs['speaker_wav_path']:
            coqui_kwargs['speaker_wav'] = [str(kwargs['speaker_wav_path'])]
        if 'internal_speaker_name' in kwargs and kwargs['internal_speaker_name']:
            coqui_kwargs['speaker'] = kwargs['internal_speaker_name']
        if 'language' in kwargs:
            coqui_kwargs['language'] = kwargs['language']
        try:
            self.engine.tts_to_file(text=text, file_path=file_path, **coqui_kwargs)
        except Exception as e:
            self.logger.error(f"Coqui XTTS - error during TTS generation: {e}")
            raise

    def get_engine_specific_voices(self) -> list:
        return [{'name': "Default XTTS Voice", 'id_or_path': '_XTTS_INTERNAL_VOICE_', 'type': 'internal'}]

class ChatterboxTTS(TTSEngine):
    """Wrapper for Chatterbox TTS engine."""
    def get_engine_name(self) -> str:
        return "Chatterbox"

    def initialize(self):
        if not CHATTERBOX_AVAILABLE:
            error_msg = "Chatterbox library not found. Please install it to use this engine."
            self.logger.error(error_msg)
            self.ui.update_queue.put({'error': error_msg})
            return False
        try:
            self.engine = ChatterboxTTSModule.from_pretrained(device="cuda" if torch.cuda.is_available() else "cpu")
            self.logger.info(f"Chatterbox engine initialized successfully on device: {self.engine.device}.")
            self.ui.update_queue.put({'status': "Chatterbox engine initialized."})
            return True
        except Exception as e:
            detailed_error = traceback.format_exc()
            self.logger.error(f"Chatterbox Initialization failed: {detailed_error}")
            self.ui.update_queue.put({'error': f"Could not initialize Chatterbox.\n\nDETAILS:\n{detailed_error}"})
            return False

    def tts_to_file(self, text: str, file_path: str, **kwargs):
        if not self.engine:
            raise RuntimeError("Chatterbox engine not initialized.")
        chatterbox_gen_kwargs = {}
        if 'speaker_wav_path' in kwargs and kwargs['speaker_wav_path']:
            wav_path = Path(kwargs['speaker_wav_path']).resolve()
            chatterbox_gen_kwargs['audio_prompt_path'] = str(wav_path)
        
        try:
            wav = self.engine.generate(text, **chatterbox_gen_kwargs)
            safe_file_path = Path(file_path).resolve()
            torchaudio.save(str(safe_file_path), wav, self.engine.sr)
        except Exception as e:
            self.logger.error(f"Chatterbox - error during TTS generation or saving file: {e}")
            raise

    def get_engine_specific_voices(self) -> list:
        return [{'name': "Chatterbox Default", 'id_or_path': 'chatterbox_default_internal', 'type': 'internal'}]