"""Tests for CLI response formatting helpers."""

from __future__ import annotations

from kcworks_import_client.api_importer import _format_response_message


def test_format_201_with_records_and_urls():
    """201 formatting lists records and URLs."""
    text = _format_response_message(
        {
            "data": [
                {
                    "item_index": 0,
                    "record_id": "r1",
                    "record_url": "https://example.com/r1",
                }
            ],
            "errors": [],
            "message": "All good",
        },
        201,
    )
    assert "Successfully imported 1 record(s)" in text
    assert "r1" in text
    assert "https://example.com/r1" in text
    assert "✓ All good" in text


def test_format_207_error_variants():
    """207 formatting covers field, validation, upload, and fallback errors."""
    text = _format_response_message(
        {
            "data": [{"item_index": 0, "record_id": "ok", "record_url": "N/A"}],
            "errors": [
                {
                    "item_index": 1,
                    "errors": [
                        {"field": "title", "message": "required"},
                        {"validation_error": "schema"},
                        {"file upload failures": ["a.pdf"]},
                        {"other": 1},
                    ],
                }
            ],
            "message": "Partial",
        },
        207,
    )
    assert "Partial success" in text
    assert "title: required" in text
    assert "Validation error: schema" in text
    assert "File upload failures" in text
    assert "Message: Partial" in text


def test_format_400_403_500_and_unknown():
    """Error status formatting and unknown-status fallback."""
    t403 = _format_response_message(
        {
            "data": [],
            "errors": [
                {
                    "item_index": 0,
                    "errors": [
                        {"field": "a", "message": "b"},
                        {"validation_error": "v"},
                        {"file upload failures": []},
                        {"x": 1},
                        "plain",
                    ],
                }
            ],
            "message": "nope",
        },
        403,
    )
    assert "Access denied" in t403
    assert "Import failed" in t403

    t400 = _format_response_message({"data": [], "errors": [], "message": ""}, 400)
    assert "Bad request" in t400

    t500 = _format_response_message({"data": [], "errors": [], "message": ""}, 500)
    assert "Server error" in t500

    other = _format_response_message(
        {
            "data": [{"record_id": "z"}],
            "errors": [{"item_index": 1}],
            "message": "hmm",
        },
        418,
    )
    assert "Response status: 418" in other
    assert "Successfully imported: 1" in other
    assert "Failed: 1" in other
