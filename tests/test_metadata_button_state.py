# tests/test_metadata_button_state.py
import sys
import tkinter as tk
from pathlib import Path
import types

# Ensure project root on path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Minimal stubs so importing ui_setup/app_logic is safe in isolated test
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
        return (0,0,10,10)
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
sys.modules.setdefault('tts_engines', types.SimpleNamespace(TTSEngine=_StubTTSEngine, CoquiXTTS=_StubTTSEngine, ChatterboxTTS=_StubTTSEngine))
sys.modules.setdefault('file_operations', types.SimpleNamespace(FileOperator=type('FileOperator', (), {'__init__': lambda self, state, q, logger: None})))
_added_text_processing_stub = False
if 'text_processing' not in sys.modules:
    sys.modules['text_processing'] = types.SimpleNamespace(TextProcessor=type('TextProcessor', (), {'__init__': lambda self, state, q, logger, sel=None: None}))
    _added_text_processing_stub = True

from ui_setup import RadioShowApp

# Remove the temporary stub if we injected it so other tests import the real module
if _added_text_processing_stub:
    del sys.modules['text_processing']


def test_buttons_reenabled_after_metadata_extraction(tmp_path):
    try:
        root = tk.Tk()
        root.withdraw()
    except tk.TclError:
        class _TmpRoot:
            def destroy(self):
                pass
        root = _TmpRoot()
    # Create dummy ebook file
    ebook_file = tmp_path / 'book.epub'
    ebook_file.write_text('dummy epub')

    app = RadioShowApp(root)
    # Simulate file accepted update
    app._handle_file_accepted_update({'ebook_path': str(ebook_file)})
    # Buttons should be disabled and show 'Extracting Metadata...'
    assert app.wizard_view.next_step_button['state'] == tk.DISABLED
    assert 'Extract' in app.wizard_view.next_step_button['text']

    # Simulate metadata extracted
    app._handle_metadata_extracted_update({'title': 'T', 'author': 'A', 'cover_path': None})

    # Now the wizard button should be enabled for conversion
    assert app.wizard_view.next_step_button['state'] == tk.NORMAL
    assert 'Convert' in app.wizard_view.next_step_button['text']

    root.destroy()


def test_stale_conversion_update_is_ignored_for_new_book(tmp_path):
    try:
        root = tk.Tk()
        root.withdraw()
    except tk.TclError:
        class _TmpRoot:
            def destroy(self):
                pass
        root = _TmpRoot()

    # Select a new book (the active context we want to preserve)
    star_wars_epub = tmp_path / 'star_wars.epub'
    star_wars_epub.write_text('dummy epub')

    app = RadioShowApp(root)
    app._handle_file_accepted_update({'ebook_path': str(star_wars_epub)})
    current_session_id = app.state.book_session_id

    # Simulate a stale conversion_complete event from a previous book.
    stale_txt = tmp_path / 'star_trek.txt'
    app._handle_conversion_complete_update({
        'txt_path': str(stale_txt),
        'ebook_path': str(tmp_path / 'star_trek.epub'),
        'book_session_id': current_session_id - 1,
    })

    # The stale event must not overwrite current conversion state.
    assert app.state.txt_path is None
    assert app._editor_loaded_txt_path is None

    root.destroy()


def test_conversion_complete_opens_editor_for_current_book(tmp_path):
    try:
        root = tk.Tk()
        root.withdraw()
    except tk.TclError:
        class _TmpRoot:
            def destroy(self):
                pass
        root = _TmpRoot()

    ebook_file = tmp_path / 'book.epub'
    ebook_file.write_text('dummy epub')
    txt_file = tmp_path / 'book.txt'
    txt_file.write_text('fresh text', encoding='utf-8')

    app = RadioShowApp(root)
    app._handle_file_accepted_update({'ebook_path': str(ebook_file)})

    opened = {'called': False}

    def _fake_show_editor_view(resize=True):
        opened['called'] = True

    app.show_editor_view = _fake_show_editor_view
    app._handle_conversion_complete_update({
        'txt_path': str(txt_file),
        'ebook_path': str(ebook_file),
        'book_session_id': app.state.book_session_id,
    })

    assert app.state.txt_path == txt_file
    assert opened['called'] is True

    root.destroy()


if __name__ == '__main__':
    import pytest
    pytest.main([str(Path(__file__).resolve())])
