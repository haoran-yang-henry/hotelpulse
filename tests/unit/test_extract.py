from datetime import UTC, datetime, timedelta

from hotelpulse.pipelines.extract import extraction_window
from hotelpulse.pipelines.pms import SOURCE_TABLES

START = datetime(2026, 10, 14, 2, tzinfo=UTC)
END = datetime(2026, 10, 15, 2, tzinfo=UTC)


def test_incremental_window_includes_lookback():
    w = extraction_window(START, END, timedelta(days=2), full_refresh=False, target_is_empty=False)
    assert w.mode == "incremental"
    assert w.start == START - timedelta(days=2)
    assert w.end == END


def test_empty_target_or_full_refresh_loads_everything():
    for full, empty in [(True, False), (False, True)]:
        w = extraction_window(START, END, timedelta(days=2), full, empty)
        assert w.mode == "full" and w.start is None and w.end == END


def test_reservations_are_incremental_and_reference_tables_full():
    assert SOURCE_TABLES["reservations"].incremental_column == "updated_at"
    assert SOURCE_TABLES["guests"].incremental_column == "updated_at"
    assert SOURCE_TABLES["hotels"].incremental_column is None
