# RadioShow Architecture & Key Functions

This document describes the major components, data flows, and key functions in RadioShow. It's intended for developers who want to understand or extend the system.

## Data Flow Overview

```
Load Ebook
    ↓
[Metadata Extraction] → app_logic.extract_metadata_from_ebook()
    ↓
[Text Conversion] → file_operations.convert_ebook_to_text()
    ↓
[Cast Extraction] → text_processing.extract_cast_list_from_book_beginning()
    ↓
[Pass 1: Rules-Based] → text_processing.analyze_text_to_lines()
    ↓
[Pass 2: LLM Resolution] → text_processing.resolve_ambiguous_speakers()
    ↓
[Speaker Refinement] → text_processing.refine_speaker_cast_list()
    ↓
[Voice Assignment] → app_logic.auto_assign_voices()
    ↓
[Audio Generation] → batch_processor.process_all_lines()
    ↓
[Audiobook Assembly] → file_operations.assemble_audiobook()
    ↓
Final M4B/MP3 File
```

## Core Processing Functions

### Text Processing Pipeline (`text_processing.py`)

#### 1. **Cast Extraction** - `extract_cast_list_from_book_beginning()`
Extracts character list from the first ~1000 words of the book.

**Parameters:**
- `text: str` - Book text
- `timeout: float` - LLM request timeout (default 240s)
- `max_tokens: int` - LLM response limit (default 900)

**Returns:**
```python
{
    "characters": [
        {"name": str, "role": str},
        ...
    ],
    "confidence": float,  # 0.0 to 1.0
    "reason": str,        # Why this confidence
    "success": bool
}
```

**Behavior:**
- Sends book beginning to LLM with structured prompt
- Looks for dramatis personae or character list sections
- Recovers from partial/truncated JSON responses using regex pair extraction
- Confidence = 1.0 if dramatis personae found, ~0.5-0.7 for inferred lists, 0.0 if no list

**Error Handling:**
- Timeout → logs warning, returns empty list
- Invalid JSON → attempts `_extract_characters_from_partial_llm_json()` salvage
- LLM model not running → returns empty with reason

#### 2. **Pass 1: Rules-Based Analysis** - `analyze_text_to_lines()`
Breaks text into lines and identifies speakers using regex patterns.

**Parameters:**
- `text: str` - Converted book text
- `use_single_quotes: bool` - Support 'quoted' speech
- `cast_seed_list: List[str]` - Optional extracted character names for seeding Pass 1 resolution
- `voicing_mode: str` - "Cast" or "Narrator" mode

**Returns:**
```python
analysis_result = [
    {
        "line_number": int,
        "speaker": str,        # e.g., "Corran Horn", "UNKNOWN", "AMBIGUOUS"
        "text": str,
        "confidence": float,   # 0.0 to 1.0
        "voicing": str         # "dialogue" or "action"
    },
    ...
]
```

**Behavior:**
- Splits text into dialogue lines and action lines
- Matches quoted speech with preceding dialogue tags (e.g., `Corran said, "text"`)
- Uses heuristics to resolve obvious patterns
- If `cast_seed_list` provided, attempts to match UNKNOWN speakers against seed names
- Returns AMBIGUOUS if multiple possible speakers, UNKNOWN if no match

**Regex Patterns:**
- Dialogue tags: `said, asked, replied, spoke, whispered`, etc.
- Quoted speech: `"text"` or `'text'` (if enabled)
- Action narration: prose without dialogue tags

#### 3. **Pass 2: LLM Resolution** - `resolve_ambiguous_speakers()`
Uses LLM to resolve remaining UNKNOWN/AMBIGUOUS speakers.

**Parameters:**
- `analysis_result: List[dict]` - Output from Pass 1
- `num_lines: int` - Context lines for surrounding dialogue
- `verification: bool` - Run extra verification pass on low-confidence speakers
- `profiling: bool` - Profile unknown speakers for character creation

**Returns:**
```python
{
    "processed": int,           # Lines processed
    "id_unresolved": int,       # Still unresolved after Pass 2
    "verify_kept_pass1": int,   # Verification pass kept original
    "profile_all_unknown": int  # New characters profiled
}
```

**Behavior:**
- Batches unresolved lines to avoid context overflow
- Sends batches to LLM with surrounding context
- LLM predicts speaker from dialogue content and context
- Optional verification pass: asks LLM to confirm low-confidence predictions
- Optional profiling: creates character profiles for truly unknown speakers
- Individual requests use 30s timeout, 96 max_tokens to avoid single-call timeouts

**Batch Strategy:**
- Groups ~25-30 lines per batch
- Sends each batch to LLM independently
- Merges results back into analysis_result

#### 4. **Speaker Refinement** - `refine_speaker_cast_list()`
Groups extracted speakers into canonical characters and consolidates aliases.

**Parameters:**
- `analysis_result: List[dict]` - Full Pass 1/2 output
- `use_profiling: bool` - Include character profiles in refinement

**Returns:**
```python
character_groups = [
    {
        "primary_name": str,     # e.g., "Corran Horn"
        "aliases": [str, ...],   # ["Commander", "Corran", ...]
        "confidence": float,
        "frequency": int         # How many lines this speaker has
    },
    ...
]
```

**Behavior:**
- Counts speaker frequencies in analysis_result
- Caps at 200 most-frequent speakers (configurable via `MAX_SPEAKERS_FOR_REFINEMENT`)
- Sends batches to LLM for grouping and alias consolidation
- LLM groups speakers that refer to the same character (e.g., "Captain Horn", "Corran" → "Corran Horn")
- Post-processes results:
  - **Top-N heuristic**: For speakers with >10 lines but not in LLM groups, keeps as individual
  - **Late backfill**: Adds speakers with <5 lines back in if needed
  - **Lonely-title merge**: Tries to attach stranded titles (e.g., "Sir", "Doctor") to compatible groups
  - **Hedged-OR split**: Splits "Character A or Character B" entries if confidence is low

**Example Output:**
```python
{
    "primary_name": "Corran Horn",
    "aliases": ["Commander Antilles", "Corran", "Horn", "pilot"],
    "frequency": 256,
    "confidence": 0.95
}
```

#### 5. **Single-Speaker Review** - `run_single_speaker_review()`
Targeted LLM review for refining one speaker's identity and aliases.

**Parameters:**
- `speaker: str` - Speaker to review
- `analysis_result: List[dict]` - Full analysis for context
- `sample_size: int` - Max dialogue samples to include (default 5)

**Returns:**
```python
{
    "primary_name": str,       # Refined name
    "suggested_aliases": [str],
    "confidence": float,
    "reasoning": str
}
```

**Behavior:**
- Extracts sample dialogue lines from the speaker in analysis_result
- Sends to LLM with request to refine identity and suggest aliases
- LLM examines dialogue context to improve speaker name/aliases
- Result updates speaker refinement data in-place
- Used via right-click context menu in UI (views/cast_refinement_view.py)

---

## State Management (`app_state.py`)

The `AppState` class maintains all application state across save/load cycles:

**Key Attributes:**
```python
class AppState:
    # Metadata
    ebook_path: str
    title: str
    author: str
    narrator: str
    cover_image: bytes
    
    # Extracted & Converted Text
    extracted_text: str
    
    # Analysis Results
    analysis_result: List[dict]  # Pass 1/2 output
    unresolved_speakers: List[dict]
    
    # Cast Data
    extracted_cast_list_metadata: dict  # From cast extraction
    cast_extraction_in_progress: bool
    character_groups: List[dict]  # From refinement
    
    # Voice Assignment
    voice_assignments: Dict[str, str]  # {"speaker": "voice_id", ...}
    voice_aliases: Dict[str, List[str]]  # {"speaker": ["alias1", ...], ...}
    
    # User Edits
    speaker_edits: Dict[str, str]  # User corrections
    deleted_speakers: List[str]
```

**Serialization:**
- `save_project_state()` → JSON file with all state
- `load_project_state()` → Restores from JSON
- Handles cover image as base64

---

## UI Orchestration (`ui_setup.py`)

The `RadioShowApp` class orchestrates the 6-step wizard workflow:

### Queue-Based Update System
- All long-running operations (LLM, TTS) run in background threads
- Results posted to `self.update_queue` (threadsafe queue)
- Main thread processes queue updates via `_process_queue()` every 100ms
- Updates trigger `_handle_*_complete()` methods

**Queue Message Format:**
```python
{
    "status": str,           # "complete", "error", "progress"
    "op_name": str,          # Operation identifier
    "result": Any,           # Operation result
    "error": str             # Error message if status="error"
}
```

### Key Methods

**Background Operations:**
- `_start_metadata_extraction()` → Calls `app_logic.extract_metadata_from_ebook()`
- `_start_text_conversion()` → Calls `file_operations.convert_ebook_to_text()`
- `_start_cast_extraction()` → Calls `text_processing.extract_cast_list_from_book_beginning()`
- `_start_pass_1()` → Calls `text_processing.analyze_text_to_lines()`
- `_start_pass_2()` → Calls `text_processing.resolve_ambiguous_speakers()`
- `_start_refinement()` → Calls `text_processing.refine_speaker_cast_list()`
- `_start_audio_generation()` → Calls `batch_processor.process_all_lines()`

**UI State Management:**
- `_set_cast_extraction_pending()` - Shows orange warning on Analyze button, displays cast_loading_chip
- `_update_progress()` - Updates progress bars and status labels
- `_handle_*_complete()` - Handles completion of each stage

### Context Menus

**Right-click on Step 4 Lines Tree:**
- "Review this speaker with AI" → Single-speaker review for selected line's speaker

**Right-click on Step 4 Cast List Tree:**
- "Review this speaker with AI" → Single-speaker review for selected character

Both trigger:
1. `start_single_speaker_review()` in app_logic.py
2. `run_single_speaker_review()` in text_processing.py
3. `_handle_single_speaker_review_complete_update()` for apply/confirm dialog

---

## Audio Generation (`batch_processor.py`)

### Main Entry Point: `process_all_lines()`

**Parameters:**
- `analysis_result: List[dict]` - Full analysis with speakers
- `character_groups: List[dict]` - Canonical characters from refinement
- `voice_assignments: Dict[str, str]` - Voice assignments
- `narrator_voice: str` - Default narrator voice
- `tts_engine: TTSEngine` - TTS engine instance
- `progress_callback: Callable` - Progress update callback

**Behavior:**
1. For each line in analysis_result:
   - Resolve speaker to canonical character name
   - Look up assigned voice
   - If action line (narration), use narrator voice
   - Call TTS engine to generate audio
   - Save as WAV file with unique ID
2. Build metadata CSV linking line IDs to speakers/content
3. Return assembly instructions for final audiobook

**Progress Reporting:**
- Calls `progress_callback()` frequently with (current, total)
- UI updates progress bar in real-time

---

## Voice Assignment (`app_logic.py`, `voice_analyzer.py`)

### Auto-Assignment: `auto_assign_voices()`

**Strategy:**
1. Prioritize voice aliases: If speaker name contains alias keyword, use that voice
2. Fallback to manual assignment or UNKNOWN

**Example:**
```python
voice_aliases = {
    "Corran": ["pilot", "commander"],
    "Wedge": ["general", "commander"]
}

# If line speaker is "General Wedge Antilles" → matches "general" alias → auto-assign Wedge's voice
```

**Parameters:**
- `character_groups: List[dict]` - From refinement
- `voice_assignments: Dict[str, str]` - User assignments so far
- `voice_aliases: Dict[str, List[str]]` - Keyword aliases for each character

**Returns:**
Updated voice_assignments with new matches

---

## Error Handling & Logging

### Logging Levels

- **INFO**: Normal operation flow, major milestones
- **WARNING**: LLM timeouts, missing data, fallback activation
- **ERROR**: Failed operations, missing files

### Diagnostic Logs (in `Audiobook_Output/`)

**speaker_pipeline_diagnostics.log:**
```
2026-05-07T17:29:54 | PASS1 | lines=7713 dialogue=2959 unresolved_dialogue=2603 voicing_mode=Cast cast_seed_count=0 cast_seed_source=none
```

**speaker_refinement_diagnostics.log:**
```
2026-05-07T17:05:19 | Batch 1/3 produced 20 raw groups.
2026-05-07T17:05:19 | Canonical character groups produced: 39
```

---

## Extension Points

### Adding a New TTS Engine

1. Create a subclass of `TTSEngine` in `tts_engines.py`
2. Implement `generate_audio(text, speaker, output_path)`
3. Register in `ui_setup.py` TTS engine dropdown
4. Implement voice listing/download if needed

### Adding a New Analysis Pass

1. Add method to `TextProcessor` in `text_processing.py`
2. Create UI step in `ui_setup.py` (new view class if needed)
3. Add queue message handler and update method
4. Update workflow buttons/transitions
5. Update `AppState` for persistence if needed

### Customizing Speaker Refinement

Edit `text_processing.py`:
- `MAX_SPEAKERS_FOR_REFINEMENT` - Cap on speakers sent to refinement (currently 200)
- Refinement prompt in `_build_speaker_refinement_prompt()` - Change LLM instructions
- Group merging logic in `_merge_speaker_groups()` - Change canonical grouping strategy

---

## Performance & Known Issues

### Timeouts

- **Cast extraction**: 240s per request (tolerates truncated JSON)
- **Pass 2 LLM calls**: 30s per batch request (90 max_tokens to avoid server overload)
- **Refinement LLM calls**: ~3-5s per speaker grouping batch

### Context Overflow Prevention

- Cast extraction: `max_tokens=900` limits response size
- Pass 2: ~25-30 lines per batch to fit context windows
- Refinement: Top 200 most-frequent speakers only (71 dropped from 221-speaker B5 cast)

### PIL Stub Cross-Test Contamination

Tests in `tests/test_metadata_button_state.py` and UI tests can interfere with text_processing tests if run together. Always run text_processing tests separately:

```powershell
.\.venv_chatterbox\Scripts\python.exe -m pytest tests/test_cast_list_extraction.py tests/test_single_speaker_review_helpers.py -q
```

### Known Limitations

1. **Large casts (200+ speakers)**: Refinement caps at 200, smaller speakers UNKNOWN
2. **No dramatis personae**: Cast extraction returns empty, all speakers resolved by Pass 2
3. **LLM not running**: All LLM operations skip (Pass 1 only, no Pass 2/refinement/cast extraction)
4. **Long lines with no speakers**: May be misclassified as action narration
