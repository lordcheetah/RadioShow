# Contributing & Quick Start for Developers

Welcome! This guide helps you set up RadioShow for development and understand the codebase organization.

## First-Time Setup (5 minutes)

### 1. Prerequisites
- Python 3.8+
- Git
- Calibre (for ebook conversion)
- LM Studio with a model loaded on port 4247 (optional but recommended)

### 2. Clone & Setup
```powershell
# Clone repo
git clone <repo-url>
cd RadioShow

# Create virtual environment
python -m venv .venv_chatterbox

# Activate it
.\.venv_chatterbox\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements_chatterbox.txt

# Optional: Install dev tools
pip install pytest pytest-cov black flake8
```

### 3. Run the App
```powershell
python main_app.py
```

### 4. Run Tests
```powershell
python scripts/run_tests.py -q
```

---

## Code Organization for Developers

### Where to Make Changes

| Component | File | Purpose | Typical Changes |
|-----------|------|---------|-----------------|
| **UI Layout** | `views/*.py` | Individual step UIs | Add buttons, change layout, add fields |
| **UI Logic** | `ui_setup.py` | Workflow orchestration, queue handling | Add workflow steps, change state transitions |
| **Core Processing** | `text_processing.py` | Text analysis, LLM orchestration | Tweak prompts, add passes, modify regex |
| **Operations** | `app_logic.py` | Background tasks, threading | Add new operations, coordinate tasks |
| **State** | `app_state.py` | Persistence, data model | Add fields, change serialization |
| **Voice/Audio** | `tts_engines.py`, `audio_effects.py` | TTS integration, effects | Add TTS engines, post-processing |
| **Files/I/O** | `file_operations.py` | Ebook conversion, file handling | Change formats, add preprocessing |
| **Config** | `config_manager.py`, `theming.py` | Settings, themes | Add config options, themes |

---

## Common Development Tasks

### 1. Add a New LLM Pass

**Example: Create a "Pass 3" for emotion detection**

**Step 1: Add function to `text_processing.py`**
```python
def detect_speaker_emotions(self, analysis_result):
    """Analyze dialogue for emotional tone."""
    # Implementation here
    return analysis_result
```

**Step 2: Add UI trigger in `ui_setup.py`**
```python
def _start_pass_3_emotion(self):
    """Background task for emotion detection."""
    def run():
        result = self.state.text_processor.detect_speaker_emotions(
            self.state.analysis_result
        )
        self.update_queue.put({
            "status": "complete",
            "op_name": "pass3_emotion",
            "result": result
        })
    
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
```

**Step 3: Handle completion**
```python
def _handle_pass3_emotion_complete_update(self, result):
    """Update UI after emotion detection."""
    self.state.analysis_result = result
    self.update_status("Emotion detection complete")
    # Update UI as needed
```

**Step 4: Add button in appropriate view**
```python
# In views/cast_refinement_view.py or similar
emotion_button = tk.Button(
    frame, 
    text="Detect Emotions",
    command=self.app_controller.run_pass_3_emotion
)
emotion_button.pack()
```

---

### 2. Modify the Speaker Refinement LLM Prompt

**File: `text_processing.py`, function `_build_speaker_refinement_prompt()`**

Current prompt groups speakers into canonical characters. To change refinement strategy:

```python
def _build_speaker_refinement_prompt(self, speakers_sample):
    """Build LLM prompt for speaker grouping."""
    prompt = """
    Analyze these character names and group them into canonical characters.
    Consider context: names like "Captain Horn", "Corran", "Commander" might all be "Corran Horn".
    
    YOUR CUSTOM INSTRUCTION HERE
    
    Return JSON: {"groups": [{"primary": "name", "aliases": ["alias1", ...]}, ...]}
    """
    return prompt
```

**Common modifications:**
- Add character relationship hints
- Change grouping strategy (looser vs stricter)
- Add confidence scoring rules

---

### 3. Add a New TTS Engine

**File: `tts_engines.py`**

**Step 1: Create engine class**
```python
class MyCustomTTS(TTSEngine):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.client = MyCustomClient()
    
    def generate_audio(self, text, speaker, output_path):
        """Generate audio file."""
        audio = self.client.tts(
            text=text,
            speaker=speaker,
            format="wav"
        )
        with open(output_path, 'wb') as f:
            f.write(audio)
        return True
    
    def get_available_voices(self):
        """Return list of voice IDs."""
        return ["voice1", "voice2", ...]
```

**Step 2: Register in `ui_setup.py`**
```python
# In __init__ or engine selection method
engine_map = {
    "Chatterbox": ChatterboxTTS,
    "My Custom": MyCustomTTS,
}
```

---

### 4. Tweak Cast Extraction Parameters

**File: `text_processing.py`, function `extract_cast_list_from_book_beginning()`**

Current settings:
- `timeout=240.0` - LLM request timeout
- `max_tokens=900` - Response size limit
- `max(20, len(characters))` - Character name length cap

To be more aggressive:
```python
# Longer responses, longer timeout for very large casts
timeout=300.0      # 300 seconds
max_tokens=1200    # Larger response
char_limit=25      # Longer names
```

To be more conservative:
```python
# Faster, shorter responses
timeout=180.0      # 180 seconds
max_tokens=600     # Shorter response
char_limit=15      # Shorter names only
```

---

### 5. Fix a Speaker Resolution Bug

**Typical flow:**

1. **Reproduce**: Run test or manual book, check `speaker_pipeline_diagnostics.log`
2. **Identify stage**: Pass 1 (rules), Pass 2 (LLM), or refinement
3. **Debug**:
   - Add logging: `self.logger.debug(f"Speaker resolution: {speaker}")` 
   - Check `analysis_result` structure after each pass
   - Verify LLM response format
4. **Check tests**: Find or create test for the scenario
5. **Fix** in `text_processing.py` or `ui_setup.py`
6. **Test**: Run `pytest tests/test_*.py -k "your_test" -v`

---

## Testing Strategy

### Test Organization

```
tests/
├── test_cast_list_extraction.py    # Cast extraction with JSON recovery
├── test_cast_seed_integration.py   # Pass 1/2 with cast seeds
├── test_speaker_validation.py      # Speaker name validation
├── test_single_speaker_review_helpers.py  # Single-speaker AI review
├── test_voice_alias_auto_assign.py # Voice matching
├── test_metadata_button_state.py   # UI state transitions
└── test_quote_fragment_handling.py  # Quote parsing
```

### Writing a New Test

**File: `tests/test_my_feature.py`**

```python
import pytest
from text_processing import TextProcessor
from app_state import AppState

class TestMyFeature:
    @pytest.fixture
    def text_processor(self):
        state = AppState()
        return TextProcessor(state)
    
    def test_my_function(self, text_processor):
        # Arrange
        test_text = "Some test dialogue"
        
        # Act
        result = text_processor.my_function(test_text)
        
        # Assert
        assert result is not None
        assert len(result) > 0
```

**Run it:**
```powershell
.\.venv_chatterbox\Scripts\python.exe -m pytest tests/test_my_feature.py -v
```

### Important Test Notes

- **PIL cross-contamination**: Don't mix PIL-dependent tests with text processing tests
- **Run separately**: `pytest tests/test_cast_list_extraction.py tests/test_cast_seed_integration.py`
- **Mock LLM**: Use fixtures to mock LLM responses for unit tests
- **Integration tests**: Run full pipeline tests with real LLM separately

---

## Debugging Tips

### 1. Enable Debug Logging

In `ui_setup.py` or `text_processing.py`:
```python
self.logger.setLevel(logging.DEBUG)
handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
))
```

### 2. Inspect State at Breakpoints

In VS Code, add breakpoint in `text_processing.py`:
```python
# At breakpoint, in Debug Console:
# self.state.analysis_result[0]  # First line
# self.state.character_groups[0]  # First group
```

### 3. Check Diagnostic Logs

```powershell
# Check last 50 lines of pipeline diagnostics
Get-Content "Audiobook_Output/speaker_pipeline_diagnostics.log" -Tail 50

# Search for errors
Select-String "ERROR|WARNING" "Audiobook_Output/audiobook_creator.log"
```

### 4. Manually Test an LLM Call

```python
# In Python REPL
from text_processing import TextProcessor
from app_state import AppState

state = AppState()
tp = TextProcessor(state)

# Test cast extraction
result = tp.extract_cast_list_from_book_beginning(
    "Your test text here...",
    timeout=240.0
)
print(result)
```

---

## Code Style Guidelines

- **Naming**: `snake_case` for functions, `PascalCase` for classes
- **Docstrings**: Document parameters, return value, and behavior
- **Type hints**: Add type hints to function signatures
- **Comments**: Explain *why*, not *what*
- **Line length**: Keep <100 chars for readability

**Example:**
```python
def resolve_ambiguous_speakers(
    self, 
    analysis_result: List[dict],
    num_context_lines: int = 2
) -> Dict[str, Any]:
    """
    Use LLM to resolve AMBIGUOUS and UNKNOWN speakers in dialogue.
    
    Batches lines to avoid context overflow, sends to LLM for
    speaker prediction based on dialogue content.
    
    Args:
        analysis_result: Output from Pass 1 analysis
        num_context_lines: Lines of context around each ambiguous speaker
        
    Returns:
        Dictionary with processing stats (processed, id_unresolved, etc.)
    """
```

---

## Common Gotchas

### 1. Queue Threading Issues
- **Problem**: UI updates don't appear
- **Solution**: Make sure update is posted to `self.update_queue`, not called directly
- **Check**: `print(f"Queue size: {self.update_queue.qsize()}")` in handler

### 2. LLM Not Running
- **Problem**: Pass 2 skipped, all speakers UNKNOWN
- **Solution**: Check LM Studio on port 4247 with `curl http://localhost:4247/v1/models`
- **Fallback**: App runs on Pass 1 only if LLM unavailable

### 3. PIL Test Failures
- **Problem**: Tests pass alone but fail together
- **Solution**: Run text_processing tests separately, UI tests separately
- **Root cause**: PIL stub contamination between test sessions

### 4. Large Book Timeouts
- **Problem**: Cast extraction times out on 500+ page books
- **Solution**: Increase `timeout` in `extract_cast_list_from_book_beginning()` or reduce `max_tokens`
- **Example**: `timeout=300.0` for very large books

### 5. Speaker Refinement Drops 50+ Speakers
- **Problem**: Cast larger than 200 speakers → some are UNKNOWN after refinement
- **Solution**: Increase `MAX_SPEAKERS_FOR_REFINEMENT` in `text_processing.py`
- **Trade-off**: Longer refinement time, larger LLM batches

---

## Filing Issues & PRs

### Before Filing
1. Check existing issues/PRs
2. Run test suite: `pytest tests/ -q`
3. Include diagnostic logs if it's a pipeline issue
4. Provide minimal reproduction (code snippet or book excerpt)

### Issue Template
```
**Description**: What's the problem?
**Reproduction**: Steps to reproduce
**Expected vs Actual**: What should happen vs what happens
**Logs**: Diagnostic logs from Audiobook_Output/
**Environment**: Python version, OS, LM Studio version
```

### PR Template
```
**What**: What does this PR do?
**Why**: Why is this needed?
**Testing**: What tests verify this works?
**Changes**: Files modified and why
```

---

## Resources

- **README.md** - User setup and feature overview
- **ARCHITECTURE.md** - Detailed component descriptions and data flows
- **GEMINI.md** - Feature list and workflow overview
- **Text Processing**: See docstrings in `text_processing.py` for all LLM functions
- **UI Setup**: See `ui_setup.py` for queue handling and workflow orchestration

---

Happy coding! 🎉 If you hit issues or have questions, check the diagnostics logs and debug tips above, or file an issue with details.
