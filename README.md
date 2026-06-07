# nl2sql-engine

Converts natural language queries into deterministic, validated SQL `SELECT` statements.

---

## Project Status

Under active development. Phase 1 is a deterministic, schema-driven pipeline; Phase 2 shifts toward an **agentic** architecture where the LLM owns join reasoning and self-correction while the engine owns schema validation and rule enforcement.

- **Phase 1 (current)** — schema-driven NL→SQL over a REST API: app/table/column resolution, automatic joins, business rules, record versioning, and a deterministic SQL builder, with four pluggable LLM providers and modular tool endpoints. Generates validated SQL (optional execution is a Phase 2 capability).
- **Phase 2 (planned)** — agent loop with LLM tool-calling and self-correction; async runtime; conversation memory and multi-turn queries; in-SQL aggregation/sorting; schema-aware RAG with embeddings; and an MCP server wrapper. **Optional** SQL execution against a read-only database (requires database infrastructure) feeds runtime errors back to the agent for self-correction.
- **Phase 3 (planned)** — Docker packaging, background log-rotation, and extended human + automated feedback loops.

> The CLI (`main.py`) is currently a scaffold; the API is the working entry point.

---

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — full architecture: pipeline, LLM layer, deterministic validator, SQL builder, API, and testing strategy.
- [docs/DECISIONS.md](docs/DECISIONS.md) — log of significant engineering decisions and their rationale, by component.

---

## Setup

### 1. Clone the repo
```bash
git clone <repo-url>
cd nl2sql-engine
```

### 2. Create a virtual environment
```bash
python -m venv .venv
.venv\Scripts\activate      # Windows
source .venv/bin/activate   # Mac/Linux
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure environment
```bash
copy .env.example .env      # Windows
cp .env.example .env        # Mac/Linux
# Edit .env and fill in your values
```

---

## Run

### API
```bash
uvicorn src.api.app:app --reload --port 8000
```

---

## Test
```bash
pytest
pytest -v
pytest tests/path/to/test_file.py -v
```

---

## Project Structure

```
nl2sql-engine/
├── main.py               # CLI entry point
├── requirements.txt
├── .env                  # Secrets (never commit)
├── .env.example          # Safe template
├── config/               # YAML config files
├── docs/                 # Architecture documentation
├── schemas/              # App schema JSON files
├── logs/                 # Runtime logs (gitignored)
├── src/                  # All source code
└── tests/                # Mirrors src/ structure
```

---

## Configuration

Set `LLM_PROVIDER` in `.env` to switch providers:

| Value | Provider |
|---|---|
| `mock` | Mock (tests + dev) |
| `openai` | OpenAI GPT-4o-mini |
| `azure_openai` | Azure OpenAI |
| `anthropic` | Anthropic Claude Sonnet |
