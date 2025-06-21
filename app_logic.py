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
        self.logger = logging.getLogger('AudiobookCreator')
        log_file_path = self.ui.output_dir / "audiobook_creator.log"
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

                narration_before = text[last_index:start].strip()
                if narration_before:
                    sentences = sentence_end_pattern.split(narration_before)
                    for sentence in sentences:
                        if sentence and sentence.strip():
                            pov = self.determine_pov(sentence.strip())
                            results.append({'speaker': 'Narrator', 'line': sentence.strip(), 'pov': pov})
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
                    results.append({'speaker': 'Narrator', 'line': tag_text_for_narration, 'pov': pov})
                    self.logger.debug(f"Pass 1: Added Narrator (tag): {results[-1]}")

                last_index = end
            
            remaining_text_at_end = text[last_index:].strip()
            if remaining_text_at_end:
                sentences = sentence_end_pattern.split(remaining_text_at_end)
                for sentence in sentences:
                    if sentence and sentence.strip():
                        pov = self.determine_pov(sentence.strip())
                        results.append({'speaker': 'Narrator', 'line': sentence.strip(), 'pov': pov})
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
        ambiguous_items = [(i, item) for i, item in enumerate(self.ui.analysis_result) if item['speaker'] == 'AMBIGUOUS']
        if not ambiguous_items:
            self.ui.update_queue.put({'status': "Pass 2 Skipped: No ambiguous speakers found to resolve."})
            self.logger.info("Pass 2 (LLM resolution) skipped: No ambiguous items.")
            return

        # Signal UI to prepare for Pass 2 resolution
        self.ui.update_queue.put({'pass_2_resolution_started': True, 'total_items': len(ambiguous_items)})
        
        self.ui.active_thread = threading.Thread(target=self.run_pass_2_llm_resolution, args=(ambiguous_items,)); self.ui.active_thread.daemon = True; self.ui.active_thread.start()
        self.ui.last_operation = 'analysis' # 'analysis' here refers to LLM pass
        self.ui.root.after(100, self.ui.check_update_queue)

    def run_pass_2_llm_resolution(self, ambiguous_items):
        try:
            # This requires a local LLM server like LM Studio or Ollama running.
            self.logger.info(f"Starting Pass 2 (LLM resolution) for {len(ambiguous_items)} items.")
            client = openai.OpenAI(base_url="http://localhost:4247/v1", api_key="not-needed", timeout=30.0)
            
            system_prompt = (
                "You are a literary analyst. Your task is to identify the speaker of a specific line of dialogue, "
                "their likely gender, and their general age range, given surrounding context. "
                "Respond concisely according to the specified format."
            )
            
            for i, (original_index, item) in enumerate(ambiguous_items):
                try:
                    before_text = self.ui.analysis_result[original_index - 1]['line'] if original_index > 0 else "[Start of Text]"
                    dialogue_text = item['line']
                    after_text = self.ui.analysis_result[original_index + 1]['line'] if original_index < len(self.ui.analysis_result) - 1 else "[End of Text]"
                    
                    user_prompt = (
                        "Based on the context below, who is the speaker of the DIALOGUE line?\n\n"
                        f"CONTEXT BEFORE: {before_text}\n"
                        f"DIALOGUE: {dialogue_text}\n"
                        f"CONTEXT AFTER: {after_text}\n\n"
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

                    completion = client.chat.completions.create(
                        model="local-model", # Model configured in your local server
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        temperature=0.0 # Low temperature for deterministic output
                    )
                    raw_response = completion.choices[0].message.content.strip()
                    
                    # Attempt to extract just the speaker name if the model is verbose
                    # Common patterns: "The speaker is X.", "Speaker: X", "X"
                    # This is a simple heuristic; more complex parsing might be needed for other models.
                    processed_name = raw_response
                    
                    speaker_name, gender, age_range = "UNKNOWN", "Unknown", "Unknown" # Defaults
                    try:
                        parts = [p.strip() for p in processed_name.split(',')]
                        if len(parts) == 3:
                            speaker_name = parts[0].title() if parts[0].lower() != "narrator" else "Narrator"
                            gender = parts[1].title()
                            age_range = parts[2].title()
                            if not speaker_name: speaker_name = "UNKNOWN" # Catch empty string after title
                        else:
                            # Fallback if parsing fails, try to get at least the speaker name from potentially verbose output
                            # This part is less critical if the LLM follows the new strict format.
                            speaker_name = processed_name.split('.')[0].split(',')[0].strip().title()
                            if not speaker_name: speaker_name = "UNKNOWN"
                            self.logger.warning(f"LLM response for item {original_index} not in expected 'Name, Gender, Age' format: '{raw_response}'. Extracted speaker: {speaker_name}")

                        # Check if the identified speaker_name looks like a quote itself.
                        # If so, the LLM likely failed to identify a speaker and returned part of the dialogue.
                        quote_chars = "\"\'‘“’”" # Common quote characters
                        if speaker_name != "Narrator" and \
                           len(speaker_name) > 1 and \
                           speaker_name.startswith(tuple(quote_chars)) and \
                           speaker_name.endswith(tuple(quote_chars)):
                            self.logger.warning(f"LLM returned what appears to be a quote ('{speaker_name}') as the speaker for item {original_index}. Overriding to UNKNOWN.")
                            speaker_name, gender, age_range = "UNKNOWN", "Unknown", "Unknown"

                    except Exception as e_parse:
                        self.logger.error(f"Error parsing LLM response for item {original_index}: '{raw_response}'. Error: {e_parse}")
                        # Speaker name might have been extracted by the fallback above if format was off.

                    self.ui.update_queue.put({'progress': i, 'original_index': original_index, 'new_speaker': speaker_name, 'gender': gender, 'age_range': age_range})
                    self.logger.debug(f"LLM resolved item {original_index} to: Speaker={speaker_name}, Gender={gender}, Age={age_range}")
                except openai.APITimeoutError:
                    self.logger.warning(f"Timeout processing item {original_index} with LLM."); 
                    self.ui.update_queue.put({'progress': i, 'original_index': original_index, 'new_speaker': 'TIMED_OUT', 'gender': 'Unknown', 'age_range': 'Unknown'})
                except Exception as e:
                     self.logger.error(f"Error processing item {original_index} with LLM: {e}"); 
                     self.ui.update_queue.put({'progress': i, 'original_index': original_index, 'new_speaker': 'UNKNOWN', 'gender': 'Unknown', 'age_range': 'Unknown'})
            self.logger.info("Pass 2 (LLM resolution) completed.")
        except Exception as e:
            detailed_error = traceback.format_exc()
            self.logger.error(f"Critical error connecting to LLM or during LLM processing: {detailed_error}")
            self.ui.update_queue.put({'error': f"A critical error occurred connecting to the LLM. Is your local server running?\n\nError: {e}"})

    def start_assembly(self, clips_info_list): # Takes list of clip info dicts
        # Signal UI to prepare for assembly
        self.ui.update_queue.put({'assembly_started': True})

        self.ui.last_operation = 'assembly'
        self.ui.active_thread = threading.Thread(target=self.assemble_audiobook, args=(clips_info_list,))
        self.ui.active_thread.daemon = True
        self.ui.active_thread.start()
        self.ui.root.after(100, self.ui.check_update_queue) # Changed to check_update_queue

    def assemble_audiobook(self, clips_info_list):
        try:
            self.logger.info(f"Starting audiobook assembly from {len(clips_info_list)} provided clip infos.")

            audio_clips_paths = []
            for clip_info in clips_info_list:
                p = Path(clip_info['clip_path'])
                if p.exists() and p.is_file():
                    audio_clips_paths.append(p)
                else:
                    self.logger.warning(f"Clip missing for assembly: {p}. Skipping.")
            
            # Sort by original index to ensure correct order, using the filename convention line_XXXXX.wav
            audio_clips_paths.sort(key=lambda p: p.name) 

            if not audio_clips_paths:
                raise FileNotFoundError("No valid audio clips were found to assemble.")
            
            self.logger.info(f"Found {len(audio_clips_paths)} valid clips to assemble.")
            combined_audio = AudioSegment.empty()
            # A short silence between clips sounds more natural
            silence = AudioSegment.silent(duration=250) 
            for clip_path in audio_clips_paths:
                # Ignore empty/corrupted files
                if clip_path.stat().st_size > 100:
                    try:
                        segment = AudioSegment.from_wav(str(clip_path))
                        combined_audio += segment + silence
                    except Exception as e: 
                        self.logger.warning(f"Skipping corrupted audio clip {clip_path.name}: {e}")
            
            if len(combined_audio) == 0: raise ValueError("No valid audio data was generated.")

            final_audio_path = self.ui.output_dir / f"{self.ui.ebook_path.stem}_audiobook.mp3"
            combined_audio.export(
                str(final_audio_path), 
                format="mp3", 
                bitrate="192k", 
                tags={'artist': 'Audiobook Creator', 'album': self.ui.ebook_path.stem}
            )
            # Signal completion to the UI thread
            self.logger.info(f"Audiobook assembly complete. Saved to: {final_audio_path}")
            self.ui.update_queue.put({'assembly_complete': True, 'final_path': final_audio_path})
        except Exception as e:
            detailed_error = traceback.format_exc()
            self.logger.error(f"Critical error during audiobook assembly: {detailed_error}")
            self.ui.update_queue.put({'error': f"A critical error occurred during assembly:\n\n{detailed_error}"})
            
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
        """Attempts to automatically assign suitable voices to speakers based on gender/age."""
        self.logger.info("Starting automatic voice assignment...")
        
        if not self.ui.character_profiles:
            self.ui.update_queue.put({'status': "No character profiles available. Run analysis first.", "level": "warning"}) # Changed to level
            self.logger.warning("Auto-assignment: No character profiles found.")
            return

        if not self.ui.voices:
            self.ui.update_queue.put({'status': "No voices in library to auto-assign.", "level": "warning"}) # Changed to level
            self.logger.warning("Auto-assignment: No voices in the library.")
            return

        new_assignments = {}
        for speaker, profile in self.ui.character_profiles.items():
            gender = profile.get('gender', 'Unknown')
            age_range = profile.get('age_range', 'Unknown')
            
            # Basic Matching (can be improved)
            potential_matches = [
                v for v in self.ui.voices
                if (v.get('gender', 'Unknown') == gender or gender == 'Unknown' or v.get('gender', 'Unknown') == 'Unknown') and
                (v.get('age_range', 'Unknown') == age_range or age_range == 'Unknown' or v.get('age_range', 'Unknown') == 'Unknown')
            ]

            if potential_matches:
                # Simple Selection (first match) - replace with better logic if needed
                chosen_voice = potential_matches[0]
                new_assignments[speaker] = chosen_voice
                self.logger.info(f"Auto-assigned voice '{chosen_voice['name']}' to '{speaker}' (Gender: {gender}, Age: {age_range})")
            else:
                self.logger.info(f"No suitable voice found for '{speaker}' (Gender: {gender}, Age: {age_range})")

        if new_assignments:
            self.ui.voice_assignments.update(new_assignments)
            self.ui.update_queue.put({'status': f"Auto-assigned voices to {len(new_assignments)} speakers.", "level": "info"}) # Changed to level
            self.logger.info(f"Auto-assigned voices: {new_assignments.keys()}")
        else:
            self.ui.update_queue.put({'status': "No voices could be auto-assigned with current criteria.", "level": "info"}) # Changed to level
            self.logger.info("Auto-assignment: No suitable matches found.")
        
        self.ui.update_cast_list() # Refresh the UI to reflect the assignments
