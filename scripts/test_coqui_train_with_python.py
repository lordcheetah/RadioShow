import queue, logging, sys
from pathlib import Path
import time
sys.path.append(r'C:\Users\third\Documents\GitHub\RadioShow')
from tts_engines import CoquiXTTS
from app_state import AppState

# Prepare tiny WAVs and metadata (reuse existing test files if present)
root = Path.cwd()
out_dir = root / 'test_output_coqui'
out_dir.mkdir(exist_ok=True)
wav_dir = root / 'test_dryrun_wavs'
wav_dir.mkdir(exist_ok=True)

# Create two tiny WAV files (16000 Hz, 0.1s silence) if missing
import wave
for i in range(2):
    fname = wav_dir / f'sample{i+1}.wav'
    if not fname.exists():
        framerate = 16000
        nframes = int(0.1 * framerate)
        with wave.open(str(fname), 'w') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(framerate)
            wf.writeframes(b'\x00\x00' * nframes)

# Create metadata file
metadata_path = root / 'test_metadata.csv'
with metadata_path.open('w', encoding='utf-8') as f:
    f.write('sample1.wav|hello world\n')
    f.write('sample2.wav|testing training\n')

# Dummy UI and logger
ui = type('U', (), {})()
ui.update_queue = queue.Queue()
ui.state = AppState()
ui.state.output_dir = out_dir
logger = logging.getLogger('coquitest')
logger.setLevel(logging.INFO)
logger.addHandler(logging.StreamHandler())

engine = CoquiXTTS(ui, logger)
print('Coqui TTS available flag (local):', getattr(engine, 'initialize', None) is not None)
# We'll rely on the trainer detection and specify python_executable
venv_python = str((Path.cwd() / '.venv_xtts' / 'Scripts' / 'python.exe').resolve())
print('.venv_xtts python path:', venv_python)

# If trainer is not available locally, we still pass python_executable to subprocess
if not engine.is_trainer_available():
    print('Local trainer not detected; create_refined_model will still stage files and attempt trainer invocation using provided python executable')
else:
    print('Local trainer detected:', getattr(engine, '_trainer_module', None))

training_params = {'epochs':1,'batch_size':1,'learning_rate':0.001,'device':'cpu','num_workers':0, 'python_executable': venv_python}

res = engine.create_refined_model([str(wav_dir / 'sample1.wav'), str(wav_dir / 'sample2.wav')], 'dry_run_model_from_test', metadata_csv_path=str(metadata_path), training_params=training_params)
print('create_refined_model returned', res)

# Poll queue for a short while to capture starting messages
start = time.time()
while time.time() - start < 30:
    try:
        msg = ui.update_queue.get(timeout=2)
    except Exception:
        continue
    print('UI MSG:', msg)
    if 'Training finished' in str(msg) or 'exited with code' in str(msg) or msg.get('error'):
        break

print('Done')
