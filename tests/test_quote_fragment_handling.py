# tests/test_quote_fragment_handling.py
import sys
import types
import json
import queue
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Minimal transformer stub
if 'transformers' not in sys.modules:
    sys.modules['transformers'] = types.SimpleNamespace(AutoTokenizer=type('AT', (), {'from_pretrained': staticmethod(lambda name: None)}))

import text_processing
from text_processing import TextProcessor

class FakeResponse:
    def __init__(self, status_code=200):
        self.status_code = status_code

class FakeCompletionChoice:
    def __init__(self, content):
        self.message = types.SimpleNamespace(content=content)

class FakeCompletions:
    def __init__(self, responses_map):
        self.responses_map = responses_map
    def create(self, **kwargs):
        msgs = kwargs.get('messages') or []
        joined = '\n'.join(m.get('content','') for m in msgs)
        # detect quote-check prompt by presence of 'CAND:' lines
        if 'CAND:' in joined:
            return types.SimpleNamespace(choices=[FakeCompletionChoice(self.responses_map.get('quote_check','[]'))])
        # otherwise grouping
        return types.SimpleNamespace(choices=[FakeCompletionChoice(self.responses_map.get('grouping','{}'))])

class FakeOpenAI:
    def __init__(self, responses_map):
        self.chat = types.SimpleNamespace(completions=FakeCompletions(responses_map))


def test_apostrophe_fragment_appended(monkeypatch):
    class State: pass
    state = State()
    state.analysis_result = [
        {'speaker': 'Bob', 'line': 'The cat'},
        {'speaker': 'Bob', 'line': "'s"},
        {'speaker': 'Carol', 'line': 'Hi.'}
    ]
    update_q = queue.Queue()
    logger = logging.getLogger('test')

    tp = TextProcessor(state, update_q, logger, 'Coqui XTTS')

    monkeypatch.setattr('requests.get', lambda url, timeout: FakeResponse(200))

    quote_resp = json.dumps([{'index': 1, 'is_dialogue': False, 'suggested_action': 'append_prev'}])
    grouping_json = json.dumps({'character_groups': [{'primary_name': 'Bob', 'aliases': []}, {'primary_name': 'Carol', 'aliases': []}]})
    fake_client = FakeOpenAI({'quote_check': quote_resp, 'grouping': grouping_json})
    import text_processing as _tp_mod
    monkeypatch.setattr(_tp_mod.openai, 'OpenAI', lambda base_url, api_key, timeout: fake_client)

    tp.run_speaker_refinement_pass()

    # After run, the fragment should have been appended to previous line
    lines = [i['line'] for i in state.analysis_result]
    assert "The cat's" in lines[0]


def test_double_quote_short_fragment_appended(monkeypatch):
    class State: pass
    state = State()
    state.analysis_result = [
        {'speaker': 'Alice', 'line': 'He called him'},
        {'speaker': 'Alice', 'line': '"The Doc"'},
        {'speaker': 'Alice', 'line': 'and left.'}
    ]
    update_q = queue.Queue()
    logger = logging.getLogger('test')
    tp = TextProcessor(state, update_q, logger, 'Coqui XTTS')
    monkeypatch.setattr('requests.get', lambda url, timeout: FakeResponse(200))

    quote_resp = json.dumps([{'index': 1, 'is_dialogue': False, 'suggested_action': 'append_prev'}])
    grouping_json = json.dumps({'character_groups': [{'primary_name': 'Alice', 'aliases': []}]})
    fake_client = FakeOpenAI({'quote_check': quote_resp, 'grouping': grouping_json})
    import text_processing as _tp_mod
    monkeypatch.setattr(_tp_mod.openai, 'OpenAI', lambda base_url, api_key, timeout: fake_client)

    tp.run_speaker_refinement_pass()
    lines = [i['line'] for i in state.analysis_result]
    assert 'He called him "The Doc"' in lines[0]


def test_llm_malformed_response_fallback(monkeypatch):
    class State: pass
    state = State()
    state.analysis_result = [
        {'speaker': 'Sam', 'line': 'I said hello'},
        {'speaker': 'Sam', 'line': "\"wow\""}
    ]
    update_q = queue.Queue()
    logger = logging.getLogger('test')
    tp = TextProcessor(state, update_q, logger, 'Coqui XTTS')
    monkeypatch.setattr('requests.get', lambda url, timeout: FakeResponse(200))

    # Simulate malformed LLM response (non-JSON), so the fallback heuristic should append to previous
    fake_client = FakeOpenAI({'quote_check': 'not json', 'grouping': json.dumps({'character_groups': [{'primary_name': 'Sam', 'aliases': []}]})})
    import text_processing as _tp_mod
    monkeypatch.setattr(_tp_mod.openai, 'OpenAI', lambda base_url, api_key, timeout: fake_client)

    tp.run_speaker_refinement_pass()
    lines = [i['line'] for i in state.analysis_result]
    assert 'I said hello "wow"' in lines[0]

if __name__ == '__main__':
    test_apostrophe_fragment_appended(None)
    test_double_quote_short_fragment_appended(None)
    test_llm_malformed_response_fallback(None)
    print('quote fragment tests passed')
