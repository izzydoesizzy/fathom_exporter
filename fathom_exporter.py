#!/usr/bin/env python3
"""Fathom transcript exporter.

This script reads a local API response JSON file to discover recording metadata,
then fetches each transcript via the Fathom External API and exports results to
local Markdown files + an index CSV.
"""

from __future__ import annotations

import csv
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass
class TranscriptRecord:
    """Normalized transcript data for exporting."""

    record_id: str
    title: str
    date: str
    transcript: str
    participants: List[str] = field(default_factory=list)


class FathomExporterError(Exception):
    """Custom error type so failures are clear and beginner-friendly."""


class FathomClient:
    """Minimal API client for transcript fetches from Fathom External API."""

    def __init__(self, api_key: str, base_url: str, timeout: int = 30):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def fetch_transcript(self, recording_id: str) -> str:
        endpoint = f"external/v1/recordings/{recording_id}/transcript"
        url = f"{self.base_url}/{endpoint}"

        print(f"[INFO] Requesting transcript for recording_id={recording_id}: {url}")
        payload = self._request_json(
            url=url,
            error_context=f"transcript endpoint for recording {recording_id}",
        )

        transcript = extract_transcript_text(payload)
        if not transcript:
            raise FathomExporterError(
                f"Transcript response for recording {recording_id} did not include transcript text."
            )

        return transcript

    def fetch_all_meetings(
        self,
        calendar_invitees_domains_type: str = "all",
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        all_items: List[Dict[str, Any]] = []
        next_cursor: Optional[str] = None
        page = 0

        while True:
            page += 1
            params: Dict[str, Any] = {
                "calendar_invitees_domains_type": calendar_invitees_domains_type,
            }
            if limit:
                params["limit"] = limit
            if next_cursor:
                params["cursor"] = next_cursor

            query = urlencode(params)
            url = f"{self.base_url}/external/v1/meetings?{query}"
            print(f"[INFO] Requesting meetings page {page}: {url}")

            payload = self._request_json(url=url, error_context=f"meetings endpoint page {page}")
            items = payload.get("items") if isinstance(payload, dict) else None
            if not isinstance(items, list):
                raise FathomExporterError(
                    f"Meetings endpoint page {page} did not return an 'items' list."
                )

            page_items = [item for item in items if isinstance(item, dict)]
            print(f"[INFO] Meetings page {page}: received {len(page_items)} items")
            all_items.extend(page_items)

            next_cursor_value = payload.get("next_cursor") if isinstance(payload, dict) else None
            next_cursor = str(next_cursor_value).strip() if next_cursor_value else None
            if not next_cursor:
                break

        print(f"[INFO] Retrieved {len(all_items)} total meetings across {page} page(s)")
        return all_items

    def _request_json(self, url: str, error_context: str) -> Any:
        headers = {
            "X-Api-Key": self.api_key,
            "Accept": "application/json",
            "User-Agent": "fathom-exporter/1.0",
        }
        request = Request(url, headers=headers, method="GET")
        try:
            with urlopen(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8")
        except HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise FathomExporterError(
                f"API request failed with HTTP {exc.code} for {error_context}. Response body: {details}"
            ) from exc
        except URLError as exc:
            raise FathomExporterError(
                f"Network error while calling {error_context}: {exc}"
            ) from exc

        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise FathomExporterError(
                f"API returned invalid JSON for {error_context}."
            ) from exc



def extract_transcript_text(payload: Any) -> str:
    """Extract transcript text from common response shapes."""
    if isinstance(payload, str):
        return payload.strip()

    if isinstance(payload, list):
        lines = [str(part).strip() for part in payload if str(part).strip()]
        return "\n".join(lines).strip()

    if isinstance(payload, dict):
        for key in (
            "transcript",
            "transcript_text",
            "transcriptText",
            "text",
            "content",
        ):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, list):
                joined = "\n".join(str(part).strip() for part in value if str(part).strip()).strip()
                if joined:
                    return joined

        # Sometimes nested under `data`.
        data = payload.get("data")
        if data is not None:
            return extract_transcript_text(data)

    return ""


def parse_source_json(source_json_path: Path) -> List[Dict[str, Any]]:
    try:
        payload = json.loads(source_json_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FathomExporterError(f"Source JSON file not found: {source_json_path}") from exc
    except json.JSONDecodeError as exc:
        raise FathomExporterError(f"Source JSON file is not valid JSON: {source_json_path}") from exc

    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise FathomExporterError(
            f"Expected an 'items' list in source JSON file: {source_json_path}"
        )

    return [item for item in items if isinstance(item, dict)]


def extract_participants(item: Dict[str, Any]) -> List[str]:
    participants: List[str] = []
    invitees = item.get("calendar_invitees")
    if isinstance(invitees, list):
        for person in invitees:
            if not isinstance(person, dict):
                continue
            name = (person.get("name") or "").strip()
            email = (person.get("email") or "").strip()
            if name:
                participants.append(name)
            elif email:
                participants.append(email)

    if not participants and isinstance(item.get("recorded_by"), dict):
        recorder = item["recorded_by"]
        fallback_name = (recorder.get("name") or recorder.get("email") or "").strip()
        if fallback_name:
            participants.append(fallback_name)

    deduped: List[str] = []
    seen = set()
    for participant in participants:
        if participant not in seen:
            seen.add(participant)
            deduped.append(participant)
    return deduped


def iter_records_from_source(
    items: List[Dict[str, Any]],
    client: FathomClient,
) -> Iterable[TranscriptRecord]:
    for index, item in enumerate(items, start=1):
        recording_id = item.get("recording_id")
        if not recording_id:
            print(f"[WARN] Skipping item #{index}: missing recording_id")
            continue

        title = (
            item.get("meeting_title")
            or item.get("title")
            or item.get("name")
            or f"Untitled Meeting {recording_id}"
        )
        raw_date = (
            item.get("recording_start_time")
            or item.get("created_at")
            or item.get("scheduled_start_time")
            or ""
        )
        participants = extract_participants(item)

        transcript = client.fetch_transcript(str(recording_id))

        yield TranscriptRecord(
            record_id=str(recording_id),
            title=str(title).strip(),
            date=normalize_date(str(raw_date)),
            transcript=transcript,
            participants=participants,
        )
        time.sleep(0.05)


def normalize_date(raw: str) -> str:
    if not raw:
        return "unknown-date"

    normalized = raw.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        return raw[:10]


def safe_filename(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = value.strip("-")
    return value or "untitled"


def export_records(records: Iterable[TranscriptRecord], output_dir: Path) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "index.csv"

    exported = 0
    with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=["id", "date", "title", "participants", "file"])
        writer.writeheader()

        for record in records:
            filename = f"{record.date}_{safe_filename(record.title)}_{safe_filename(record.record_id)}.md"
            file_path = output_dir / filename
            participant_line = ", ".join(record.participants) if record.participants else "Unknown"

            body = (
                f"# {record.title}\n\n"
                f"- **Date:** {record.date}\n"
                f"- **ID:** {record.record_id}\n"
                f"- **Participants:** {participant_line}\n\n"
                f"## Transcript\n\n"
                f"{record.transcript}\n"
            )

            file_path.write_text(body, encoding="utf-8")
            writer.writerow(
                {
                    "id": record.record_id,
                    "date": record.date,
                    "title": record.title,
                    "participants": participant_line,
                    "file": filename,
                }
            )
            exported += 1
            print(f"[INFO] Exported: {file_path}")

    print(f"[INFO] Wrote CSV index: {csv_path}")
    return exported


def export_records_streaming(items: List[Dict[str, Any]], client: FathomClient, output_dir: Path) -> int:
    """Fetch + export transcripts one at a time so partial progress is preserved on failure."""
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "index.csv"
    exported = 0
    total_items = len(items)

    with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=["id", "date", "title", "participants", "file"])
        writer.writeheader()

        for record in iter_records_from_source(items, client=client):
            filename = f"{record.date}_{safe_filename(record.title)}_{safe_filename(record.record_id)}.md"
            file_path = output_dir / filename
            participant_line = ", ".join(record.participants) if record.participants else "Unknown"
            body = (
                f"# {record.title}\n\n"
                f"- **Date:** {record.date}\n"
                f"- **ID:** {record.record_id}\n"
                f"- **Participants:** {participant_line}\n\n"
                f"## Transcript\n\n"
                f"{record.transcript}\n"
            )

            file_path.write_text(body, encoding="utf-8")
            writer.writerow(
                {
                    "id": record.record_id,
                    "date": record.date,
                    "title": record.title,
                    "participants": participant_line,
                    "file": filename,
                }
            )
            csv_file.flush()

            exported += 1
            print(f"[INFO] Exported {exported}/{total_items}: {file_path}")

    print(f"[INFO] Wrote CSV index: {csv_path}")
    return exported


def load_env(name: str, required: bool = False, default: Optional[str] = None) -> str:
    value = os.environ.get(name, default)
    if required and not value:
        raise FathomExporterError(
            f"Missing required environment variable: {name}. "
            f"Please set it in your terminal before running this script."
        )
    return value or ""


def main() -> int:
    print("[INFO] Starting Fathom transcript export...")
    try:
        api_key = load_env("FATHOM_API_KEY", required=True)
        base_url = load_env("FATHOM_API_BASE_URL", default="https://api.fathom.ai")
        output_dir = Path(load_env("FATHOM_OUTPUT_DIR", default="TRANSCRIPTS"))
        meetings_scope = load_env("FATHOM_MEETINGS_DOMAINS_TYPE", default="all")
        page_limit_raw = load_env("FATHOM_MEETINGS_PAGE_LIMIT", default="")
        page_limit = int(page_limit_raw) if page_limit_raw.strip() else None

        print(f"[INFO] Base URL: {base_url}")
        print(f"[INFO] Output directory: {output_dir.resolve()}")
        print(f"[INFO] Meetings filter (calendar_invitees_domains_type): {meetings_scope}")
        if page_limit:
            print(f"[INFO] Meetings page limit override: {page_limit}")

        client = FathomClient(api_key=api_key, base_url=base_url)
        items = client.fetch_all_meetings(
            calendar_invitees_domains_type=meetings_scope,
            limit=page_limit,
        )
        if not items:
            print("[WARN] No transcript records were found.")
            return 0

        count = export_records_streaming(items, client=client, output_dir=output_dir)
        print(f"[INFO] Done. Exported {count} transcript files.")
        print(
            "[INFO] Export summary: every transcript is written one-by-one as it is fetched, "
            "so partial exports remain available if the script stops early."
        )
        print(f"[INFO] Transcript markdown files: {output_dir.resolve()}")
        print(f"[INFO] CSV index of all exported files: {(output_dir / 'index.csv').resolve()}")
        return 0

    except FathomExporterError as exc:
        print(f"[ERROR] {exc}")
        return 1
    except Exception as exc:  # pragma: no cover
        print(f"[ERROR] Unexpected failure: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
