# MCB Tutor — Quick Start

## 0. Prerequisites
- Python 3.11+, Node 20+
- Pinecone account (rotate the key in config.env before use)
- OpenAI, Anthropic, LangSmith API keys
- Neon Postgres connection string
- Google OAuth credentials (console.cloud.google.com, allowed origin: localhost:3000)

## 1. Secrets
```bash
cp .env.example .env
# Fill in all values. Never commit .env.
```

## 2. Install Python deps
```bash
pip install ".[api,ingest]"
```

## 3. Install Node deps
```bash
cd apps/web && npm install
```

## 4. Run DB migrations
```bash
cd apps/api
alembic upgrade head
```

## 5. Ingest one course
Drop your PPTX / DOCX files into `data/mcb102/slides/` and `data/mcb102/handouts/`.
Export Ed Discussion to `data/mcb102/ed_export.json`.

```bash
python -m ingest sync --course mcb102
# verify:
python -m ingest stats --course mcb102
```

## 6. Run backend (dev)
```bash
uvicorn apps.api.main:app --reload --port 8000
```

## 7. Run frontend (dev)
```bash
cd apps/web
npm run dev
```

Open http://localhost:3000.

## 8. Smoke test the agent (no UI)
```python
from apps.api.agent.graph import run_agent

result = run_agent(
    messages=[{"role": "user", "content": "What is the closed-loop model of translation initiation?"}],
    course="mcb102",
    user_id="test",
)
print(result["pedagogy_level"], result["draft"])
```

## 9. Deploy
- FastAPI → Render (infra/render.yaml)
- Next.js → Vercel (connect GitHub repo, set env vars)
- Set NEXTAUTH_URL to your Vercel deployment URL
- Set API_URL env var in Vercel to your Render URL
