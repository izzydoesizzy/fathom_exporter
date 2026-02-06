import csv
from pathlib import Path

from fathom_exporter import (
    TranscriptRecord,
    extract_participants,
    extract_transcript_text,
    normalize_date,
    parse_source_json,
    safe_filename,
    export_records,
    _parse_retry_after_seconds,
)


class StubClient:
    def __init__(self, pages):
        self.pages = list(pages)
        self.urls = []

    def _request_json(self, url, error_context):
        self.urls.append(url)
        if not self.pages:
            raise AssertionError("No more stub pages available")
        return self.pages.pop(0)


def test_extract_transcript_text_accepts_common_shapes():
    assert extract_transcript_text({"transcript": "Hello world"}) == "Hello world"
    assert extract_transcript_text({"data": {"transcriptText": "Nested"}}) == "Nested"
    assert extract_transcript_text(["Line one", "Line two"]) == "Line one\nLine two"


def test_extract_participants_from_calendar_invitees():
    item = {
        "calendar_invitees": [
            {"name": "Alice", "email": "alice@example.com"},
            {"name": "", "email": "bob@example.com"},
        ]
    }
    assert extract_participants(item) == ["Alice", "bob@example.com"]


def test_parse_source_json_reads_items(tmp_path: Path):
    path = tmp_path / "api-response.json"
    path.write_text('{"items": [{"recording_id": 1}], "next_cursor": null}', encoding="utf-8")
    items = parse_source_json(path)
    assert len(items) == 1
    assert items[0]["recording_id"] == 1


def test_safe_filename_sanitizes_text():
    assert safe_filename("  My Meeting: Q4 / Plan ") == "my-meeting-q4-plan"


def test_normalize_date_fallbacks():
    assert normalize_date("2024-11-08T10:00:00Z") == "2024-11-08"
    assert normalize_date("not-a-date-at-all") == "not-a-date"


def test_export_records_writes_markdown_and_index(tmp_path: Path):
    records = [
        TranscriptRecord(
            record_id="abc123",
            title="Team Sync",
            date="2024-12-01",
            transcript="Line one\nLine two",
            participants=["Alice", "Bob"],
        )
    ]

    count = export_records(records, output_dir=tmp_path)

    assert count == 1
    files = list(tmp_path.glob("*.md"))
    assert len(files) == 1
    body = files[0].read_text(encoding="utf-8")
    assert "# Team Sync" in body
    assert "- **Participants:** Alice, Bob" in body
    assert "Line two" in body

    csv_path = tmp_path / "index.csv"
    assert csv_path.exists()
    rows = list(csv.DictReader(csv_path.open("r", encoding="utf-8")))
    assert rows[0]["id"] == "abc123"
    assert rows[0]["participants"] == "Alice, Bob"


def test_fetch_all_meetings_follows_next_cursor():
    from fathom_exporter import FathomClient

    pages = [
        {"items": [{"recording_id": 1}], "next_cursor": "abc"},
        {"items": [{"recording_id": 2}], "next_cursor": None},
    ]
    client = FathomClient(api_key="test", base_url="https://api.fathom.ai")
    stub = StubClient(pages)
    client._request_json = stub._request_json  # type: ignore[method-assign]

    items = client.fetch_all_meetings(calendar_invitees_domains_type="all")

    assert [item["recording_id"] for item in items] == [1, 2]
    assert "cursor=abc" in stub.urls[1]



def test_parse_retry_after_seconds_handles_plain_english_limit_message():
    body = "Currently, you are able to make a maximum of 60 calls to the API in a 60 second window."
    assert _parse_retry_after_seconds(body) == 60.0


def test_parse_retry_after_seconds_returns_none_without_seconds_phrase():
    assert _parse_retry_after_seconds("no guidance in this body") is None
