# PE Scraper

Build and maintain a structured dataset of US private equity firms' investment criteria with a local crawler, a local language model, and no paid extraction API.

PE Scraper turns a list of firm websites into a queryable SQLite database and polished CSV/Excel exports. It uses Crawl4AI to find and clean relevant pages, Ollama's `qwen3:4b` to extract structured criteria, and code-computed confidence and provenance to flag results that need human review.

> **Supported environment:** Windows 11 with PowerShell. Docker and NanoClaw are optional.

## What it collects

Each firm is stored in a fixed 24-column schema covering:

- Firm identity, location, website, and US investment focus
- Revenue, EBITDA, enterprise value, and check-size ranges
- Deal types, sectors, AUM, activity, last deal, and fund name
- Confidence, review status, last-checked time, and lifecycle status

The system preserves `null` when a criterion cannot be found. It does not invent a value just to fill a column.

## How it works

```text
A CSV of URLs, or a single URL
        |
        v
Crawl the site and pull out the pages that matter
        |
        v
Clean up the page text
        |
        v
A local AI reads it and pulls out the investment criteria
        |
        v
Score confidence, flag anything shaky, save it
        |
        v
Export to CSV and a styled Excel file
```

The crawl and extraction layers are cached, queue jobs are committed one firm at a time, and a failed firm does not stop the rest of a batch.

## Quick start

### 1. Install the prerequisites

Required:

| Tool | Requirement | Purpose |
|---|---:|---|
| Git | Current version | Clone the repository |
| Python | 3.11 or 3.12 | Run the pipeline; `.python-version` selects 3.11 |
| [`uv`](https://docs.astral.sh/uv/getting-started/installation/) | Current version | Install locked dependencies and run commands |
| [Ollama for Windows](https://docs.ollama.com/windows) | Current version | Serve the local extraction model |
| `qwen3:4b` | Ollama model | Perform structured extraction |

Optional:

| Tool | Needed for |
|---|---|
| Docker Desktop | Self-hosted SearXNG discovery |
| NanoClaw v2 in WSL2 | Chat-driven operation and agent orchestration |

Install `uv` from PowerShell if it is not already available:

```powershell
winget install --id=astral-sh.uv -e
```

Install Ollama with its Windows installer, launch the Ollama application, and keep it running while PE Scraper is working.

### 2. Clone and install PE Scraper

```powershell
git clone https://github.com/Metdez/PE-Scraper.git
Set-Location PE-Scraper

uv sync
uv run crawl4ai-setup
ollama pull qwen3:4b
```

`uv sync` creates `.venv` and installs the versions locked in `uv.lock`. `crawl4ai-setup` installs and checks the Chromium runtime used for JavaScript-rendered sites.

### 3. Verify the environment

```powershell
uv run pescraper doctor
```

The command checks three independent seams:

- `runtime`: supported Python, Windows Proactor event loop, and UTF-8 output
- `ollama`: a schema-constrained `qwen3:4b` round trip on `localhost:11434`
- `crawl4ai`: the Crawl4AI diagnostic plus a real headless Chromium launch

Do not start a production batch until all three lines are `GREEN`.

### 4. Run the included Capital IQ batch

The repository's working input is `capiq_test.csv`. It contains 472 Capital IQ rows; 459 currently include a website that can be queued for crawling.

Start by processing one firm:

```powershell
uv run pescraper run --csv capiq_test.csv --limit 1
```

This imports the entire CSV into SQLite, queues every available website, and processes at most one queued firm. Increase the limit only after the first result looks healthy:

```powershell
uv run pescraper run --limit 10
uv run pescraper status
```

To inspect a stored record and export the dataset:

```powershell
uv run pescraper research "Firm Name"
uv run pescraper export
```

The default export files are:

- `data/exports/firms.csv` — UTF-8 CSV
- `data/exports/firms.xlsx` — styled workbook with review highlighting and a summary sheet

## Common workflows

### Research one URL immediately

```powershell
uv run pescraper run-firm https://www.example-firm.com
```

This bypasses the queue and runs the complete crawl, extraction, confidence, merge, persistence, and provenance path for one firm.

### Seed a CSV and process a bounded batch

```powershell
uv run pescraper run --csv capiq_test.csv --limit 5
```

Recognized Capital IQ identity headers include `Entity Name`, `Web Address`, and `Sector Emphasis`. Bare web addresses are normalized to HTTPS. Generic headers such as `Firm Name`, `Website`, `EBITDA Range`, and `Check Size` are also supported.

Useful variants:

```powershell
# Queue one urgent URL and process one job
uv run pescraper run --slug https://www.example-firm.com --limit 1

# Show queue counts without processing
uv run pescraper run --summary

# Process jobs already in the queue
uv run pescraper run --limit 10
```

### Query the stored dataset

```powershell
# Find one firm by name or URL
uv run pescraper research "A&M Capital"

# Find firms matching structured criteria
uv run pescraper ask --ebitda-min 5 --ebitda-max 50
uv run pescraper ask --deal-type Buyout --sector Healthcare
```

Multiple `ask` filters are combined.

### Export to another location

Pass a path without a file extension; PE Scraper writes both `.csv` and `.xlsx`:

```powershell
uv run pescraper export --output C:\PE-Exports\firms
```

### Check status

```powershell
uv run pescraper status
```

The JSON response separates queue job counts from firm lifecycle counts. Pay attention to `failed`, `in_progress`, and `needs_review` instead of reporting only completed firms.

### Run the accuracy benchmark

```powershell
uv run pescraper benchmark tests/fixtures/benchmark.jsonl
```

The benchmark prints per-field accuracy for the hand-verified JSONL fixture.

## Data and configuration

### SQLite database

The source of truth is `data/pipeline.db`. SQLite runs in WAL mode with foreign keys and a busy timeout so the queue and readers can operate safely together.

Set `PESCRAPER_DB` **before** a command to use a different database:

```powershell
$env:PESCRAPER_DB = "C:\PE-Data\pipeline.db"
uv run pescraper init-db
uv run pescraper status
```

Remove the environment variable to return to the default:

```powershell
Remove-Item Env:PESCRAPER_DB
```

### Confidence and provenance

PE Scraper computes confidence in code after extraction. Low-confidence records, records without core numeric criteria, and seed/extraction conflicts are marked `needs_review`.

Extracted values are stored with supporting quotes, source-page URLs, prompt versions, model names, and content hashes. A missing or unmatched source is retained as an explicit provenance gap rather than silently presented as verified.

### Cache behavior

Page and extraction caches live in SQLite. Re-running an unchanged site can reuse prior work, while prompt-version and model changes naturally invalidate extraction-cache entries.

## Optional: discover firms with SearXNG

The checked-in SearXNG configuration exposes a JSON search endpoint on `127.0.0.1:8080` only.

Start it with Docker Desktop running:

```powershell
docker compose -f integrations/searxng/docker-compose.yml up -d

# Confirm that JSON search works
Invoke-RestMethod "http://127.0.0.1:8080/search?q=private%20equity&format=json"
```

Discover and queue firms, then process a bounded batch:

```powershell
uv run pescraper discover
uv run pescraper status
uv run pescraper run --limit 10
```

Use a more specific query when needed:

```powershell
uv run pescraper discover --query "US healthcare private equity firm investment criteria"
```

Stop the local service with:

```powershell
docker compose -f integrations/searxng/docker-compose.yml down
```

The bundled `secret_key` is for localhost-only development. Change it before exposing SearXNG beyond the local machine.

## Optional: unattended heartbeats

`heartbeat` queues firms that have never been checked or have become stale, processes queued work, logs firm failures to `data/heartbeat.log`, and exits without model work when there is nothing to do.

Run it manually:

```powershell
uv run pescraper heartbeat --limit 5
```

Install the bundled Windows Scheduled Task, which runs every 15 minutes by default:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/install-heartbeat.ps1
```

Choose another interval or task name:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/install-heartbeat.ps1 `
  -TaskName "PE Scraper Heartbeat" `
  -EveryMinutes 30
```

The task uses the current repository path and the installed `uv` executable, so reinstall it after moving the repository.

## Optional: connect NanoClaw v2

NanoClaw is an orchestration layer, not the scraper runtime. The Python pipeline, Chromium, SQLite, and Ollama stay on Windows; the NanoClaw container calls an authenticated localhost bridge.

The integration files are in `integrations/nanoclaw/pe-scraper/`.

### 1. Create the bridge token on Windows

Run once in PowerShell:

```powershell
$stateDir = Join-Path $env:LOCALAPPDATA "PE-Scraper"
New-Item -ItemType Directory -Force -Path $stateDir | Out-Null

$bytes = New-Object byte[] 32
[Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
$token = [BitConverter]::ToString($bytes).Replace("-", "").ToLowerInvariant()
$token | Set-Content -NoNewline -Encoding ascii `
  (Join-Path $stateDir "nanoclaw-bridge.token")
```

Start and check the bridge:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start-nanoclaw-bridge.ps1
Invoke-RestMethod http://127.0.0.1:8765/healthz
```

The bridge accepts only a fixed command allowlist, validates argument sizes, translates `/workspace/extra/pe-scraper/...` paths back to this checkout, and applies a four-hour command timeout.

### 2. Prepare a dedicated NanoClaw agent group in WSL2

From the NanoClaw v2 repository, set these paths for your machine:

```bash
PE_ROOT="/mnt/c/Users/John Doe/Desktop/PE Scraper"
GROUP_DIR="$HOME/nanoclaw/nanoclaw-v2/groups/<your-pe-agent-folder>"

cp "$PE_ROOT/integrations/nanoclaw/pe-scraper/CLAUDE.md" \
  "$GROUP_DIR/instructions.prepend.md"
cp "$PE_ROOT/integrations/nanoclaw/pe-scraper/run-pescraper.sh" "$GROUP_DIR/"
cp "$PE_ROOT/integrations/nanoclaw/pe-scraper/run-pescraper.mjs" "$GROUP_DIR/"
cp "/mnt/c/Users/John Doe/AppData/Local/PE-Scraper/nanoclaw-bridge.token" \
  "$GROUP_DIR/.pe-scraper-bridge-token"
chmod +x "$GROUP_DIR/run-pescraper.sh"
```

Use a dedicated group because the first `cp` replaces that group's standing instructions.

### 3. Allow and mount the project

NanoClaw validates extra host mounts against `~/.config/nanoclaw/mount-allowlist.json`. Merge an entry for the parent of this checkout into `allowedRoots`; read-only access is sufficient:

```json
{
  "allowedRoots": [
    {
      "path": "/mnt/c/Users/John Doe/Desktop",
      "allowReadWrite": false,
      "description": "Local PE Scraper checkout"
    }
  ]
}
```

Then add the mount from the NanoClaw host CLI and restart the group:

```bash
pnpm ncl groups list
pnpm ncl groups config add-mount \
  --id <agent-group-id> \
  --host "/mnt/c/Users/John Doe/Desktop/PE Scraper" \
  --container pe-scraper \
  --ro
pnpm ncl groups restart --id <agent-group-id>
```

Inside the agent container, the project appears at `/workspace/extra/pe-scraper` and the wrapper is `/workspace/agent/run-pescraper.sh`.

Test the non-mutating route from the container:

```bash
/workspace/agent/run-pescraper.sh doctor
```

The group instructions map chat requests for batches, firms, dataset questions, discovery, refreshes, and status checks onto the stable CLI.

## Using an AI coding assistant

You can attach the repository folder to Codex, Claude Code, Cursor, or another coding assistant and use this prompt:

```text
Set up and verify this PE Scraper repository on Windows.

Read README.md, pyproject.toml, .claude/CLAUDE.md, and src/pescraper/cli.py
before changing anything. Preserve capiq_test.csv and all existing files under
data/. Use uv, the checked-in lockfile, Ollama qwen3:4b, and Crawl4AI's setup
command. Run pescraper doctor and the automated tests. Use a temporary
PESCRAPER_DB for destructive or experimental checks. Report exact command
output and ask before starting a large crawl. Do not add paid APIs or upload
the Capital IQ data to an external service.
```

> **Data privacy:** Capital IQ exports may be licensed or confidential. If the AI service uploads attachments to a third party, attach the source code without `capiq_test.csv`, `data/`, databases, or exports. A local coding assistant is the safer choice for data-bearing runs.

## Development

Install the locked environment and run the complete test suite:

```powershell
uv sync
uv run pytest
```

Run focused tests while changing a subsystem:

```powershell
uv run pytest tests/test_ingest.py -q
uv run pytest tests/test_cli.py -q
uv run pytest tests/test_crawl.py -q
```

Show the live CLI contract:

```powershell
uv run pescraper --help
uv run pescraper run --help
```

The package uses a `src/` layout, Typer for the CLI, Pydantic for the extraction/data contract, stdlib SQLite as the source of truth, and pytest for tests.

## Troubleshooting

### `doctor` reports Ollama as `RED`

Confirm the Windows Ollama application is running and the model is installed:

```powershell
ollama list
ollama pull qwen3:4b
```

PE Scraper expects Ollama on `localhost:11434` and specifically exercises structured JSON output.

### `doctor` reports Crawl4AI as `RED`

Reinstall/check the browser runtime inside the same `uv` environment:

```powershell
uv run crawl4ai-setup
uv run crawl4ai-doctor
```

On Windows, run through `uv run pescraper ...` so the package can apply the Proactor event-loop and UTF-8 runtime settings before Crawl4AI starts.

### The Capital IQ CSV imports zero firms

Use the current checkout and verify the file is actually CSV, not an Excel workbook renamed to `.csv`:

```powershell
Get-Item .\capiq_test.csv
uv run pytest tests/test_ingest.py -k capital_iq -q
```

The importer supports the UTF-8 BOM, multiline Capital IQ headers, `Entity Name`, `Web Address`, and bare-domain normalization used by the included file.

### Discovery returns HTTP 403 or non-JSON output

Use the checked-in `integrations/searxng/settings.yml`. SearXNG must include `json` in `search.formats`; the bundled configuration already does.

### Commands are using the wrong database

`PESCRAPER_DB` is read when the process starts. Set or remove it in the same terminal before invoking `uv run pescraper`.

### A batch reports failures

Run `uv run pescraper status`, inspect the failed-job count, and check `data/heartbeat.log` for unattended-run exceptions. A batch intentionally isolates failures per firm instead of aborting all remaining work.

## Project principles

- Local-first and zero marginal paid-API cost
- Missing facts stay missing
- Every extracted value should be traceable to source evidence
- Weak results are surfaced for review
- SQLite is the durable source of truth; spreadsheets are exports
- Agents orchestrate the deterministic Python pipeline rather than performing extraction in chat
