"""Tests for cast list extraction from book beginnings."""
import pytest
import json
import tempfile
from pathlib import Path
from app_state import AppState
from text_processing import TextProcessor
import logging
from queue import Queue
from unittest.mock import Mock, patch


@pytest.fixture
def text_processor():
    """Create a TextProcessor instance for testing."""
    state = AppState()
    state.output_dir = Path(tempfile.gettempdir())
    queue = Queue()
    logger = logging.getLogger("test")
    processor = TextProcessor(state, queue, logger, "Coqui XTTS")
    return processor


@pytest.fixture
def sample_text_with_cast_list():
    """Sample text with a character list at the beginning."""
    return """CHAPTER CHARACTERS

Wedge Antilles - Leader of the Rogue Squadron, X-Wing pilot with tactical genius
Tycho Celchu - Commander Celchu, veteran pilot and Wedge's right hand
Corran Horn - Undercover agent and pilot, former CorSec officer
General Salm - Squadron commander with strategic oversight
Mirax Terrik - Former smuggler turned informant
Admiral Ackbar - Mon Calamari admiral commanding the fleet

CHAPTER 1: THE BRIEFING

Wedge stood at attention as the holodisplay flickered to life. Around him,
the Rogue Squadron pilots gathered, their faces tight with anticipation.
"""


@pytest.fixture
def sample_text_without_cast_list():
    """Sample text without a character list."""
    return """X-WING ROGUE SQUADRON

By Michael Stackpole

CHAPTER 1: THE BRIEFING

Wedge stood at attention as the holodisplay flickered to life. Around him,
the Rogue Squadron pilots gathered, their faces tight with anticipation.
The General's stern face appeared on the screen before them.
"""


def test_extract_cast_list_detects_valid_list(text_processor, sample_text_with_cast_list):
    """Test that cast list extraction detects a valid character list."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
        f.write(sample_text_with_cast_list)
        txt_path = Path(f.name)

    try:
        # Mock the LLM response
        mock_response = {
            'has_character_list': True,
            'characters': [
                {'name': 'Wedge Antilles', 'role': 'Leader of Rogue Squadron, X-Wing pilot'},
                {'name': 'Tycho Celchu', 'role': 'Commander Celchu, veteran pilot'},
                {'name': 'Corran Horn', 'role': 'Undercover agent and pilot'},
            ],
            'confidence': 0.95,
            'reason': 'Found formatted character list with names and descriptions'
        }

        with patch('text_processing.openai.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_openai.return_value = mock_client
            mock_completion = Mock()
            mock_completion.choices = [Mock(message=Mock(content=json.dumps(mock_response)))]
            mock_client.chat.completions.create.return_value = mock_completion

            result = text_processor.extract_cast_list_from_book_beginning(txt_path)

        assert result is not None
        assert result['has_character_list'] if 'has_character_list' in result else len(result['characters']) > 0
        assert len(result['characters']) == 3
        assert result['characters'][0]['name'] == 'Wedge Antilles'
        assert result['confidence'] == 0.95

    finally:
        txt_path.unlink()


def test_extract_cast_list_returns_none_for_no_list(text_processor, sample_text_without_cast_list):
    """Test that extraction returns None when no character list is found."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
        f.write(sample_text_without_cast_list)
        txt_path = Path(f.name)

    try:
        mock_response = {
            'has_character_list': False,
            'characters': [],
            'confidence': 0.02,
            'reason': 'No formatted character list detected'
        }

        with patch('text_processing.openai.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_openai.return_value = mock_client
            mock_completion = Mock()
            mock_completion.choices = [Mock(message=Mock(content=json.dumps(mock_response)))]
            mock_client.chat.completions.create.return_value = mock_completion

            result = text_processor.extract_cast_list_from_book_beginning(txt_path)

        assert result is None

    finally:
        txt_path.unlink()


def test_extract_cast_list_handles_nonexistent_file(text_processor):
    """Test that extraction handles missing files gracefully."""
    nonexistent_path = Path('/tmp/nonexistent_book_12345.txt')
    result = text_processor.extract_cast_list_from_book_beginning(nonexistent_path)
    assert result is None


def test_extract_cast_list_handles_malformed_json(text_processor, sample_text_with_cast_list):
    """Test that malformed JSON falls back to heuristic extraction when possible."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
        f.write(sample_text_with_cast_list)
        txt_path = Path(f.name)

    try:
        with patch('text_processing.openai.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_openai.return_value = mock_client
            mock_completion = Mock()
            # Return malformed JSON
            mock_completion.choices = [Mock(message=Mock(content="{ invalid json ]"))]
            mock_client.chat.completions.create.return_value = mock_completion

            result = text_processor.extract_cast_list_from_book_beginning(txt_path)

        assert result is not None
        assert result.get('source') == 'heuristic'
        assert len(result.get('characters') or []) >= 4

    finally:
        txt_path.unlink()


def test_extract_cast_list_parses_markdown_json(text_processor, sample_text_with_cast_list):
    """Test that extraction handles JSON wrapped in markdown code blocks."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
        f.write(sample_text_with_cast_list)
        txt_path = Path(f.name)

    try:
        mock_json = {
            'has_character_list': True,
            'characters': [
                {'name': 'Character 1', 'role': 'Role 1'},
            ],
            'confidence': 0.9,
            'reason': 'Found list'
        }
        markdown_response = f"```json\n{json.dumps(mock_json)}\n```"

        with patch('text_processing.openai.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_openai.return_value = mock_client
            mock_completion = Mock()
            mock_completion.choices = [Mock(message=Mock(content=markdown_response))]
            mock_client.chat.completions.create.return_value = mock_completion

            result = text_processor.extract_cast_list_from_book_beginning(txt_path)

        assert result is not None
        assert len(result['characters']) == 1
        assert result['characters'][0]['name'] == 'Character 1'

    finally:
        txt_path.unlink()


def test_extract_cast_list_uses_heuristic_on_llm_timeout(text_processor, sample_text_with_cast_list):
    """If the LLM times out, heuristic parser should still extract obvious cast lists."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
        f.write(sample_text_with_cast_list)
        txt_path = Path(f.name)

    try:
        with patch('text_processing.openai.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_openai.return_value = mock_client
            mock_client.chat.completions.create.side_effect = TimeoutError("timeout")

            result = text_processor.extract_cast_list_from_book_beginning(txt_path)

        assert result is not None
        assert result.get('source') == 'heuristic'
        assert len(result.get('characters') or []) >= 4
        names = {c.get('name') for c in result['characters']}
        assert 'Wedge Antilles' in names
        assert 'Tycho Celchu' in names
    finally:
        txt_path.unlink()


def test_extract_cast_list_uses_heuristic_on_malformed_json(text_processor, sample_text_with_cast_list):
    """If LLM returns malformed JSON, heuristic fallback should still recover cast names."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
        f.write(sample_text_with_cast_list)
        txt_path = Path(f.name)

    try:
        with patch('text_processing.openai.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_openai.return_value = mock_client
            mock_completion = Mock()
            mock_completion.choices = [Mock(message=Mock(content='{"bad_json": '))]
            mock_client.chat.completions.create.return_value = mock_completion

            result = text_processor.extract_cast_list_from_book_beginning(txt_path)

        assert result is not None
        assert result.get('source') == 'heuristic'
        assert len(result.get('characters') or []) >= 4
    finally:
        txt_path.unlink()
