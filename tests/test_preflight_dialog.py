# tests/test_preflight_dialog.py
import sys
import tkinter as tk
from pathlib import Path

# If Tcl/Tk isn't available (headless CI/containers), provide lightweight Tk stubs so tests can run
if getattr(tk, 'Tk', None) is None:
    class _FakeTk:
        def __init__(self):
            pass
        def withdraw(self):
            pass
        def destroy(self):
            pass
    tk.Tk = _FakeTk
if getattr(tk, 'Toplevel', None) is None:
    class _FakeTop:
        def __init__(self, *a, **k):
            pass
        def destroy(self):
            pass
    tk.Toplevel = _FakeTop
if getattr(tk, 'Frame', None) is None:
    class _FakeFrame:
        def __init__(self, *a, **k):
            pass
        def pack(self):
            pass
    tk.Frame = _FakeFrame
# Ensure project root is on sys.path so imports of application modules work when run from tests/ folder
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# Provide minimal dummy modules for optional heavy deps so importing ui_setup is safe in the test environment
import types
pydub_mod = sys.modules.setdefault('pydub', types.SimpleNamespace())
setattr(pydub_mod, 'AudioSegment', type('AudioSegment', (), {}))
sys.modules.setdefault('pydub.playback', types.SimpleNamespace(play=lambda *a, **k: None))

# Stubs for modules imported by app_logic during import-time
sys.modules.setdefault('ebooklib', types.SimpleNamespace(ITEM_COVER='cover'))
sys.modules.setdefault('ebooklib.epub', types.SimpleNamespace(read_epub=lambda p: None))

# Minimal PIL stub for Image, ImageDraw, ImageFont
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

# Minimal tts_engines stub
class _StubTTSEngine:
    def __init__(self, *a, **k):
        pass
    def get_engine_name(self):
        return 'stub'
    def is_trainer_available(self):
        return False

sys.modules.setdefault('tts_engines', types.SimpleNamespace(TTSEngine=_StubTTSEngine, CoquiXTTS=_StubTTSEngine, ChatterboxTTS=_StubTTSEngine))

# Minimal file_operations stub
sys.modules.setdefault('file_operations', types.SimpleNamespace(FileOperator=type('FileOperator', (), {'__init__': lambda self, state, q, logger: None})))

# Add a temporary text_processing stub only for import time of ui_setup (to avoid pulling heavy deps during import)
_added_text_processing_stub = False
if 'text_processing' not in sys.modules:
    sys.modules['text_processing'] = types.SimpleNamespace(TextProcessor=type('TextProcessor', (), {'__init__': lambda self, state, q, logger, sel=None: None}))
    _added_text_processing_stub = True

from ui_setup import RadioShowApp
from dialogs import DependencyInstallDialog

# Remove the temporary stub if we injected it so other tests import the real module
if _added_text_processing_stub:
    del sys.modules['text_processing']


def test_toggle_and_gather(tmp_path):
    try:
        root = tk.Tk()
        root.withdraw()
    except tk.TclError:
        class _TmpRoot:
            def __init__(self):
                import types as _types
                self.tk = _types.SimpleNamespace()
                self._last_child_ids = {}
                self.children = {}
                self._w = '.'
            def withdraw(self):
                pass
            def destroy(self):
                pass
        root = _TmpRoot()
    theme = {'frame_bg': '#fff', 'fg': '#000', 'button_bg': '#ddd'}
    missing = [('psutil', 'psutil', 'psutil>=5.9.0')]
    all_candidates = missing + [('Coqui TTS', 'TTS.api', 'TTS'), ('Chatterbox TTS', 'chatterbox.tts', 'chatterbox-tts>=0.1.0')]

    dlg = DependencyInstallDialog(root, theme, missing, engine_context='Chatterbox', all_candidates=all_candidates)

    # Render into a temporary frame and confirm initial selection
    popup = tk.Toplevel(root)
    frame = tk.Frame(popup)
    frame.pack()
    dlg._render_candidates(frame, missing)
    sel = dlg._gather_selected_candidates()
    assert len(sel) == 1 and sel[0][0] == 'psutil'

    # Toggle to show all and set only Coqui selected
    dlg._displaying_all = True
    dlg._render_candidates(frame, all_candidates)
    # Uncheck all first
    for k,v in dlg._check_vars.items():
        v.set(False)
    # Find Coqui key and select it
    for k in dlg._check_vars.keys():
        if k.startswith('Coqui TTS'):
            dlg._check_vars[k].set(True)
    sel2 = dlg._gather_selected_candidates()
    assert len(sel2) == 1 and sel2[0][0] == 'Coqui TTS'

    popup.destroy()
    root.destroy()


def test_engine_scoping_returns_relevant_packages():
    try:
        root = tk.Tk()
    except tk.TclError:
        class _TmpRoot:
            def destroy(self):
                pass
        root = _TmpRoot()
    app = RadioShowApp(root)

    miss_cb = app._check_dependencies(engine_context='Chatterbox')
    # When scoped to Chatterbox, nothing should suggest Coqui explicitly
    assert all('coqui' not in disp.lower() for disp,_,_ in miss_cb)

    miss_co = app._check_dependencies(engine_context='Coqui XTTS')
    assert all('chatterbox' not in disp.lower() for disp,_,_ in miss_co)

    root.destroy()


if __name__ == '__main__':
    test_toggle_and_gather(None)
    test_engine_scoping_returns_relevant_packages()
    print('Preflight dialog tests passed')
