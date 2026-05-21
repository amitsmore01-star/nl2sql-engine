# src/core/logging/logger.py
# V0 - Initial implementation
#
# StructuredLogger — writes one JSONL log file per request_id.
# Rotation: on every write, checks if the log file is from a previous day.
# If yes, moves it to logs/archive/YYYY-MM-DD/ before writing the new entry.
#
# Reads all paths from settings — nothing hardcoded.
# Called by every pipeline stage to emit a structured log entry.

import json
import shutil
from datetime import date, datetime, timezone
from pathlib import Path

from src.core.logging.log_models import LogEntry


class StructuredLogger:
    """
    Writes structured JSONL log entries, one file per request_id.

    Usage:
        logger = StructuredLogger(settings)
        logger.log(LogEntry(request_id="abc", stage="REQUEST_RECEIVED", ...))

    File locations (all from settings — never hardcoded):
        Active logs:  {log_dir}/{request_id}.log
        Archived:     {log_archive_dir}/YYYY-MM-DD/{request_id}.log
    """

    def __init__(self, settings) -> None:
        """
        Initialise the logger.

        Args:
            settings: Loaded Settings object from src/config/settings.py.
                      Reads settings.logging.log_dir and
                      settings.logging.log_archive_dir.
        """
        self._log_dir = Path(settings.logging.log_dir)
        self._archive_dir = Path(settings.logging.log_archive_dir)

        # Create both directories on startup if they do not exist.
        # parents=True  — creates any missing parent folders too
        # exist_ok=True — no error if the folder already exists
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._archive_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def log(self, entry: LogEntry) -> None:
        """
        Write a log entry to {log_dir}/{request_id}.log.

        Before writing, checks if the file is from a previous day.
        If so, rotates it to the archive directory first.

        Args:
            entry: A validated LogEntry instance.
        """
        log_file = self._log_dir / f"{entry.request_id}.log"

        # Rotation check — only if the file already exists
        if log_file.exists():
            self._rotate_if_stale(log_file)

        # Write the entry as a single JSON line (JSONL format)
        # mode="a" — append; creates the file if it does not exist
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(self._serialise(entry) + "\n")

    def rotate(self) -> None:
        """
        Explicitly rotate all stale log files in the log directory.

        A log file is stale if its modification date is before today.
        Useful to call at startup to clean up any files left from yesterday
        if the service was running at midnight.
        """
        for log_file in self._log_dir.glob("*.log"):
            self._rotate_if_stale(log_file)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _rotate_if_stale(self, log_file: Path) -> None:
        """
        Move log_file to archive if its modification date is before today.

        Archive path: {archive_dir}/YYYY-MM-DD/{filename}
        The date used is the file's last-modified date (the day it was written).
        """
        file_date = self._file_date(log_file)
        today = date.today()

        if file_date < today:
            # Build archive subfolder for that specific date
            archive_subdir = self._archive_dir / file_date.strftime("%Y-%m-%d")
            archive_subdir.mkdir(parents=True, exist_ok=True)

            # Move the file — shutil.move handles cross-drive moves on Windows
            destination = archive_subdir / log_file.name
            shutil.move(str(log_file), str(destination))

    def _file_date(self, log_file: Path) -> date:
        """
        Return the last-modified date of a log file as a date object.

        Uses the file's mtime (modification time) — the most reliable
        cross-platform indicator of when the file was last written to.
        """
        mtime = log_file.stat().st_mtime
        return datetime.fromtimestamp(mtime, tz=timezone.utc).date()

    def _serialise(self, entry: LogEntry) -> str:
        """
        Serialise a LogEntry to a JSON string.

        - datetime fields are converted to ISO 8601 strings
        - No extra whitespace — one compact line per entry
        """
        # model_dump() converts the Pydantic model to a plain dict
        # round-trip through json.dumps with a custom default handler
        # ensures datetime objects are serialised correctly
        raw = entry.model_dump()
        return json.dumps(raw, default=self._json_default, ensure_ascii=False)

    @staticmethod
    def _json_default(obj):
        """
        Fallback serialiser for types json.dumps cannot handle by default.
        Currently handles datetime — converts to ISO 8601 string.
        """
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f"Object of type {type(obj)} is not JSON serialisable")
