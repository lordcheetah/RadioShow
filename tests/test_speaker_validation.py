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
from app_state import VoicingMode

# Stubs for network and openai
class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {'data': [{'id': 'test-model'}]}

    def json(self):
        return self._payload

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


def test_refinement_canonicalizes_reciprocal_groups(monkeypatch):
    class State:
        pass
    state = State()
    state.analysis_result = [
        {'speaker': 'Blair', 'line': '"Hobbes!"'},
        {'speaker': 'Blair', 'line': '"Move out."'},
        {'speaker': 'Blair', 'line': '"Now."'},
        {'speaker': 'Hobbes', 'line': '"Colonel."'},
        {'speaker': 'Hobbes', 'line': '"I agree."'},
    ]
    state.character_profiles = {}

    update_q = queue.Queue()
    logger = logging.getLogger('test')
    tp = TextProcessor(state, update_q, logger, 'Coqui XTTS')

    import requests as _req
    monkeypatch.setattr(_req, 'get', lambda url, timeout: FakeResponse(200))

    validation_json = json.dumps([
        {"original_name": "Blair", "is_name": True, "suggested_name": None, "reason": "valid"},
        {"original_name": "Hobbes", "is_name": True, "suggested_name": None, "reason": "valid"}
    ])
    grouping_json = json.dumps({
        "character_groups": [
            {"primary_name": "Blair", "aliases": ["Hobbes"]},
            {"primary_name": "Hobbes", "aliases": ["Blair"]}
        ]
    })

    fake_client = FakeOpenAI({'validation': validation_json, 'grouping': grouping_json})
    import text_processing as _tp_mod
    monkeypatch.setattr(_tp_mod.openai, 'OpenAI', lambda base_url, api_key, timeout: fake_client)

    tp.run_speaker_refinement_pass()

    found = False
    while not update_q.empty():
        u = update_q.get()
        if u.get('speaker_refinement_complete'):
            found = True
            groups = u.get('groups')
            # Reciprocal groups should collapse into one canonical group.
            assert len(groups) == 1
            aliases = groups[0].get('aliases', [])
            assert any(a in {'Blair', 'Hobbes'} for a in aliases)
    assert found


def test_canonical_primary_prefers_informative_name():
    class State:
        pass
    state = State()
    state.analysis_result = []

    update_q = queue.Queue()
    logger = logging.getLogger('test')
    tp = TextProcessor(state, update_q, logger, 'Coqui XTTS')

    groups = tp._canonicalize_character_groups(
        [
            {'primary_name': 'Captain Kirk', 'aliases': ['Captain James T. Kirk', 'Jim']}
        ],
        {'Captain Kirk': 12, 'Captain James T. Kirk': 5, 'Jim': 3}
    )

    assert groups
    assert groups[0]['primary_name'] == 'Captain James T. Kirk'


def test_late_backfill_merges_unique_navigator_alias():
    class State:
        pass
    state = State()
    state.analysis_result = []

    update_q = queue.Queue()
    logger = logging.getLogger('test')
    tp = TextProcessor(state, update_q, logger, 'Coqui XTTS')

    speaker_counts = {
        'Navigator': 5,
        'Navigator Chekov': 12,
        'Captain James T. Kirk': 30,
    }
    all_speakers = list(speaker_counts.keys())

    groups = tp._build_late_backfill_groups(all_speakers, speaker_counts)
    assert any(g.get('primary_name') == 'Navigator Chekov' and 'Navigator' in g.get('aliases', []) for g in groups)


def test_late_backfill_keeps_ambiguous_lieutenant_unmerged():
    class State:
        pass
    state = State()
    state.analysis_result = []

    update_q = queue.Queue()
    logger = logging.getLogger('test')
    tp = TextProcessor(state, update_q, logger, 'Coqui XTTS')

    speaker_counts = {
        'Lieutenant': 9,
        'Lieutenant Uhura': 8,
        'Lieutenant Sulu': 7,
    }
    all_speakers = list(speaker_counts.keys())

    groups = tp._build_late_backfill_groups(all_speakers, speaker_counts)
    assert not any('Lieutenant' in g.get('aliases', []) for g in groups)


def test_pass1_title_only_tag_is_low_confidence():
    class State:
        pass
    state = State()
    state.analysis_result = []

    update_q = queue.Queue()
    logger = logging.getLogger('test')
    tp = TextProcessor(state, update_q, logger, 'Coqui XTTS')

    text = '"Move out," Colonel said.'
    results = tp.run_rules_pass(text, VoicingMode.CAST, use_single_quotes=False)

    dialogue_rows = [r for r in (results or []) if r.get('line', '').startswith('"')]
    assert dialogue_rows
    assert dialogue_rows[0].get('speaker') == 'Colonel'
    assert dialogue_rows[0].get('speaker_confidence') == 'low'

def test_refinement_handles_no_model_loaded_gracefully(monkeypatch):
    class State:
        pass
    state = State()
    state.analysis_result = [
        {'speaker': 'Alice', 'line': '"I agree," Alice replied.'},
        {'speaker': 'Bob', 'line': '"Proceed," Bob said.'},
    ]

    update_q = queue.Queue()
    logger = logging.getLogger('test')
    tp = TextProcessor(state, update_q, logger, 'Coqui XTTS')

    import requests as _req
    monkeypatch.setattr(_req, 'get', lambda url, timeout: FakeResponse(200, {'data': []}))

    tp.run_speaker_refinement_pass()

    found = False
    while not update_q.empty():
        u = update_q.get()
        if u.get('speaker_refinement_complete'):
            found = True
            assert u.get('groups') == []
            assert 'no model is loaded' in str(u.get('reason', '')).lower()
    assert found


def test_refinement_adds_kirk_variant_group_when_llm_misses_it(monkeypatch):
    class State:
        pass
    state = State()
    state.analysis_result = [
        {'speaker': 'Captain James T. Kirk', 'line': '"Set course," Captain James T. Kirk said.'},
        {'speaker': 'Captain Kirk', 'line': '"Shields up," Captain Kirk ordered.'},
        {'speaker': 'Jim', 'line': '"Bones, status?" Jim asked.'},
        {'speaker': 'Spock', 'line': '"Fascinating," Spock replied.'},
    ]
    state.character_profiles = {}

    update_q = queue.Queue()
    logger = logging.getLogger('test')
    tp = TextProcessor(state, update_q, logger, 'Coqui XTTS')

    import requests as _req
    monkeypatch.setattr(_req, 'get', lambda url, timeout: FakeResponse(200))

    validation_json = json.dumps([
        {"original_name": "Captain James T. Kirk", "is_name": True, "suggested_name": None, "reason": "valid"},
        {"original_name": "Captain Kirk", "is_name": True, "suggested_name": None, "reason": "valid"},
        {"original_name": "Jim", "is_name": True, "suggested_name": None, "reason": "valid"},
        {"original_name": "Spock", "is_name": True, "suggested_name": None, "reason": "valid"}
    ])
    # Simulate LLM missing the obvious group entirely.
    grouping_json = json.dumps({"character_groups": []})

    fake_client = FakeOpenAI({'validation': validation_json, 'grouping': grouping_json})
    import text_processing as _tp_mod
    monkeypatch.setattr(_tp_mod.openai, 'OpenAI', lambda base_url, api_key, timeout: fake_client)

    tp.run_speaker_refinement_pass()

    found = False
    while not update_q.empty():
        u = update_q.get()
        if u.get('speaker_refinement_complete'):
            found = True
            groups = u.get('groups') or []
            target = next((g for g in groups if g.get('primary_name') == 'Captain James T. Kirk'), None)
            assert target is not None
            aliases = set(target.get('aliases', []))
            assert 'Captain Kirk' in aliases
            assert 'Jim' in aliases
    assert found


def test_refinement_merges_surname_and_nickname_into_full_name(monkeypatch):
    class State:
        pass
    state = State()
    state.analysis_result = [
        {'speaker': 'Captain James T. Kirk', 'line': '"Set course," Captain James T. Kirk said.'},
        {'speaker': 'Kirk', 'line': '"Red alert," Kirk ordered.'},
        {'speaker': 'Jim', 'line': '"Bones, report," Jim said.'},
        {'speaker': 'Spock', 'line': '"Affirmative," Spock replied.'},
    ]
    state.character_profiles = {}

    update_q = queue.Queue()
    logger = logging.getLogger('test')
    tp = TextProcessor(state, update_q, logger, 'Coqui XTTS')

    import requests as _req
    monkeypatch.setattr(_req, 'get', lambda url, timeout: FakeResponse(200))

    validation_json = json.dumps([
        {"original_name": "Captain James T. Kirk", "is_name": True, "suggested_name": None, "reason": "valid"},
        {"original_name": "Kirk", "is_name": True, "suggested_name": None, "reason": "valid"},
        {"original_name": "Jim", "is_name": True, "suggested_name": None, "reason": "valid"},
        {"original_name": "Spock", "is_name": True, "suggested_name": None, "reason": "valid"}
    ])
    grouping_json = json.dumps({"character_groups": []})

    fake_client = FakeOpenAI({'validation': validation_json, 'grouping': grouping_json})
    import text_processing as _tp_mod
    monkeypatch.setattr(_tp_mod.openai, 'OpenAI', lambda base_url, api_key, timeout: fake_client)

    tp.run_speaker_refinement_pass()

    found = False
    while not update_q.empty():
        u = update_q.get()
        if u.get('speaker_refinement_complete'):
            found = True
            groups = u.get('groups') or []
            target = next((g for g in groups if g.get('primary_name') == 'Captain James T. Kirk'), None)
            assert target is not None
            aliases = set(target.get('aliases', []))
            assert 'Kirk' in aliases
            assert 'Jim' in aliases
    assert found

if __name__ == '__main__':
    test_validation_and_grouping()
    print('speaker validation tests passed')
