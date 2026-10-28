# Personalized Study Guide Generator — Project Spec

**Project Name:** `personalized-study-guide-generator` (working name — rename if you have a product name)

---

## 0. Project Status (update this section as you build)

| Field | Value |
|---|---|
| Current stage | Planning / architecture finalized, no code yet |
| Last updated | 2026-09-23 |
| Next milestone | *(fill in — e.g. "set up FastAPI + LangGraph skeleton")* |
| Blockers / open decisions | Sync vs async multi-output generation (see §9); time-budget capping strategy (see §9) |

> **How to use this file across chats:** Claude does not automatically remember past conversations unless memory is enabled in Settings. Upload this file at the start of a new chat and say "continue from here" (or update Section 0 yourself as you progress) so the conversation picks up from the correct stage instead of starting from scratch.

---

## 1. Project Objective

The **Personalized Study Guide Generator** is an Agentic RAG application. A learner provides a topic, one or more learning goals, their current knowledge level, available time, and preferred learning style. The system retrieves relevant material from an educational knowledge base, plans what to study, checks retrieval quality, and generates **multiple selected output artifacts** (study guide, flashcards, quiz, etc.) — grounded in retrieved content, not free-form LLM generation.

It also tracks the learner over time: what they've studied, how they performed on quizzes, and which subtopics are weak vs. strong — and uses that history to personalize future requests.

The system is explicitly **not**:

```
Question → RAG → LLM → Answer
```

It is:

```
User Profile + Goals → Understand → Plan → Retrieve → Check → Summarize
                     → Generate (multi-mode) → Validate (per mode) → Store → Deliver
```

---

## 2. Technology Stack

| Component | Technology | Purpose |
|---|---|---|
| Frontend | Streamlit | Learner interface |
| Backend | FastAPI | REST API layer |
| Agentic AI | LangGraph | Controls the multi-step, multi-output workflow |
| RAG | LangChain | Document processing and retrieval pipeline |
| Vector DB | Qdrant | Stores embeddings and searchable chunks |
| Application DB | MongoDB | Users, requests, guides, history, progress, quiz attempts |
| LLM | OpenAI / Local LLM | Understanding, planning, summarization, generation |
| Embeddings | OpenAI / HuggingFace | Convert chunks and queries into vectors |
| Reranker | Cross-Encoder | Optional retrieval ranking improvement |
| Validation | Pydantic | Structured input/output per output-mode schema |

No changes from the original stack — the enhancements are workflow and schema changes, not new infrastructure (aside from new MongoDB collections).

---

## 3. High-Level Architecture

```
                                   USER
                                     │
                                     ▼
                            ┌─────────────────┐
                            │    Streamlit    │
                            └────────┬────────┘
                                     │ HTTP
                                     ▼
                            ┌─────────────────┐
                            │     FastAPI     │
                            └────────┬────────┘
                                     │
                                     ▼
                       ┌───────────────────────────┐
                       │      LangGraph Agent       │
                       │                            │
                       │ 1. Query Understanding     │
                       │ 2. Study Planning (goal-   │
                       │    tagged subtopics)       │
                       │ 3. Sub-query Generation    │
                       │ 4. Retrieval               │
                       │ 5. Retrieval Evaluator     │
                       │ 6. Summarization           │
                       │ 7. Multi-Output Generation │◄── fan-out per
                       │    (fan-out)               │    requested mode
                       │ 8. Quality Check (per mode)│
                       │ 9. Aggregate Result        │
                       └───────────┬────────┬───────┘
                                   │        │
                             RAG   │        │ LLM
                                   ▼        ▼
                             ┌────────┐ ┌─────────┐
                             │ Qdrant │ │   LLM   │
                             └───┬────┘ └─────────┘
                                 │
                                 ▼
                          Educational KB


                       ┌────────────────────┐
                       │      MongoDB        │
                       │                      │
                       │ users                │
                       │ study_requests       │
                       │ generated_guides     │
                       │ request_history      │
                       │ agent_execution_hist │
                       │ document_metadata    │
                       │ user_progress   (NEW)│
                       │ quiz_attempts   (NEW)│
                       │ topic_mastery   (NEW)│
                       └──────────────────────┘
```

---

## 4. User Journey

### Step 1 — Learner provides input

```
Topic: CNN

Learning Goal (multi-select):
☑ Understand concepts
☑ Prepare for interview
☐ Prepare for exam
☑ Learn for implementation

Current Knowledge:      Beginner / Intermediate / Advanced
Available Time:         30 min / 1 hour / 3 hours / 1 week
Preferred Learning Style: Conceptual / Examples / Code-heavy / Mixed
Difficulty:              Beginner / Intermediate / Advanced

Generate (multi-select):
☑ Study Guide
☑ Flashcards
☑ Quiz
☑ Interview Questions
☐ Revision Notes
☐ Practical Exercises
☐ Cheat Sheet
```

The learner never needs to understand RAG, agents, or retrieval.

### Step 2 — FastAPI receives the request

```
POST /generate-guide
```

FastAPI validates the payload against a Pydantic model covering the new multi-select and profile fields (see §8).

### Step 3 — Query Understanding

Parses vague input into a structured intent object, now including multiple goals:

```
Subject: Deep Learning
Topic: CNN
Goals: [understand_concepts, prepare_interview, learn_implementation]
Level: Beginner
Style: Mixed
Time budget: 1 hour
```

### Step 4 — Study Planning (goal-tagged)

The plan is no longer a flat topic tree — each subtopic is tagged with which goal(s) it serves, and the tree is pruned to fit the time budget *before* retrieval happens (not truncated after generation):

```
CNN
├── [concepts, interview]  What is CNN / why used for images
├── [concepts]              Convolution, filters, feature maps
├── [interview]             CNN vs RNN, why pooling, receptive field
├── [implementation]        Building a CNN in PyTorch/TF, layer config
└── [exam]                  (skipped — not selected as a goal)
```

### Step 5 — Retrieval (per sub-query)

```
Sub-query → Embedding → Qdrant → Top-K chunks → Optional reranking → Best chunks
```

Unchanged from original design, run once across the full pruned plan — **not** re-run per output mode.

### Step 6 — Retrieval Quality Check

```
Poor retrieval → Refine query → Retrieve again   (MAX_RETRIES = 2 or 3, then fallback)
```

### Step 7 — Summarization

```
Map → Summarize individual groups → Reduce → Combine summaries
```
or
```
Refine → Continuously improve one summary
```

One shared, grounded summary set feeds *all* requested output modes — this keeps a flashcard and the study guide's coverage of the same subtopic consistent with each other.

### Step 8 — Multi-Output Generation (fan-out)

Only the nodes for `outputs_requested` run. Each has its own prompt and Pydantic output schema (see §9).

```
                         Summarized, Grounded Content
        ┌───────────┬───────────┬───────────┬───────────┬───────────┐
        ▼           ▼           ▼           ▼           ▼           ▼
  Study Guide   Flashcards    Quiz     Interview Q   Cheat Sheet  Exercises
```

### Step 9 — Quality Check (per output type)

Each generated artifact is checked against criteria specific to its type (a quiz's answer key correctness is a different check than a guide's structural completeness) — see §9 for detail. Failures trigger refine/regenerate for that mode only, not the whole batch.

### Step 10 — Store and Return

All generated artifacts for the request are stored together under one `request_id`, linked to `guide_id`s per mode. FastAPI returns the full bundle to Streamlit; the learner sees whichever tabs/modes they selected.

### Step 11 — Progress Update (NEW)

If the request included a quiz and the learner submits answers (`POST /quiz/{quiz_id}/submit`), results are written to `quiz_attempts` and roll up into `user_progress` and `topic_mastery_summary` (see §7).

---

## 5. Database Segregation

Unchanged core split, with new MongoDB collections for personalization.

### Qdrant — Knowledge Retrieval

```
Qdrant
├── vector
├── chunk_id
├── document_id
├── page_number
├── subject
├── chapter
└── other retrieval metadata
```

Primary question: *"Which pieces of knowledge are relevant to this query?"*

### MongoDB — Application Data

```
MongoDB
├── users
├── study_requests
├── generated_guides
├── request_history
├── agent_execution_history
├── document_metadata
├── user_progress          (NEW)
├── quiz_attempts          (NEW)
└── topic_mastery_summary  (NEW)
```

Primary question: *"What happened in my application, and what does this learner know?"*

### Relationship

```
MongoDB:  request_id, guide_id, user_id, quiz_id
Qdrant:   document_id, chunk_id
```

Example:

```
MongoDB
request_id = REQ_101
guide_id   = GUIDE_101
quiz_id    = QUIZ_101

Qdrant
document_id = CNN_BOOK_01
chunk_id    = CNN_BOOK_01_CH_23
```

---

## 6. Dataset / Knowledge Base

Unchanged from original design — no traditional ML training data needed, just a well-structured educational document corpus.

```
knowledge_base/
├── Machine_Learning/
│   ├── Regression.pdf
│   ├── Decision_Trees.pdf
│   └── Clustering.pdf
├── Deep_Learning/
│   ├── Neural_Networks.pdf
│   ├── CNN.pdf
│   └── RNN.pdf
└── NLP/
    ├── Transformers.pdf
    ├── Attention.pdf
    └── Embeddings.pdf
```

Sources: open educational textbooks, open courseware (e.g. MIT OCW), OpenStax, your own notes/PDFs. 10–20 well-structured documents (chapters/sections/pages intact) are enough for v1 — structure matters for chunking and source attribution.

---

## 7. User History, Progress & Weak/Strong Topics (NEW)

### New collections

```
user_progress
├── user_id
├── topic
├── subtopic
├── confidence_score     (derived, not user-entered)
├── times_studied
├── last_studied_at
└── status: weak | moderate | strong

quiz_attempts
├── user_id, quiz_id, topic
├── questions_answered[]   { question_id, subtopic, correct: bool }
└── score, timestamp

topic_mastery_summary   (aggregated, updated after each session)
├── user_id
├── strong_topics: []
├── weak_topics: []
└── last_updated
```

### How weak/strong is determined

Not self-reported — inferred from behavioral signals:

- **Quiz/flashcard accuracy**, tracked **per subtopic**, not per topic (a learner can be strong on convolution but weak on architecture — topic-level scoring would hide that).
- **Repetition without improvement** — repeated requests on the same subtopic without quiz score gains is itself a weak-topic signal.
- **Time-decay** — confidence scores should decay slowly (something "mastered" 6 months ago shouldn't stay flagged strong forever). Good candidate for a scheduled job rather than inline logic on each request.

Suggested scoring:

```
confidence_score = weighted_avg(quiz_accuracy, recency, repetition_penalty)

< 0.40           → weak
0.40 – 0.75      → moderate
> 0.75           → strong
```

### Feedback loop into planning

When a returning learner requests a new guide:

- Query Understanding pulls their `topic_mastery_summary`.
- Study Planner can **compress or skip** subtopics they're already strong on.
- Study Planner can **flag prerequisite weak topics** — e.g. "you're weak on backpropagation, which CNN training depends on — include it?"

This is what makes the system "personalized" beyond just the input form — it's personalized based on demonstrated performance, not just stated preference.

---

## 8. Expected Input (updated schema)

```json
{
  "user_id": "USR_001",
  "topic": "Convolutional Neural Networks",
  "learning_goals": ["understand_concepts", "prepare_interview", "learn_implementation"],
  "current_knowledge": "beginner",
  "available_time": "1_hour",
  "learning_style": "mixed",
  "difficulty": "beginner",
  "outputs_requested": ["study_guide", "flashcards", "quiz", "interview_questions"]
}
```

| Field | Type | Notes |
|---|---|---|
| `learning_goals` | list | Multi-select; drives goal-tagged planning (§4 Step 4) |
| `current_knowledge` | enum | beginner / intermediate / advanced |
| `available_time` | enum | 30_min / 1_hour / 3_hours / 1_week — prunes plan **before** retrieval |
| `learning_style` | enum | conceptual / examples / code_heavy / mixed — affects generation prompt, not retrieval |
| `outputs_requested` | list | Drives which fan-out nodes run in Step 8 |

---

## 9. Multi-Output Generation — Output Schemas

Each requested mode gets its own generator node and Pydantic schema, and its own quality check pass (not one shared global check):

```
Study Guide        → sections: objective, prerequisites, overview, key concepts,
                      step-by-step explanation, examples, terms, common mistakes,
                      quick revision, glossary, sources
                      Quality check: goal coverage, grounding, structure

Flashcards         → [{ front, back, topic_tag, source_ref }]
                      Quality check: no duplicate fronts, answer grounded in source

Quiz               → [{ question, options[4], correct_answer, explanation, difficulty }]
                      Quality check: exactly one correct answer, explanation grounded,
                      difficulty matches requested level

Interview Questions → [{ question, ideal_answer_points, follow_up_questions, difficulty }]
                      Quality check: questions match "interview" goal tag coverage

Revision Notes      → condensed, goal-filtered bullet version of the study guide
                      Quality check: no new claims vs. study guide (consistency)

Practical Exercises → [{ problem_statement, hints, solution_approach, code_starter? }]
                      Quality check: solvable from covered material only

Cheat Sheet         → single-page key terms/formulas/diagrams reference
                      Quality check: density/brevity, no unsupported claims
```

**Shared retrieval principle:** all modes are generated from the *same* summarized, grounded content produced once in Step 7 — never re-retrieved per mode. This keeps outputs mutually consistent and avoids wasted retrieval calls.

### Open decisions (still unresolved — revisit before building Step 8/9)

1. **Sync vs. async generation.** Generate all requested modes in one blocking request, or return the study guide immediately and stream flashcards/quiz/etc. asynchronously after? Sync is simpler to build first; async gives a faster perceived response.
2. **Time-budget capping.** Should `available_time` cap *how many output modes* can be requested (e.g. a 30-min request can't reasonably produce 6 artifact types), or only cap the depth/length within each requested mode? Needs a decision before the Study Planner's pruning logic is finalized.

---

## 10. API Endpoints

```
POST   /generate-guide              Accepts full multi-goal, multi-output request
GET    /guide/{guide_id}
GET    /history/{user_id}
GET    /progress/{user_id}          NEW — weak/strong topic summary
GET    /progress/{user_id}/{topic}  NEW — subtopic-level breakdown
POST   /quiz/{quiz_id}/submit       NEW — records quiz attempt, triggers progress update
DELETE /guide/{guide_id}
GET    /health
```

---

## 11. Frontend

Streamlit for v1, unchanged rationale — no need for React unless demonstrating a separate production frontend is a goal.

New UI elements needed vs. the original spec:

- Multi-select checkboxes for `learning_goals` and `outputs_requested`
- Dropdowns for `current_knowledge`, `available_time`, `learning_style`, `difficulty`
- Tabbed output display (one tab per generated mode: Guide / Flashcards / Quiz / etc.)
- Interactive quiz-taking UI that posts to `/quiz/{quiz_id}/submit`
- A "My Progress" page hitting `/progress/{user_id}` — weak/strong topic list, history

```
Browser
   │
   ▼
Streamlit :8501
   │  REST API
   ▼
FastAPI :8000
   │
   ▼
LangGraph
```

---

## 12. System Design

Still no microservices needed for this scope. Modular monolith, same as original:

```
Streamlit
    ↓
FastAPI
    ↓
LangGraph
 ┌──┴──────────────┐
RAG              LLM
 │
Qdrant
 │
Knowledge Base

MongoDB (users, requests, guides, history, progress, quiz_attempts, mastery)
```

Keep components modular (separate modules per LangGraph node, separate service layer for Mongo/Qdrant access) so pieces can become independent services later if needed.

---

## 13. Steps That Can Cause Misleading Output (carried over, still relevant)

1. **Query Understanding** — misreading intent (e.g. "interview prep" ≠ just architecture facts; needs comparisons and common Q&A).
2. **Sub-topic generation** — too few subtopics starve the guide; too many dilute quality. Now compounded by needing to prune per `available_time` *before* retrieval.
3. **Chunking** — bad splits destroy context; needs experimentation on size/overlap.
4. **Retrieval** — semantic similarity ≠ factual relevance; use metadata filtering, top-K tuning, reranking, relevance checks.
5. **Query refinement** — refine and retry on poor retrieval rather than generating on thin context.
6. **Summarization** — must not introduce information absent from source chunks.
7. **Hallucination** — clearly separate source-grounded content from any allowed pedagogical additions (e.g. an illustrative example not in the corpus).
8. **Source attribution** — every section traceable to document/chapter/page/chunk.
9. **Agent loops** — hard `MAX_RETRIES` (2–3) with a defined fallback action.
10. **Prompt injection from documents** — retrieved content is always treated as data, never as instructions to the agent. Especially important once user-uploaded documents are supported.
11. **(NEW) Cross-mode inconsistency** — because all output modes share one summarization pass, a bug in Step 7 propagates to every artifact at once. Worth extra test coverage here specifically.
12. **(NEW) Progress-score gaming/noise** — a learner rushing through a quiz to "finish" shouldn't tank their confidence score as hard as a slow, considered wrong answer might warrant; consider whether response time or attempt patterns should factor in, or keep it simple for v1 and revisit later.

---

## 14. Most Important Engineering Concerns (checklist)

```
✓ Good document ingestion
✓ Good chunking strategy
✓ Correct embeddings
✓ Reliable Qdrant retrieval
✓ Query decomposition (goal-tagged)
✓ Agent state management across fan-out nodes
✓ Retrieval retry logic
✓ Reranking
✓ Grounded generation
✓ Source attribution
✓ Structured output (per output-mode schema)
✓ Quality validation (per output-mode)
✓ MongoDB persistence (incl. progress/mastery collections)
✓ API validation
✓ Error handling
✓ Logging
✓ Retrieval/generation evaluation
✓ Progress-score computation & decay job (NEW)
✓ Time-budget-aware plan pruning (NEW)
```

---

## 15. Core Idea (summary diagram)

```
                       PERSONALIZED STUDY GUIDE GENERATOR
                                     │
                                     ▼
                          USER (profile + goals + time budget)
                                     │
                                     ▼
                                  FASTAPI
                                     │
                                     ▼
                             LANGGRAPH AGENT
                                     │
                ┌────────────┬───────┴────────┬─────────────┐
                ▼            ▼                ▼             ▼
            PLANNING     RETRIEVAL       MULTI-OUTPUT    VALIDATION
           (goal-tagged,      │           GENERATION      (per mode)
            time-pruned)      ▼           (fan-out)
                            QDRANT             │
                              │                ▼
                              ▼          Guide / Flashcards /
                        EDUCATIONAL KB   Quiz / Interview Qs /
                                         Cheat Sheet / Exercises
                                                │
                                                ▼
                                              LLM
                                                │
                                 ┌──────────────┴──────────────┐
                                 ▼                             ▼
                             STREAMLIT                     MONGODB
                             Display                Persistence + Progress
                                                          Tracking
```

**Key differentiator:** the agent doesn't just retrieve-and-answer. It plans across multiple learning goals under a time constraint, retrieves and validates once, fans out into several structurally distinct output artifacts validated independently, and — new in this version — learns from quiz performance over time to personalize future sessions.
