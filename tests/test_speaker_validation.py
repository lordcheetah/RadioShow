# tests/test_speaker_validation.py
import sys
import types
import json
import queue
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Provide a stub for transformers.AutoTokenizer so imports succeed in test env
import types
if 'transformers' not in sys.modules:
    sys.modules['transformers'] = types.SimpleNamespace(AutoTokenizer=type('AT', (), {'from_pretrained': staticmethod(lambda name: None)}))
import text_processing
from text_processing import TextProcessor

# Stubs for network and openai
class FakeResponse:
    def __init__(self, status_code=200):
        self.status_code = status_code

class FakeCompletionChoice:
    def __init__(self, content):
        self.message = types.SimpleNamespace(content=content)

class FakeCompletions:
    def __init__(self, responses_map):
        # responses_map: dict with keys like 'validation' and 'grouping'
        self.responses_map = responses_map
    def create(self, **kwargs):
        msgs = kwargs.get('messages') or []
        content = ''
        if msgs:
            joined = '\n'.join(m.get('content','') for m in msgs)
            if 'Return JSON array of objects' in joined or 'Return JSON array' in joined:
                content = self.responses_map.get('validation', '[]')
            elif 'character_groups' in joined or 'Return a JSON object with key "character_groups"' in joined:
                content = self.responses_map.get('grouping', '{}')
            else:
                # fallback: pick grouping if available else validation
                content = self.responses_map.get('grouping') or self.responses_map.get('validation') or '[]'
        else:
            content = self.responses_map.get('grouping') or self.responses_map.get('validation') or '[]'
        return types.SimpleNamespace(choices=[FakeCompletionChoice(content)])

class FakeOpenAI:
    def __init__(self, responses_map):
        self.chat = types.SimpleNamespace(completions=FakeCompletions(responses_map))

def test_validation_and_grouping(monkeypatch=None):
    if monkeypatch is None:
        import importlib
        class SimpleMP:
            def setattr(self, *args):
                if len(args) == 2:
                    target, value = args
                    if isinstance(target, str):
                        mod_name, attr = target.rsplit('.', 1)
                        mod = importlib.import_module(mod_name)
                        setattr(mod, attr, value)
                    else:
                        raise TypeError('SimpleMP setattr expects (str, value) or (obj, name, value)')
                elif len(args) == 3:
                    obj, name, value = args
                    setattr(obj, name, value)
                else:
                    raise TypeError('SimpleMP setattr requires 2 or 3 args')
        monkeypatch = SimpleMP()
    # Prepare a minimal state with analysis_result
    class State:
        pass
    state = State()
    # Two speakers found by Pass1: one is a 'said' artifact, one is a real name
    state.analysis_result = [
        {'speaker': 'said', 'line': '"Hello there," John Doe said.'},
        {'speaker': 'Alice', 'line': '"I agree," Alice replied.'}
    ]

    update_q = queue.Queue()
    logger = logging.getLogger('test')

    tp = TextProcessor(state, update_q, logger, 'Coqui XTTS')

    # Patch requests.get to simulate LM Studio available
    import requests as _req
    monkeypatch.setattr(_req, 'get', lambda url, timeout: FakeResponse(200))

    # Prepare responses: first for validation (JSON array), then for grouping (character_groups JSON)
    validation_json = json.dumps([
        {"original_name": "said", "is_name": False, "suggested_name": "John Doe", "reason": "Dialogue references John Doe as speaker."},
        {"original_name": "Alice", "is_name": True, "suggested_name": None, "reason": "Proper name used as speaker tag."}
    ])
    grouping_json = json.dumps({
        "character_groups": [
            {"primary_name": "John Doe", "aliases": ["said"]},
            {"primary_name": "Alice", "aliases": []}
        ]
    })

    fake_client = FakeOpenAI({'validation': validation_json, 'grouping': grouping_json})
    import text_processing as _tp_mod
    monkeypatch.setattr(_tp_mod.openai, 'OpenAI', lambda base_url, api_key, timeout: fake_client)

    # Run refinement (this should use our fake client and produce a speaker_refinement_complete update)
    tp.run_speaker_refinement_pass()

    # Check the queue for completion update
    found = False
    while not update_q.empty():
        u = update_q.get()
        if u.get('speaker_refinement_complete'):
            found = True
            groups = u.get('groups')
            assert any(g['primary_name'] == 'John Doe' for g in groups)
            assert any(g['primary_name'] == 'Alice' for g in groups)
    assert found


def test_validation_malformed_response(monkeypatch):
    # Similar setup but the validation response is malformed text with heuristics
    class State:
        pass
    state = State()
    state.analysis_result = [
        {'speaker': 'said', 'line': '"Hello there," John Doe said.'},
    ]
    update_q = queue.Queue()
    logger = logging.getLogger('test')
    tp = TextProcessor(state, update_q, logger, 'Coqui XTTS')
    import requests as _req
    monkeypatch.setattr(_req, 'get', lambda url, timeout: FakeResponse(200))

    # Validation returns an unstructured note suggesting John Doe
    val_raw = 'original_name: said, is_name: false, suggested_name: John Doe'
    grouping_json = json.dumps({"character_groups": [{"primary_name": "John Doe", "aliases": ["said"]}]})
    fake_client = FakeOpenAI({'validation': val_raw, 'grouping': grouping_json})
    import text_processing as _tp_mod
    monkeypatch.setattr(_tp_mod.openai, 'OpenAI', lambda base_url, api_key, timeout: fake_client)

    tp.run_speaker_refinement_pass()

    found = False
    while not update_q.empty():
        u = update_q.get()
        if u.get('speaker_refinement_complete'):
            found = True
            groups = u.get('groups')
            assert any(g['primary_name'] == 'John Doe' for g in groups)
    assert found


def test_retry_on_timeout(monkeypatch):
    class State:
        pass
    state = State()
    state.analysis_result = [
        {'speaker': 'Alice', 'line': '"I agree," Alice replied.'}
    ]
    update_q = queue.Queue()
    logger = logging.getLogger('test')
    tp = TextProcessor(state, update_q, logger, 'Coqui XTTS')
    import requests as _req
    monkeypatch.setattr(_req, 'get', lambda url, timeout: FakeResponse(200))

    # Grouping JSON expected
    grouping_json = json.dumps({"character_groups": [{"primary_name": "Alice", "aliases": []}]})

    # Create a client where the first call raises an exception (timeout), then returns valid JSON
    class FlakyCompletions:
        def __init__(self):
            self._called = False
        def create(self, **kwargs):
            if not self._called:
                self._called = True
                raise Exception('Simulated timeout')
            return types.SimpleNamespace(choices=[FakeCompletionChoice(grouping_json)])
    class FlakyOpenAI:
        def __init__(self):
            self.chat = types.SimpleNamespace(completions=FlakyCompletions())
    import text_processing as _tp_mod
    monkeypatch.setattr(_tp_mod.openai, 'OpenAI', lambda base_url, api_key, timeout: FlakyOpenAI())

    tp.run_speaker_refinement_pass()
    found = False
    while not update_q.empty():
        u = update_q.get()
        if u.get('speaker_refinement_complete'):
            found = True
            groups = u.get('groups')
            assert any(g['primary_name'] == 'Alice' for g in groups)
    assert found

if __name__ == '__main__':
    test_validation_and_grouping()
    print('speaker validation tests passed')
