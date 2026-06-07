# tests/api/test_models.py
# V0 - Initial implementation
#
# Tests for all HTTP request and response models.
#
# Coverage:
#   QueryRequest    — QReq-1 to QReq-6
#   FeedbackRequest — FReq-1 to FReq-5
#   ToolRequest     — TReq-1 to TReq-5
#   ErrorDetail     — ED-1 to ED-3
#   QueryResponse   — QRes-1 to QRes-7
#   ToolResponse    — TRes-1 to TRes-5
#
# All tests use plain dicts as input — no real HTTP calls, no FastAPI client.
# Pydantic models are instantiated directly using model_validate(dict).
#
# Key concept — model_validate vs direct construction:
#   MyModel(field=value)          → direct Python construction
#   MyModel.model_validate(dict)  → parses from a dict (simulates JSON body parsing)
#   We use model_validate() because that is what FastAPI does when it receives
#   a JSON request body — it deserialises the JSON dict into the Pydantic model.

import pytest
from pydantic import ValidationError

from src.api.models.request import FeedbackRequest, QueryRequest, ToolRequest
from src.api.models.response import (
    ErrorDetail,
    QueryResponse,
    QueryResponseData,
    QueryResponseMeta,
    ToolResponse,
)
from src.core.models import QueryContext, ResolvedColumn, ResolvedJoin, ResolvedTable, StructuredQuery


# ---------------------------------------------------------------------------
# Shared helpers — reusable dicts for building test inputs
# ---------------------------------------------------------------------------

def make_query_request(**overrides) -> dict:
    """Minimal valid QueryRequest dict. Pass overrides to change specific fields."""
    base = {
        "nl_query": "give me customer name for customer CUST01 in Acme",
        "user_id": "test-user-001",
    }
    base.update(overrides)
    return base


def make_feedback_request(**overrides) -> dict:
    """Minimal valid FeedbackRequest dict."""
    base = {
        "request_id": "req-uuid-001",
        "status": "pass",
    }
    base.update(overrides)
    return base


def make_query_context_dict(**overrides) -> dict:
    """
    Minimal valid QueryContext dict — used for ToolRequest and ToolResponse tests.
    Matches the minimal_context fixture pattern from the architecture doc.
    """
    base = {
        "request_id": "test-uuid-001",
        "user_id": "test-agent",
        "app_id": "Acme_app",
        "app_schema_version": "1.0",
        "nl_query_original": "give me customer name for customer CUST01 in Acme",
        "nl_query_corrected": None,
        "llm_output": None,
        "resolved_tables": [],
        "resolved_columns": [],
        "resolved_filters": [],
        "resolved_joins": [],
        "applied_rules": [],
        "structured_query": None,
        "sql": None,
        "latency_ms": {},
        "token_usage": {},
        "warnings": [],
        "status": "pending",
        "error": None,
    }
    base.update(overrides)
    return base


def make_structured_query() -> StructuredQuery:
    """A minimal valid StructuredQuery for use in response tests."""
    return StructuredQuery(
        app_id="Acme_app",
        tables=[ResolvedTable(table_name="Major.Customer", alias="c")],
        columns=[ResolvedColumn(table_alias="c", column_name="CustomerCID", output_alias="CustomerCID")],
        joins=[],
        filters=[],
        applied_rules=["c.VersionTermDate IS NULL"],
    )


def make_query_response_meta() -> dict:
    """Minimal valid QueryResponseMeta dict."""
    return {
        "app_id": "Acme_app",
        "app_schema_version": "1.0",
        "total_latency_ms": 310,
        "total_tokens_used": 2140,
    }


# ===========================================================================
# QueryRequest tests
# ===========================================================================

class TestQueryRequest:
    """Tests for QueryRequest — POST /v1/query body."""

    def test_qreq1_valid_all_fields(self):
        """QReq-1: Valid body with all fields parses correctly."""
        data = make_query_request(
            app_id="Acme_app",
            request_id="my-custom-uuid",
        )
        req = QueryRequest.model_validate(data)

        assert req.nl_query == "give me customer name for customer CUST01 in Acme"
        assert req.user_id == "test-user-001"
        assert req.app_id == "Acme_app"
        assert req.request_id == "my-custom-uuid"

    def test_qreq2_request_id_auto_generated(self):
        """QReq-2: request_id omitted → auto-generated UUID string."""
        data = make_query_request()  # no request_id
        req = QueryRequest.model_validate(data)

        assert req.request_id is not None
        assert isinstance(req.request_id, str)
        assert len(req.request_id) > 0
        # UUID format check — should contain hyphens
        assert "-" in req.request_id

    def test_qreq3_app_id_optional(self):
        """QReq-3: app_id omitted → field is None."""
        data = make_query_request()  # no app_id
        req = QueryRequest.model_validate(data)

        assert req.app_id is None

    def test_qreq4_nl_query_missing_raises(self):
        """QReq-4: nl_query missing → raises ValidationError."""
        data = {"user_id": "test-user-001"}  # no nl_query

        with pytest.raises(ValidationError) as exc_info:
            QueryRequest.model_validate(data)

        # Confirm the error is about nl_query
        errors = exc_info.value.errors()
        field_names = [e["loc"][0] for e in errors]
        assert "nl_query" in field_names

    def test_qreq5_user_id_missing_raises(self):
        """QReq-5: user_id missing → raises ValidationError."""
        data = {"nl_query": "give me customers in Acme"}  # no user_id

        with pytest.raises(ValidationError) as exc_info:
            QueryRequest.model_validate(data)

        errors = exc_info.value.errors()
        field_names = [e["loc"][0] for e in errors]
        assert "user_id" in field_names

    def test_qreq6_empty_nl_query_raises(self):
        """QReq-6: nl_query is empty string → raises ValidationError."""
        data = make_query_request(nl_query="")

        with pytest.raises(ValidationError) as exc_info:
            QueryRequest.model_validate(data)

        errors = exc_info.value.errors()
        assert any("nl_query" in str(e) for e in errors)

    def test_qreq6b_whitespace_only_nl_query_raises(self):
        """QReq-6 extension: nl_query is whitespace only → raises ValidationError."""
        data = make_query_request(nl_query="   ")

        with pytest.raises(ValidationError):
            QueryRequest.model_validate(data)


# ===========================================================================
# FeedbackRequest tests
# ===========================================================================

class TestFeedbackRequest:
    """Tests for FeedbackRequest — POST /v1/feedback body."""

    def test_freq1_valid_all_fields(self):
        """FReq-1: Valid body with all fields parses correctly."""
        data = make_feedback_request(
            status="fail",
            expected_output="SELECT CustomerName FROM ...",
            actual_sql="SELECT TOP 10000 cd.CustomerName ...",
        )
        req = FeedbackRequest.model_validate(data)

        assert req.request_id == "req-uuid-001"
        assert req.status == "fail"
        assert req.expected_output == "SELECT CustomerName FROM ..."
        assert req.actual_sql == "SELECT TOP 10000 cd.CustomerName ..."

    def test_freq2_optional_fields_default_to_none(self):
        """FReq-2: expected_output and actual_sql omitted → both None."""
        data = make_feedback_request()  # no expected_output or actual_sql
        req = FeedbackRequest.model_validate(data)

        assert req.expected_output is None
        assert req.actual_sql is None

    def test_freq3_request_id_missing_raises(self):
        """FReq-3: request_id missing → raises ValidationError."""
        data = {"status": "pass"}

        with pytest.raises(ValidationError) as exc_info:
            FeedbackRequest.model_validate(data)

        errors = exc_info.value.errors()
        field_names = [e["loc"][0] for e in errors]
        assert "request_id" in field_names

    def test_freq4_status_missing_raises(self):
        """FReq-4: status missing → raises ValidationError."""
        data = {"request_id": "req-uuid-001"}

        with pytest.raises(ValidationError) as exc_info:
            FeedbackRequest.model_validate(data)

        errors = exc_info.value.errors()
        field_names = [e["loc"][0] for e in errors]
        assert "status" in field_names

    def test_freq5_invalid_status_raises(self):
        """FReq-5: status not 'pass' or 'fail' → raises ValidationError."""
        data = make_feedback_request(status="wrong")

        with pytest.raises(ValidationError) as exc_info:
            FeedbackRequest.model_validate(data)

        # Confirm the error is about status field
        errors = exc_info.value.errors()
        assert any("status" in str(e) for e in errors)

    def test_freq5b_status_pass_accepted(self):
        """FReq-5 extension: status='pass' → accepted."""
        data = make_feedback_request(status="pass")
        req = FeedbackRequest.model_validate(data)
        assert req.status == "pass"

    def test_freq5c_status_fail_accepted(self):
        """FReq-5 extension: status='fail' → accepted."""
        data = make_feedback_request(status="fail")
        req = FeedbackRequest.model_validate(data)
        assert req.status == "fail"


# ===========================================================================
# ToolRequest tests
# ===========================================================================

class TestToolRequest:
    """Tests for ToolRequest — POST /v1/tools/{stage} body."""

    def test_treq1_valid_full_context_parses(self):
        """TReq-1: Valid full QueryContext dict parses as ToolRequest correctly."""
        data = make_query_context_dict()
        req = ToolRequest.model_validate(data)

        assert req.request_id == "test-uuid-001"
        assert req.nl_query_original == "give me customer name for customer CUST01 in Acme"

    def test_treq2_missing_request_id_auto_generated(self):
        """TReq-2: request_id missing from context → auto-generated UUID, not an error.
        
        request_id has default_factory=uuid4 in QueryContext — so omitting it
        is valid. Pydantic generates a new UUID instead of raising ValidationError.
        This matches the same behaviour as QueryRequest.request_id.
        """
        data = make_query_context_dict()
        del data["request_id"]

        req = ToolRequest.model_validate(data)

        assert req.request_id is not None
        assert isinstance(req.request_id, str)
        assert "-" in req.request_id  # UUID format check

    def test_treq3_missing_nl_query_original_raises(self):
        """TReq-3: nl_query_original missing → raises ValidationError."""
        data = make_query_context_dict()
        del data["nl_query_original"]

        with pytest.raises(ValidationError) as exc_info:
            ToolRequest.model_validate(data)

        errors = exc_info.value.errors()
        field_names = [e["loc"][0] for e in errors]
        assert "nl_query_original" in field_names

    def test_treq4_spot_check_five_inherited_fields(self):
        """TReq-4: Spot-check 5 inherited QueryContext fields present after parsing."""
        data = make_query_context_dict(
            app_id="Acme_app",
            app_schema_version="1.0",
            status="pending",
        )
        req = ToolRequest.model_validate(data)

        assert req.app_id == "Acme_app"
        assert req.app_schema_version == "1.0"
        assert req.status == "pending"
        assert req.llm_output is None # TODO: decide if we want to keep llm_output or just intent_output in QueryContext — for now, just check intent_output
        assert req.sql is None

    def test_treq5_is_subclass_of_query_context(self):
        """TReq-5: ToolRequest is a subclass of QueryContext → isinstance check passes."""
        data = make_query_context_dict()
        req = ToolRequest.model_validate(data)

        # ToolRequest inherits QueryContext — so it IS a QueryContext
        assert isinstance(req, QueryContext)
        assert isinstance(req, ToolRequest)


# ===========================================================================
# ErrorDetail tests
# ===========================================================================

class TestErrorDetail:
    """Tests for ErrorDetail — shared error block in all response types."""

    def test_ed1_valid_code_and_message(self):
        """ED-1: Valid code + message → parses correctly."""
        detail = ErrorDetail.model_validate({
            "code": "NO_JOIN_PATH",
            "message": "No join path found between Major.Customer and Major.Package",
        })

        assert detail.code == "NO_JOIN_PATH"
        assert detail.message == "No join path found between Major.Customer and Major.Package"

    def test_ed2_missing_code_raises(self):
        """ED-2: code missing → raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            ErrorDetail.model_validate({"message": "Something went wrong"})

        errors = exc_info.value.errors()
        field_names = [e["loc"][0] for e in errors]
        assert "code" in field_names

    def test_ed3_missing_message_raises(self):
        """ED-3: message missing → raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            ErrorDetail.model_validate({"code": "INTERNAL_ERROR"})

        errors = exc_info.value.errors()
        field_names = [e["loc"][0] for e in errors]
        assert "message" in field_names


# ===========================================================================
# QueryResponse tests
# ===========================================================================

class TestQueryResponse:
    """Tests for QueryResponse — POST /v1/query response envelope."""

    def test_qres1_valid_full_response(self):
        """QRes-1: Valid full response with status='success', data, meta, empty errors."""
        response = QueryResponse.model_validate({
            "request_id": "req-001",
            "status": "success",
            "data": {
                "sql": "SELECT TOP 10000 cd.CustomerName FROM Major.Customer c ...",
                "structured_query": None,
                "warnings": [],
            },
            "meta": make_query_response_meta(),
            "errors": [],
        })

        assert response.request_id == "req-001"
        assert response.status == "success"
        assert response.data.sql is not None
        assert response.errors == []

    def test_qres2_data_sql_none_on_failure(self):
        """QRes-2: data.sql is None (failed query) → valid."""
        response = QueryResponse.model_validate({
            "request_id": "req-002",
            "status": "failed",
            "data": {"sql": None, "structured_query": None, "warnings": []},
            "meta": make_query_response_meta(),
            "errors": [{"code": "NO_RELEVANT_TABLES", "message": "No tables found"}],
        })

        assert response.data.sql is None
        assert response.status == "failed"

    def test_qres3_structured_query_full_object_serialises(self):
        """QRes-3: data.structured_query is full StructuredQuery → serialises to dict correctly."""
        sq = make_structured_query()

        response = QueryResponse(
            request_id="req-003",
            status="success",
            data=QueryResponseData(
                sql="SELECT TOP 10000 c.CustomerCID FROM Major.Customer c",
                structured_query=sq,
                warnings=[],
            ),
            meta=QueryResponseMeta(**make_query_response_meta()),
            errors=[],
        )

        # Serialise to dict (simulates what FastAPI sends as JSON)
        serialised = response.model_dump()

        # structured_query should be a dict in the serialised output
        sq_dict = serialised["data"]["structured_query"]
        assert isinstance(sq_dict, dict)
        assert sq_dict["app_id"] == "Acme_app"
        assert len(sq_dict["tables"]) == 1
        assert sq_dict["tables"][0]["table_name"] == "Major.Customer"
        assert sq_dict["applied_rules"] == ["c.VersionTermDate IS NULL"]

    def test_qres4_errors_list_with_one_error(self):
        """QRes-4: errors list contains one ErrorDetail → parses correctly."""
        response = QueryResponse.model_validate({
            "request_id": "req-004",
            "status": "failed",
            "data": {},
            "errors": [{"code": "APP_NOT_DETERMINED", "message": "Could not identify app"}],
        })

        assert len(response.errors) == 1
        assert response.errors[0].code == "APP_NOT_DETERMINED"
        assert response.errors[0].message == "Could not identify app"

    def test_qres5_meta_block_has_all_fields(self):
        """QRes-5: meta block contains all expected fields."""
        response = QueryResponse.model_validate({
            "request_id": "req-005",
            "status": "success",
            "data": {},
            "meta": make_query_response_meta(),
            "errors": [],
        })

        assert response.meta.app_id == "Acme_app"
        assert response.meta.app_schema_version == "1.0"
        assert response.meta.total_latency_ms == 310
        assert response.meta.total_tokens_used == 2140

    def test_qres6_missing_request_id_raises(self):
        """QRes-6: request_id missing → raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            QueryResponse.model_validate({
                "status": "success",
                "data": {},
                "errors": [],
            })

        errors = exc_info.value.errors()
        field_names = [e["loc"][0] for e in errors]
        assert "request_id" in field_names

    def test_qres7_missing_status_raises(self):
        """QRes-7: status missing → raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            QueryResponse.model_validate({
                "request_id": "req-007",
                "data": {},
                "errors": [],
            })

        errors = exc_info.value.errors()
        field_names = [e["loc"][0] for e in errors]
        assert "status" in field_names


# ===========================================================================
# ToolResponse tests
# ===========================================================================

class TestToolResponse:
    """Tests for ToolResponse — POST /v1/tools/{stage} response envelope."""

    def test_tres1_valid_response_with_full_context(self):
        """TRes-1: Valid response with status='success' and full QueryContext under context."""
        context_data = make_query_context_dict(
            app_id="Acme_app",
            status="success",
            llm_output={"intent": "select", "entities": ["customer"]},
        )

        response = ToolResponse.model_validate({
            "request_id": "req-t001",
            "status": "success",
            "context": context_data,
            "errors": [],
        })

        assert response.request_id == "req-t001"
        assert response.status == "success"
        assert response.context is not None
        assert isinstance(response.context, QueryContext)

    def test_tres2_context_fields_accessible(self):
        """TRes-2: context field spot-check app_id and intent_output accessible."""
        intent = {"intent": "select", "entities": ["customer"], "fields": ["customer name"]}
        context_data = make_query_context_dict(
            app_id="Acme_app",
            llm_output=intent,
        )

        response = ToolResponse.model_validate({
            "request_id": "req-t002",
            "status": "success",
            "context": context_data,
            "errors": [],
        })

        assert response.context.app_id == "Acme_app"
        assert response.context.llm_output == intent  #TODO: decide if we want to keep llm_output or just intent_output in QueryContext — for now, just check intent_output

    def test_tres3_errors_list_with_one_error(self):
        """TRes-3: errors list contains one ErrorDetail → parses correctly."""
        response = ToolResponse.model_validate({
            "request_id": "req-t003",
            "status": "failed",
            "context": make_query_context_dict(),
            "errors": [{"code": "MISSING_CONTEXT_FIELDS", "message": "intent_output is required"}],
        })

        assert len(response.errors) == 1
        assert response.errors[0].code == "MISSING_CONTEXT_FIELDS"

    def test_tres4_empty_errors_list_valid(self):
        """TRes-4: errors empty list → valid."""
        response = ToolResponse.model_validate({
            "request_id": "req-t004",
            "status": "success",
            "context": make_query_context_dict(),
            "errors": [],
        })

        assert response.errors == []

    def test_tres5_missing_request_id_raises(self):
        """TRes-5: request_id missing → raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            ToolResponse.model_validate({
                "status": "success",
                "context": make_query_context_dict(),
                "errors": [],
            })

        errors = exc_info.value.errors()
        field_names = [e["loc"][0] for e in errors]
        assert "request_id" in field_names
