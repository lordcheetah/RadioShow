# app_logic.py
from TTS.api import TTS
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
import torch.serialization # For add_safe_globals
import logging # For logging
import platform # For system actions

# Import classes needed for PyTorch's safe unpickling
from TTS.tts.configs.xtts_config import XttsConfig
from TTS.tts.models.xtts import XttsAudioConfig, XttsArgs
from TTS.config.shared_configs import BaseDatasetConfig

class AppLogic:
    def __init__(self, ui_app):
        self.ui = ui_app
        # TTS initialization is started from the UI after the window appears

        # Add problematic classes to PyTorch's safe globals once at initialization
        torch.serialization.add_safe_globals([XttsConfig, XttsAudioConfig, BaseDatasetConfig, XttsArgs])
        
        # Setup Logger
        self.logger = logging.getLogger('AudiobookCreator')
        log_file_path = self.ui.output_dir / "audiobook_creator.log"
        file_handler = logging.FileHandler(log_file_path, encoding='utf-8', mode='a') # Append mode
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(module)s - %(message)s')
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)
        self.logger.setLevel(logging.INFO)
        self.logger.info("AppLogic initialized and logger configured.")

    # In app_logic.py

    def run_tts_initialization(self):
        """--- FINAL CORRECTED VERSION: Reinstates local model loading from a manual download. ---"""
        try:
            os.environ["COQUI_TOS_AGREED"] = "1"
            self.logger.info("Attempting to initialize TTS engine.")
            user_local_model_dir = self.ui.output_dir / "XTTS_Model"
            model_file = user_local_model_dir / "model.pth"
            config_file = user_local_model_dir / "config.json"
            vocab_file = user_local_model_dir / "vocab.json"
            speakers_file = user_local_model_dir / "speakers_xtts.pth" # Crucial for XTTSv2

            model_loaded_from_user_local = False # Renamed for clarity
            
            # Attempt to load from user-specified local directory first
            if model_file.is_file() and config_file.is_file() and vocab_file.is_file() and speakers_file.is_file():
                self.ui.update_queue.put({'status': f"Found user-provided local model at {user_local_model_dir}. Attempting to load..."})
                print(f"Attempting to load user-provided local TTS model from: {user_local_model_dir}")
                try:
                    self.ui.tts_engine = TTS(
                        model_path=str(user_local_model_dir), # Point to the directory
                        progress_bar=False, 
                        gpu=True # Enable GPU
                    )
                    model_loaded_from_user_local = True
                    self.ui.update_queue.put({'status': f"Successfully loaded model from {user_local_model_dir}."})
                    self.logger.info(f"Successfully loaded user-provided model from {user_local_model_dir}.")
                except Exception as e_local_load:
                    detailed_error_local = traceback.format_exc()
                    self.ui.update_queue.put({'status': f"Warning: Failed to load user-provided model from {user_local_model_dir}. Error: {str(e_local_load)[:100]}... Will try default model."})
                    self.logger.warning(f"Failed to load user-provided model from {user_local_model_dir}:\n{detailed_error_local}")
                    # Proceed to try default model
            else:
                # Optional: Inform user if some files for local model were missing, leading to fallback
                if user_local_model_dir.exists(): # If the directory exists but files are incomplete
                    missing_for_local = []
                    if not model_file.is_file(): missing_for_local.append("'model.pth'")
                    if not config_file.is_file(): missing_for_local.append("'config.json'")
                    if not vocab_file.is_file(): missing_for_local.append("'vocab.json'")
                    if not speakers_file.is_file(): missing_for_local.append("'speakers_xtts.pth'")
                    if missing_for_local:
                        msg = f"User-provided local model at {user_local_model_dir} is incomplete (missing: {', '.join(missing_for_local)}). Will try default model."
                        self.ui.update_queue.put({'status': msg})
                        self.logger.info(msg)

            if not model_loaded_from_user_local:
                self.ui.update_queue.put({'status': "Attempting to load/download default XTTSv2 model (this may take a while on first run)..."})
                self.logger.info("Attempting to load/download default XTTSv2 model...")
                # This will use Coqui's cache. If downloaded once, it will load from cache.
                # If not in cache, it will download.
                model_name = "tts_models/multilingual/multi-dataset/xtts_v2"
                self.ui.tts_engine = TTS(model_name, progress_bar=False, gpu=True) # Enable GPU
                self.ui.update_queue.put({'status': "Default XTTSv2 model loaded/downloaded successfully."})
                self.logger.info("Default XTTSv2 model loaded/downloaded successfully.")

            # If we reach here, one of the TTS engine initializations should have succeeded.
            self.ui.update_queue.put({'tts_init_complete': True})
            self.logger.info("TTS engine initialization complete.")
        except Exception as e:
            detailed_error = traceback.format_exc()
            error_message = f"Could not initialize Coqui TTS.\n\nDETAILS:\n{detailed_error}\n\n"

            # Check if the failure likely occurred during the default model load/download attempt.
            # This is inferred if model_loaded_from_user_local is False (meaning user local load was skipped or failed, and we proceeded to default).
            if not model_loaded_from_user_local: # This includes the case where user_local_model_dir didn't exist or was incomplete.
                error_message += ("The error likely occurred while loading/downloading the default XTTSv2 model.\n"
                                  "This can happen if the model files in the Coqui TTS cache "
                                  "(e.g., in a folder like '.local/share/tts/' in your user directory, then 'tts_models--multilingual--multi-dataset--xtts_v2') "
                                  "are incomplete or corrupted, or if there was a network issue during a previous download.\n"
                                  "RECOMMENDATION: Try deleting this specific model folder from the Coqui TTS cache to force a fresh download. Ensure a stable internet connection.\n")
            else: # This branch implies model_loaded_from_user_local was True, but an error still occurred (less likely for this specific error)
                  # OR the error happened during the *attempt* to load the user_local_model (which is caught by the inner try-except, but this is a fallback).
                error_message += (f"If you were attempting to use a user-provided model from '{user_local_model_dir}', "
                                  "ensure it is complete (model.pth, config.json, vocab.json, speakers_xtts.pth are all present and valid) "
                                  "and compatible with TTS version 0.22.0.\n")
            
            self.logger.error(f"TTS Initialization failed: {error_message}")
            self.ui.update_queue.put({'error': error_message})
            
    def run_audio_generation(self):
        """Generates audio for each line in analysis_result, 1-to-1 mapping."""
        try:
            clips_dir = self.ui.output_dir / self.ui.ebook_path.stem
            clips_dir.mkdir(exist_ok=True)
            self.logger.info(f"Starting audio generation. Clips will be saved to: {clips_dir}")

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
                tts_call_args = {"text": sanitized_line, "file_path": str(clip_path)}

                if voice_info_for_this_line['path'] == '_XTTS_INTERNAL_VOICE_':
                    self.logger.info(f"Using internal XTTS voice for line {original_idx}.")
                    tts_call_args["speaker"] = "Claribel Dervla" # Default XTTS speaker
                    tts_call_args["language"] = "en"
                else:
                    speaker_wav_path = Path(voice_info_for_this_line['path'])
                    if speaker_wav_path.exists():
                        tts_call_args["speaker_wav"] = [str(speaker_wav_path)]
                        tts_call_args["language"] = "en" # XTTS generally infers language from speaker_wav
                    else:
                        self.logger.error(f"Voice WAV for '{voice_info_for_this_line['name']}' not found at '{speaker_wav_path}'. Using internal voice for line {original_idx}.")
                        tts_call_args["speaker"] = "Claribel Dervla"; tts_call_args["language"] = "en"
                
                self.logger.info(f"Generating line {original_idx} with voice '{voice_info_for_this_line['name']}' for text: \"{sanitized_line[:50]}...\"")
                self.ui.tts_engine.tts_to_file(**tts_call_args) # XTTS handles long text by auto-chunking

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
            original_text = line_data['text'] # Use original text for regeneration
            sanitized_text_for_tts = self.ui.sanitize_for_tts(original_text)
            clip_path_to_overwrite = Path(line_data['clip_path'])
            original_idx = line_data['original_index']

            if not sanitized_text_for_tts.strip():
                self.logger.warning(f"Skipping regeneration for line {original_idx} as it's empty after sanitization.")
                self.ui.update_queue.put({'error': f"Line {original_idx+1} is empty after sanitization. Cannot regenerate."})
                return

            tts_call_args = {"text": sanitized_text_for_tts, "file_path": str(clip_path_to_overwrite)}
            if target_voice_info['path'] == '_XTTS_INTERNAL_VOICE_':
                tts_call_args["speaker"] = "Claribel Dervla"
                tts_call_args["language"] = "en"
            else:
                speaker_wav_path = Path(target_voice_info['path'])
                if speaker_wav_path.exists():
                    tts_call_args["speaker_wav"] = [str(speaker_wav_path)]
                    tts_call_args["language"] = "en"
                else:
                    self.logger.error(f"Regen: Voice WAV for '{target_voice_info['name']}' not found. Using internal.")
                    tts_call_args["speaker"] = "Claribel Dervla"; tts_call_args["language"] = "en"
            
            self.logger.info(f"Regenerating line {original_idx} with voice '{target_voice_info['name']}'")
            self.ui.tts_engine.tts_to_file(**tts_call_args)

            self.ui.update_queue.put({
                'single_line_regeneration_complete': True, 
                'original_index': original_idx, 
                'new_clip_path': str(clip_path_to_overwrite) # Path remains the same
            })
        except Exception as e:
            detailed_error = traceback.format_exc()
            self.logger.error(f"Critical error during single line regeneration: {detailed_error}")
            self.ui.update_queue.put({'error': f"Error regenerating line:\n\n{detailed_error}"})

    # ... The rest of the AppLogic class is unchanged ...
    def initialize_tts(self):
        self.ui.last_operation = 'tts_init'
        self.ui.active_thread = threading.Thread(target=self.run_tts_initialization)
        self.ui.active_thread.daemon = True
        self.ui.active_thread.start()
        self.ui.root.after(100, self.ui.check_update_queue)

    def find_calibre_executable(self):
        if self.ui.calibre_exec_path and self.ui.calibre_exec_path.exists(): return True
        possible_paths = [Path("C:/Program Files/Calibre2/ebook-convert.exe"), Path("C:/Program Files/Calibre/ebook-convert.exe")]
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
            speaker_tag_pattern = r"""\s*(?:,?\s*(\w[\w\s\.]*)?\s*(said|replied|shouted|whispered|muttered|asked|protested|exclaimed|gasped|continued|began|explained|answered))?"""
            patterns = {'"': re.compile(r'"([^"]*)"' + speaker_tag_pattern, re.VERBOSE | re.IGNORECASE), "'": re.compile(r"'([^']*)'" + speaker_tag_pattern, re.VERBOSE | re.IGNORECASE), '‘': re.compile(r'‘([^’]*)’' + speaker_tag_pattern, re.VERBOSE | re.IGNORECASE), '“': re.compile(r'“([^”]*)”' + speaker_tag_pattern, re.VERBOSE | re.IGNORECASE)}
            all_matches = [];
            for quote_char, pattern in patterns.items():
                for match in pattern.finditer(text): all_matches.append({'match': match, 'quote_char': quote_char})
            all_matches.sort(key=lambda x: x['match'].start())
            
            # Simple sentence splitter for narrator lines
            sentence_end_pattern = re.compile(r'(?<=[.!?])\s+(?=[A-Z"\'‘“])|(?<=[.!?])$')

            for item in all_matches:
                match = item['match']; quote_char = item['quote_char']; start, end = match.span()
                narration_text = text[last_index:start].strip()
                if narration_text:
                    sentences = sentence_end_pattern.split(narration_text)
                    for sentence in sentences:
                        if sentence and sentence.strip():
                            results.append({'speaker': 'Narrator', 'line': sentence.strip()})
                dialogue_text = match.group(1).strip(); speaker = match.group(2); full_dialogue = f"{quote_char}{dialogue_text}{quote_char}"
                if speaker: results.append({'speaker': speaker.strip().title(), 'line': full_dialogue})
                else: results.append({'speaker': 'AMBIGUOUS', 'line': full_dialogue})
                last_index = end
            remaining_text = text[last_index:].strip()
            if remaining_text:
                sentences = sentence_end_pattern.split(remaining_text)
                for sentence in sentences:
                    if sentence and sentence.strip():
                        results.append({'speaker': 'Narrator', 'line': sentence.strip()})
            self.logger.info("Pass 1 (rules-based analysis) complete.")
            self.ui.update_queue.put({'rules_pass_complete': True, 'results': results})
        except Exception as e:
            detailed_error = traceback.format_exc()
            self.logger.error(f"Error during Pass 1 (rules-based analysis): {detailed_error}")
            self.ui.update_queue.put({'error': f"Error during Pass 1 (rules-based analysis):\n\n{detailed_error}"})

    def start_rules_pass_thread(self, text):
        self.ui.last_operation = 'rules_pass_analysis' 
        self.ui.active_thread = threading.Thread(target=self.run_rules_pass, args=(text,))
        self.ui.active_thread.daemon = True
        self.ui.active_thread.start()
        self.ui.root.after(100, self.ui.check_update_queue)

    def start_pass_2_resolution(self):
        ambiguous_items = [(i, item) for i, item in enumerate(self.ui.analysis_result) if item['speaker'] == 'AMBIGUOUS']
        if not ambiguous_items:
            messagebox.showinfo("All Clear", "No ambiguous speakers found to resolve.")
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
            
            system_prompt = "You are a literary analyst. Your task is to identify the speaker of a specific line of dialogue given its surrounding context. You must follow all instructions precisely."
            
            for i, (original_index, item) in enumerate(ambiguous_items):
                try:
                    before_text = self.ui.analysis_result[original_index - 1]['line'] if original_index > 0 else "[Start of Text]"
                    dialogue_text = item['line']
                    after_text = self.ui.analysis_result[original_index + 1]['line'] if original_index < len(self.ui.analysis_result) - 1 else "[End of Text]"
                    
                    # user_prompt = (
                    #     f"CONTEXT BEFORE: \"{context_before}\"\n\n"
                    #     f"DIALOGUE: \"{dialogue}\"\n\n"
                    #     f"CONTEXT AFTER: \"{context_after}\"\n\n"
                    #     "Who is the speaker of the dialogue?"
                    # )
                    user_prompt = (
                        "Based on the context below, who is the speaker of the DIALOGUE line?\n\n"
                        f"CONTEXT BEFORE: {before_text}\n"
                        f"DIALOGUE: {dialogue_text}\n"
                        f"CONTEXT AFTER: {after_text}\n\n"
                        "CRITICAL INSTRUCTIONS:\n"
                        "1. Respond with ONLY the speaker's name (e.g., 'Hunter', 'Narrator', 'Jimmy').\n"
                        "2. If the speaker's name cannot be determined from the context, you MUST respond with the single word 'Unknown'.\n"
                        "3. Do not add any explanation, punctuation, or other words to your response."
                    )

                    completion = client.chat.completions.create(
                        model="local-model", # Model configured in your local server
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        temperature=0.0
                    )
                    raw_response = completion.choices[0].message.content.strip()
                    
                    # Attempt to extract just the speaker name if the model is verbose
                    # Common patterns: "The speaker is X.", "Speaker: X", "X"
                    # This is a simple heuristic; more complex parsing might be needed for other models.
                    processed_name = raw_response
                    phrases_to_remove = [
                        "the speaker of the dialogue is ", "the speaker is ", "speaker: ",
                        "it is likely that the speaker is ", "the speaker could be "
                    ]
                    for phrase in phrases_to_remove:
                        if processed_name.lower().startswith(phrase):
                            processed_name = processed_name[len(phrase):].strip()
                    speaker_name = processed_name.split('.')[0].split(',')[0].strip().title() # Take first part before punctuation

                    if not speaker_name: speaker_name = "UNKNOWN"

                    self.ui.update_queue.put({'progress': i, 'original_index': original_index, 'new_speaker': speaker_name})
                    self.logger.debug(f"LLM resolved item {original_index} to speaker: {speaker_name}")
                except openai.APITimeoutError:
                    self.logger.warning(f"Timeout processing item {original_index} with LLM."); 
                    self.ui.update_queue.put({'progress': i, 'original_index': original_index, 'new_speaker': 'TIMED_OUT'})
                except Exception as e:
                     self.logger.error(f"Error processing item {original_index} with LLM: {e}"); 
                     self.ui.update_queue.put({'progress': i, 'original_index': original_index, 'new_speaker': 'UNKNOWN'})
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
            return messagebox.showerror("Invalid File Type", f"Supported formats are: {', '.join(self.ui.allowed_extensions)}")
        self.ui.ebook_path = ebook_candidate_path
        # Remove explicit fg="black" to allow theme to control color
        self.ui.file_status_label.config(text=f"Selected: {self.ui.ebook_path.name}")
        self.ui.next_step_button.config(state=tk.NORMAL, text="Convert to Text")
        self.ui.edit_text_button.config(state=tk.DISABLED)
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

