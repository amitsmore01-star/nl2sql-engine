# tests/core/logging/test_log_models.py
# V0 - Initial implementation
#
# Tests for src/core/logging/log_models.py and src/core/constants.py
# Covers scenarios M1-M9.

import pytest
from datetime import datetime, timezone
from pydantic import ValidationError

from src.core.logging.log_models import LogEntry
import src.core.constants as constants


# ===========================================================================
# Group 1 — LogEntry base model
# ===========================================================================

class TestLogEntryModel:

    def test_m1_valid_log_entry_creates_successfully(self):
        """M1 — All required fields accepted, entry created without error."""
        entry = LogEntry(
            request_id="req-001",
            stage=constants.REQUEST_RECEIVED,
        )
        assert entry.request_id == "req-001"
        assert entry.stage == constants.REQUEST_RECEIVED

    def test_m2_timestamp_utc_auto_populated(self):
        """M2 — timestamp_utc is set to now (UTC) if caller does not provide it."""
        before = datetime.now(timezone.utc)
        entry = LogEntry(request_id="req-002", stage=constants.SQL_BUILT)
        after = datetime.now(timezone.utc)

        assert entry.timestamp_utc is not None
        assert before <= entry.timestamp_utc <= after

    def test_m2_timestamp_utc_accepted_when_provided(self):
        """M2 — Caller-supplied timestamp_utc is used as-is."""
        fixed_time = datetime(2025, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        entry = LogEntry(
            request_id="req-002b",
            stage=constants.APP_DETECTED,
            timestamp_utc=fixed_time,
        )
        assert entry.timestamp_utc == fixed_time

    def test_m3_missing_request_id_raises_validation_error(self):
        """M3 — request_id is required — omitting it raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            LogEntry(stage=constants.REQUEST_RECEIVED)
        assert "request_id" in str(exc_info.value)

    def test_m4_missing_stage_raises_validation_error(self):
        """M4 — stage is required — omitting it raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            LogEntry(request_id="req-004")
        assert "stage" in str(exc_info.value)

    def test_m5_payload_accepts_arbitrary_dict(self):
        """M5 — payload accepts any dict structure — no fixed schema."""
        entry = LogEntry(
            request_id="req-005",
            stage=constants.VALIDATION_RESULT,
            payload={
                "resolved_tables": ["Major.Customer", "Major.Acc"],
                "applied_rules": ["VersionTermDate IS NULL"],
                "nested": {"key": "value"},
                "count": 42,
            },
        )
        assert entry.payload["resolved_tables"] == ["Major.Customer", "Major.Acc"]
        assert entry.payload["count"] == 42

    def test_m6_latency_ms_defaults_to_none(self):
        """M6 — latency_ms is optional and defaults to None."""
        entry = LogEntry(request_id="req-006", stage=constants.SQL_BUILT)
        assert entry.latency_ms is None

    def test_m6_latency_ms_accepted_when_provided(self):
        """M6 — latency_ms is stored correctly when provided."""
        entry = LogEntry(
            request_id="req-006b",
            stage=constants.SQL_BUILT,
            latency_ms=123,
        )
        assert entry.latency_ms == 123

    def test_optional_fields_default_to_none(self):
        """Optional fields user_id, app_id, app_schema_version default to None."""
        entry = LogEntry(request_id="req-007", stage=constants.APP_DETECTED)
        assert entry.user_id is None
        assert entry.app_id is None
        assert entry.app_schema_version is None

    def test_all_optional_fields_accepted(self):
        """All optional fields are stored correctly when provided."""
        entry = LogEntry(
            request_id="req-008",
            stage=constants.RESPONSE_SENT,
            user_id="Phase1_user",
            app_id="ABC_app",
            app_schema_version="1.0",
            latency_ms=310,
            payload={"status": "success"},
        )
        assert entry.user_id == "Phase1_user"
        assert entry.app_id == "ABC_app"
        assert entry.app_schema_version == "1.0"
        assert entry.latency_ms == 310


# ===========================================================================
# Group 2 — Log stage constants
# ===========================================================================

class TestLogStageConstants:

    ALL_STAGES = [
        "REQUEST_RECEIVED",
        "APP_DETECTED",
        "LLM_INTENT_OUTPUT",
        "LLM_SCHEMA_MAPPING_OUTPUT",
        "VALIDATION_RESULT",
        "STRUCTURED_QUERY_BUILT",
        "SQL_BUILT",
        "RESPONSE_SENT",
        "USER_FEEDBACK",
    ]

    def test_m7_all_nine_stage_constants_exist(self):
        """M7 — All 9 log stage constants are defined in constants.py."""
        for stage in self.ALL_STAGES:
            assert hasattr(constants, stage), (
                f"Missing log stage constant: {stage}"
            )

    def test_m8_all_stage_constants_are_strings(self):
        """M8 — Every stage constant is a string type."""
        for stage in self.ALL_STAGES:
            value = getattr(constants, stage)
            assert isinstance(value, str), (
                f"Stage constant {stage} is {type(value)}, expected str"
            )

    def test_m9_no_duplicate_stage_constant_values(self):
        """M9 — No two stage constants share the same string value."""
        values = [getattr(constants, stage) for stage in self.ALL_STAGES]
        assert len(values) == len(set(values)), (
            "Duplicate stage constant values detected"
        )
