#!/usr/bin/env python3
"""Fathom transcript exporter.

This script fetches transcript-like records from the Fathom API and exports each
record to a local Markdown file with title/date metadata.

It intentionally uses only Python's standard library so it can run on a Mac
without extra CLI tools or third-party package installs.
"""

from __future__ import annotations

import csv
import json
import os
import re
import sys
import time
from dataclasses import dataclass
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


class FathomExporterError(Exception):
    """Custom error type so failures are clear and beginner-friendly."""


class FathomClient:
    """Minimal API client for listing transcript-like objects from Fathom."""

    def __init__(self, api_key: str, base_url: str, page_size: int = 50, timeout: int = 30):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.page_size = page_size
        self.timeout = timeout

    def _build_request(self, endpoint: str, query: Optional[Dict[str, Any]] = None) -> Request:
        query_string = f"?{urlencode(query)}" if query else ""
        url = f"{self.base_url}/{endpoint.lstrip('/')}" + query_string
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "User-Agent": "fathom-exporter/1.0",
        }
        print(f"[INFO] Requesting: {url}")
        return Request(url, headers=headers, method="GET")

    def _get_json(self, endpoint: str, query: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        request = self._build_request(endpoint, query=query)
        try:
            with urlopen(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8")
                print(f"[INFO] Response status: {response.status}, bytes: {len(body)}")
                return json.loads(body)
        except HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise FathomExporterError(
                f"API request failed with HTTP {exc.code} for endpoint '{endpoint}'.\n"
                f"Response body: {details}"
            ) from exc
        except URLError as exc:
            raise FathomExporterError(f"Network error while calling endpoint '{endpoint}': {exc}") from exc
        except json.JSONDecodeError as exc:
            raise FathomExporterError(
                f"API returned invalid JSON for endpoint '{endpoint}'."
            ) from exc

    def fetch_all_records(self) -> List[TranscriptRecord]:
        """Try common transcript endpoints and normalize returned records."""
        candidate_endpoints = [
            "v1/transcripts",
            "v1/calls",
            "v1/meetings",
        ]

        for endpoint in candidate_endpoints:
            print(f"[INFO] Trying endpoint: {endpoint}")
            records = self._fetch_paginated(endpoint)
            if records:
                print(f"[INFO] Successfully found {len(records)} transcript records at '{endpoint}'.")
                return records
            print(f"[INFO] Endpoint '{endpoint}' returned no transcript records.")

        raise FathomExporterError(
            "Could not find transcript records using built-in endpoints. "
            "Please update the endpoint list in `FathomClient.fetch_all_records` to match your account/API version."
        )

    def _fetch_paginated(self, endpoint: str) -> List[TranscriptRecord]:
        records: List[TranscriptRecord] = []
        page = 1
        cursor: Optional[str] = None

        while True:
            params: Dict[str, Any] = {"limit": self.page_size, "page": page}
            if cursor:
                params["cursor"] = cursor

            payload = self._get_json(endpoint, query=params)
            raw_items = self._extract_item_list(payload)
            normalized = [normalize_record(item) for item in raw_items]
            normalized = [item for item in normalized if item is not None]

            print(
                f"[INFO] Parsed page {page} from '{endpoint}' -> "
                f"{len(raw_items)} raw items, {len(normalized)} transcript-like items"
            )
            records.extend(normalized)

            cursor = payload.get("next_cursor") or payload.get("nextCursor")
            has_more = bool(payload.get("has_more") or payload.get("hasMore") or cursor)

            if not has_more:
                break

            page += 1
            time.sleep(0.1)

        return records

    @staticmethod
    def _extract_item_list(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]

        for key in ("items", "data", "results", "meetings", "calls", "transcripts"):
            maybe_items = payload.get(key)
            if isinstance(maybe_items, list):
                return [item for item in maybe_items if isinstance(item, dict)]

        if isinstance(payload.get("data"), dict):
            data_obj = payload["data"]
            for key in ("items", "results", "meetings", "calls", "transcripts"):
                maybe_items = data_obj.get(key)
                if isinstance(maybe_items, list):
                    return [item for item in maybe_items if isinstance(item, dict)]

        return []


def normalize_record(item: Dict[str, Any]) -> Optional[TranscriptRecord]:
    """Convert many possible API field names into one normalized structure."""
    record_id = (
        item.get("id")
        or item.get("meeting_id")
        or item.get("meetingId")
        or item.get("call_id")
        or item.get("callId")
    )

    transcript = (
        item.get("transcript")
        or item.get("transcript_text")
        or item.get("transcriptText")
        or item.get("content")
        or ""
    )

    if isinstance(transcript, list):
        transcript = "\n".join(str(part) for part in transcript)

    if not record_id or not str(transcript).strip():
        return None

    title = (
        item.get("title")
        or item.get("name")
        or item.get("meeting_title")
        or item.get("meetingTitle")
        or f"Untitled Meeting {record_id}"
    )

    raw_date = (
        item.get("date")
        or item.get("created_at")
        or item.get("createdAt")
        or item.get("started_at")
        or item.get("startedAt")
        or ""
    )

    formatted_date = normalize_date(str(raw_date))
    return TranscriptRecord(
        record_id=str(record_id),
        title=str(title).strip(),
        date=formatted_date,
        transcript=str(transcript).strip(),
    )


def normalize_date(raw: str) -> str:
    if not raw:
        return "unknown-date"

    normalized = raw.replace("Z", "+00:00")
    for parser in (datetime.fromisoformat,):
        try:
            dt = parser(normalized)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

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
        writer = csv.DictWriter(csv_file, fieldnames=["id", "date", "title", "file"])
        writer.writeheader()

        for record in records:
            filename = f"{record.date}_{safe_filename(record.title)}_{safe_filename(record.record_id)}.md"
            file_path = output_dir / filename

            body = (
                f"# {record.title}\n\n"
                f"- **Date:** {record.date}\n"
                f"- **ID:** {record.record_id}\n\n"
                f"## Transcript\n\n"
                f"{record.transcript}\n"
            )

            file_path.write_text(body, encoding="utf-8")
            writer.writerow(
                {
                    "id": record.record_id,
                    "date": record.date,
                    "title": record.title,
                    "file": filename,
                }
            )
            exported += 1
            print(f"[INFO] Exported: {file_path}")

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
        output_dir = Path(load_env("FATHOM_OUTPUT_DIR", default="exports"))
        page_size_raw = load_env("FATHOM_PAGE_SIZE", default="50")
        page_size = int(page_size_raw)

        print(f"[INFO] Base URL: {base_url}")
        print(f"[INFO] Output directory: {output_dir.resolve()}")
        print(f"[INFO] Page size: {page_size}")

        client = FathomClient(api_key=api_key, base_url=base_url, page_size=page_size)
        records = client.fetch_all_records()

        if not records:
            print("[WARN] No transcript records were found.")
            return 0

        count = export_records(records, output_dir=output_dir)
        print(f"[INFO] Done. Exported {count} transcript files.")
        return 0

    except ValueError as exc:
        print(f"[ERROR] Invalid numeric config: {exc}")
        return 1
    except FathomExporterError as exc:
        print(f"[ERROR] {exc}")
        return 1
    except Exception as exc:  # pragma: no cover
        print(f"[ERROR] Unexpected failure: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
