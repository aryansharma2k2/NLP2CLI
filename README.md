# NL2CLI — Natural Language Command Workbench

Convert plain English into inspected, risk-scored shell commands. NL2CLI generates a bash command from your intent, shows a dry-run preview, scores execution risk, and requires deliberate confirmation before anything destructive runs.

[![Demo](https://img.youtube.com/vi/vhcE0R1wASA/maxresdefault.jpg)](https://www.youtube.com/watch?v=vhcE0R1wASA)

**Built with:** Python · Flask · Claude API (Haiku) · Bootstrap 5

## Features

- **Natural language → bash** — powered by the Claude API (Haiku), with a deterministic local fallback when no API key is set
- **Dry-run preview** — read-only commands show real output before you execute; destructive commands show which files would be affected
- **Risk scoring** — every command is classified as low / medium / high with specific findings and safer alternatives
- **High-risk gate** — commands scored high return HTTP 403 unless the user explicitly checks a confirmation box
- **Session history** — persisted to `session.json` across restarts; each entry stores the original intent alongside the command, output, and risk analysis
- **Markdown export** — download your full session as a structured `.md` file
- **Demo chips** — one-click example instructions for instant demos

## Running Locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=your_key_here
python app.py
```

Open `http://localhost:5000`.

Without `ANTHROPIC_API_KEY` the app falls back to deterministic local rules — all UI features still work, commands are just less flexible.

## Running with Docker

```bash
docker build -t nl2cli .
docker run -p 5000:5000 -e ANTHROPIC_API_KEY=your_key_here nl2cli
```

## Running Tests

```bash
pip install -r requirements-dev.txt
pytest
```

## Environment Variables

| Variable | Values | Default |
|---|---|---|
| `ANTHROPIC_API_KEY` | your Anthropic API key | — |
| `NL2CLI_GENERATOR` | `auto`, `fallback` | `auto` |
| `NL2CLI_MODEL_ID` | any Claude model ID | `claude-haiku-4-5-20251001` |

## Architecture

```
app.py          Flask routes and session persistence (load/save session.json)
generators.py   Claude API generation with deterministic fallback rules
safety.py       Command risk scoring, pattern detection, safer-alternative suggestions
preview.py      Dry-run preview — live output for read-only commands, impact estimate for others
commands.py     Shell execution, directory context, command cleanup
```

**Request flow:**

1. `POST /generate` — generates a command via Claude (or fallback), scores risk, returns `{generated_command, analysis, model_status}`
2. `POST /preview` — runs read-only commands safely to show output, or estimates impact for write/delete commands, without executing
3. `POST /execute` — runs the command; returns 403 for high-risk commands unless `confirmed_high_risk` is set
4. `GET /export` — returns the session as a Markdown file download
5. `POST /clear` — wipes in-memory history and deletes `session.json`
