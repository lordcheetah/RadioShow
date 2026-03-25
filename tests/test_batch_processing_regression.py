import queue
from pathlib import Path

from app_logic import AppLogic
from app_state import AppState


class DummyUI:
    def __init__(self):
        self.update_queue = queue.Queue()


def _drain_updates(q):
    items = []
    while not q.empty():
        items.append(q.get_nowait())
    return items


def test_process_ebook_batch_success_path(tmp_path):
    state = AppState()
    state.output_dir = tmp_path
    state.output_dir.mkdir(parents=True, exist_ok=True)

    book1 = tmp_path / "book1.epub"
    book2 = tmp_path / "book2.epub"
    book1.write_text("dummy", encoding="utf-8")
    book2.write_text("dummy", encoding="utf-8")
    state.ebook_queue = [book1, book2]

    ui = DummyUI()
    logic = AppLogic(ui, state, selected_tts_engine_name="Chatterbox")

    calls = {
        "metadata": [],
        "convert": [],
        "analyze": [],
        "generate": [],
        "assemble": [],
    }

    def fake_metadata(path_str):
        calls["metadata"].append(Path(path_str).name)
        state.title = Path(path_str).stem
        state.author = "Test Author"
        state.cover_path = None

    def fake_find_calibre():
        return True

    def fake_convert():
        calls["convert"].append(state.ebook_path.name)
        out_dir = Path("/tmp") if False else Path(__import__("tempfile").gettempdir()) / "radio_show"
        out_dir.mkdir(parents=True, exist_ok=True)
        txt_path = out_dir / f"{state.ebook_path.stem}.txt"
        txt_path.write_text("Narration line.", encoding="utf-8")

    def fake_rules_pass(raw_text, voicing_mode, use_single_quotes):
        calls["analyze"].append(state.ebook_path.name)
        return [{"speaker": "Narrator", "line": "Narration line."}]

    def fake_generate():
        calls["generate"].append(state.ebook_path.name)
        state.generated_clips_info = [
            {
                "text": "Narration line.",
                "speaker": "Narrator",
                "clip_path": str(tmp_path / f"{state.ebook_path.stem}_line_00000_chunk_000.wav"),
                "original_index": 0,
                "chunk_index": 0,
                "voice_used": {"name": "stub", "path": "stub"},
            }
        ]

    def fake_assemble(clips_info_list):
        calls["assemble"].append((state.ebook_path.name, len(clips_info_list)))

    logic.run_metadata_extraction = fake_metadata
    logic.file_op.find_calibre_executable = fake_find_calibre
    logic.file_op.run_calibre_conversion = fake_convert
    logic.text_proc.run_rules_pass = fake_rules_pass
    logic.run_audio_generation = fake_generate
    logic.file_op.assemble_audiobook = fake_assemble

    logic.process_ebook_batch()

    assert state.ebook_queue == []
    assert state.batch_errors == {}
    assert calls["metadata"] == ["book1.epub", "book2.epub"]
    assert calls["convert"] == ["book1.epub", "book2.epub"]
    assert calls["analyze"] == ["book1.epub", "book2.epub"]
    assert calls["generate"] == ["book1.epub", "book2.epub"]
    assert [x[0] for x in calls["assemble"]] == ["book1.epub", "book2.epub"]

    updates = _drain_updates(ui.update_queue)
    batch_done = [u for u in updates if u.get("batch_complete")]
    assert len(batch_done) == 1
    assert batch_done[0]["success"] is True
    assert batch_done[0]["errors"] == {}


def test_process_ebook_batch_partial_failure(tmp_path):
    """When one book fails, the batch continues, records the error,
    and reports success=False with the failed book's error recorded."""
    state = AppState()
    state.output_dir = tmp_path
    state.output_dir.mkdir(parents=True, exist_ok=True)

    book1 = tmp_path / "good.epub"
    book2 = tmp_path / "bad.epub"
    book1.write_text("dummy", encoding="utf-8")
    book2.write_text("dummy", encoding="utf-8")
    state.ebook_queue = [book1, book2]

    ui = DummyUI()
    logic = AppLogic(ui, state, selected_tts_engine_name="Chatterbox")

    processed_books = []

    def fake_metadata(path_str):
        name = Path(path_str).name
        state.title = Path(path_str).stem
        state.author = "Test Author"
        state.cover_path = None
        if name == "bad.epub":
            raise RuntimeError("Simulated metadata failure")

    def fake_find_calibre():
        return True

    def fake_convert():
        out_dir = Path(__import__("tempfile").gettempdir()) / "radio_show"
        out_dir.mkdir(parents=True, exist_ok=True)
        txt_path = out_dir / f"{state.ebook_path.stem}.txt"
        txt_path.write_text("Narration line.", encoding="utf-8")

    def fake_rules_pass(raw_text, voicing_mode, use_single_quotes):
        return [{"speaker": "Narrator", "line": "Narration line."}]

    def fake_generate():
        processed_books.append(state.ebook_path.name)
        state.generated_clips_info = [
            {
                "text": "Narration line.",
                "speaker": "Narrator",
                "clip_path": str(tmp_path / f"{state.ebook_path.stem}_line_00000_chunk_000.wav"),
                "original_index": 0,
                "chunk_index": 0,
                "voice_used": {"name": "stub", "path": "stub"},
            }
        ]

    def fake_assemble(clips_info_list):
        pass

    logic.run_metadata_extraction = fake_metadata
    logic.file_op.find_calibre_executable = fake_find_calibre
    logic.file_op.run_calibre_conversion = fake_convert
    logic.text_proc.run_rules_pass = fake_rules_pass
    logic.run_audio_generation = fake_generate
    logic.file_op.assemble_audiobook = fake_assemble

    logic.process_ebook_batch()

    # good.epub should complete fully; bad.epub should be skipped after the error
    assert processed_books == ["good.epub"]
    assert state.ebook_queue == []

    # Error for bad.epub is recorded
    assert "bad.epub" in state.batch_errors
    assert "Simulated metadata failure" in state.batch_errors["bad.epub"]

    # batch_complete payload reflects the partial failure
    updates = _drain_updates(ui.update_queue)
    batch_done = [u for u in updates if u.get("batch_complete")]
    assert len(batch_done) == 1
    assert batch_done[0]["success"] is False
    assert "bad.epub" in batch_done[0]["errors"]
