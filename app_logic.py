# app_logic.py
import openai
from pydub import AudioSegment
import queue
import re
import tkinter as tk
from tkinter import messagebox
from pathlib import Path
import subprocess
import threading
import os
import tempfile
import json
import traceback
import time # For cleanup thread wait
import torch.serialization # For add_safe_globals
import torchaudio # For audio file handling
import logging # For logging
import platform # For system actions

# Import classes needed for PyTorch's safe unpickling
from abc import ABC, abstractmethod

try:
    from chatterbox.tts import ChatterboxTTS as ChatterboxTTSModule # Alias to avoid conflict with class name
except ImportError:
    ChatterboxTTSModule = None # Placeholder if not installed

class TTSEngine(ABC):
    """Abstract Base Class for TTS Engines."""
    def __init__(self, app_logic, logger):
        self.app_logic = app_logic
        self.ui = app_logic.ui # Convenience
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
        """Returns a list of voice-like objects specific to this engine.
           Each object should be a dict, e.g., {'name': str, 'id_or_path': any, 'type': 'internal'/'file_based'}
        """
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
        """Initializes the Coqui XTTS engine."""
        user_local_model_dir = self.ui.output_dir / "XTTS_Model"

        try:
            from TTS.api import TTS
            from TTS.tts.configs.xtts_config import XttsConfig
            from TTS.tts.models.xtts import XttsAudioConfig, XttsArgs
            from TTS.config.shared_configs import BaseDatasetConfig
            torch.serialization.add_safe_globals([XttsConfig, XttsAudioConfig, BaseDatasetConfig, XttsArgs])
            os.environ["COQUI_TOS_AGREED"] = "1"
            self.logger.info("Initializing Coqui XTTS engine.")
            model_file = user_local_model_dir / "model.pth"
            config_file = user_local_model_dir / "config.json"
            vocab_file = user_local_model_dir / "vocab.json"
            speakers_file = user_local_model_dir / "speakers_xtts.pth"

            model_loaded_from_user_local = False
            if model_file.is_file() and config_file.is_file() and vocab_file.is_file() and speakers_file.is_file():
                self.ui.update_queue.put({'status': f"Found user-provided local XTTS model at {user_local_model_dir}. Attempting to load..."})
                self.logger.info(f"Attempting to load user-provided local XTTS model from: {user_local_model_dir}")
                try:
                    self.engine = TTS(model_path=str(user_local_model_dir), progress_bar=False, gpu=True)
                    model_loaded_from_user_local = True
                    self.ui.update_queue.put({'status': f"Successfully loaded XTTS model from {user_local_model_dir}."})
                    self.logger.info(f"Successfully loaded user-provided XTTS model from {user_local_model_dir}.")
                except Exception as e_local_load:
                    detailed_error_local = traceback.format_exc()
                    self.ui.update_queue.put({'status': f"Warning: Failed to load local XTTS model from {user_local_model_dir}. Error: {str(e_local_load)[:100]}... Will try default."})
                    self.logger.warning(f"Failed to load user-provided XTTS model from {user_local_model_dir}:\n{detailed_error_local}")
            else:
                if user_local_model_dir.exists():
                    missing_for_local = [f"'{f.name}'" for f in [model_file, config_file, vocab_file, speakers_file] if not f.is_file()]
                    if missing_for_local:
                        msg = f"Local XTTS model at {user_local_model_dir} incomplete (missing: {', '.join(missing_for_local)}). Will try default."
                        self.ui.update_queue.put({'status': msg}); self.logger.info(msg)

            if not model_loaded_from_user_local:
                self.ui.update_queue.put({'status': "Attempting to load/download default XTTSv2 model..."})
                self.logger.info("Attempting to load/download default XTTSv2 model...")
                model_name = "tts_models/multilingual/multi-dataset/xtts_v2"
                self.engine = TTS(model_name, progress_bar=False, gpu=True) # This might raise an exception
                self.ui.update_queue.put({'status': "Default XTTSv2 model loaded/downloaded successfully."})
                self.logger.info("Default XTTSv2 model loaded/downloaded successfully.")
            
            return True # Indicate success
        except ModuleNotFoundError as e_module:
            self.logger.error(f"Coqui XTTS module not found: {e_module}. This engine cannot be used in the current environment.")
            self.ui.update_queue.put({'error': f"Coqui XTTS is not available in this Python environment. Please install it or select a different TTS engine."})
            return False # Indicate failure
        except Exception as e:
            detailed_error = traceback.format_exc()
            error_message = f"Could not initialize Coqui XTTS.\n\nDETAILS:\n{detailed_error}\n\n"
            if model_loaded_from_user_local: # Error happened after successfully loading local model (unlikely here, but for completeness)
                 error_message += (f"The error occurred after attempting to load a model, possibly from '{user_local_model_dir}'.\n")
            else: # Error happened trying to load default or during initial setup
                error_message += ("The error likely occurred while loading/downloading the default XTTSv2 model. "
                                            "or a user-provided one. Check network, disk space, and model integrity.\n")
            self.logger.error(f"Coqui XTTS Initialization failed: {error_message}")
            self.ui.update_queue.put({'error': error_message})
            return False # Indicate failure

    def tts_to_file(self, text: str, file_path: str, **kwargs):
        if not self.engine:
            raise RuntimeError("Coqui XTTS engine not initialized.")
        # Map generic kwargs to Coqui-specific ones if needed, or pass directly
        # For XTTS, 'speaker_wav' and 'language' are common.
        # 'speaker' is for internal Coqui speakers.
        coqui_kwargs = {}
        if 'speaker_wav_path' in kwargs and kwargs['speaker_wav_path']:
            coqui_kwargs['speaker_wav'] = [str(kwargs['speaker_wav_path'])]
        if 'internal_speaker_name' in kwargs and kwargs['internal_speaker_name']:
            coqui_kwargs['speaker'] = kwargs['internal_speaker_name']
        if 'language' in kwargs:
            coqui_kwargs['language'] = kwargs['language']
        
        self.engine.tts_to_file(text=text, file_path=file_path, **coqui_kwargs)

    def get_engine_specific_voices(self) -> list:
        # XTTS primarily uses WAV files for voice cloning, plus one internal default.
        # The UI currently manages these WAV files. This method could list known internal speakers if any.
        # For now, we'll represent the "Default XTTS Voice" as an engine-specific voice.
        return [{'name': "Default XTTS Voice", 'id_or_path': '_XTTS_INTERNAL_VOICE_', 'type': 'internal'}]

class ChatterboxTTS(TTSEngine):
    """Wrapper for Chatterbox TTS engine."""
    def get_engine_name(self) -> str:
        return "Chatterbox"

    def initialize(self):
        """Initializes the Chatterbox engine."""
        self.logger.info("Attempting to initialize Chatterbox engine.")
        if not ChatterboxTTSModule:
            error_msg = "Chatterbox library not found. Please install it to use this engine."
            self.logger.error(error_msg)
            self.ui.update_queue.put({'error': error_msg})
            return False
        try:
            # Initialize Chatterbox using the imported module
            self.engine = ChatterboxTTSModule.from_pretrained(device="cuda" if torch.cuda.is_available() else "cpu")
            self.logger.info(f"Chatterbox engine initialized successfully on device: {self.engine.device}.")
            self.ui.update_queue.put({'status': "Chatterbox engine initialized." })
            return True
        except Exception as e:
            detailed_error = traceback.format_exc()
            error_message = f"Could not initialize Chatterbox.\n\nDETAILS:\n{detailed_error}"
            self.logger.error(f"Chatterbox Initialization failed: {error_message}")
            self.ui.update_queue.put({'error': error_message})
            return False

    def tts_to_file(self, text: str, file_path: str, **kwargs):
        if not self.engine:
            raise RuntimeError("Chatterbox engine not initialized.")
        
        chatterbox_gen_kwargs = {}
        log_message_suffix = "using its pre-loaded default voice."

        # Prioritize speaker_wav_path for voice conditioning
        if 'speaker_wav_path' in kwargs and kwargs['speaker_wav_path']:
            speaker_wav = str(kwargs['speaker_wav_path'])
            self.logger.info(f"[Chatterbox] Attempting to use voice conditioning with WAV: {speaker_wav}")
            chatterbox_gen_kwargs['audio_prompt_path'] = speaker_wav # Corrected keyword
            log_message_suffix = f"using voice conditioning from {Path(speaker_wav).name}."
        elif 'internal_speaker_name' in kwargs and kwargs['internal_speaker_name']:
            # This case handles explicit selection of "Chatterbox Default" or fallbacks
            self.logger.info(f"[Chatterbox] Explicitly using pre-loaded default voice (received internal_speaker_name: {kwargs['internal_speaker_name']}).")
            # No specific args needed for default voice, chatterbox_gen_kwargs remains empty
        else:
            self.logger.info(f"[Chatterbox] No voice conditioning WAV or explicit internal default. Using pre-loaded default voice.")
            # No specific args needed for default voice

        self.logger.info(f"[Chatterbox] Synthesizing text: '{text[:30]}...' to {file_path} {log_message_suffix}")
        try:
            # Chatterbox generate returns a tensor, sr is sample rate
            wav = self.engine.generate(text, **chatterbox_gen_kwargs)
            torchaudio.save(file_path, wav, self.engine.sr)
            self.logger.info(f"Chatterbox successfully saved audio to {file_path}")
        except Exception as e:
            self.logger.error(f"Chatterbox - error during TTS generation or saving file: {e}")
            if 'audio_prompt_path' in chatterbox_gen_kwargs: # Corrected keyword in error logging
                self.logger.error(f"The error might be related to the voice conditioning WAV: {chatterbox_gen_kwargs['audio_prompt_path']}. Ensure it's a valid audio file suitable for Chatterbox.")
            raise

    def get_engine_specific_voices(self) -> list:
        # Chatterbox seems to have one main default voice, not multiple selectable ones via this interface.
        return [{'name': "Chatterbox Default", 'id_or_path': 'chatterbox_default_internal', 'type': 'internal'}]

class AppLogic:
    def __init__(self, ui_app):
        self.ui = ui_app
        self.current_tts_engine_instance: TTSEngine | None = None
        
        # Setup Logger
        self.logger = logging.getLogger('RadioShow')
        log_file_path = self.ui.output_dir / "radioshow.log"
        file_handler = logging.FileHandler(log_file_path, encoding='utf-8', mode='a') # Append mode
        # Playback management attributes
        self._current_playback_process: subprocess.Popen | None = None
        self._current_playback_temp_file: Path | None = None
        self._playback_cleanup_thread: threading.Thread | None = None
        self._current_playback_original_index: int | None = None # Track which line is playing
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(module)s - %(message)s')
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)
        self.logger.setLevel(logging.INFO)
        self.logger.info("AppLogic initialized and logger configured.")

    def run_tts_initialization(self):
        """Initializes the selected TTS engine."""
        current_engine_to_init = self.ui.selected_tts_engine_name # Use the UI's current selection
        self.logger.info(f"Attempting to initialize TTS engine: {current_engine_to_init}")

        if not current_engine_to_init: # Handle case where no engine is selected/available
            self.logger.warning("No TTS engine selected for initialization (e.g., none found).")
            self.ui.update_queue.put({'error': "No TTS engine selected or available for initialization."})
            return

        if current_engine_to_init == "Coqui XTTS":
            self.current_tts_engine_instance = CoquiXTTS(self, self.logger)
        elif current_engine_to_init == "Chatterbox":
            self.current_tts_engine_instance = ChatterboxTTS(self, self.logger)
        else:
            self.logger.error(f"Unknown TTS engine selected: {current_engine_to_init}")
            self.ui.update_queue.put({'error': f"Unknown TTS engine: {current_engine_to_init}"})
            return

        if self.current_tts_engine_instance.initialize():
            self.ui.update_queue.put({'tts_init_complete': True})
            self.logger.info("TTS engine initialization complete.")
        else:
            self.logger.error("TTS engine initialization failed.")
                       
    def run_audio_generation(self):
        """Generates audio for each line in analysis_result, 1-to-1 mapping."""
        try:
            clips_dir = self.ui.output_dir / self.ui.ebook_path.stem
            clips_dir.mkdir(exist_ok=True)
            self.logger.info(f"Starting audio generation. Clips will be saved to: {clips_dir}")

            if not self.current_tts_engine_instance:
                self.ui.update_queue.put({'error': "TTS Engine not initialized. Cannot generate audio."})
                self.logger.error("Audio generation failed: TTS Engine not initialized.")
                return

            voice_assignments = self.ui.voice_assignments
            app_default_voice_info = self.ui.default_voice_info
            
            if not app_default_voice_info:
                self.ui.update_queue.put({'error': "No default voice set. Please set a default voice in the 'Voice Library'."})
                self.logger.error("Audio generation failed: No default voice set.")
                return

            generated_clips_info_list = []
            lines_to_process_count = len([item for item in self.ui.analysis_result if self.ui.sanitize_for_tts(item['line'])])
            processed_line_counter = 0

            def get_voice_info_for_speaker(speaker_name_local):
                if speaker_name_local in voice_assignments:
                    return voice_assignments[speaker_name_local]
                return app_default_voice_info

            for original_idx, item in enumerate(self.ui.analysis_result):
                line_text = item['line']
                speaker_name = item['speaker']
                
                sanitized_line = self.ui.sanitize_for_tts(line_text)
                voice_info_for_this_line = get_voice_info_for_speaker(speaker_name)

                if not sanitized_line.strip():
                    self.logger.info(f"Skipping empty sanitized line at original index {original_idx} (original: '{line_text}')")
                    # Still add a placeholder if you want to keep indexing consistent for review, or skip entirely
                    # For now, we skip adding it to generated_clips_info_list
                    continue

                clip_path = clips_dir / f"line_{original_idx:05d}.wav"
                
                # Prepare kwargs for the TTS engine's tts_to_file method
                engine_tts_kwargs = {'language': "en"} # Default language
                voice_path_str = voice_info_for_this_line['path']

                if voice_path_str == '_XTTS_INTERNAL_VOICE_':
                    self.logger.info(f"Using internal XTTS voice for line {original_idx}.")
                    engine_tts_kwargs['internal_speaker_name'] = "Claribel Dervla" # Example for Coqui
                elif voice_path_str == 'chatterbox_default_internal':
                    self.logger.info(f"Using internal Chatterbox default voice for line {original_idx}.")
                    engine_tts_kwargs['internal_speaker_name'] = 'chatterbox_default_internal'
                else:
                    speaker_wav_path = Path(voice_path_str)
                    if speaker_wav_path.exists() and speaker_wav_path.is_file():
                        engine_tts_kwargs['speaker_wav_path'] = speaker_wav_path
                    else:
                        self.logger.error(f"Voice WAV for '{voice_info_for_this_line['name']}' not found or invalid at '{speaker_wav_path}'. Using engine's default voice for line {original_idx}.")
                        # Fallback to engine's default
                        if isinstance(self.current_tts_engine_instance, CoquiXTTS):
                            engine_tts_kwargs['internal_speaker_name'] = "Claribel Dervla" 
                        elif isinstance(self.current_tts_engine_instance, ChatterboxTTS):
                            engine_tts_kwargs['internal_speaker_name'] = 'chatterbox_default_internal'
                
                self.logger.info(f"Generating line {original_idx} with voice '{voice_info_for_this_line['name']}' for text: \"{sanitized_line[:50]}...\"")
                try:
                    self.current_tts_engine_instance.tts_to_file(text=sanitized_line, file_path=str(clip_path), **engine_tts_kwargs)
                except Exception as e_tts:
                    self.logger.error(f"TTS generation failed for line {original_idx} with voice '{voice_info_for_this_line['name']}': {e_tts}. Skipping clip.")
                    continue # Skip adding this clip to the list
                generated_clips_info_list.append({
                    'text': line_text, # Original, non-sanitized text for display
                    'speaker': speaker_name,
                    'clip_path': str(clip_path),
                    'original_index': original_idx,
                    'voice_used': voice_info_for_this_line # Store the voice dict used
                })
                processed_line_counter += 1
                self.ui.update_queue.put({'progress': processed_line_counter -1 , 'is_generation': True}) # Progress based on non-empty lines

            self.logger.info("Audio generation process completed.")
            if not generated_clips_info_list and lines_to_process_count > 0:
                self.logger.error("Audio generation finished, but no clips were successfully created. This often happens if the voice .wav files are unsuitable for the TTS engine (e.g. too short, silent, wrong format for Chatterbox voice conditioning) or if there's a persistent issue with the TTS engine itself. Check logs for individual line errors.")
                self.ui.update_queue.put({'error': "Audio generation completed, but NO clips were created. Please check the application log (Audiobook_Output/audiobook_creator.log) for details on why each line might have failed. Common issues include unsuitable .wav files for voice conditioning."})
                return # Explicitly return to avoid sending 'generation_for_review_complete' if nothing was made

            self.ui.update_queue.put({'generation_for_review_complete': True, 'clips_info': generated_clips_info_list})

        except Exception as e:
            detailed_error = traceback.format_exc()
            self.logger.error(f"Critical error during audio generation: {detailed_error}")
            self.ui.update_queue.put({'error': f"A critical error occurred during audio generation:\n\n{detailed_error}"})

    def start_single_line_regeneration_thread(self, line_data, target_voice_info):
        self.ui.active_thread = threading.Thread(target=self.run_regenerate_single_line, 
                                                 args=(line_data, target_voice_info), daemon=True)
        self.ui.active_thread.start()
        # Queue checking is already running or will be initiated by UI

    def run_regenerate_single_line(self, line_data, target_voice_info):
        try:
            if not self.current_tts_engine_instance:
                self.ui.update_queue.put({'error': "TTS Engine not initialized. Cannot regenerate audio."})
                self.logger.error("Single line regeneration failed: TTS Engine not initialized.")
                return
            
            original_text = line_data['text'] # Use original text for regeneration
            sanitized_text_for_tts = self.ui.sanitize_for_tts(original_text)
            clip_path_to_overwrite = Path(line_data['clip_path'])
            original_idx = line_data['original_index']

            if not sanitized_text_for_tts.strip():
                self.logger.warning(f"Skipping regeneration for line {original_idx} as it's empty after sanitization.")
                self.ui.update_queue.put({'error': f"Line {original_idx+1} is empty after sanitization. Cannot regenerate."})
                return

            engine_tts_kwargs = {'language': "en"}
            voice_path_str = target_voice_info['path']

            if voice_path_str == '_XTTS_INTERNAL_VOICE_':
                engine_tts_kwargs['internal_speaker_name'] = "Claribel Dervla"
            elif voice_path_str == 'chatterbox_default_internal':
                self.logger.info(f"Regen: Using internal Chatterbox default voice for line {original_idx}.")
                engine_tts_kwargs['internal_speaker_name'] = 'chatterbox_default_internal'
            else:
                speaker_wav_path = Path(voice_path_str)
                if speaker_wav_path.exists() and speaker_wav_path.is_file():
                    engine_tts_kwargs['speaker_wav_path'] = speaker_wav_path
                else:
                    self.logger.error(f"Regen: Voice WAV for '{target_voice_info['name']}' not found or invalid at '{speaker_wav_path}'. Using engine's default.")
                    if isinstance(self.current_tts_engine_instance, CoquiXTTS):
                        engine_tts_kwargs['internal_speaker_name'] = "Claribel Dervla"
                    elif isinstance(self.current_tts_engine_instance, ChatterboxTTS):
                        engine_tts_kwargs['internal_speaker_name'] = 'chatterbox_default_internal'
            
            self.logger.info(f"Regenerating line {original_idx} with voice '{target_voice_info['name']}'")

            self.current_tts_engine_instance.tts_to_file(
                text=sanitized_text_for_tts, 
                file_path=str(clip_path_to_overwrite), 
                **engine_tts_kwargs)

            self.ui.update_queue.put({
                'single_line_regeneration_complete': True, 
                'original_index': original_idx, 
                'new_clip_path': str(clip_path_to_overwrite) # Path remains the same
            })
        except Exception as e:
            detailed_error = traceback.format_exc()
            self.logger.error(f"Critical error during single line regeneration: {detailed_error}")
            self.ui.update_queue.put({'error': f"Error regenerating line:\n\n{detailed_error}"})

    def play_audio_clip(self, clip_path: Path, original_index: int):
        """
        Plays an audio clip using ffplay via subprocess, managing concurrent playback.
        original_index is the index in the analysis_result list for UI updates.
        """
        self.stop_playback() # Stop any currently playing clip

        if not clip_path.exists():
            self.logger.error(f"Playback failed: Audio file not found at {clip_path}")
            self.ui.update_queue.put({'error': f"Playback failed: Audio file not found."})
            return

        try:
            audio_segment = self.load_audio_segment(str(clip_path))
            if audio_segment is None:
                 self.logger.error(f"Playback failed: Could not load audio segment from {clip_path}")
                 self.ui.update_queue.put({'error': f"Playback failed: Could not load audio file."})
                 return

            temp_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            temp_file_path = Path(temp_file.name)
            temp_file.close() 

            self.logger.info(f"Exporting audio segment to temporary file: {temp_file_path}")
            audio_segment.export(str(temp_file_path), format="wav")

            ffplay_cmd = ['ffplay', '-nodisp', '-autoexit', '-loglevel', 'quiet', str(temp_file_path)]
            self.logger.info(f"Starting ffplay process: {' '.join(ffplay_cmd)}")
            
            creationflags = 0
            if platform.system() == "Windows":
                creationflags = subprocess.CREATE_NO_WINDOW

            process = subprocess.Popen(ffplay_cmd, creationflags=creationflags)
            
            self._current_playback_process = process
            self._current_playback_temp_file = temp_file_path
            self._current_playback_original_index = original_index

            self._playback_cleanup_thread = threading.Thread(
                target=self._cleanup_playback, 
                args=(process, temp_file_path, original_index),
                daemon=True
            )
            self._playback_cleanup_thread.start()

        except FileNotFoundError:
             self.logger.error("Playback failed: ffplay executable not found. Is FFmpeg installed and in your PATH?")
             self.ui.update_queue.put({'error': "Playback failed: ffplay not found. Ensure FFmpeg is installed and in your system's PATH."})
             self.stop_playback()
        except Exception as e:
            detailed_error = traceback.format_exc()
            self.logger.error(f"Error during playback setup: {detailed_error}")
            self.ui.update_queue.put({'error': f"An error occurred during playback: {e}"})
            self.stop_playback()

    def start_voice_preview_thread(self, voice_info: dict):
        """Starts a thread to generate and play a voice preview."""
        # Stop any existing playback before starting a new preview
        self.stop_playback()
        
        # Use a new thread to avoid blocking the UI
        preview_thread = threading.Thread(
            target=self.run_voice_preview,
            args=(voice_info,),
            daemon=True
        )
        preview_thread.start()

    def run_voice_preview(self, voice_info: dict):
        """Generates a preview TTS clip and plays it."""
        preview_text = "The quick brown fox jumps over the lazy dog."
        self.logger.info(f"Generating preview for voice '{voice_info['name']}' with text: '{preview_text}'")

        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                preview_clip_path = Path(tmp.name)

            engine_tts_kwargs = {'language': "en"}
            voice_path_str = voice_info['path']

            if voice_path_str == '_XTTS_INTERNAL_VOICE_':
                engine_tts_kwargs['internal_speaker_name'] = "Claribel Dervla"
            elif voice_path_str == 'chatterbox_default_internal':
                engine_tts_kwargs['internal_speaker_name'] = 'chatterbox_default_internal'
            else:
                engine_tts_kwargs['speaker_wav_path'] = Path(voice_path_str)

            self.current_tts_engine_instance.tts_to_file(
                text=preview_text,
                file_path=str(preview_clip_path),
                **engine_tts_kwargs
            )
            self.play_audio_clip(preview_clip_path, original_index=-1) # Use a special index for previews
        except Exception as e:
            self.logger.error(f"Error during voice preview generation: {traceback.format_exc()}")
            self.ui.update_queue.put({'error': f"Failed to generate voice preview: {e}"})

    def stop_playback(self):
        if self._current_playback_process and self._current_playback_process.poll() is None:
            self.logger.info("Stopping existing playback process.")
            try:
                if self._current_playback_original_index is not None:
                     self.ui.update_queue.put({
                         'playback_finished': True, 
                         'original_index': self._current_playback_original_index, 
                         'status': 'Stopped'
                     })
                self._current_playback_process.terminate()
                try:
                    self._current_playback_process.wait(timeout=1) 
                except subprocess.TimeoutExpired:
                    self.logger.warning("Playback process did not terminate gracefully, killing.")
                    self._current_playback_process.kill()
                self.logger.info("Playback process stopped.")
            except Exception as e:
                self.logger.error(f"Error stopping playback process: {e}")
        
        self._current_playback_process = None
        self._current_playback_temp_file = None
        self._current_playback_original_index = None

    def _cleanup_playback(self, process: subprocess.Popen, temp_file_path: Path, original_index: int):
        try:
            returncode = process.wait()
            self.logger.info(f"Playback process finished for {temp_file_path} with return code {returncode}. Attempting cleanup.")
            
            if self._current_playback_process is None or self._current_playback_process.pid != process.pid:
                 self.logger.debug(f"Cleanup thread for PID {process.pid} found it's not the current process. Skipping 'Completed' signal.")
            else:
                self.ui.update_queue.put({'playback_finished': True, 'original_index': original_index, 'status': 'Completed'})
                self._current_playback_process = None; self._current_playback_temp_file = None; self._current_playback_original_index = None
        except Exception as e:
            self.logger.error(f"Error waiting for playback process {process.pid}: {e}")
            if self._current_playback_original_index is not None:
                 self.ui.update_queue.put({'playback_finished': True, 'original_index': self._current_playback_original_index, 'status': 'Error'})
            self._current_playback_process = None; self._current_playback_temp_file = None; self._current_playback_original_index = None

        time.sleep(0.1) 
        if temp_file_path and temp_file_path.exists():
            try:
                os.unlink(temp_file_path)
                self.logger.info(f"Temporary playback file deleted: {temp_file_path}")
            except Exception as e:
                self.logger.error(f"Error deleting temporary playback file {temp_file_path}: {e}")
        self.logger.debug("Playback cleanup thread finished.")

    def on_app_closing(self):
        self.stop_playback()

    # ... The rest of the AppLogic class is unchanged ...
    def initialize_tts(self):
        self.ui.last_operation = 'tts_init'
        self.ui.active_thread = threading.Thread(target=self.run_tts_initialization)
        self.ui.active_thread.daemon = True
        self.ui.active_thread.start()
        self.ui.root.after(100, self.ui.check_update_queue)

    def find_calibre_executable(self):
        if self.ui.calibre_exec_path and self.ui.calibre_exec_path.exists(): return True
        possible_paths = [
            Path("C:/Program Files/Calibre2/ebook-convert.exe"), 
            Path("C:/Program Files (x86)/Calibre2/ebook-convert.exe"), # Added for 32-bit Calibre on 64-bit Windows
            Path("C:/Program Files/Calibre/ebook-convert.exe")]
        for path in possible_paths:
            if path.exists(): self.ui.calibre_exec_path = path; return True
        return False
        
    def start_conversion_process(self):
        if not self.find_calibre_executable(): return messagebox.showerror("Calibre Not Found", "Could not find Calibre's 'ebook-convert.exe'.")
        self.ui.start_progress_indicator("Converting, please wait...")
        self.ui.last_operation = 'conversion'
        self.ui.active_thread = threading.Thread(target=self.run_calibre_conversion); self.ui.active_thread.daemon = True; self.ui.active_thread.start()
        self.ui.root.after(100, self.ui.check_update_queue) # Changed to check_update_queue

    def run_calibre_conversion(self):
        try:
            output_dir = Path(tempfile.gettempdir()) / "audiobook_creator"; output_dir.mkdir(exist_ok=True)
            # txt_path is generated here and will be sent back to UI via queue
            txt_path = output_dir / f"{self.ui.ebook_path.stem}.txt"
            command = [str(self.ui.calibre_exec_path), str(self.ui.ebook_path), str(txt_path), '--enable-heuristics', '--verbose']
            result = subprocess.run(command, capture_output=True, text=True, check=False, creationflags=subprocess.CREATE_NO_WINDOW, encoding='utf-8')
            if result.returncode != 0:
                error_log_msg = f"STDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}"; 
                self.logger.error(f"Calibre conversion failed: {error_log_msg}")
                raise RuntimeError(f"Calibre failed with error:\n{error_log_msg}")
            self.ui.update_queue.put({'conversion_complete': True, 'txt_path': txt_path})
        except Exception as e:
            self.logger.error(f"Calibre conversion exception: {e}")
            self.ui.update_queue.put({'error': f"Calibre conversion failed: {str(e)}"})

    def expand_abbreviations(self, text_to_expand):
        abbreviations = {
            r"\bMr\.\s": "Mister ",
            r"\bMrs\.\s": "Missus ", # Or "Mistress" depending on context/preference
            r"\bMs\.\s": "Miss ",    # Or "Mizz"
            r"\bDr\.\s": "Doctor ",
            r"\bSt\.\s": "Saint ",   # Could also be "Street" depending on context
            r"\bCapt\.\s": "Captain ",
            r"\bCmdr\.\s": "Commander ",
            r"\bAdm\.\s": "Admiral ",
            r"\bEns\.\s": "Ensign ",
            r"\bGen\.\s": "General ",
            r"\bLt\.\s": "Lieutenant ",
            r"\bLt\.\sCmdr\.\s": "Lieutenant Commander ", # Order matters, more specific first
            r"\bLt\.\sGen\.\s": "Lieutenant General ",
            r"\bCol\.\s": "Colonel ",
            r"\bSgt\.\s": "Sergeant ",
            r"\bMaj\.\s": "Major ",
            r"\bPvt\.\s": "Private ",
            r"\bCpl\.\s": "Corporal ",
            r"\bGov\.\s": "Governor ",
            r"\bSen\.\s": "Senator ",
            r"\bRep\.\s": "Representative ",
            r"\bPres\.\s": "President ",
            r"\bAmb\.\s": "Ambassador ",
            r"\bRev\.\s": "Reverend ",
            r"\bProf\.\s": "Professor ",
            r"\bHon\.\s": "Honorable ", # The Honorable
            # Nobility (less common with periods, but sometimes seen)
            r"\bLd\.\s": "Lord ",
            r"\bLy\.\s": "Lady ",
            r"\bSir\.\s": "Sir ", # Usually not abbreviated with a period in prose
            # Add more as needed, be mindful of context (e.g., St. for Saint vs. Street)
        }
        for abbr, expansion in abbreviations.items():
            text_to_expand = re.sub(abbr, expansion, text_to_expand, flags=re.IGNORECASE | re.UNICODE)
        return text_to_expand

    def run_rules_pass(self, text): # This will be the target of the thread
        try:
            self.logger.info("Starting Pass 1 (rules-based analysis).")
            text = self.expand_abbreviations(text) # Expand abbreviations first
            results = []; last_index = 0
            base_dialogue_patterns = {
                '"': r'"([^"]*)"',
                "'": r"'([^']*)'",
                '‘': r'‘([^’]*)’', # Left single quote
                '“': r'“([^”]*)”'  # Left double quote
            }
            # This captures (speaker_name_if_before_verb, verb_itself)
            verbs_list_str = (r"(said|replied|shouted|whispered|muttered|asked|protested|exclaimed|gasped|continued|began|explained|answered|inquired|stated|declared|announced|remarked|observed|commanded|ordered|suggested|wondered|thought|mused|cried|yelled|bellowed|stammered|sputtered|sighed|laughed|chuckled|giggled|snorted|hissed|growled|murmured|drawled|retorted|snapped|countered|concluded|affirmed|denied|agreed|acknowledged|admitted|queried|responded|questioned|urged|warned|advised|interjected|interrupted|corrected|repeated|echoed|insisted|pleaded|begged|demanded|challenged|taunted|scoffed|jeered|mocked|conceded|boasted|bragged|lectured|preached|reasoned|argued|debated|negotiated|proposed|guessed|surmised|theorized|speculated|posited|opined|ventured|volunteered|offered|added|finished|paused|resumed|narrated|commented|noted|recorded|wrote|indicated|signed|gestured|nodded|shrugged|pointed out)")
            speaker_name_bits = r"\w[\w\s\.]*" # Greedy match for speaker names

            # Regex for the content of the speaker tag.
            # Chapter detection pattern
            chapter_pattern = re.compile(r"^(Chapter\s+\w+|Prologue|Epilogue|Part\s+\w+|Section\s+\w+)\s*[:.]?\s*([^\n]*)$", re.IGNORECASE)

            # This captures (speaker_name_if_before_verb, verb_itself)
            # This pattern aims to capture the entire tag as one group,
            # and within that, identify the speaker.
            # Group 1 (of this sub_pattern): Entire tag text (e.g., ", said Hunter bravely.")
            # Group 2 (of this sub_pattern): Speaker if "Speaker Verb ..."
            # Group 3 (of this sub_pattern): Speaker if "Verb Speaker ..."
            speaker_tag_sub_pattern = rf"""
                ( # Capturing Group for the entire tag text (this will be match.group(2) of full_pattern_regex)
                    \s*,?\s* # Optional space, optional comma, optional space
                    (?: # Non-capturing group for the OR logic of tag structure
                        (?: # Option 1: Speaker then Verb
                            ({speaker_name_bits}) # Capture Speaker (becomes group 3 of full_pattern_regex)
                            \s+
                            (?:{verbs_list_str}) # Match Verb (non-capturing)
                        )
                        | # OR
                        (?: # Option 2: Verb then Speaker
                            (?:{verbs_list_str}) # Match Verb (non-capturing)
                            \s+
                            ({speaker_name_bits}) # Capture Speaker (becomes group 4 of full_pattern_regex)
                        )
                    )
                    (?:[\s\w\.,!?;:-]*) # Match trailing parts greedily, EXCLUDING QUOTES that start new dialogue
                )
            """
            
            compiled_patterns = []
            for qc, dp in base_dialogue_patterns.items():
                # Pattern to match dialogue and an optional following tag
                # Group 1: Dialogue content
                # Group 2: The entire tag text (from the outer capturing group in speaker_tag_sub_pattern)
                # Group 3: Speaker name if "Speaker Verb" format matched
                # Group 4: Speaker name if "Verb Speaker" format matched
                full_pattern_regex = dp + f'{speaker_tag_sub_pattern}?' # Tag is optional. speaker_tag_sub_pattern itself defines group 2.
                compiled_patterns.append({'qc': qc, 'pattern': re.compile(full_pattern_regex, re.IGNORECASE | re.VERBOSE)})

            all_matches = []
            for item in compiled_patterns:
                for match in item['pattern'].finditer(text):
                    all_matches.append({'match': match, 'qc': item['qc']})
            
            all_matches.sort(key=lambda x: x['match'].start())
            
            sentence_end_pattern = re.compile(r'(?<=[.!?])\s+(?=[A-Z"\'‘“])|(?<=[.!?])$')

            for item in all_matches:
                match = item['match']
                quote_char = item['qc']
                start, end = match.span()

                # Check for chapter headings in the narration before the current dialogue
                # This is a simplified approach; a more robust solution might involve
                # parsing the entire text into paragraphs/sentences first.
                # For now, we'll check the line immediately preceding a dialogue or tag.
                # A better approach would be to check the narration_before segment.
                # This will be handled by checking the narration_before segment.

                narration_before = text[last_index:start].strip()
                if narration_before:
                    sentences = sentence_end_pattern.split(narration_before)
                    for sentence in sentences:
                        if sentence and sentence.strip():
                            pov = self.determine_pov(sentence.strip())
                            line_data = {'speaker': 'Narrator', 'line': sentence.strip(), 'pov': pov}
                            
                            # Check if this narration line is a chapter heading
                            chapter_match = chapter_pattern.match(sentence.strip())
                            if chapter_match:
                                line_data['is_chapter_start'] = True
                                line_data['chapter_title'] = chapter_match.group(0).strip() # Full matched string
                            results.append(line_data)
                            self.logger.debug(f"Pass 1: Added Narrator (before): {results[-1]}")

                dialogue_content = match.group(1).strip()
                full_dialogue_text = f"{quote_char}{dialogue_content}{quote_char}"
                
                speaker_for_dialogue = "AMBIGUOUS"
                tag_text_for_narration = None

                if match.group(2): # If the optional tag group (group 2 of full_pattern_regex) matched
                    # match.group(1) is dialogue_content
                    # match.group(2) is ENTIRE tag (e.g., " said Hunter bravely.") from the outer parens of speaker_tag_sub_pattern
                    # match.group(3) is Speaker from "Speaker Verb" part (if that matched)
                    # match.group(4) is Speaker from "Verb Speaker" part (if that matched)
                    
                    raw_tag_text = match.group(2) # This is the full matched tag, like ", said Hunter"
                    speaker_name_from_sv = match.group(3)
                    speaker_name_from_vs = match.group(4) 
                    speaker_name_candidate = speaker_name_from_sv or speaker_name_from_vs

                    # If the candidate is a common pronoun, treat it as ambiguous for Pass 1 speaker ID
                    common_pronouns = {"he", "she", "they", "i", "we", "you", "it"} # Case-insensitive check later
                    if speaker_name_candidate and speaker_name_candidate.strip().lower() in common_pronouns:
                        self.logger.debug(f"Pass 1: Speaker candidate '{speaker_name_candidate}' is a pronoun. Reverting to AMBIGUOUS for dialogue line.")
                        speaker_name_candidate = None # This will ensure speaker_for_dialogue remains AMBIGUOUS

                    if speaker_name_candidate and speaker_name_candidate.strip():
                        # Ensure "Narrator" isn't accidentally titled if LLM returns it
                        speaker_for_dialogue = "Narrator" if speaker_name_candidate.strip().lower() == "narrator" else speaker_name_candidate.strip().title()
                                        
                    # Clean the raw_tag_text for the Narrator line
                    # Remove leading comma and space, keep the rest including punctuation.
                    # Also replace internal newlines with spaces to ensure it's a single visual line.
                    cleaned_tag_for_narration = raw_tag_text.lstrip(',').strip().replace('\n', ' ').replace('\r', '')
                    if cleaned_tag_for_narration:
                        tag_text_for_narration = cleaned_tag_for_narration
                
                dialogue_pov = self.determine_pov(dialogue_content) # Determine POV from the content of the dialogue
                results.append({'speaker': speaker_for_dialogue, 'line': full_dialogue_text, 'pov': dialogue_pov})
                self.logger.debug(f"Pass 1: Added Dialogue: {results[-1]} with POV: {dialogue_pov}")
                
                if tag_text_for_narration:
                    pov = self.determine_pov(tag_text_for_narration) # POV for speaker tags
                    line_data = {'speaker': 'Narrator', 'line': tag_text_for_narration, 'pov': pov}
                    # Check if this tag text is a chapter heading (less likely but possible)
                    chapter_match = chapter_pattern.match(tag_text_for_narration)
                    if chapter_match:
                        line_data['is_chapter_start'] = True
                        line_data['chapter_title'] = chapter_match.group(0).strip()
                    results.append(line_data)
                    self.logger.debug(f"Pass 1: Added Narrator (tag): {results[-1]}")

                last_index = end
            
            remaining_text_at_end = text[last_index:].strip()
            if remaining_text_at_end:
                sentences = sentence_end_pattern.split(remaining_text_at_end)
                for sentence in sentences:
                    if sentence and sentence.strip():
                        pov = self.determine_pov(sentence.strip())
                        line_data = {'speaker': 'Narrator', 'line': sentence.strip(), 'pov': pov}
                    # Check if this narration line is a chapter heading
                    chapter_match = chapter_pattern.match(sentence.strip())
                    if chapter_match:
                        line_data['is_chapter_start'] = True
                        line_data['chapter_title'] = chapter_match.group(0).strip()
                    results.append(line_data)
                    self.logger.debug(f"Pass 1: Added Narrator (after): {results[-1]}")
            self.logger.info("Pass 1 (rules-based analysis) complete with new tag handling.")
            self.ui.update_queue.put({'rules_pass_complete': True, 'results': results})
        except Exception as e:
            detailed_error = traceback.format_exc()
            self.logger.error(f"Error during Pass 1 (rules-based analysis): {detailed_error}")
            self.ui.update_queue.put({'error': f"Error during Pass 1 (rules-based analysis):\n\n{detailed_error}"})

    def determine_pov(self, text: str) -> str:
        """Determines the Point of View of a text segment based on pronouns."""
        text_lower = text.lower()
        
        # More specific first person pronouns
        first_person_singular_matches = re.findall(r'\b(i|me|my|mine)\b', text_lower)
        first_person_plural_matches = re.findall(r'\b(we|us|our|ours)\b', text_lower)
        first_person_count = len(first_person_singular_matches) + len(first_person_plural_matches)
        
        second_person_count = len(re.findall(r'\b(you|your|yours)\b', text_lower))
        
        third_person_count = len(re.findall(r'\b(he|him|his|she|her|hers|it|its|they|them|their|theirs)\b', text_lower))

        # Basic heuristic:
        if first_person_count > 0 and first_person_count >= second_person_count and first_person_count >= third_person_count:
            # Further distinguish if needed, or just return "1st Person"
            # Example: if len(first_person_singular_matches) > len(first_person_plural_matches): return "1st Person Singular"
            return "1st Person"
        elif second_person_count > 0 and second_person_count >= first_person_count and second_person_count >= third_person_count:
            return "2nd Person"
        elif third_person_count > 0 and third_person_count >= first_person_count and third_person_count >= second_person_count:
            return "3rd Person"
        elif first_person_count > 0 : return "1st Person" # Fallback if counts are equal but 1st is present
        elif second_person_count > 0 : return "2nd Person"
        elif third_person_count > 0 : return "3rd Person"
        return "Unknown"

    def start_rules_pass_thread(self, text):
        self.ui.last_operation = 'rules_pass_analysis' 
        self.ui.active_thread = threading.Thread(target=self.run_rules_pass, args=(text,))
        self.ui.active_thread.daemon = True
        self.ui.active_thread.start()
        self.ui.root.after(100, self.ui.check_update_queue)

    def start_pass_2_resolution(self):
        if self.ui.cast_list:
            for speaker_name in self.ui.cast_list:
                if speaker_name.upper() not in {"AMBIGUOUS", "UNKNOWN", "TIMED_OUT"}:
                    if speaker_name not in self.ui.character_profiles:
                        self.ui.character_profiles[speaker_name] = {'gender': 'Unknown', 'age_range': 'Unknown'}

        speakers_needing_profile = set()
        for speaker, profile in self.ui.character_profiles.items():
            gender = profile.get('gender', 'Unknown')
            age_range = profile.get('age_range', 'Unknown')
            if gender in {'Unknown', 'N/A', ''} or age_range in {'Unknown', 'N/A', ''}:
                speakers_needing_profile.add(speaker)
        
        # Separate tasks: identifying unknown speakers vs. profiling known ones.
        items_for_id = []
        items_for_profiling = []
        processed_speakers_for_profiling = set()

        for i, item in enumerate(self.ui.analysis_result):
            speaker = item['speaker']
            if speaker == 'AMBIGUOUS':
                items_for_id.append((i, item))
            elif speaker in speakers_needing_profile and speaker not in processed_speakers_for_profiling:
                items_for_profiling.append((i, item))
                processed_speakers_for_profiling.add(speaker)

        total_items_to_process = len(items_for_id) + len(items_for_profiling)

        if not total_items_to_process:
            self.ui.update_queue.put({'status': "Pass 2 Skipped: No ambiguous speakers or incomplete profiles found."})
            self.logger.info("Pass 2 (LLM resolution) skipped: No ambiguous items or incomplete profiles.")
            return

        self.logger.info(f"Pass 2: Will process {len(items_for_id)} lines for speaker identification.")
        self.logger.info(f"Pass 2: Will process {len(items_for_profiling)} lines for character profiling.")

        # Signal UI to prepare for Pass 2 resolution
        self.ui.update_queue.put({'pass_2_resolution_started': True, 'total_items': total_items_to_process})
        
        self.ui.active_thread = threading.Thread(
            target=self.run_pass_2_llm_resolution, 
            args=(items_for_id, items_for_profiling),
            daemon=True
        )
        self.ui.active_thread.start()
        self.ui.last_operation = 'analysis' # 'analysis' here refers to LLM pass
        self.ui.root.after(100, self.ui.check_update_queue)

    def run_pass_2_llm_resolution(self, items_for_id, items_for_profiling):
        try:
            client = openai.OpenAI(base_url="http://localhost:4247/v1", api_key="not-needed", timeout=30.0)
            total_processed_count = 0

            # --- PROMPT TEMPLATES ---
            system_prompt_id = (
                "You are a literary analyst. Your task is to identify the speaker of a specific line of dialogue, "
                "their likely gender, and their general age range, given surrounding context. "
                "Respond concisely according to the specified format."
            )
            user_prompt_template_id = (
                "Based on the context below, who is the speaker of the DIALOGUE line?\n\n"
                "CONTEXT BEFORE: {before_text}\n"
                "DIALOGUE: {dialogue_text}\n"
                "CONTEXT AFTER: {after_text}\n\n"
                "CRITICAL INSTRUCTIONS:\n"
                "1. Identify the SPEAKER of the DIALOGUE.\n"
                "2. Determine the likely GENDER of the SPEAKER (Male, Female, Neutral, or Unknown).\n"
                "3. Determine the general AGE RANGE of the SPEAKER (Child, Teenager, Young Adult, Adult, Elderly, or Unknown).\n"
                "4. Respond with ONLY these three pieces of information, formatted exactly as: SpeakerName, Gender, AgeRange\n"
                "   Example for a character: Hunter, Male, Adult\n"
                "   Example for narration: Narrator, Unknown, Unknown\n"
                "   Example if truly unknown: Unknown, Unknown, Unknown\n"
                "5. Do NOT add any explanation, extra punctuation, or other words to your response.\n"
                "6. CAUTION: A name mentioned *inside* the DIALOGUE is often NOT the speaker.\n"
                "7. The CONTEXT AFTER the DIALOGUE is the most likely place to find an explicit speaker tag for this DIALOGUE line."
            )

            system_prompt_profile = (
                "You are a literary analyst. Your task is to determine the likely gender and age range for a known speaker, "
                "based on their dialogue and surrounding context. Respond concisely according to the specified format."
            )
            user_prompt_template_profile = (
                "The speaker of the DIALOGUE line is known to be '{known_speaker_name}'.\n"
                "Based on the context below, what is their likely gender and age range?\n\n"
                "CONTEXT BEFORE: {before_text}\n"
                "DIALOGUE: {dialogue_text}\n"
                "CONTEXT AFTER: {after_text}\n\n"
                "CRITICAL INSTRUCTIONS:\n"
                "1. The SPEAKER is '{known_speaker_name}'.\n"
                "2. Determine the likely GENDER of the SPEAKER (Male, Female, Neutral, or Unknown).\n"
                "3. Determine the general AGE RANGE of the SPEAKER (Child, Teenager, Young Adult, Adult, Elderly, or Unknown).\n"
                "4. Respond with ONLY these three pieces of information, formatted exactly as: SpeakerName, Gender, AgeRange\n"
                "   Example: {known_speaker_name}, Male, Adult\n"
                "   Example if unknown: {known_speaker_name}, Unknown, Unknown\n"
                "5. Do NOT add any explanation, extra punctuation, or other words to your response."
            )

            # --- PROCESS BATCHES ---
            # Batch 1: Identify unknown speakers
            self.logger.info(f"Starting Pass 2, Batch 1: Speaker Identification for {len(items_for_id)} items.")
            for original_index, item in items_for_id:
                try:
                    before_text = self.ui.analysis_result[original_index - 1]['line'] if original_index > 0 else "[Start of Text]"
                    dialogue_text = item['line']
                    after_text = self.ui.analysis_result[original_index + 1]['line'] if original_index < len(self.ui.analysis_result) - 1 else "[End of Text]"
                    
                    user_prompt = user_prompt_template_id.format(
                        before_text=before_text, dialogue_text=dialogue_text, after_text=after_text
                    )

                    # --- LLM Call and Parsing (shared logic) ---
                    speaker_name, gender, age_range = self._call_llm_and_parse(client, system_prompt_id, user_prompt, original_index)
                    
                    total_processed_count += 1
                    self.ui.update_queue.put({'progress': total_processed_count - 1, 'original_index': original_index, 'new_speaker': speaker_name, 'gender': gender, 'age_range': age_range})
                    self.logger.debug(f"LLM (ID) resolved item {original_index} to: Speaker={speaker_name}, Gender={gender}, Age={age_range}")

                except openai.APITimeoutError:
                    self.logger.warning(f"Timeout processing item {original_index} with LLM."); 
                    total_processed_count += 1
                    self.ui.update_queue.put({'progress': total_processed_count - 1, 'original_index': original_index, 'new_speaker': 'TIMED_OUT', 'gender': 'Unknown', 'age_range': 'Unknown'})
                except Exception as e:
                     self.logger.error(f"Error processing item {original_index} with LLM: {e}"); 
                     total_processed_count += 1
                     self.ui.update_queue.put({'progress': total_processed_count - 1, 'original_index': original_index, 'new_speaker': 'UNKNOWN', 'gender': 'Unknown', 'age_range': 'Unknown'})

            # Batch 2: Profile known speakers
            self.logger.info(f"Starting Pass 2, Batch 2: Profiling for {len(items_for_profiling)} speakers.")
            for original_index, item in items_for_profiling:
                try:
                    known_speaker_name = item['speaker']
                    before_text = self.ui.analysis_result[original_index - 1]['line'] if original_index > 0 else "[Start of Text]"
                    dialogue_text = item['line']
                    after_text = self.ui.analysis_result[original_index + 1]['line'] if original_index < len(self.ui.analysis_result) - 1 else "[End of Text]"

                    user_prompt = user_prompt_template_profile.format(
                        known_speaker_name=known_speaker_name, before_text=before_text, dialogue_text=dialogue_text, after_text=after_text
                    )

                    # --- LLM Call and Parsing (shared logic) ---
                    # We still get all three parts, but we will only use gender and age.
                    # The LLM is instructed to return the known name, which reinforces the task.
                    _, gender, age_range = self._call_llm_and_parse(client, system_prompt_profile, user_prompt, original_index)

                    total_processed_count += 1
                    # We send the *original* speaker name back, as we are only updating their profile.
                    self.ui.update_queue.put({'progress': total_processed_count - 1, 'original_index': original_index, 'new_speaker': known_speaker_name, 'gender': gender, 'age_range': age_range})
                    self.logger.debug(f"LLM (Profile) resolved item {original_index} for '{known_speaker_name}' to: Gender={gender}, Age={age_range}")

                except openai.APITimeoutError:
                    self.logger.warning(f"Timeout processing item {original_index} with LLM."); 
                    total_processed_count += 1
                    self.ui.update_queue.put({'progress': total_processed_count - 1, 'original_index': original_index, 'new_speaker': item['speaker'], 'gender': 'Unknown', 'age_range': 'Unknown'})
                except Exception as e:
                     self.logger.error(f"Error processing item {original_index} with LLM: {e}"); 
                     total_processed_count += 1
                     self.ui.update_queue.put({'progress': total_processed_count - 1, 'original_index': original_index, 'new_speaker': item['speaker'], 'gender': 'Unknown', 'age_range': 'Unknown'})

            self.logger.info("Pass 2 (LLM resolution) completed.")
            self.ui.update_queue.put({'pass_2_complete': True})
        except Exception as e:
            detailed_error = traceback.format_exc()
            self.logger.error(f"Critical error connecting to LLM or during LLM processing: {detailed_error}")
            self.ui.update_queue.put({'error': f"A critical error occurred connecting to the LLM. Is your local server running?\n\nError: {e}"})

    def start_speaker_refinement_pass(self):
        """Starts a thread to run the speaker co-reference resolution pass."""
        if not self.ui.cast_list or len(self.ui.cast_list) <= 1:
            self.ui.update_queue.put({'status': "Not enough speakers to refine.", "level": "info"})
            return

        if not messagebox.askyesno("Confirm Speaker Refinement",
                                   "This will use the AI to analyze the speaker list and attempt to merge aliases (e.g., 'Jim' and 'James') into a single character.\n\nThis can alter your speaker list. Proceed?"):
            return

        self.ui.last_operation = 'speaker_refinement'
        self.ui.start_progress_indicator("Refining speaker list with AI...")
        
        self.ui.active_thread = threading.Thread(
            target=self.run_speaker_refinement_pass,
            daemon=True
        )
        self.ui.active_thread.start()
        self.ui.root.after(100, self.ui.check_update_queue)

    def run_speaker_refinement_pass(self):
        try:
            client = openai.OpenAI(base_url="http://localhost:4247/v1", api_key="not-needed", timeout=60.0)

            # 1. Build the context for the prompt
            speaker_context = []
            for speaker_name in self.ui.cast_list:
                if speaker_name.upper() in {"AMBIGUOUS", "UNKNOWN", "TIMED_OUT"}:
                    continue
                # Find first line for context
                first_line = next((item['line'] for item in self.ui.analysis_result if item['speaker'] == speaker_name), "No dialogue found.")
                speaker_context.append(f"- **{speaker_name}**: \"{first_line[:100]}...\"")
            
            context_str = "\n".join(speaker_context)

            # 2. Create the prompts
            system_prompt = (
                "You are an expert literary analyst specializing in character co-reference resolution. Your task is to analyze a list of speaker names from a book and group them if they refer to the same character. "
                "You must also identify which names are temporary descriptions rather than proper names."
            )
            user_prompt = (
                f"Here is a list of speaker names from a book, along with a representative line of dialogue for each:\n\n"
                f"{context_str}\n\n"
                "CRITICAL INSTRUCTIONS:\n"
                "1. Group names that refer to the same character. Use the most complete name as the primary name.\n"
                "2. Identify names that are just descriptions (e.g., 'The Man', 'An Officer').\n"
                "3. Do not group 'Narrator' with any character.\n"
                "4. Provide your response as a valid JSON object with a single key 'character_groups'. The value should be an array of objects. Each object represents a final, unique character and contains two keys:\n"
                "   - 'primary_name': The canonical name for the character (e.g., 'Captain Ian St. John').\n"
                "   - 'aliases': An array of all other names from the input list that refer to this character (e.g., ['Hunter', 'The Captain', 'Ian St.John']).\n"
                "5. If a name is a temporary description and cannot be linked to a specific character, create a group for it with the description as the 'primary_name' and an empty 'aliases' array.\n"
                "6. If a name is unique and not an alias, it should be its own group with its name as 'primary_name' and an empty 'aliases' array.\n\n"
                "Example JSON response format:\n"
                "```json\n"
                "{\n"
                "  \"character_groups\": [\n"
                "    {\n"
                "      \"primary_name\": \"Captain Ian St. John\",\n"
                "      \"aliases\": [\"Hunter\", \"The Captain\", \"Ian St.John\"]\n"
                "    },\n"
                "    {\n"
                "      \"primary_name\": \"Jimmy\",\n"
                "      \"aliases\": []\n"
                "    }\n"
                "  ]\n"
                "}\n"
                "```"
            )

            # 3. Call LLM
            self.logger.info("Sending speaker list to LLM for refinement.")
            completion = client.chat.completions.create(
                model="local-model", 
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                temperature=0.0
                # Removed response_format={"type": "json_object"} as it's not supported by all local LLM servers.
                # The prompt is explicit enough to request JSON output.
            )
            raw_response = completion.choices[0].message.content.strip()
            self.logger.info(f"LLM refinement response: {raw_response}")

            # Extract JSON block from the potentially verbose response
            json_string = None
            try:
                start_index = raw_response.find('{')
                end_index = raw_response.rfind('}')
                if start_index != -1 and end_index != -1 and end_index > start_index:
                    json_string = raw_response[start_index:end_index+1]
                    response_data = json.loads(json_string)
                else:
                    raise ValueError("No JSON object found in the response.")
            except (json.JSONDecodeError, ValueError) as e:
                self.logger.error(f"Failed to decode JSON from LLM response. Raw response was: {raw_response}. Error: {e}")
                raise ValueError(f"Could not parse a valid JSON object from the AI's response. The model returned text instead of the expected format. See log for details.") from e

            character_groups = response_data.get("character_groups", [])
            if not character_groups: raise ValueError("LLM response did not contain 'character_groups'.")
            self.ui.update_queue.put({'speaker_refinement_complete': True, 'groups': character_groups})
        except Exception as e:
            detailed_error = traceback.format_exc()
            self.logger.error(f"Error during speaker refinement pass: {detailed_error}")
            self.ui.update_queue.put({'error': f"Error during speaker refinement:\n\n{detailed_error}"})

    def _call_llm_and_parse(self, client, system_prompt, user_prompt, original_index):
        """Helper function to call the LLM and parse the 'Name, Gender, Age' response format."""
        completion = client.chat.completions.create(
            model="local-model",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.0
        )
        raw_response = completion.choices[0].message.content.strip()
        
        speaker_name, gender, age_range = "UNKNOWN", "Unknown", "Unknown"
        try:
            parts = [p.strip() for p in raw_response.split(',')]
            if len(parts) == 3:
                speaker_name = parts[0].title() if parts[0].lower() != "narrator" else "Narrator"
                gender = parts[1].title()
                age_range = parts[2].title()
                if not speaker_name: speaker_name = "UNKNOWN"
            else:
                speaker_name = raw_response.split('.')[0].split(',')[0].strip().title()
                if not speaker_name: speaker_name = "UNKNOWN"
                self.logger.warning(f"LLM response for item {original_index} not in expected 'Name, Gender, Age' format: '{raw_response}'. Extracted speaker: {speaker_name}")

            quote_chars = "\"\'‘“’”"
            if speaker_name != "Narrator" and len(speaker_name) > 1 and \
               speaker_name.startswith(tuple(quote_chars)) and speaker_name.endswith(tuple(quote_chars)):
                self.logger.warning(f"LLM returned what appears to be a quote ('{speaker_name}') as the speaker for item {original_index}. Overriding to UNKNOWN.")
                speaker_name, gender, age_range = "UNKNOWN", "Unknown", "Unknown"

        except Exception as e_parse:
            self.logger.error(f"Error parsing LLM response for item {original_index}: '{raw_response}'. Error: {e_parse}")

        return speaker_name, gender, age_range

    def start_assembly(self, clips_info_list): # Takes list of clip info dicts
        # Signal UI to prepare for assembly
        self.ui.update_queue.put({'assembly_started': True})

        self.ui.last_operation = 'assembly'
        # Pass clips_info_list directly, as it contains original_index needed for chapter timing
        self.ui.active_thread = threading.Thread(target=self.assemble_audiobook, args=(clips_info_list,))
        self.ui.active_thread.daemon = True
        self.ui.active_thread.start()
        self.ui.root.after(100, self.ui.check_update_queue) # Changed to check_update_queue

    def assemble_audiobook(self, clips_info_list):
        try:
            self.logger.info(f"Starting audiobook assembly from {len(clips_info_list)} provided clip infos. Will attempt to add chapters.")

            audio_clips_paths = []
            for clip_info in clips_info_list:
                p = Path(clip_info['clip_path'])
                if p.exists() and p.is_file():
                    audio_clips_paths.append(p)
                else:
                    self.logger.warning(f"Clip missing for assembly: {p}. Skipping.")
            
            # Sort clips_info_list by original_index to ensure correct order
            clips_info_list.sort(key=lambda x: x['original_index'])

            if not audio_clips_paths:
                raise FileNotFoundError("No valid audio clips were found to assemble.")
            
            self.logger.info(f"Found {len(audio_clips_paths)} valid clips to assemble.")
            combined_audio = AudioSegment.empty()
            # A short silence between clips sounds more natural
            silence = AudioSegment.silent(duration=250) # A short silence between clips
            
            chapter_markers = [] # List to store (start_time_ms, chapter_title)
            current_cumulative_duration_ms = 0

            for clip_info in clips_info_list:
                clip_path = Path(clip_info['clip_path'])
                # Ignore empty/corrupted files
                if clip_path.stat().st_size > 100:
                    try:
                        segment = AudioSegment.from_wav(str(clip_path))

                         # Check if this line is a chapter start
                        original_index = clip_info['original_index']
                        # Access the original analysis_result to get chapter info
                        if original_index < len(self.ui.analysis_result):
                            analysis_item = self.ui.analysis_result[original_index]
                            if analysis_item.get('is_chapter_start'):
                                chapter_title = analysis_item.get('chapter_title', f"Chapter {len(chapter_markers) + 1}")
                                chapter_markers.append((current_cumulative_duration_ms, chapter_title))
                                self.logger.info(f"Detected chapter '{chapter_title}' at {current_cumulative_duration_ms}ms.")

                        combined_audio += segment + silence
                        current_cumulative_duration_ms += len(segment) + len(silence)
                    except Exception as e: 
                        self.logger.warning(f"Skipping corrupted audio clip {clip_path.name}: {e}")
            
            if len(combined_audio) == 0: raise ValueError("No valid audio data was generated.")

            # Export combined audio to a temporary WAV file
            temp_wav_path = self.ui.output_dir / f"{self.ui.ebook_path.stem}_temp.wav"
            combined_audio.export(str(temp_wav_path), format="wav")
            self.logger.info(f"Combined audio exported to temporary WAV: {temp_wav_path}")

            final_audio_path = self.ui.output_dir / f"{self.ui.ebook_path.stem}_audiobook.m4b"

            # Generate FFmpeg chapter metadata file if chapters were found
            chapter_metadata_file = None
            if chapter_markers:
                chapter_metadata_file = self.ui.output_dir / f"{self.ui.ebook_path.stem}_chapters.txt"
                with open(chapter_metadata_file, 'w', encoding='utf-8') as f:
                    f.write(';FFMETADATA1\n')
                    for i, (start_ms, title) in enumerate(chapter_markers):
                        f.write('[CHAPTER]\n')
                        f.write('TIMEBASE=1/1000\n')
                        f.write(f'START={start_ms}\n')
                        # FFmpeg needs END time for chapters, but we don't have it easily here.
                        # For M4B, it's often sufficient to just provide START.
                        # A common workaround is to set END to the start of the next chapter or end of file.
                        # For simplicity, we'll omit END for now, as many players handle this gracefully.
                        # If issues arise, we'd need to calculate the end time of each chapter.
                        f.write(f'title={title}\n\n')
                self.logger.info(f"FFmpeg chapter metadata written to: {chapter_metadata_file}")

            # Use FFmpeg to convert WAV to M4B and add chapters
            ffmpeg_cmd = [
                'ffmpeg',
                '-i', str(temp_wav_path),
                '-c:a', 'aac', # AAC codec for M4B
                '-b:a', '128k', # Audio bitrate
                '-map_chapters', '-1', # Clear existing chapters if any
            ]
            if chapter_metadata_file:
                ffmpeg_cmd.extend(['-f', 'ffmetadata', '-i', str(chapter_metadata_file)])
                ffmpeg_cmd.extend(['-map_metadata', '1']) # Map metadata from the chapter file
            
            # Add general metadata
            ffmpeg_cmd.extend([
                '-metadata', f'artist=Radio Show',
                '-metadata', f'album={self.ui.ebook_path.stem}',
                '-metadata', f'title={self.ui.ebook_path.stem} Radio Show',
                str(final_audio_path)
            ])
            
            self.logger.info(f"Executing FFmpeg command: {' '.join(ffmpeg_cmd)}")
            subprocess.run(ffmpeg_cmd, check=True, capture_output=True, text=True)
            self.logger.info(f"FFmpeg output:\n{subprocess.run(ffmpeg_cmd, capture_output=True, text=True).stdout}")

            # Signal completion to the UI thread
            self.logger.info(f"Audiobook assembly complete. Saved to: {final_audio_path}")
            self.ui.update_queue.put({'assembly_complete': True, 'final_path': final_audio_path})
        except Exception as e:
            detailed_error = traceback.format_exc()
            self.logger.error(f"Critical error during audiobook assembly: {detailed_error}")
            self.logger.error(f"FFmpeg stderr: {subprocess.run(ffmpeg_cmd, capture_output=True, text=True).stderr}") # Log FFmpeg errors
            self.ui.update_queue.put({'error': f"A critical error occurred during assembly:\n\n{detailed_error}"})
        finally:
            # Clean up temporary files
            if temp_wav_path and temp_wav_path.exists():
                try:
                    os.remove(temp_wav_path)
                    self.logger.info(f"Cleaned up temporary WAV file: {temp_wav_path}")
                except Exception as e:
                    self.logger.warning(f"Could not delete temporary WAV file {temp_wav_path}: {e}")
            if chapter_metadata_file and chapter_metadata_file.exists():
                try:
                    os.remove(chapter_metadata_file)
                    self.logger.info(f"Cleaned up temporary chapter metadata file: {chapter_metadata_file}")
                except Exception as e:
                    self.logger.warning(f"Could not delete temporary chapter metadata file {chapter_metadata_file}: {e}")
            
    def process_ebook_path(self, filepath_str):
        if not filepath_str: return
        ebook_candidate_path = Path(filepath_str)
        if ebook_candidate_path.suffix.lower() not in self.ui.allowed_extensions:
            self.ui.update_queue.put({'error': f"Invalid File Type: '{ebook_candidate_path.suffix}'. Supported: {', '.join(self.ui.allowed_extensions)}"})
            return # messagebox.showerror("Invalid File Type", f"Supported formats are: {', '.join(self.ui.allowed_extensions)}")
        self.ui.ebook_path = ebook_candidate_path
        # Remove explicit fg="black" to allow theme to control color
        self.ui.wizard_view.file_status_label.config(text=f"Selected: {self.ui.ebook_path.name}")
        self.ui.wizard_view.next_step_button.config(state=tk.NORMAL, text="Convert to Text")
        self.ui.wizard_view.edit_text_button.config(state=tk.DISABLED)
        self.ui.status_label.config(text="")

    def perform_system_action(self, action_type, success):
        """
        Performs a system action like shutdown or sleep.
        'success' indicates if the preceding operation was successful.
        """
        current_os = platform.system()
        command = None

        self.logger.info(f"Perform system action requested: {action_type} due to operation {'success' if success else 'failure'}")

        if action_type == "shutdown":
            if current_os == "Windows":
                command = "shutdown /s /t 15"  # Shutdown in 15 seconds
            elif current_os == "Darwin": # macOS
                command = "osascript -e 'tell app \"System Events\" to shut down'" # May need permissions/confirmation
            elif current_os == "Linux":
                command = "shutdown -h +0" # May require privileges (systemctl poweroff is also an option)
        elif action_type == "sleep":
            if current_os == "Windows":
                command = "rundll32.exe powrprof.dll,SetSuspendState 0,1,0"
            elif current_os == "Darwin": # macOS
                command = "pmset sleepnow"
            elif current_os == "Linux":
                command = "systemctl suspend" # May require privileges

        if command:
            self.logger.info(f"Executing system command: {command}")
            try:
                # Use subprocess.run for better control and consistency
                subprocess.run(command, shell=True, check=True)
                # Note: shell=True can be a security hazard if the command is constructed from external input.
                # For these specific, hardcoded commands, it's generally acceptable.
                # For macOS and Linux, 'shell=True' might not be strictly necessary if commands are simple.

            except Exception as e:
                self.logger.error(f"Error executing system command '{command}': {e}")
                self.ui.update_queue.put({'error': f"Failed to initiate system {action_type}: {e}"})
        else:
            self.logger.warning(f"System action '{action_type}' not supported on this OS ({current_os}) by this script.")
            self.ui.update_queue.put({'error': f"System {action_type} not implemented for {current_os}."})

    def load_audio_segment(self, filepath_str):
        """Loads an audio file into a pydub AudioSegment."""
        try:
            return AudioSegment.from_file(filepath_str)
        except Exception as e:
            self.logger.error(f"Error loading audio file {filepath_str}: {e}")
            return None

    def remove_voice(self, voice_to_delete: dict):
        """Handles the logic of removing a voice and its associated data."""
        voice_name = voice_to_delete['name']
        self.logger.info(f"Attempting to remove voice: {voice_name}")

        # Un-assign from any speakers
        speakers_to_update = [s for s, v in self.ui.voice_assignments.items() if v['name'] == voice_name]
        for speaker in speakers_to_update:
            del self.ui.voice_assignments[speaker]
            self.logger.info(f"Unassigned voice '{voice_name}' from speaker '{speaker}'.")

        # Unset as default if it's the default
        if self.ui.default_voice_info and self.ui.default_voice_info['name'] == voice_name:
            self.ui.default_voice_info = None
            self.logger.info(f"Unset '{voice_name}' as the default voice.")

        # Remove from the main voices list
        self.ui.voices.remove(voice_to_delete)

        # Delete the actual file
        try:
            voice_path = Path(voice_to_delete['path'])
            os.remove(voice_path)
            self.logger.info(f"Deleted voice file: {voice_path}")
        except OSError as e:
            self.logger.error(f"Error deleting voice file {voice_to_delete['path']}: {e}")
            self.ui.show_status_message(f"Error deleting file for '{voice_name}'. Check logs.", "error")

    def auto_assign_voices(self):
        """
        Attempts to automatically assign a unique, available voice to each unassigned speaker.
        It prioritizes matching voices to speakers with known characteristics (gender/age).
        """
        self.logger.info("Starting unique voice auto-assignment for unassigned speakers...")

        # --- 1. Initialization and Data Preparation ---
        # Synchronize character_profiles with the cast_list to ensure all speakers are considered.
        if self.ui.cast_list:
            self.logger.info("Synchronizing character profiles with current cast list.")
            for speaker_name in self.ui.cast_list:
                # We only care about actual characters, not these placeholders.
                if speaker_name.upper() not in {"AMBIGUOUS", "UNKNOWN", "TIMED_OUT"}: # Allow "Narrator"
                    if speaker_name not in self.ui.character_profiles:
                        self.logger.info(f"Adding '{speaker_name}' to character profiles with default 'Unknown' values.")
                        self.ui.character_profiles[speaker_name] = {'gender': 'Unknown', 'age_range': 'Unknown'}

        if not self.ui.character_profiles:
            self.ui.update_queue.put({'status': "No characters found to assign voices to.", "level": "warning"})
            return

        # Get voices that are not currently in use
        assigned_voice_paths = {v['path'] for v in self.ui.voice_assignments.values()}
        available_voices = [v for v in self.ui.voices if v['path'] not in assigned_voice_paths]

        if not available_voices:
            self.ui.update_queue.put({'status': "No unassigned voices available in the library.", "level": "info"})
            self.logger.warning("Auto-assignment: No unassigned voices available.")
            return

        # Get speakers who do not have an assignment yet
        unassigned_speakers_names = [s for s in self.ui.character_profiles if s not in self.ui.voice_assignments]

        if not unassigned_speakers_names:
            self.ui.update_queue.put({'status': "All speakers already have a voice assigned.", "level": "info"})
            self.logger.info("Auto-assignment: All speakers already have voices.")
            return

        # --- 2. Prioritization: Separate unassigned speakers ---
        speakers_with_info = []
        speakers_without_info = []

        for speaker_name in unassigned_speakers_names:
            profile = self.ui.character_profiles.get(speaker_name, {})
            gender = profile.get('gender', 'Unknown')
            if gender == 'N/A': gender = 'Unknown'
            age_range = profile.get('age_range', 'Unknown')
            if age_range == 'N/A': age_range = 'Unknown'

            if gender != 'Unknown' or age_range != 'Unknown':
                speakers_with_info.append(speaker_name)
            else:
                speakers_without_info.append(speaker_name)
        
        self.logger.info(f"Attempting to assign voices to {len(unassigned_speakers_names)} speakers. Prioritizing {len(speakers_with_info)} with info.")

        assignments_made_this_run = {}

        # --- 3. First Pass: Assign to speakers with info ---
        for speaker in speakers_with_info:
            if not available_voices: break

            profile = self.ui.character_profiles[speaker]
            speaker_gender = profile.get('gender', 'Unknown')
            if speaker_gender == 'N/A': speaker_gender = 'Unknown'
            speaker_age_range = profile.get('age_range', 'Unknown')
            if speaker_age_range == 'N/A': speaker_age_range = 'Unknown'

            best_voice = None
            best_score = -1

            for voice in available_voices:
                score = 0
                voice_gender = voice.get('gender', 'Unknown')
                voice_age_range = voice.get('age_range', 'Unknown')

                if speaker_gender != 'Unknown' and voice_gender != 'Unknown':
                    score += 3 if speaker_gender == voice_gender else -3
                
                if speaker_age_range != 'Unknown' and voice_age_range != 'Unknown':
                    score += 3 if speaker_age_range == voice_age_range else -3

                if score > best_score:
                    best_score = score
                    best_voice = voice
            
            if best_voice and best_score >= 0:
                assignments_made_this_run[speaker] = best_voice
                available_voices.remove(best_voice)
                self.logger.info(f"PASS 1: Matched '{best_voice['name']}' to '{speaker}' with score {best_score}.")
            else:
                # Add to wildcard list if no good match found
                speakers_without_info.append(speaker)

        # --- 4. Second Pass: Assign remaining voices to wildcard speakers ---
        self.logger.info(f"PASS 2: Assigning remaining {len(available_voices)} voices to {len(speakers_without_info)} wildcard speakers.")
        # Sort wildcards to have a consistent assignment order
        speakers_without_info.sort()
        for speaker in speakers_without_info:
            if not available_voices: break

            voice_to_assign = None
            # Prefer default voice if it's available and unassigned
            if self.ui.default_voice_info and self.ui.default_voice_info in available_voices:
                voice_to_assign = self.ui.default_voice_info
            else:
                voice_to_assign = available_voices[0]
            
            assignments_made_this_run[speaker] = voice_to_assign
            available_voices.remove(voice_to_assign)
            self.logger.info(f"PASS 2: Assigned '{voice_to_assign['name']}' to wildcard speaker '{speaker}'.")

        # --- 5. Finalization ---
        if assignments_made_this_run:
            self.ui.voice_assignments.update(assignments_made_this_run)
            self.ui.update_queue.put({'status': f"Auto-assigned voices to {len(assignments_made_this_run)} speakers.", "level": "info"})
            self.logger.info(f"Auto-assignment complete. Assigned voices to: {list(assignments_made_this_run.keys())}")
        else:
            self.ui.update_queue.put({'status': "No new voices could be auto-assigned.", "level": "info"})
            self.logger.info("Auto-assignment: No new assignments made.")
        
        self.ui.update_cast_list() # Refresh the UI to reflect the assignments
