# tests/core/logging/test_logger.py
# V0 - Initial implementation
#
# Tests for src/core/logging/logger.py
# Covers scenarios L1-L17.
# Uses tmp_path (pytest built-in) for all file operations — no real logs/ dir touched.

import json
import time
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from src.core.logging.log_models import LogEntry
from src.core.logging.logger import StructuredLogger
import src.core.constants as constants


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_settings(tmp_path: Path):
    """
    Build a minimal settings-like object with logging.log_dir and
    logging.log_archive_dir pointing at tmp_path subdirectories.

    We use a simple namespace object instead of loading real Settings
    so these tests have zero dependency on YAML files or .env.
    """
    from types import SimpleNamespace

    log_dir     = tmp_path / "logs"
    archive_dir = tmp_path / "logs" / "archive"

    logging_ns = SimpleNamespace(
        log_dir=str(log_dir),
        log_archive_dir=str(archive_dir),
        level="DEBUG",
        rotation="daily",
    )
    return SimpleNamespace(logging=logging_ns)


def _make_entry(request_id: str = "req-test", stage: str = None, **kwargs) -> LogEntry:
    """Helper — build a LogEntry with sensible defaults."""
    return LogEntry(
        request_id=request_id,
        stage=stage or constants.REQUEST_RECEIVED,
        **kwargs,
    )


def _read_lines(log_file: Path) -> list[dict]:
    """Read all JSONL lines from a log file and parse each as a dict."""
    lines = log_file.read_text(encoding="utf-8").strip().splitlines()
    return [json.loads(line) for line in lines]


# ===========================================================================
# Group 3 — Logger initialisation
# ===========================================================================

class TestLoggerInitialisation:

    def test_l1_creates_log_dir_if_not_exists(self, tmp_path):
        """L1 — Logger creates log_dir on __init__ if it does not exist."""
        settings = _make_settings(tmp_path)
        log_dir = Path(settings.logging.log_dir)

        assert not log_dir.exists()
        StructuredLogger(settings)
        assert log_dir.exists()
        assert log_dir.is_dir()

    def test_l2_creates_archive_dir_if_not_exists(self, tmp_path):
        """L2 — Logger creates log_archive_dir on __init__ if it does not exist."""
        settings = _make_settings(tmp_path)
        archive_dir = Path(settings.logging.log_archive_dir)

        assert not archive_dir.exists()
        StructuredLogger(settings)
        assert archive_dir.exists()
        assert archive_dir.is_dir()

    def test_l3_log_dir_comes_from_settings(self, tmp_path):
        """L3 — Logger uses path from settings — not a hardcoded 'logs/' string."""
        custom_log_dir = tmp_path / "custom_logs"
        from types import SimpleNamespace
        settings = SimpleNamespace(
            logging=SimpleNamespace(
                log_dir=str(custom_log_dir),
                log_archive_dir=str(custom_log_dir / "archive"),
                level="DEBUG",
                rotation="daily",
            )
        )
        logger = StructuredLogger(settings)
        assert custom_log_dir.exists()
        # Verify internal path matches settings — not a hardcoded value
        assert logger._log_dir == custom_log_dir


# ===========================================================================
# Group 4 — Writing log entries
# ===========================================================================

class TestWritingLogEntries:

    def test_l4_writing_entry_creates_correct_filename(self, tmp_path):
        """L4 — Writing an entry creates logs/{request_id}.log."""
        settings = _make_settings(tmp_path)
        logger = StructuredLogger(settings)
        entry = _make_entry(request_id="abc123")

        logger.log(entry)

        log_file = Path(settings.logging.log_dir) / "abc123.log"
        assert log_file.exists()

    def test_l5_written_entry_is_valid_jsonl(self, tmp_path):
        """L5 — Written entry is a single valid JSON line (JSONL format)."""
        settings = _make_settings(tmp_path)
        logger = StructuredLogger(settings)
        entry = _make_entry(request_id="json-test")

        logger.log(entry)

        log_file = Path(settings.logging.log_dir) / "json-test.log"
        content = log_file.read_text(encoding="utf-8")
        lines = content.strip().splitlines()

        assert len(lines) == 1
        # Must parse as valid JSON — no exception means it is valid
        parsed = json.loads(lines[0])
        assert isinstance(parsed, dict)

    def test_l6_written_entry_contains_required_fields(self, tmp_path):
        """L6 — Written entry contains request_id, stage, timestamp_utc."""
        settings = _make_settings(tmp_path)
        logger = StructuredLogger(settings)
        entry = _make_entry(request_id="fields-test", stage=constants.SQL_BUILT)

        logger.log(entry)

        log_file = Path(settings.logging.log_dir) / "fields-test.log"
        parsed = _read_lines(log_file)[0]

        assert parsed["request_id"] == "fields-test"
        assert parsed["stage"] == constants.SQL_BUILT
        assert "timestamp_utc" in parsed
        assert parsed["timestamp_utc"] is not None

    def test_l7_two_entries_same_request_id_appends(self, tmp_path):
        """L7 — Writing two entries to same request_id appends — file has two lines."""
        settings = _make_settings(tmp_path)
        logger = StructuredLogger(settings)

        logger.log(_make_entry(request_id="append-test", stage=constants.REQUEST_RECEIVED))
        logger.log(_make_entry(request_id="append-test", stage=constants.SQL_BUILT))

        log_file = Path(settings.logging.log_dir) / "append-test.log"
        lines = _read_lines(log_file)

        assert len(lines) == 2
        assert lines[0]["stage"] == constants.REQUEST_RECEIVED
        assert lines[1]["stage"] == constants.SQL_BUILT

    def test_l8_different_request_ids_create_separate_files(self, tmp_path):
        """L8 — Two different request_ids produce two separate log files."""
        settings = _make_settings(tmp_path)
        logger = StructuredLogger(settings)

        logger.log(_make_entry(request_id="req-aaa"))
        logger.log(_make_entry(request_id="req-bbb"))

        log_dir = Path(settings.logging.log_dir)
        assert (log_dir / "req-aaa.log").exists()
        assert (log_dir / "req-bbb.log").exists()

        lines_a = _read_lines(log_dir / "req-aaa.log")
        lines_b = _read_lines(log_dir / "req-bbb.log")

        assert len(lines_a) == 1
        assert len(lines_b) == 1
        assert lines_a[0]["request_id"] == "req-aaa"
        assert lines_b[0]["request_id"] == "req-bbb"

    def test_l9_payload_round_trip(self, tmp_path):
        """L9 — payload dict is written to file and readable back correctly."""
        settings = _make_settings(tmp_path)
        logger = StructuredLogger(settings)

        payload = {
            "resolved_tables": ["Major.Customer", "Major.Acc"],
            "applied_rules": ["VersionTermDate IS NULL"],
            "count": 2,
        }
        entry = _make_entry(request_id="payload-test", payload=payload)
        logger.log(entry)

        log_file = Path(settings.logging.log_dir) / "payload-test.log"
        parsed = _read_lines(log_file)[0]

        assert parsed["payload"]["resolved_tables"] == ["Major.Customer", "Major.Acc"]
        assert parsed["payload"]["applied_rules"] == ["VersionTermDate IS NULL"]
        assert parsed["payload"]["count"] == 2


# ===========================================================================
# Group 5 — Rotation on write
# ===========================================================================

class TestRotationOnWrite:

    def test_l10_no_rotation_when_file_date_is_today(self, tmp_path):
        """L10 — File written today is not rotated — stays in log_dir."""
        settings = _make_settings(tmp_path)
        logger = StructuredLogger(settings)

        # Write first entry — creates file with today's mtime
        logger.log(_make_entry(request_id="no-rotate"))

        log_file = Path(settings.logging.log_dir) / "no-rotate.log"
        assert log_file.exists()

        # Write second entry — should NOT trigger rotation
        logger.log(_make_entry(request_id="no-rotate", stage=constants.SQL_BUILT))

        # File still in log_dir, not in archive
        assert log_file.exists()
        archive_dir = Path(settings.logging.log_archive_dir)
        archived_files = list(archive_dir.rglob("no-rotate.log"))
        assert len(archived_files) == 0

    def test_l11_stale_file_is_moved_to_archive(self, tmp_path):
        """L11 — File from a previous day is moved to archive before new entry written.
        After rotation the old file moves to archive AND a new file is created in log_dir
        for the new entry — so log_dir still has the file but with only the new entry.
        """
        import os, time as time_mod
        settings = _make_settings(tmp_path)
        logger = StructuredLogger(settings)

        # Write first entry (old entry — will be archived)
        logger.log(_make_entry(request_id="stale-test", stage=constants.REQUEST_RECEIVED))
        log_file = Path(settings.logging.log_dir) / "stale-test.log"
        assert log_file.exists()

        # Set file mtime to yesterday so logger sees it as stale
        from datetime import date, timedelta
        yesterday = date.today() - timedelta(days=1)
        yesterday_ts = time_mod.mktime(yesterday.timetuple())
        os.utime(log_file, (yesterday_ts, yesterday_ts))

        # Write second entry — rotation triggers, old file archived, new file created
        logger.log(_make_entry(request_id="stale-test", stage=constants.SQL_BUILT))

        # Old file must be in archive
        archive_subdir = (
            Path(settings.logging.log_archive_dir)
            / yesterday.strftime("%Y-%m-%d")
        )
        assert (archive_subdir / "stale-test.log").exists()

        # Archived file must contain the OLD entry
        archived_lines = _read_lines(archive_subdir / "stale-test.log")
        assert archived_lines[0]["stage"] == constants.REQUEST_RECEIVED

        # New file in log_dir must contain only the NEW entry
        assert log_file.exists()
        new_lines = _read_lines(log_file)
        assert len(new_lines) == 1
        assert new_lines[0]["stage"] == constants.SQL_BUILT

    def test_l12_new_entry_written_to_fresh_file_after_rotation(self, tmp_path):
        """L12 — After rotation, new entry is written to a fresh log file."""
        import os, time as time_mod
        settings = _make_settings(tmp_path)
        logger = StructuredLogger(settings)

        # Write first entry
        logger.log(_make_entry(request_id="fresh-test", stage=constants.REQUEST_RECEIVED))

        from datetime import date, timedelta
        yesterday = date.today() - timedelta(days=1)
        log_file = Path(settings.logging.log_dir) / "fresh-test.log"
        yesterday_ts = time_mod.mktime(yesterday.timetuple())
        os.utime(log_file, (yesterday_ts, yesterday_ts))

        # Write new entry — rotation fires, old file archived, new file created
        logger.log(_make_entry(request_id="fresh-test", stage=constants.SQL_BUILT))

        # New file in log_dir must contain only the new entry (not the old one)
        assert log_file.exists()
        lines = _read_lines(log_file)
        assert len(lines) == 1
        assert lines[0]["stage"] == constants.SQL_BUILT

    def test_l13_rotated_file_in_correct_dated_subfolder(self, tmp_path):
        """L13 — Rotated file lands in archive subfolder named after the old file's date."""
        import os, time as time_mod
        settings = _make_settings(tmp_path)
        logger = StructuredLogger(settings)

        logger.log(_make_entry(request_id="date-check"))

        from datetime import date, timedelta
        two_days_ago = date.today() - timedelta(days=2)
        log_file = Path(settings.logging.log_dir) / "date-check.log"
        two_days_ago_ts = time_mod.mktime(two_days_ago.timetuple())
        os.utime(log_file, (two_days_ago_ts, two_days_ago_ts))

        logger.log(_make_entry(request_id="date-check", stage=constants.SQL_BUILT))

        expected_folder = (
            Path(settings.logging.log_archive_dir)
            / two_days_ago.strftime("%Y-%m-%d")
        )
        assert (expected_folder / "date-check.log").exists()

    def test_l14_archive_subdir_created_if_not_exists(self, tmp_path):
        """L14 — Archive subdirectory for the date is created automatically if missing."""
        import os, time as time_mod
        settings = _make_settings(tmp_path)
        logger = StructuredLogger(settings)

        logger.log(_make_entry(request_id="mkdir-test"))

        from datetime import date, timedelta
        yesterday = date.today() - timedelta(days=1)

        # Confirm archive subdir does not yet exist
        archive_subdir = (
            Path(settings.logging.log_archive_dir)
            / yesterday.strftime("%Y-%m-%d")
        )
        assert not archive_subdir.exists()

        # Set file mtime to yesterday so rotation triggers
        log_file = Path(settings.logging.log_dir) / "mkdir-test.log"
        yesterday_ts = time_mod.mktime(yesterday.timetuple())
        os.utime(log_file, (yesterday_ts, yesterday_ts))

        logger.log(_make_entry(request_id="mkdir-test", stage=constants.SQL_BUILT))

        # Subdir must now exist
        assert archive_subdir.exists()
        assert archive_subdir.is_dir()


# ===========================================================================
# Group 6 — Edge cases
# ===========================================================================

class TestEdgeCases:

    def test_l15_empty_payload_dict_succeeds(self, tmp_path):
        """L15 — Writing a log entry with an empty payload dict succeeds."""
        settings = _make_settings(tmp_path)
        logger = StructuredLogger(settings)

        entry = _make_entry(request_id="empty-payload", payload={})
        logger.log(entry)

        log_file = Path(settings.logging.log_dir) / "empty-payload.log"
        parsed = _read_lines(log_file)[0]
        assert parsed["payload"] == {}

    def test_l16_latency_ms_zero_written_correctly(self, tmp_path):
        """L16 — latency_ms=0 is written as 0 — not treated as falsy/missing."""
        settings = _make_settings(tmp_path)
        logger = StructuredLogger(settings)

        entry = _make_entry(request_id="zero-latency", latency_ms=0)
        logger.log(entry)

        log_file = Path(settings.logging.log_dir) / "zero-latency.log"
        parsed = _read_lines(log_file)[0]
        assert parsed["latency_ms"] == 0

    def test_l17_log_dir_comes_from_settings_not_hardcoded(self, tmp_path):
        """L17 — Logger respects a non-default log_dir from settings."""
        from types import SimpleNamespace

        custom_dir = tmp_path / "my_custom_logs"
        settings = SimpleNamespace(
            logging=SimpleNamespace(
                log_dir=str(custom_dir),
                log_archive_dir=str(custom_dir / "archive"),
                level="INFO",
                rotation="daily",
            )
        )
        logger = StructuredLogger(settings)
        logger.log(_make_entry(request_id="custom-dir-test"))

        assert (custom_dir / "custom-dir-test.log").exists()
        # The default "logs/" directory must NOT have been used
        default_logs = Path("logs")
        if default_logs.exists():
            assert not (default_logs / "custom-dir-test.log").exists()
