import logging
import queue

from app_state import AppState, VoicingMode
from text_processing import TextProcessor


def _make_processor():
    state = AppState()
    return TextProcessor(state, queue.Queue(), logging.getLogger("test"), "Chatterbox")


def test_quote_repair_removes_empty_and_orphan_double_quotes():
    tp = _make_processor()
    raw = 'He said "" and then “ ” and stray " markers.\n"Hello," she said.'

    cleaned, stats = tp._repair_quote_noise(raw)

    assert stats["empty_pairs_removed"] >= 2
    assert stats["orphan_double_removed"] >= 1
    assert stats["total_repairs"] >= 3
    assert '""' not in cleaned


def test_quote_sanity_report_flags_odd_lines_and_unbalanced_curly_quotes():
    tp = _make_processor()
    raw = '"Open only\nNarration\n“Curly open only\n'

    report = tp._build_quote_sanity_report(raw)

    assert report["needs_attention"] is True
    assert report["odd_straight_line_count"] >= 1
    assert report["curly_unbalanced_global"] is True


def test_run_rules_pass_emits_quote_sanity_payload():
    state = AppState()
    q = queue.Queue()
    tp = TextProcessor(state, q, logging.getLogger("test"), "Chatterbox")

    text = '""\n"Hello," Alice said.'
    results = tp.run_rules_pass(text, VoicingMode.CAST, use_single_quotes=False)

    assert results is not None
    update = q.get_nowait()
    assert update.get("rules_pass_complete") is True
    assert "quote_sanity" in update
    quote_sanity = update["quote_sanity"]
    assert quote_sanity["repairs"]["total_repairs"] >= 1
