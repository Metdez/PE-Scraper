# PE Scraper Agent Group

Operate the PE Scraper through its stable CLI. The project directory must be
mounted into this agent group at `/workspace/extra/pe-scraper`. Run commands
through `/workspace/agent/run-pescraper.sh`; it provides the isolated Linux
runtime and routes host services correctly.

## User Intent Mapping

- A CSV or firm-count batch request: run `/workspace/agent/run-pescraper.sh run --csv <path> --limit <count>`.
- A firm URL: run `/workspace/agent/run-pescraper.sh run --slug <url> --limit 1`, then `/workspace/agent/run-pescraper.sh research <url>`.
- A firm name: run `/workspace/agent/run-pescraper.sh research <name>`.
- A dataset criteria question: translate explicit criteria to `/workspace/agent/run-pescraper.sh ask` options.
- A refresh request: run `/workspace/agent/run-pescraper.sh heartbeat`.
- A discovery request: run `/workspace/agent/run-pescraper.sh discover`.
- A status request: run `/workspace/agent/run-pescraper.sh status` and include failed-job counts.

Never invent missing criteria. Report `null` fields as not found and surface
`needs_review`, queue failures, and discovery endpoint errors plainly.

## Scheduled Task

Schedule `uv run pescraper heartbeat` from the project root. Use this gate before
waking an agent:

```powershell
uv run pescraper status | Select-String '"queued": [1-9]|"in_progress": [1-9]'
```

An empty gate result means no chat/model wake is needed. The native Windows task
installed by `scripts/install-heartbeat.ps1` can also run the heartbeat directly.
