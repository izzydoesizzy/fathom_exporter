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
    export_records_streaming,
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


def test_export_records_streaming_writes_files_incrementally(tmp_path: Path):
    class StreamingStubClient:
        def fetch_transcript(self, recording_id: str) -> str:
            return f"transcript for {recording_id}"

    items = [
        {
            "recording_id": "id-1",
            "meeting_title": "First Meeting",
            "recording_start_time": "2024-12-01T10:00:00Z",
            "calendar_invitees": [{"name": "Alice"}],
        },
        {
            "recording_id": "id-2",
            "meeting_title": "Second Meeting",
            "recording_start_time": "2024-12-02T10:00:00Z",
            "calendar_invitees": [{"name": "Bob"}],
        },
    ]

    count = export_records_streaming(items, client=StreamingStubClient(), output_dir=tmp_path)

    assert count == 2
    markdown_files = sorted(tmp_path.glob("*.md"))
    assert len(markdown_files) == 2
    assert "transcript for id-1" in markdown_files[0].read_text(encoding="utf-8")
    assert "transcript for id-2" in markdown_files[1].read_text(encoding="utf-8")

    csv_path = tmp_path / "index.csv"
    rows = list(csv.DictReader(csv_path.open("r", encoding="utf-8")))
    assert len(rows) == 2



def test_iter_records_from_source_skips_failed_transcript_fetch():
    class FlakyClient:
        def fetch_transcript(self, recording_id: str) -> str:
            from fathom_exporter import FathomExporterError

            if recording_id == "bad":
                raise FathomExporterError("429")
            return "ok"

    from fathom_exporter import iter_records_from_source

    items = [
        {"recording_id": "good", "meeting_title": "Good", "recording_start_time": "2024-01-01T00:00:00Z"},
        {"recording_id": "bad", "meeting_title": "Bad", "recording_start_time": "2024-01-01T00:00:00Z"},
    ]

    records = list(iter_records_from_source(items, client=FlakyClient()))
    assert len(records) == 1
    assert records[0].record_id == "good"


def test_request_json_retries_on_429(monkeypatch):
    import io
    from urllib.error import HTTPError

    from fathom_exporter import FathomClient

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"transcript":"done"}'

    calls = {"count": 0}

    def fake_urlopen(request, timeout):
        calls["count"] += 1
        if calls["count"] == 1:
            raise HTTPError(
                url=request.full_url,
                code=429,
                msg="Too Many Requests",
                hdrs={"Retry-After": "0"},
                fp=io.BytesIO(b""),
            )
        return FakeResponse()

    monkeypatch.setattr("fathom_exporter.urlopen", fake_urlopen)
    monkeypatch.setattr("fathom_exporter.time.sleep", lambda *_: None)

    client = FathomClient(
        api_key="key",
        base_url="https://api.fathom.ai",
        min_interval_seconds=0,
        max_retries=2,
        retry_backoff_seconds=0.01,
        max_backoff_seconds=0.01,
    )

    payload = client._request_json("https://api.fathom.ai/external/v1/x", "test endpoint")
    assert payload["transcript"] == "done"
    assert calls["count"] == 2
