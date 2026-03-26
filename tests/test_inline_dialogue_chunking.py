import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Lightweight stubs so app_logic imports cleanly in test environments.
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

sys.modules.setdefault('PIL', types.SimpleNamespace(Image=_StubImage, ImageDraw=_StubDraw, ImageFont=_StubFont))
sys.modules.setdefault('PIL.Image', _StubImage)
sys.modules.setdefault('PIL.ImageDraw', _StubDraw)
sys.modules.setdefault('PIL.ImageFont', _StubFont)

class _StubTTSEngine:
    def __init__(self, *a, **k):
        pass

sys.modules.setdefault('tts_engines', types.SimpleNamespace(TTSEngine=_StubTTSEngine, CoquiXTTS=_StubTTSEngine, ChatterboxTTS=_StubTTSEngine))
sys.modules.setdefault('file_operations', types.SimpleNamespace(FileOperator=type('FileOperator', (), {'__init__': lambda self, state, q, logger: None})))
sys.modules.setdefault('text_processing', types.SimpleNamespace(TextProcessor=type('TextProcessor', (), {'__init__': lambda self, state, q, logger, sel=None: None})))

from app_logic import AppLogic


def _logic_stub():
    return AppLogic.__new__(AppLogic)


def test_quote_aware_splitter_splits_narration_quote_tag_quote_pattern():
    logic = _logic_stub()
    line = 'He stepped into the room. "Hello there," he said. "Stay calm."'

    segments = logic._split_quote_aware_segments(line, 'Captain Pike')

    assert [s['speaker'] for s in segments] == ['Narrator', 'Captain Pike', 'Narrator', 'Captain Pike']
    assert [s['text'] for s in segments] == [
        'He stepped into the room.',
        'Hello there,',
        'he said.',
        'Stay calm.'
    ]


def test_quote_aware_splitter_keeps_all_segments_narrator_when_resolved_is_narrator():
    logic = _logic_stub()
    line = 'The log read, "Condition green," he wrote. "All systems nominal."'

    segments = logic._split_quote_aware_segments(line, 'Narrator')

    assert [s['speaker'] for s in segments] == ['Narrator', 'Narrator', 'Narrator', 'Narrator']
    assert len(segments) == 4


def test_subline_type_classification_marks_bridge_as_tag():
    logic = _logic_stub()
    segments = logic._split_quote_aware_segments(
        'He stepped in. "Hello," he said. "Stay calm."',
        'Captain Pike'
    )

    types = [logic._classify_subline_type(segments, i) for i in range(len(segments))]
    assert types == ['Narration', 'Dialogue', 'Tag', 'Dialogue']
