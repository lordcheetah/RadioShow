# app_logic.py
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
#import torch.serialization # For add_safe_globals
#import torchaudio # For audio file handling
import logging # For logging
import ebooklib
from ebooklib import epub
from PIL import Image, ImageDraw, ImageFont
import platform # For system actions

from tts_engines import CoquiXTTS, ChatterboxTTS
from file_operations import FileOperator
from text_processing import TextProcessor

class AppLogic:
    def __init__(self, ui_app, state):
        self.ui = ui_app
        self.state = state
        
        # Setup Logger
        self.logger = logging.getLogger('AudiobookCreator')
        log_file_path = self.state.output_dir / "audiobook_creator.log"
        file_handler = logging.FileHandler(log_file_path, encoding='utf-8', mode='a') # Append mode
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(module)s - %(message)s')
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)
        self.logger.setLevel(logging.INFO)
        self.logger.info("AppLogic initialized and logger configured.")

        # Initialize components that depend on the logger
        self.file_op = FileOperator(self.state, self.ui.update_queue, self.logger)
        self.text_proc = TextProcessor(self.state, self.ui.update_queue, self.logger)
        self.current_tts_engine_instance: TTSEngine | None = None
        
        # Playback management attributes
        self._current_playback_process: subprocess.Popen | None = None
        self._current_playback_temp_file: Path | None = None
        self._playback_cleanup_thread: threading.Thread | None = None
        self._current_playback_original_index: int | None = None # Track which line is playing

    def _generate_fallback_cover(self, title, author):
        """Generates a simple fallback cover image."""
        try:
            # Create a temporary file for the cover
            cover_file = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            cover_path = Path(cover_file.name)
            cover_file.close()

            width, height = 600, 900
            bg_color = (20, 20, 40) # Dark blue
            text_color = (240, 240, 240) # Light grey
            image = Image.new('RGB', (width, height), color=bg_color)
            draw = ImageDraw.Draw(image)

            try:
                title_font = ImageFont.truetype("arialbd.ttf", 50)
                author_font = ImageFont.truetype("arial.ttf", 30)
            except IOError:
                self.logger.warning("Arial font not found, using default PIL font.")
                title_font = ImageFont.load_default()
                author_font = ImageFont.load_default()

            def draw_wrapped_text(text, font, max_width):
                lines = []
                words = text.split(' ')
                line = ''
                for word in words:
                    if font.getlength(line + word + ' ') <= max_width:
                        line += word + ' '
                    else:
                        lines.append(line)
                        line = word + ' '
                lines.append(line)
                return lines

            title_lines = draw_wrapped_text(title, title_font, width - 80)
            y_text = height / 3
            for line in title_lines:
                line_width = draw.textlength(line, font=title_font)
                draw.text(((width - line_width) / 2, y_text), line, font=title_font, fill=text_color)
                y_text += title_font.getbbox(line)[3] + 10

            y_text += 50
            author_lines = draw_wrapped_text(f"by {author}", author_font, width - 80)
            for line in author_lines:
                line_width = draw.textlength(line, font=author_font)
                draw.text(((width - line_width) / 2, y_text), line, font=author_font, fill=text_color)
                y_text += author_font.getbbox(line)[3] + 5

            image.save(cover_path)
            self.logger.info(f"Generated fallback cover image at: {cover_path}")
            return cover_path
        except Exception as e:
            self.logger.error(f"Failed to generate fallback cover: {traceback.format_exc()}")
            return None

    def run_metadata_extraction(self, ebook_path_str):
        ebook_path = Path(ebook_path_str)
        title, author, cover_path = None, None, None
        
        try:
            if ebook_path.suffix.lower() == '.epub':
                try:
                    self.logger.info(f"Attempting metadata extraction with ebooklib for {ebook_path.name}")
                    book = epub.read_epub(ebook_path)
                    if book.get_metadata('DC', 'title'): title = book.get_metadata('DC', 'title')[0][0]
                    if book.get_metadata('DC', 'creator'): author = book.get_metadata('DC', 'creator')[0][0]
                    
                    cover_items = book.get_items_of_type(ebooklib.ITEM_COVER)
                    cover_image_item = next(cover_items, None)
                    if cover_image_item:
                        cover_file = tempfile.NamedTemporaryFile(suffix=f".{cover_image_item.media_type.split('/')[-1]}", delete=False)
                        cover_path = Path(cover_file.name)
                        cover_file.write(cover_image_item.content)
                        cover_file.close()
                        self.logger.info(f"Extracted cover from EPUB to {cover_path}")
                except Exception as e_epub:
                    self.logger.warning(f"ebooklib failed for {ebook_path.name}: {e_epub}. Will try Calibre.")

            if not all([title, author, cover_path]) and self.file_op.find_calibre_executable():
                self.logger.info(f"Using Calibre's ebook-meta for {ebook_path.name}")
                ebook_meta_path = str(self.state.calibre_exec_path).replace('ebook-convert', 'ebook-meta')
                if not title or not author:
                    meta_cmd = [ebook_meta_path, str(ebook_path), '--to-json']
                    result = subprocess.run(meta_cmd, capture_output=True, text=True, check=False, creationflags=subprocess.CREATE_NO_WINDOW, encoding='utf-8')
                    if result.returncode == 0 and result.stdout:
                        meta_json = json.loads(result.stdout)
                        if not title: title = meta_json.get('title')
                        if not author and meta_json.get('authors'): author = " & ".join(meta_json.get('authors'))
                if not cover_path:
                    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as cover_file:
                        temp_cover_path = Path(cover_file.name)
                    cover_cmd = [ebook_meta_path, str(ebook_path), f'--get-cover={temp_cover_path}']
                    if subprocess.run(cover_cmd, capture_output=True, check=False).returncode == 0 and temp_cover_path.stat().st_size > 0:
                        cover_path = temp_cover_path
                        self.logger.info(f"Extracted cover with Calibre to {cover_path}")

            final_title = title or ebook_path.stem.replace('_', ' ').title()
            final_author = author or "Unknown Author"
            if not cover_path: cover_path = self._generate_fallback_cover(final_title, final_author)
            self.ui.update_queue.put({'metadata_extracted': True, 'title': final_title, 'author': final_author, 'cover_path': str(cover_path) if cover_path else None})
        except Exception as e:
            self.logger.error(f"Critical error during metadata extraction: {traceback.format_exc()}")
            self.ui.update_queue.put({'error': f"Failed to extract metadata: {e}"})

    def run_tts_initialization(self):
        """Initializes the selected TTS engine."""
        current_engine_to_init = self.ui.selected_tts_engine_name # Use the UI's current selection
        self.logger.info(f"Attempting to initialize TTS engine: {current_engine_to_init}")

        if not current_engine_to_init: # Handle case where no engine is selected/available
            self.logger.warning("No TTS engine selected for initialization (e.g., none found).")
            self.ui.update_queue.put({'error': "No TTS engine selected or available for initialization."})
            return

        if current_engine_to_init == "Coqui XTTS":
            self.current_tts_engine_instance = CoquiXTTS(self.ui, self.logger)
        elif current_engine_to_init == "Chatterbox":
            self.current_tts_engine_instance = ChatterboxTTS(self.ui, self.logger)
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
            clips_dir = self.state.output_dir / self.state.ebook_path.stem
            clips_dir.mkdir(exist_ok=True)
            self.logger.info(f"Starting audio generation. Clips will be saved to: {clips_dir}")

            if not self.current_tts_engine_instance:
                self.ui.update_queue.put({'error': "TTS Engine not initialized. Cannot generate audio."})
                self.logger.error("Audio generation failed: TTS Engine not initialized.")
                return

            voice_assignments = self.state.voice_assignments
            app_default_voice_info = self.state.default_voice_info
            
            if not app_default_voice_info:
                self.ui.update_queue.put({'error': "No default voice set. Please set a default voice in the 'Voice Library'."})
                self.logger.error("Audio generation failed: No default voice set.")
                return

            generated_clips_info_list = []
            lines_to_process_count = len([item for item in self.state.analysis_result if self.ui.sanitize_for_tts(item['line'])])
            processed_line_counter = 0

            def get_voice_info_for_speaker(speaker_name_local):
                if speaker_name_local in voice_assignments:
                    return voice_assignments[speaker_name_local]
                return app_default_voice_info

            for original_idx, item in enumerate(self.state.analysis_result):
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
            # Play the original clip path directly, no need for temp files
            ffplay_cmd = ['ffplay', '-nodisp', '-autoexit', '-loglevel', 'quiet', str(clip_path)]
            self.logger.info(f"Starting ffplay process: {' '.join(ffplay_cmd)}")
            
            creationflags = 0
            if platform.system() == "Windows":
                creationflags = subprocess.CREATE_NO_WINDOW

            # The cleanup thread will now only wait for the process, not delete a temp file
            process = subprocess.Popen(ffplay_cmd, creationflags=creationflags)
            
            self._current_playback_process = process
            self._current_playback_temp_file = None # No longer need a temp file
            self._current_playback_original_index = original_index

            self._playback_cleanup_thread = threading.Thread(
                target=self._cleanup_playback,
                args=(process, original_index),
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

    def _cleanup_playback(self, process: subprocess.Popen, original_index: int):
        try:
            returncode = process.wait()
            self.logger.info(f"Playback process for line {original_index} finished with return code {returncode}.")
            
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
        self.logger.debug("Playback cleanup thread finished.")

    def on_app_closing(self):
        self.stop_playback()

    # ... The rest of the AppLogic class is unchanged ...
    def initialize_tts(self):
        self.state.last_operation = 'tts_init'
        self.state.active_thread = threading.Thread(target=self.run_tts_initialization)
        self.state.active_thread.daemon = True
        self.state.active_thread.start()
        self.ui.root.after(100, self.ui.check_update_queue)

    def process_ebook_path(self, filepath_str):
        # This method remains in AppLogic as it coordinates UI updates and thread creation
        if not filepath_str: return
        ebook_candidate_path = Path(filepath_str)
        if ebook_candidate_path.suffix.lower() not in self.ui.allowed_extensions:
            self.ui.update_queue.put({'error': f"Invalid File Type: '{ebook_candidate_path.suffix}'. Supported: {', '.join(self.ui.allowed_extensions)}"})
            return
        
        self.state.last_operation = 'metadata_extraction'
        self.ui.update_queue.put({'file_accepted': True, 'ebook_path': str(ebook_candidate_path)})

        self.state.active_thread = threading.Thread(target=self.run_metadata_extraction, args=(filepath_str,), daemon=True)
        self.state.active_thread.start()
        
    def start_conversion_process(self):
        if not self.file_op.find_calibre_executable(): return messagebox.showerror("Calibre Not Found", "Could not find Calibre's 'ebook-convert.exe'.")
        self.ui.start_progress_indicator("Converting, please wait...")
        self.state.last_operation = 'conversion'

        self.state.active_thread = threading.Thread(target=self.file_op.run_calibre_conversion); self.state.active_thread.daemon = True; self.state.active_thread.start()
        self.ui.root.after(100, self.ui.check_update_queue)

    def start_rules_pass_thread(self, text):
        self.state.last_operation = 'rules_pass_analysis' 
        self.state.active_thread = threading.Thread(target=self.text_proc.run_rules_pass, args=(text,))
        self.state.active_thread.daemon = True
        self.state.active_thread.start()
        self.ui.root.after(100, self.ui.check_update_queue)

    def start_pass_2_resolution(self):
        if self.state.cast_list:
            for speaker_name in self.state.cast_list:
                if speaker_name.upper() not in {"AMBIGUOUS", "UNKNOWN", "TIMED_OUT"}:
                    if speaker_name not in self.state.character_profiles:
                        self.state.character_profiles[speaker_name] = {'gender': 'Unknown', 'age_range': 'Unknown'}

        speakers_needing_profile = set()
        for speaker, profile in self.state.character_profiles.items():
            gender = profile.get('gender', 'Unknown')
            age_range = profile.get('age_range', 'Unknown')
            if gender in {'Unknown', 'N/A', ''} or age_range in {'Unknown', 'N/A', ''}:
                speakers_needing_profile.add(speaker)
        
        # Separate tasks: identifying unknown speakers vs. profiling known ones.
        items_for_id = []
        items_for_profiling = []
        processed_speakers_for_profiling = set()

        for i, item in enumerate(self.state.analysis_result):
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
        
        self.state.active_thread = threading.Thread(
            target=self.text_proc.run_pass_2_llm_resolution, 
            args=(items_for_id, items_for_profiling),
            daemon=True
        )
        self.state.active_thread.start()
        self.state.last_operation = 'analysis' # 'analysis' here refers to LLM pass
        self.ui.root.after(100, self.ui.check_update_queue)

    def start_speaker_refinement_pass(self):
        """Starts a thread to run the speaker co-reference resolution pass."""
        if not self.state.cast_list or len(self.state.cast_list) <= 1:
            self.ui.update_queue.put({'status': "Not enough speakers to refine.", "level": "info"})
            return

        if not messagebox.askyesno("Confirm Speaker Refinement",
                                   "This will use the AI to analyze the speaker list and attempt to merge aliases (e.g., 'Jim' and 'James') into a single character.\n\nThis can alter your speaker list. Proceed?"):
            return

        self.state.last_operation = 'speaker_refinement'
        self.ui.start_progress_indicator("Refining speaker list with AI...")
        
        self.state.active_thread = threading.Thread(
            target=self.text_proc.run_speaker_refinement_pass,
            daemon=True
        )
        self.state.active_thread.start()
        self.ui.root.after(100, self.ui.check_update_queue)

    def start_assembly(self, clips_info_list): # Takes list of clip info dicts
        # Signal UI to prepare for assembly
        self.ui.update_queue.put({'assembly_started': True})

        self.state.last_operation = 'assembly'
        # Pass clips_info_list directly, as it contains original_index needed for chapter timing
        self.state.active_thread = threading.Thread(target=self.file_op.assemble_audiobook, args=(clips_info_list,))
        self.state.active_thread.daemon = True
        self.state.active_thread.start()
        self.ui.root.after(100, self.ui.check_update_queue) # Changed to check_update_queue

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
        speakers_to_update = [s for s, v in self.state.voice_assignments.items() if v['name'] == voice_name]
        for speaker in speakers_to_update:
            del self.state.voice_assignments[speaker]
            self.logger.info(f"Unassigned voice '{voice_name}' from speaker '{speaker}'.")

        # Unset as default if it's the default
        if self.state.default_voice_info and self.state.default_voice_info['name'] == voice_name:
            self.state.default_voice_info = None
            self.logger.info(f"Unset '{voice_name}' as the default voice.")

        # Remove from the main voices list
        self.state.voices.remove(voice_to_delete)

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
        if self.state.cast_list:
            self.logger.info("Synchronizing character profiles with current cast list.")
            for speaker_name in self.state.cast_list:
                # We only care about actual characters, not these placeholders.
                if speaker_name.upper() not in {"AMBIGUOUS", "UNKNOWN", "TIMED_OUT"}: # Allow "Narrator"
                    if speaker_name not in self.state.character_profiles:
                        self.logger.info(f"Adding '{speaker_name}' to character profiles with default 'Unknown' values.")
                        self.state.character_profiles[speaker_name] = {'gender': 'Unknown', 'age_range': 'Unknown'}

        if not self.state.character_profiles:
            self.ui.update_queue.put({'status': "No characters found to assign voices to.", "level": "warning"})
            return

        # Get voices that are not currently in use
        assigned_voice_paths = {v['path'] for v in self.state.voice_assignments.values()}
        available_voices = [v for v in self.state.voices if v['path'] not in assigned_voice_paths]

        if not available_voices:
            self.ui.update_queue.put({'status': "No unassigned voices available in the library.", "level": "info"})
            self.logger.warning("Auto-assignment: No unassigned voices available.")
            return

        # Get speakers who do not have an assignment yet
        unassigned_speakers_names = [s for s in self.state.character_profiles if s not in self.state.voice_assignments]

        if not unassigned_speakers_names:
            self.ui.update_queue.put({'status': "All speakers already have a voice assigned.", "level": "info"})
            self.logger.info("Auto-assignment: All speakers already have voices.")
            return

        # --- 2. Prioritization: Separate unassigned speakers ---
        speakers_with_info = []
        speakers_without_info = []

        for speaker_name in unassigned_speakers_names:
            profile = self.state.character_profiles.get(speaker_name, {})
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

            profile = self.state.character_profiles[speaker]
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
            if self.state.default_voice_info and self.state.default_voice_info in available_voices:
                voice_to_assign = self.state.default_voice_info
            else:
                voice_to_assign = available_voices[0]
            
            assignments_made_this_run[speaker] = voice_to_assign
            available_voices.remove(voice_to_assign)
            self.logger.info(f"PASS 2: Assigned '{voice_to_assign['name']}' to wildcard speaker '{speaker}'.")

        # --- 5. Finalization ---
        if assignments_made_this_run:
            self.state.voice_assignments.update(assignments_made_this_run)
            self.ui.update_queue.put({'status': f"Auto-assigned voices to {len(assignments_made_this_run)} speakers.", "level": "info"})
            self.logger.info(f"Auto-assignment complete. Assigned voices to: {list(assignments_made_this_run.keys())}")
        else:
            self.ui.update_queue.put({'status': "No new voices could be auto-assigned.", "level": "info"})
            self.logger.info("Auto-assignment: No new assignments made.")
        
        self.ui.update_cast_list() # Refresh the UI to reflect the assignments
