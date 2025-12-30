# tts_engines.py
import os
import traceback
from abc import ABC, abstractmethod
from pathlib import Path
import shutil
import threading
import time
import re

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
            # Respect an environment override for device selection (RADIOSHOW_TTS_DEVICE)
            device_pref = os.environ.get('RADIOSHOW_TTS_DEVICE', 'auto').lower()
            if device_pref == 'auto':
                gpu_available = torch.cuda.is_available()
            elif device_pref == 'cpu':
                gpu_available = False
            else:
                # Any explicit 'cuda' or 'cuda:X' is treated as GPU requested
                gpu_available = True

            if gpu_available:
                self.logger.info("Attempting to initialize XTTS with GPU support")
            else:
                self.logger.info("Initializing XTTS on CPU")
                if device_pref == 'auto':
                    self.logger.info("No CUDA device detected. To enable GPU, install a CUDA-enabled PyTorch and set RADIOSHOW_TTS_DEVICE=cuda or an explicit cuda device id.")

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

    def _find_trainer_module(self) -> str | None:
        """Return a trainer module to invoke (e.g., 'TTS.bin.train_tts') or None if not found."""
        import importlib, pkgutil
        # Common candidates
        candidates = [
            'TTS.bin.train',
            'TTS.bin.train_tts',
            'TTS.bin.train_encoder',
            'TTS.bin.train_vocoder',
            'TTS.bin.train_tts'
        ]
        for c in candidates:
            try:
                if importlib.util.find_spec(c) is not None:
                    return c
            except Exception:
                continue
        # Fallback: scan installed TTS package for any 'train' submodule
        try:
            import TTS
            for mod in pkgutil.walk_packages(TTS.__path__, prefix='TTS.bin.'):
                if 'train' in mod.name:
                    return mod.name
        except Exception:
            pass
        # Last-resort: try invoking a few likely -m names and see if python accepts them
        import subprocess, sys
        for c in ['TTS.bin.train', 'TTS.bin.train_tts']:
            try:
                proc = subprocess.Popen([sys.executable, '-m', c, '--help'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                proc.wait(timeout=5)
                if proc.returncode in (0, 1):
                    return c
            except Exception:
                continue
        return None

    def is_trainer_available(self) -> bool:
        """Return True if a Coqui TTS trainer module is available to invoke."""
        trainer = self._find_trainer_module()
        if trainer:
            self._trainer_module = trainer
            return True
        return False

    def _parse_trainer_output(self, line: str) -> dict | None:
        """Parse trainer stdout/stderr lines and extract progress info.

        Returns a dict with optional keys: percent (float), epoch (int), epoch_total (int),
        step (int), step_total (int), loss (float), eta (str), raw (str).
        This is best-effort — returns None if no parseable metrics found.
        """
        if not line or not line.strip():
            return None
        parsed: dict = {'raw': line}
        l = line.strip()

        # Common epoch format: "Epoch: 1/100" or "Epoch 1/100"
        m = re.search(r'[Ee]poch[: ]*\s*(\d+)\s*/\s*(\d+)', l)
        if m:
            try:
                parsed['epoch'] = int(m.group(1))
                parsed['epoch_total'] = int(m.group(2))
            except Exception:
                pass

        # Step/iteration progress: 'Step: 10/100' or [10/100]
        m = re.search(r'[Ss]tep[: ]*\s*(\d+)\s*/\s*(\d+)', l)
        if m:
            try:
                parsed['step'] = int(m.group(1))
                parsed['step_total'] = int(m.group(2))
                try:
                    parsed['percent'] = (parsed['step'] / parsed['step_total']) * 100.0
                except Exception:
                    pass
            except Exception:
                pass
        else:
            m = re.search(r'\[(\d+)\s*/\s*(\d+)(?:[^\]]*)\]', l)
            if m:
                try:
                    parsed['step'] = int(m.group(1))
                    parsed['step_total'] = int(m.group(2))
                    try:
                        parsed['percent'] = (parsed['step'] / parsed['step_total']) * 100.0
                    except Exception:
                        pass
                except Exception:
                    pass

        # Percent explicit like '12%'
        m = re.search(r'(\d{1,3})\s*%', l)
        if m:
            try:
                parsed['percent'] = float(m.group(1))
            except Exception:
                pass

        # Loss field like 'loss: 0.1234' or 'Loss=0.1234'
        m = re.search(r'loss[:=]\s*([0-9]*\.?[0-9]+)', l, re.I)
        if m:
            try:
                parsed['loss'] = float(m.group(1))
            except Exception:
                parsed['loss'] = m.group(1)

        # ETA patterns: 'ETA: 00:20' or progressbar-like '<00:20,'
        m = re.search(r'ETA[:=]?\s*([0-9hms:]+)', l, re.I)
        if m:
            parsed['eta'] = m.group(1)
        else:
            m = re.search(r'<\s*([0-9:]+)\s*,', l)
            if m:
                parsed['eta'] = m.group(1)

        # If we only have epoch/epoch_total, compute coarse percent
        if 'percent' not in parsed and 'epoch' in parsed and 'epoch_total' in parsed:
            try:
                parsed['percent'] = (parsed['epoch'] / parsed['epoch_total']) * 100.0
            except Exception:
                pass

        # If no meaningful keys other than raw, return None
        keys = set(parsed.keys()) - {'raw'}
        if not keys:
            return None
        return parsed

    def create_refined_model(self, training_wav_paths: list, model_name: str, metadata_csv_path: str | None = None, training_params: dict | None = None, log_window=None) -> bool:
        """
        Prepares a refined XTTS model workspace using the provided WAV files and metadata CSV
        (format: wav_filename|transcript). Starts a background thread that kicks off actual Coqui
        training via the installed TTS trainer when available. `training_params` is a dict of hyperparameters.
        Optionally accepts a `log_window` (TrainingLogWindow) that will receive appended log lines.
        """
        try:
            wav_paths = [Path(p) for p in training_wav_paths if Path(p).is_file()]
            if not wav_paths:
                self.ui.update_queue.put({'error': "No valid WAV files provided for refined model creation."})
                return False

            if not metadata_csv_path or not Path(metadata_csv_path).is_file():
                self.ui.update_queue.put({'error': "Valid metadata CSV file is required for training (wav_filename|transcript)."})
                return False

            # Check for trainer availability before proceeding
            if not self.is_trainer_available():
                self.ui.update_queue.put({'error': "TTS trainer (TTS.bin.train) not found. Install the Coqui TTS package to enable training (e.g., `pip install TTS`)."})
                return False

            models_dir = self.ui.state.output_dir / "XTTS_Model"
            models_dir.mkdir(exist_ok=True)
            safe_model_name = re.sub(r'[^\w.-]+', '_', model_name).strip() or "refined_model"
            target_dir = models_dir / safe_model_name
            counter = 1
            while target_dir.exists():
                target_dir = models_dir / f"{safe_model_name}_{counter}"
                counter += 1
            target_dir.mkdir(parents=True)

            # Copy wavs into 'wavs' subdir and create metadata.csv compatible with Coqui format (wav_filename|text)
            wavs_dir = target_dir / "wavs"
            wavs_dir.mkdir()
            for wav in wav_paths:
                shutil.copy2(wav, wavs_dir / wav.name)
            self.logger.info(f"Copied {len(wav_paths)} training files to {wavs_dir}")

            # Normalize metadata.csv: ensure file references the copied filenames (basename only)
            metadata_in = Path(metadata_csv_path)
            metadata_out = target_dir / "metadata.csv"
            try:
                with metadata_in.open('r', encoding='utf-8') as fin, metadata_out.open('w', encoding='utf-8') as fout:
                    for line in fin:
                        if not line.strip():
                            continue
                        parts = line.strip().split('|', 1)
                        if not parts:
                            continue
                        fname = Path(parts[0]).name
                        transcript = parts[1].strip() if len(parts) > 1 else ""
                        fout.write(f"{fname}|{transcript}\n")
                self.logger.info(f"Written metadata.csv to {metadata_out}")
            except Exception as e:
                self.logger.error(f"Failed to copy/normalize metadata CSV: {e}")
                self.ui.update_queue.put({'error': f"Failed to handle metadata CSV: {e}"})
                return False

            # Create a minimal config for training. The full config may require tuning; this serves as a base.
            config_path = target_dir / "config.json"
            training_params = training_params or {}
            config = {
                "run_name": safe_model_name,
                "dataset": {
                    "name": "custom",
                    "path": str(wavs_dir.resolve()),
                    "meta_file": str(metadata_out.name)
                },
                "audio": {
                    "sample_rate": 22050
                },
                "model": {
                    "base_model": "tts_models/multilingual/multi-dataset/xtts_v2"
                },
                "training": {
                    "epochs": int(training_params.get('epochs', 30)),
                    "batch_size": int(training_params.get('batch_size', 8)),
                    "learning_rate": float(training_params.get('learning_rate', 0.0005)),
                    "num_workers": int(training_params.get('num_workers', 2)),
                    "device": training_params.get('device', 'auto')
                }
            }
            try:
                import json
                with config_path.open('w', encoding='utf-8') as f:
                    json.dump(config, f, indent=2)
                self.logger.info(f"Wrote training config to {config_path}")
            except Exception as e:
                self.logger.error(f"Failed to write config.json: {e}")

            def _background_train():
                try:
                    self.ui.update_queue.put({'status': f"Starting Coqui XTTS training for: {safe_model_name} (epochs={config['training']['epochs']}, batch_size={config['training']['batch_size']})"})
                    self.logger.info(f"Starting Coqui XTTS training for: {safe_model_name}")

                    # Preferred: try to call the TTS trainer via module
                    import sys
                    import subprocess
                    # Allow caller to specify a Python executable (for running trainer in a different venv)
                    caller_py = None
                    try:
                        caller_py = training_params.get('python_executable') if isinstance(training_params, dict) else None
                    except Exception:
                        caller_py = None
                    python_exe = caller_py or sys.executable

                    # Build the training command using a discovered trainer module
                    trainer_mod = getattr(self, '_trainer_module', None) or self._find_trainer_module()
                    if not trainer_mod:
                        self.ui.update_queue.put({'error': "No TTS trainer module available to start training."})
                        self.logger.error("No trainer module found to invoke training.")
                        return

                    if not Path(python_exe).is_file():
                        self.ui.update_queue.put({'error': f"Specified Python executable not found: {python_exe}"})
                        self.logger.error(f"Specified Python executable not found: {python_exe}")
                        return

                    train_cmd = [python_exe, '-m', trainer_mod, '--config_path', str(config_path)]

                    self.logger.info(f"Running training command: {' '.join(train_cmd)}")
                    proc = subprocess.Popen(train_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

                    # Stream output to logger and UI
                    for line in proc.stdout:
                        line = line.rstrip('\n')
                        self.logger.info(f"[TTS TRAIN] {line}")
                        # Send to UI queue for general status
                        try:
                            self.ui.update_queue.put({'status': line})
                        except Exception:
                            pass

                        # Parse trainer output for progress info and send structured updates
                        try:
                            parsed = self._parse_trainer_output(line)
                            if parsed:
                                try:
                                    self.ui.update_queue.put({'training_progress': parsed})
                                except Exception:
                                    pass
                                if log_window and hasattr(log_window, 'update_progress'):
                                    try:
                                        log_window.update_progress(parsed)
                                    except Exception:
                                        pass
                        except Exception:
                            # Parsing must not interrupt the training loop
                            self.logger.debug("Trainer output parsing failed for line: " + line)

                        # Also append the raw line to the live log window if provided
                        try:
                            if log_window and hasattr(log_window, 'append_line'):
                                log_window.append_line(line)
                        except Exception:
                            pass

                    proc.wait()
                    if proc.returncode == 0:
                        msg = f"Training finished for model: {safe_model_name}. Output at {target_dir}"
                        self.ui.update_queue.put({'status': msg})
                        self.logger.info(msg)
                        if log_window and hasattr(log_window, 'append_line'):
                            log_window.append_line(msg)
                    else:
                        err_msg = f"Training process exited with code {proc.returncode}. Check logs for details."
                        self.ui.update_queue.put({'error': err_msg})
                        self.logger.error(f"Training failed with returncode {proc.returncode}")
                        if log_window and hasattr(log_window, 'append_line'):
                            log_window.append_line(err_msg)
                except Exception as e:
                    self.logger.error(f"Training background task failed: {traceback.format_exc()}")
                    self.ui.update_queue.put({'error': f"Training failed: {e}"})

            threading.Thread(target=_background_train, daemon=True).start()
            return True
        except Exception as e:
            self.logger.error(f"create_refined_model error: {traceback.format_exc()}")
            self.ui.update_queue.put({'error': f"Failed to start refined model creation: {e}"})
            return False

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
            # Determine device preference from environment (RADIOSHOW_TTS_DEVICE: 'auto'|'cpu'|'cuda')
            device_pref = os.environ.get('RADIOSHOW_TTS_DEVICE', 'auto').lower()
            if device_pref == 'auto':
                device = 'cuda' if torch.cuda.is_available() else 'cpu'
                if device == 'cpu':
                    self.logger.info("No CUDA device detected for Chatterbox. To enable GPU, install a CUDA-enabled PyTorch and set RADIOSHOW_TTS_DEVICE=cuda or an explicit cuda device id.")
            elif device_pref == 'cpu':
                device = 'cpu'
            else:
                device = device_pref  # allow explicit 'cuda' or 'cuda:0'

            self.engine = ChatterboxTTSModule.from_pretrained(device=device)
            self.logger.info(f"Chatterbox engine initialized successfully on device: {self.engine.device}.")
            self.ui.update_queue.put({'status': f"Chatterbox engine initialized on device: {self.engine.device}."})
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