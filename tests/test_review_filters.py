import sys
import tkinter as tk
from pathlib import Path
import types
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pydub_mod = sys.modules.setdefault('pydub', types.SimpleNamespace())
setattr(pydub_mod, 'AudioSegment', type('AudioSegment', (), {}))
sys.modules.setdefault('pydub.playback', types.SimpleNamespace(play=lambda *a, **k: None))
ebooklib_mod = sys.modules.setdefault('ebooklib', types.SimpleNamespace(ITEM_COVER='cover'))
setattr(ebooklib_mod, 'epub', types.SimpleNamespace(read_epub=lambda p: None))
sys.modules.setdefault('ebooklib.epub', types.SimpleNamespace(read_epub=lambda p: None))

class _StubImage:
    @staticmethod
    def new(mode, size, color=None):
        class _I:
            def save(self, path):
                return None
        return _I()

class _StubDraw:
    def __init__(self, img):
        pass
    def text(self, *a, **k):
        return None
    def textbbox(self, *a, **k):
        return (0, 0, 10, 10)

class _StubFont:
    @staticmethod
    def truetype(*a, **k):
        return _StubFont()
    @staticmethod
    def load_default():
        return _StubFont()
    def getlength(self, s):
        return len(s) * 6

sys.modules.setdefault('PIL', types.SimpleNamespace(Image=_StubImage, ImageDraw=_StubDraw, ImageFont=_StubFont))
sys.modules.setdefault('PIL.Image', _StubImage)
sys.modules.setdefault('PIL.ImageDraw', _StubDraw)
sys.modules.setdefault('PIL.ImageFont', _StubFont)

class _StubTTSEngine:
    def __init__(self, *a, **k):
        pass
    def get_engine_name(self):
        return 'stub'
    def is_trainer_available(self):
        return False
    def get_engine_specific_voices(self):
        return []

sys.modules.setdefault('tts_engines', types.SimpleNamespace(TTSEngine=_StubTTSEngine, CoquiXTTS=_StubTTSEngine, ChatterboxTTS=_StubTTSEngine))
sys.modules.setdefault('file_operations', types.SimpleNamespace(FileOperator=type('FileOperator', (), {'__init__': lambda self, state, q, logger: None})))
_added_text_processing_stub = False
if 'text_processing' not in sys.modules:
    sys.modules['text_processing'] = types.SimpleNamespace(TextProcessor=type('TextProcessor', (), {'__init__': lambda self, state, q, logger, sel=None: None}))
    _added_text_processing_stub = True

from ui_setup import RadioShowApp

if _added_text_processing_stub:
    del sys.modules['text_processing']


def _make_app():
    try:
        root = tk.Tk()
        root.withdraw()
    except tk.TclError:
        class _TmpRoot:
            def destroy(self):
                pass
        root = _TmpRoot()
    return root, RadioShowApp(root)


def _make_wav(path: Path, duration_s: float):
    sample_rate = 22050
    total_frames = max(1, int(sample_rate * duration_s))
    with wave.open(str(path), 'wb') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(b'\x00\x00' * total_frames)


def test_review_flagged_filter_detects_duration_anomalies(tmp_path):
    root, app = _make_app()

    short_wav = tmp_path / 'short.wav'
    long_wav = tmp_path / 'long.wav'
    ok_wav = tmp_path / 'ok.wav'
    _make_wav(short_wav, 0.2)
    _make_wav(long_wav, 18.0)
    _make_wav(ok_wav, 2.5)

    app.state.generated_clips_info = [
        {
            'text': 'This is a moderately long line that should not be very short.',
            'speaker': 'Narrator',
            'clip_path': str(short_wav),
            'original_index': 0,
            'chunk_index': 0,
            'voice_used': {'name': 'stub', 'path': 'stub'}
        },
        {
            'text': 'Tiny line.',
            'speaker': 'Narrator',
            'clip_path': str(long_wav),
            'original_index': 1,
            'chunk_index': 0,
            'voice_used': {'name': 'stub', 'path': 'stub'}
        },
        {
            'text': 'This line should be acceptable for its duration.',
            'speaker': 'Narrator',
            'clip_path': str(ok_wav),
            'original_index': 2,
            'chunk_index': 0,
            'voice_used': {'name': 'stub', 'path': 'stub'}
        },
    ]

    all_rows = app._build_review_display_rows()
    assert len(all_rows) == 3
    assert 'Too short' in all_rows[0]['issues']
    assert 'Too long' in all_rows[1]['issues']
    assert all_rows[2]['issue'] == 'OK'

    app.review_filter_var.set('Flagged Only')
    flagged_rows = app._filter_review_display_rows(all_rows)
    assert len(flagged_rows) == 2

    app.review_filter_var.set('Too Short')
    short_rows = app._filter_review_display_rows(all_rows)
    assert len(short_rows) == 1
    assert short_rows[0]['original_index'] == 0

    app.review_filter_var.set('Too Long')
    long_rows = app._filter_review_display_rows(all_rows)
    assert len(long_rows) == 1
    assert long_rows[0]['original_index'] == 1

    root.destroy()


def test_review_asr_mismatch_filter_uses_deterministic_text_scoring(tmp_path):
    root, app = _make_app()

    wav_path = tmp_path / 'clip.wav'
    _make_wav(wav_path, 2.0)

    app.state.generated_clips_info = [
        {
            'text': 'The ship entered orbit around Vulcan.',
            'asr_text': 'The ship entered orbit around Vulcan.',
            'speaker': 'Narrator',
            'clip_path': str(wav_path),
            'original_index': 0,
            'chunk_index': 0,
            'voice_used': {'name': 'stub', 'path': 'stub'}
        },
        {
            'text': 'Captain, raise shields and prepare the phasers.',
            'asr_text': 'The weather is sunny and the market opens at dawn.',
            'speaker': 'Narrator',
            'clip_path': str(wav_path),
            'original_index': 1,
            'chunk_index': 0,
            'voice_used': {'name': 'stub', 'path': 'stub'}
        },
    ]

    all_rows = app._build_review_display_rows()
    assert all_rows[0]['asr_mismatch_score'] is not None
    assert all_rows[0]['asr_mismatch_score'] < 0.1
    assert all_rows[1]['asr_mismatch_score'] is not None
    assert all_rows[1]['asr_mismatch_score'] > 0.35
    assert 'ASR mismatch' in all_rows[1]['issues']

    app.review_filter_var.set('ASR Mismatch')
    mismatch_rows = app._filter_review_display_rows(all_rows)
    assert len(mismatch_rows) == 1
    assert mismatch_rows[0]['original_index'] == 1

    root.destroy()


def test_asr_backend_writes_transcriptions_to_state(tmp_path):
    """run_asr_validation() with a stubbed WhisperModel writes asr_text back to generated_clips_info."""
    import queue as _queue
    import types as _types
    import app_logic as _al

    wav_path = tmp_path / 'clip.wav'
    _make_wav(wav_path, 2.0)

    # Build a minimal state stub
    class _State:
        generated_clips_info = [
            {'text': 'Hello world.', 'clip_path': str(wav_path), 'original_index': 0, 'chunk_index': 0},
            {'text': 'Goodbye world.', 'clip_path': str(wav_path), 'original_index': 1, 'chunk_index': 0},
        ]
        stop_requested = False
        active_thread = None
        last_operation = None
        output_dir = str(tmp_path)
        voices_config_path = str(tmp_path / 'voices.json')

    class _UI:
        update_queue = _queue.Queue()

    # Stub the WhisperModel so transcribe() returns synthetic segments
    class _FakeSegment:
        def __init__(self, text): self.text = text
    class _FakeWhisper:
        def transcribe(self, path, **kwargs):
            return [_FakeSegment('hello world'), _FakeSegment('goodbye earth')], None

    # Patch faster-whisper into app_logic for this test
    original_available = _al.FASTER_WHISPER_AVAILABLE
    original_model_cls = _al._FasterWhisperModel
    _al.FASTER_WHISPER_AVAILABLE = True
    _al._FasterWhisperModel = _FakeWhisper  # type: ignore

    try:
        state = _State()
        ui = _UI()

        logic = _al.AppLogic.__new__(_al.AppLogic)
        logic.ui = ui
        logic.state = state
        logic._asr_model = _FakeWhisper()  # bypass model loading entirely
        import logging
        logic.logger = logging.getLogger('test_asr')

        logic.run_asr_validation()
    finally:
        _al.FASTER_WHISPER_AVAILABLE = original_available
        _al._FasterWhisperModel = original_model_cls

    # Check that asr_text was written back
    assert state.generated_clips_info[0]['asr_text'] == 'hello world goodbye earth'
    assert state.generated_clips_info[1]['asr_text'] == 'hello world goodbye earth'

    # Check queue messages: one asr_validation_total, two progress, one complete
    messages = []
    while not ui.update_queue.empty():
        messages.append(ui.update_queue.get_nowait())

    total_msg = next((m for m in messages if 'asr_validation_total' in m), None)
    assert total_msg is not None
    assert total_msg['asr_validation_total'] == 2

    progress_msgs = [m for m in messages if 'asr_validation_progress' in m]
    assert len(progress_msgs) == 2

    complete_msg = next((m for m in messages if m.get('asr_validation_complete')), None)
    assert complete_msg is not None
    assert complete_msg['total'] == 2
