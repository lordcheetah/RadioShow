import queue, logging, sys
from pathlib import Path
sys.path.append(r'C:\Users\third\Documents\GitHub\RadioShow')
from tts_engines import ChatterboxTTS
from app_state import AppState

ui = type('U', (), {})()
ui.update_queue = queue.Queue()
ui.state = AppState()
ui.state.output_dir = Path.cwd() / 'test_output_cb'
logger = logging.getLogger('cbtest')
logger.setLevel(logging.INFO)
logger.addHandler(logging.StreamHandler())

engine = ChatterboxTTS(ui, logger)
print('CHATTERBOX_AVAILABLE flag: Preliminary check done')
res = engine.initialize()
print('initialize() returned:', res)
# Pull any queued messages
while not ui.update_queue.empty():
    print('MSG:', ui.update_queue.get())
