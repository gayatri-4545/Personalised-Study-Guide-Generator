# Personalized Study Guide Generator

Agentic RAG app that turns a topic + learning goals + time budget into a
personalized bundle of study materials (guide, flashcards, quiz, interview
questions, revision notes, practical exercises, cheat sheet), grounded in a
textbook knowledge base, with weak/strong topic tracking over time.

See `personalized-study-guide-generator-spec.md` (from the planning phase)
for the full architecture rationale.

## Project Structure

```
study-guide-generator/
├── .env.example              # copy to .env and fill in
├── config/
│   └── settings.py           # single source of truth for all config
├── knowledge_base/           # textbook PDFs, organized by subject
│   ├── Machine_Learning/
│   ├── Deep_Learning/
│   └── NLP/
├── ingestion/
│   └── ingest.py             # PDF -> chunks -> embeddings -> Qdrant
├── backend/
│   ├── main.py                # FastAPI app entrypoint
│   ├── api/
│   │   ├── routes.py          # all endpoints
│   │   └── schemas.py         # request/response models
│   ├── agent/                 # LangGraph pipeline
│   │   ├── state.py
│   │   ├── prompts.py
│   │   ├── llm.py
│   │   ├── nodes.py            # understand/plan/retrieve/evaluate/summarize
│   │   ├── generators.py       # multi-output generation + quality check
│   │   └── graph.py            # StateGraph wiring
│   ├── db/
│   │   ├── mongodb.py
│   │   └── qdrant_client.py
│   └── services/
│       └── progress.py         # weak/strong topic scoring
└── frontend/
    └── app.py                  # Streamlit UI
```

## Setup

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env            # then fill in OPENAI_API_KEY etc.
```

Start MongoDB and Qdrant (e.g. via Docker):

```bash
docker run -d -p 27017:27017 mongo
docker run -d -p 6333:6333 qdrant/qdrant
```

## 1. Ingest your knowledge base

Add textbook PDFs to `knowledge_base/<Subject>/`, then:

```bash
python ingestion/ingest.py
```

## 2. Run the backend

```bash
uvicorn backend.main:app --reload --port 8000
```

## 3. Run the frontend

```bash
streamlit run frontend/app.py
```

## Status / Known Simplifications (v1 scaffold)

- Multi-output generation runs sequentially inside one `generate_outputs` node,
  not as parallel LangGraph nodes — simpler to reason about first; split into
  per-type nodes with `langgraph.types.Send` later if latency matters.
- `chapter` detection in ingestion uses PDF bookmarks when present, else a
  font-size heuristic — spot-check the printed subtopic list after your first
  ingestion run.
- No auth/user-signup flow yet — `user_id` is passed in freely by the frontend.
- No automated tests yet.
