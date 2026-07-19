# PE Scraper Agent Group

Operate the PE Scraper through its stable CLI. The project directory must be
mounted into this agent group at `/workspace/pe-scraper`, and the command runner
must have access to the Windows host command bridge configured for this group.

## User Intent Mapping

- A CSV or firm-count batch request: run `pescraper run --csv <path> --limit <count>`.
- A firm URL: run `pescraper run --slug <url> --limit 1`, then `pescraper research <url>`.
- A firm name: run `pescraper research <name>`.
- A dataset criteria question: translate explicit criteria to `pescraper ask` options.
- A refresh request: run `pescraper heartbeat`.
- A discovery request: run `pescraper discover`.
- A status request: run `pescraper status` and include failed-job counts.

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
