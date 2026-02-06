# Fathom Transcript Exporter (Beginner-Friendly)

Export all of your Fathom transcripts into local files that you can keep, search, and back up.

This project is designed for people with very little coding experience.

## What this does

- Retrieves every meeting from the Fathom meetings API (auto-paginates until `next_cursor` is empty)
- Fetches each transcript from the Fathom External API (`/external/v1/recordings/{id}/transcript`)
- Exports each transcript into a **Markdown (`.md`) file**
- Includes the **title** and **date** in each exported file
- Creates an `index.csv` so you can open a spreadsheet of all exports
- Prints very verbose logs so you can see each step

---

## Requirements

You only need:

1. A Mac terminal
2. Python 3 installed (most Macs already have it)
3. A Fathom API key

Check Python:

```bash
python3 --version
```

---

## Step-by-step setup

### 1) Download this project

If you already cloned the repo, open Terminal and go to this folder.

```bash
cd /path/to/fathom_exporter
```

### 2) Add your Fathom API key

In the same terminal session:

```bash
export FATHOM_API_KEY="paste_your_real_key_here"
```

Optional settings:

```bash
export FATHOM_API_BASE_URL="https://api.fathom.ai"
export FATHOM_OUTPUT_DIR="exports"
export FATHOM_MEETINGS_DOMAINS_TYPE="all"
export FATHOM_MEETINGS_PAGE_LIMIT=""  # optional override for debugging
```

### 3) Run the exporter

```bash
python3 fathom_exporter.py
```

You should see verbose logs like:

- How many meeting pages were fetched from the API
- Which recording ID transcript is being called
- Which files are written

---

## Where your files go

By default, exports are written into:

```text
./exports/
```

Inside that folder you will find:

- One Markdown file per transcript
- `index.csv` with `id`, `date`, `title`, and file name

---

## Troubleshooting

### “Missing required environment variable: FATHOM_API_KEY”

You forgot to set your API key in this terminal session.

### “Could not find transcript records using built-in endpoints”

Fathom API endpoints can vary by account/version.

The script first calls:

- `GET /external/v1/meetings?calendar_invitees_domains_type=all` (and follows `next_cursor`)

Then for each `recording_id` it calls:

- `GET /external/v1/recordings/{recording_id}/transcript`
- Header: `X-Api-Key: <your key>`

---

## Run tests

This repo includes tests for key parts:

- transcript normalization
- date formatting
- filename safety
- export file generation
- optional live DNS/HTTPS connectivity diagnostics

### Quick test run (quiet)

```bash
python3 -m pytest -q
```

### Verbose test run (recommended for understanding behavior)

```bash
python3 -m pytest -vv -s
```

What you will see in verbose mode:

- `[TEST] ...` lines that explain what each unit test is verifying
- assertion messages that explain why a failure happened
- exporter log lines (`[INFO] ...`) when file export tests run

### Optional live connectivity diagnostics

By default, live network tests are skipped because they depend on your internet/proxy/DNS setup.

To enable them:

```bash
export FATHOM_RUN_NETWORK_TESTS="1"
python3 -m pytest -vv -s tests/test_connectivity_diagnostics.py
```

What the connectivity test checks:

- resolves DNS for the configured base URL host
- performs an HTTPS GET request to the base URL
- prints diagnostic details (host, resolved IP, HTTP status)

It uses `FATHOM_API_BASE_URL` if set, otherwise defaults to `https://api.fathom.ai`.

If `pytest` is not installed, use:

```bash
python3 -m pip install pytest
```

---

## Project structure

```text
.
├── fathom_exporter.py
├── tests/
│   ├── test_fathom_exporter.py
│   └── test_connectivity_diagnostics.py
└── README.md
```

---

## Security notes

- Keep your API key private
- Do not commit API keys to GitHub
- Prefer setting keys via environment variables (as shown above)

---

## License

Use/adapt this for your own exports.
