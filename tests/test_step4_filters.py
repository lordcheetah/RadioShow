import sys
import tkinter as tk
from pathlib import Path
import types

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


def test_step4_issue_classification_and_filters():
    root, app = _make_app()
    app.state.analysis_result = [
        {
            'speaker': 'Narrator',
            'line': 'A normal narration line.',
            'pov': '3rd Person',
            'speaker_confidence': 'high',
            'speaker_source': 'narration_text',
        },
        {
            'speaker': 'AMBIGUOUS',
            'line': '"Who goes there?',
            'pov': '1st Person',
            'speaker_confidence': 'low',
            'speaker_source': 'dialogue_unattributed',
        },
        {
            'speaker': 'Narrator',
            'line': 'He waited in the hall for an answer.',
            'pov': 'Unknown',
            'speaker_confidence': 'medium',
            'speaker_source': 'narration_text',
        },
        {
            'speaker': 'Narrator',
            'line': ' '.join(['longline'] * 40),
            'pov': 'Unknown',
            'speaker_confidence': 'medium',
            'speaker_source': 'narration_text',
        },
    ]

    rows = app._build_step4_display_rows()
    assert len(rows) == 4
    assert rows[0]['issue'] == 'OK'
    assert 'Ambiguous speaker' in rows[1]['issues']
    assert 'Quote warning' in rows[1]['issues']
    assert 'Low confidence' in rows[1]['issues']
    assert 'Quote spillover' in rows[2]['issues']
    assert 'Long line' in rows[3]['issues']

    app.step4_filter_var.set('Issues Only')
    issue_rows = app._filter_step4_display_rows(rows)
    assert len(issue_rows) == 3

    app.step4_filter_var.set('Quote Warnings')
    quote_rows = app._filter_step4_display_rows(rows)
    assert len(quote_rows) == 3
    assert quote_rows[0]['speaker'] == 'AMBIGUOUS'

    app.step4_filter_var.set('Long Lines')
    long_rows = app._filter_step4_display_rows(rows)
    assert len(long_rows) == 1
    assert long_rows[0]['speaker'] == 'Narrator'

    app.step4_filter_var.set('Issues Only')
    app._refresh_step4_table()
    assert len(app._step4_flagged_positions) == 3
    assert app.cast_refinement_view.next_flagged_button['state'] == tk.NORMAL

    root.destroy()
