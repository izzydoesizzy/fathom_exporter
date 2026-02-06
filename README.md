# Fathom Transcript Exporter (Beginner-Friendly)

Export all of your Fathom transcripts into local files that you can keep, search, and back up.

This project is designed for people with very little coding experience.

## What this does

- Connects to the Fathom API
- Fetches transcript records (with pagination)
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
export FATHOM_API_BASE_URL="https://api.fathom.video"
export FATHOM_OUTPUT_DIR="exports"
export FATHOM_PAGE_SIZE="50"
```

### 3) Run the exporter

```bash
python3 fathom_exporter.py
```

You should see verbose logs like:

- Which endpoint is being called
- How many records are found per page
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

Open `fathom_exporter.py`, find:

- `FathomClient.fetch_all_records`
- `candidate_endpoints = [...]`

Add or update endpoints based on your Fathom API docs.

---

## Run tests

This repo includes tests for key parts:

- transcript normalization
- date formatting
- filename safety
- export file generation

Run them with:

```bash
python3 -m pytest -q
```

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
│   └── test_fathom_exporter.py
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
