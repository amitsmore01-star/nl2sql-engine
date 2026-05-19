# nl2sql-engine

Converts natural language queries into deterministic, validated SQL `SELECT` statements.

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

### CLI
```bash
python main.py query "give me customer name for customer ASA in ABC"
python main.py query "give me customers" --app-id ABC_app
python main.py query "give me customers" --output json
```

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
