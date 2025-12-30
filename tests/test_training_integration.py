import os
import sys
import time
import tempfile
import threading
from pathlib import Path
import queue
import logging

from tts_engines import CoquiXTTS


class DummyUI:
    def __init__(self, work_dir: Path):
        self.update_queue = queue.Queue()
        class S: pass
        self.state = S()
        self.state.output_dir = work_dir
        # Ensure the output/voices directory exists if other code expects it
        (Path(self.state.output_dir) / 'voices').mkdir(parents=True, exist_ok=True)


class DummyLogWindow:
    def __init__(self):
        self.lines = []
        self.progress_updates = []

    def append_line(self, line: str):
        self.lines.append(line)

    def update_progress(self, info: dict):
        self.progress_updates.append(info)


def test_training_integration_simulated_trainer(tmp_path):
    ui = DummyUI(tmp_path)
    logger = logging.getLogger('test_training')
    engine = CoquiXTTS(ui, logger)

    # Create small dummy wav files and metadata
    wav1 = tmp_path / 'sample1.wav'
    wav2 = tmp_path / 'sample2.wav'
    wav1.write_bytes(b"RIFF....")
    wav2.write_bytes(b"RIFF....")

    metadata = tmp_path / 'metadata.csv'
    metadata.write_text('sample1.wav|hello\nsample2.wav|world\n')

    # Point trainer to our dummy trainer module installed under tests
    engine._trainer_module = 'tests.dummy_trainer'
    # Prevent the engine from trying to autodetect the system's TTS trainer during this test
    engine.is_trainer_available = lambda: True

    # Prepare training params with current python executable
    training_params = {'python_executable': sys.executable, 'epochs': 1}

    log = DummyLogWindow()

    started = engine.create_refined_model([str(wav1), str(wav2)], 'integration_dummy_model', metadata_csv_path=str(metadata), training_params=training_params, log_window=log)
    assert started is True

    # Wait for background process to run and to collect progress (timeout after 10s)
    start = time.time()
    got_progress = False
    while time.time() - start < 10:
        if log.progress_updates:
            got_progress = True
            break
        time.sleep(0.1)

    assert got_progress, "No progress updates were recorded by the dummy log window"
    # Check that at least one parsed update contains percent
    assert any('percent' in p for p in log.progress_updates), f"Progress updates didn't include percent: {log.progress_updates}"


if __name__ == '__main__':
    import runpy
    test_training_integration_simulated_trainer(Path(tempfile.mkdtemp()))
    print('Integration test run finished')
