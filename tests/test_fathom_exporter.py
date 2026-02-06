import csv
from pathlib import Path

from fathom_exporter import TranscriptRecord, export_records, normalize_date, normalize_record, safe_filename


def test_normalize_record_accepts_common_fields():
    row = {
        "id": "abc123",
        "title": "Weekly Product Sync",
        "created_at": "2024-10-12T13:00:00Z",
        "transcript": "Hello world",
    }
    record = normalize_record(row)
    assert record is not None
    assert record.record_id == "abc123"
    assert record.title == "Weekly Product Sync"
    assert record.date == "2024-10-12"
    assert record.transcript == "Hello world"


def test_normalize_record_ignores_empty_transcript():
    row = {"id": "abc123", "title": "No text", "transcript": "   "}
    assert normalize_record(row) is None


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
        )
    ]

    count = export_records(records, output_dir=tmp_path)

    assert count == 1
    files = list(tmp_path.glob("*.md"))
    assert len(files) == 1
    body = files[0].read_text(encoding="utf-8")
    assert "# Team Sync" in body
    assert "Line two" in body

    csv_path = tmp_path / "index.csv"
    assert csv_path.exists()
    rows = list(csv.DictReader(csv_path.open("r", encoding="utf-8")))
    assert rows[0]["id"] == "abc123"
