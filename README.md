# RadioShow

Create multi-voice audiobooks from ebooks with AI-powered speaker detection and voice assignment.

## Overview

RadioShow is a Python Tkinter desktop application that transforms ebooks (EPUB, MOBI, etc.) into professional multi-voice audiobooks. The app automatically detects speakers, resolves character identities using LLM analysis, assigns distinct voices to each character, and generates audio using TTS engines.

### Key Features

- **Ebook Conversion**: Converts EPUB and other ebook formats to text using Calibre
- **Metadata Extraction**: Automatically extracts title, author, and cover art
- **AI-Powered Speaker Detection**: 
  - Cast list extraction from book beginnings with partial JSON recovery
  - Rules-based dialogue speaker identification (Pass 1)
  - LLM-powered speaker resolution (Pass 2)
  - Character profile refinement with grouping and alias consolidation
- **Single-Speaker AI Review**: Right-click any speaker to refine their identity and aliases using AI
- **Voice Assignment**: Assign voices to characters with voice alias auto-matching
- **TTS Integration**: Supports Chatterbox and other TTS engines
- **Project Management**: Save/load project state with voice assignments and refinements
- **Theme Support**: Light, dark, and system-default themes
- **Drag-and-Drop**: Load ebooks via file browser or drag-and-drop

## Setup

### Prerequisites

- Python 3.8+
- Calibre (for ebook conversion) - Download from [calibre-ebook.com](https://calibre-ebook.com)
- Local LLM running on `localhost:4247` (tested with LM Studio)
  - Recommended models: qwen2.5-32b-instruct, meta-llama-3.1-8b
- GPU or CPU for TTS (Chatterbox runs on CUDA/CPU)

### Installation

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd RadioShow
   ```

2. **Create a Python virtual environment**:
   ```powershell
   python -m venv .venv_chatterbox
   .\.venv_chatterbox\Scripts\Activate.ps1
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements_chatterbox.txt
   ```

4. **Verify Calibre installation**:
   - On Windows: Ensure `ebook-convert` is in your PATH or Calibre is installed
   - Test: `ebook-convert --version`

5. **Configure LLM (Optional but recommended)**:
   - Install [LM Studio](https://lmstudio.ai/)
   - Download a model (e.g., Qwen 2.5 32B Instruct)
   - Start LM Studio server on port 4247
   - App will use LLM features automatically if server is running

### Running the Application

```powershell
.\.venv_chatterbox\Scripts\python.exe main_app.py
```

Or on Windows, use the provided batch script:
```batch
RadioShow.bat
```

## Project Structure

```
RadioShow/
├── main_app.py              # Entry point - initializes Tkinter root and launches UI
├── ui_setup.py              # Main UI orchestration, queue handling, workflow transitions
├── app_logic.py             # Operational orchestration, background task management
├── app_state.py             # Application state management and serialization
├── text_processing.py       # Core text analysis, cast extraction, LLM orchestration
│
├── views/                   # UI views for each wizard step
│   ├── editor_view.py       # Step 3: Text editor and cast extraction
│   ├── cast_refinement_view.py  # Step 4: Cast list refinement UI
│   ├── voice_assignment_view.py # Step 5: Voice assignment
│   ├── review_view.py       # Step 6: Audio review and editing
│   └── ...
│
├── config_manager.py        # Configuration loading and management
├── validators.py            # Input validation rules
├── theming.py              # Theme definitions (light/dark)
├── dialogs.py              # Common dialog utilities
├── file_operations.py       # File I/O, ebook conversion, directory management
├── tts_engines.py          # TTS engine adapters (Chatterbox, etc.)
├── voice_analyzer.py       # Voice feature analysis and matching
├── audio_effects.py        # Audio post-processing effects
├── batch_processor.py      # Batch audio processing and generation
├── performance_monitor.py  # Performance tracking and diagnostics
├── progress_tracker.py     # Progress calculation and reporting
│
├── tests/                   # Pytest test suite
├── scripts/                 # Helper scripts (test runners, etc.)
├── requirements_chatterbox.txt
├── README.md
└── GEMINI.md               # Feature overview document
```

## Main Components

### `main_app.py` - Entry Point
- Initializes Tkinter root window
- Creates RadioShowApp instance from ui_setup.py
- Handles window positioning and sizing

### `ui_setup.py` - UI Orchestration
- Manages the 6-step wizard workflow
- Handles queue-based updates for background LLM operations
- Implements context menus for speaker refinement
- Manages UI state transitions and button enables/disables

### `app_logic.py` - Operation Management
- Orchestrates background tasks (cast extraction, Pass 1/2 analysis, refinement)
- Handles threading for long-running LLM operations
- Manages voice alias auto-assignment
- Coordinates with TTS engine initialization

### `text_processing.py` - Core Analysis Engine
- **Cast Extraction**: `extract_cast_list_from_book_beginning()` - Extracts character list from book beginning with LLM
  - Timeout: 240 seconds, max tokens: 900
  - Recovers from partial JSON responses
  - Confidence scoring based on dramatis personae detection
  
- **Pass 1 (Rules-Based)**: `analyze_text_to_lines()` - Identifies dialogue speakers using regex patterns
  - Handles quoted speech, action line narration, etc.
  - Can seed initial speaker resolution from extracted cast list
  
- **Pass 2 (LLM Resolution)**: `resolve_ambiguous_speakers()` - Uses LLM to resolve remaining unknown speakers
  - Verification pass for low-confidence speakers
  - Character profiling for unknown speakers
  - Batch processing to avoid context overflow
  
- **Speaker Refinement**: `refine_speaker_cast_list()` - Groups speakers into canonical characters
  - LLM-powered grouping with alias consolidation
  - Top-N heuristic fallback for ungrouped speakers
  - Late backfill for truly minor speakers
  - Caps at 200 most-frequent speakers to prevent context overflow
  
- **Single-Speaker Review**: `run_single_speaker_review()` - Targeted AI review for one speaker
  - Refines identity and suggests aliases
  - Updates refinement data in-place

### `app_state.py` - State Management
Persists across save/load cycles:
- Ebook path, metadata (title, author, cover)
- Extracted text and line analysis
- Pass 1/2 speaker data and unresolved speakers
- Speaker refinement groups and canonical names
- Voice assignments and voice aliases
- User edits and corrections

### `views/cast_refinement_view.py` - Step 4 UI
- Displays refined speaker list (canonical characters)
- Shows detailed line analysis for each speaker
- Right-click context menu on lines tree for single-speaker review
- Right-click context menu on cast list tree for speaker refinement
- Edit and delete speaker operations

## Workflow

### Step 1: Metadata Entry
- Enter book title, author, and narrator voice
- Upload or drag-and-drop ebook file

### Step 2: Metadata Review
- Review extracted metadata (title, author, cover art)
- Calibrate Calibre conversion settings if needed

### Step 3: Text Review & Cast Extraction
- Review extracted text
- Trigger cast list extraction from book beginning (if available)
- Review extracted cast list with confidence score
- Modify or clear extraction as needed

### Step 4: Cast Refinement
- Review Pass 1 rules-based speaker detection
- Run Pass 2 LLM resolution (identifies ~80% of speakers)
- Run speaker refinement (groups speakers into canonical characters)
- Right-click any speaker or line to review/refine with AI
- Edit speaker names, add aliases, merge speakers
- Review unresolved speakers

### Step 5: Voice Assignment
- Assign unique voices to each character
- Voice aliases auto-match based on speaker name components
- Assign narrator voice to dialogue-less lines

### Step 6: Audio Generation & Review
- Generate audio for all lines
- Listen to clips
- Edit speaker assignments, regenerate as needed
- Final audiobook assembly

## Diagnostics & Logging

The app generates detailed diagnostic logs in `Audiobook_Output/`:

- **speaker_pipeline_diagnostics.log**: Pass 1/2 statistics (dialogue counts, unresolved rates, cast seed info)
- **speaker_refinement_diagnostics.log**: Refinement batches, group counts, canonical character preview
- **audiobook_creator.log**: General application events, errors, and warnings

Example diagnostic output:
```
2026-05-07T17:29:54 | PASS1 | lines=7713 dialogue=2959 unresolved_dialogue=2603 cast_seed_count=0 cast_seed_source=none
2026-05-07T20:46:21 | PASS2 | complete processed=2652 id_unresolved=1025/2603 verify_kept_pass1=2/16
```

## Configuration

### Voice Configuration
Voices are managed in `Audiobook_Output/voices_config.json`:
```json
{
  "narrator": "Neil Gaiman",
  "speaker": "Commander Spock",
  "voices": { "Character Name": "voice_id", ... }
}
```

### LLM Configuration
- Default endpoint: `http://localhost:4247/v1` (OpenAI-compatible)
- Models probed automatically from `/models` endpoint
- Timeouts: 240s for cast extraction, 30s for Pass 2 ops
- Batch size for refinement: ~25 speakers per batch to avoid context overflow

## Development

### Running Tests ✅

Use the repository virtualenv when running tests to ensure imports and test stubs load consistently.

- Run the cross-platform helper script:

```bash
python scripts/run_tests.py [pytest args]
```

- On Windows with PowerShell use the helper:

```powershell
./scripts/run_tests.ps1 -Args "-k test_name"
```

- Or run pytest directly with the repo venv python (default: `.venv_chatterbox`):

```powershell
.\.venv_chatterbox\Scripts\python.exe -m pytest tests/test_cast_list_extraction.py -q
```

If pytest is not installed:

```powershell
.\.venv_chatterbox\Scripts\python.exe -m pip install pytest
```

- VS Code task available: Command Palette → Run Task → `pytest: repo venv`

Adjust virtualenv path in scripts if using a different name.

### Key Test Files

- `tests/test_cast_list_extraction.py` - Cast extraction with truncation/recovery
- `tests/test_cast_seed_integration.py` - Pass 1/2 cast seed integration
- `tests/test_single_speaker_review_helpers.py` - Single-speaker AI review parsing
- `tests/test_voice_alias_auto_assign.py` - Voice alias matching
- `tests/test_speaker_validation.py` - Speaker name validation

### Known Limitations

- **PIL stub cross-test contamination**: Run text_processing tests separately from UI tests
- **LLM endpoint timeout**: Cast extraction uses 240s timeout; increase if needed for larger books
- **Speaker refinement cap**: Limited to 200 most-frequent speakers to prevent context overflow (71 speakers were dropped from 221-speaker cast on B5 Psy Corps)
