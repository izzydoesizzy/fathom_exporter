import csv
from pathlib import Path

from fathom_exporter import TranscriptRecord, export_records, normalize_date, normalize_record, safe_filename


def test_normalize_record_accepts_common_fields():
    print("\n[TEST] normalize_record should map common API fields to TranscriptRecord")
    row = {
        "id": "abc123",
        "title": "Weekly Product Sync",
        "created_at": "2024-10-12T13:00:00Z",
        "transcript": "Hello world",
    }
    record = normalize_record(row)
    assert record is not None, "Expected a TranscriptRecord when id + transcript are present"
    assert record.record_id == "abc123", "Expected id to map to record_id"
    assert record.title == "Weekly Product Sync", "Expected title to be preserved"
    assert record.date == "2024-10-12", "Expected ISO datetime to normalize to YYYY-MM-DD"
    assert record.transcript == "Hello world", "Expected transcript text to be preserved"


def test_normalize_record_ignores_empty_transcript():
    print("\n[TEST] normalize_record should ignore records with empty transcript text")
    row = {"id": "abc123", "title": "No text", "transcript": "   "}
    assert normalize_record(row) is None, "Expected None when transcript is blank/whitespace"


def test_safe_filename_sanitizes_text():
    print("\n[TEST] safe_filename should lowercase, strip, and replace punctuation with dashes")
    assert safe_filename("  My Meeting: Q4 / Plan ") == "my-meeting-q4-plan"


def test_normalize_date_fallbacks():
    print("\n[TEST] normalize_date should parse ISO timestamps and gracefully fallback on invalid input")
    assert normalize_date("2024-11-08T10:00:00Z") == "2024-11-08"
    assert normalize_date("not-a-date-at-all") == "not-a-date"


def test_export_records_writes_markdown_and_index(tmp_path: Path):
    print("\n[TEST] export_records should write one markdown file per record plus index.csv")
    records = [
        TranscriptRecord(
            record_id="abc123",
            title="Team Sync",
            date="2024-12-01",
            transcript="Line one\nLine two",
        )
    ]

    count = export_records(records, output_dir=tmp_path)

    assert count == 1, "Expected exactly one exported transcript"
    files = list(tmp_path.glob("*.md"))
    assert len(files) == 1, "Expected exactly one markdown export file"
    body = files[0].read_text(encoding="utf-8")
    assert "# Team Sync" in body, "Expected markdown title header"
    assert "Line two" in body, "Expected transcript content in markdown file"

    csv_path = tmp_path / "index.csv"
    assert csv_path.exists(), "Expected index.csv to be created"
    rows = list(csv.DictReader(csv_path.open("r", encoding="utf-8")))
    assert rows[0]["id"] == "abc123", "Expected index.csv to include transcript record id"
