import queue, logging, sys
from pathlib import Path
sys.path.append(r'C:\Users\third\Documents\GitHub\RadioShow')
from tts_engines import ChatterboxTTS
from app_state import AppState

# Prepare
out_dir = Path.cwd() / 'test_output_cb'
out_dir.mkdir(exist_ok=True)
ui = type('U', (), {})()
ui.update_queue = queue.Queue()
ui.state = AppState()
ui.state.output_dir = out_dir
logger = logging.getLogger('cbgen')
logger.setLevel(logging.INFO)
logger.addHandler(logging.StreamHandler())

engine = ChatterboxTTS(ui, logger)
if not engine.initialize():
    print('Chatterbox failed to initialize')
    sys.exit(2)

# Try a generation to file
out_path = out_dir / 'chatterbox_test.wav'
try:
    engine.tts_to_file('This is a quick Chatterbox dry-run.', str(out_path))
    print('Generated file exists:', out_path.exists(), 'size:', out_path.stat().st_size if out_path.exists() else 'n/a')
except Exception as e:
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Pull messages
while not ui.update_queue.empty():
    print('MSG:', ui.update_queue.get())
print('Done')
