# Desk

### A distributed multi-agent study platform for AI/ML

**Desk** is not another chatbot wrapped in a pretty shell.  
It’s a full learning product: study paths, checkpoint quizzes, flashcards, daily practice, and progress — powered by a mesh of specialized agents that talk over queues.

Built as a real system: FastAPI microservices, RabbitMQ, Postgres, Redis, React, Docker, CI, and an LLM-judge eval gate.

---

## Why this exists

Most “AI tutors” do one thing: dump text into a thread.

Desk does something different:

1. **Propose a roadmap** before teaching  
2. **Teach one lesson at a time** with a clear Proceed / Continue loop  
3. **Unlock quizzes at checkpoints** in their own tab (never merged into chat)  
4. **Reteach** only what you missed  
5. **Grow flashcards** continuously from lessons  
6. **Practice daily** in an arena where the model picks MCQ / short / code  

It feels like a study coach with a curriculum — not a blank prompt box.

---

## Product tour

| Surface | What it does |
| --- | --- |
| **Path** | Ask to study a topic → full roadmap → Proceed → lessons → Continue |
| **Quiz** | Separate checkpoint quizzes (Quiz 1, Quiz 2, …) with same-tab feedback + reteach |
| **Cards** | Flashcards accumulated from every lesson |
| **Problems** | Arena practice — format chosen by the model; wrong MCQ explains in-tab |
| **Daily** | One sharp concept every day |
| **Progress** | Streaks, quiz scores, topics touched |

### Session flow

```text
“I want to study machine learning”
        │
        ▼
   Full roadmap (lessons + quiz gates)
        │  Proceed
        ▼
   Lesson 1  →  Continue  →  Lesson 2  →  Quiz unlocks
        │
        ▼
   Quiz tab (own session) → miss? reteach on Path → back to Quiz
        │
        ▼
   Cards grow in the background · Progress updates
```

---

## Architecture

Desk is intentionally **multi-agent**, not a single LLM loop.

```text
                 ┌────────────┐
   Browser ─────▶│  Gateway   │◀── WebSocket + REST
   (React/TS)    │  :8000     │
                 └─────┬──────┘
                       │
                 ┌─────▼──────┐
                 │   Router   │  intent classification
                 │   :8001    │
                 └─────┬──────┘
           ┌───────────┼───────────┐
           ▼           ▼           ▼
     Study Agent   Quiz Agent   Progress
       :8002         :8003        :8004
           │           │           │
           └───── RabbitMQ ────────┘
                       │
              Postgres · Redis
```

### Services

| Service | Role |
| --- | --- |
| **Gateway** | SPA host, WebSocket fan-out, arena/daily/ratings HTTP APIs |
| **Router** | Routes study / quiz / progress / flashcard intents (with circuit-breaker fallbacks) |
| **Study agent** | LangGraph tutoring, plan propose/start/advance, reteach, flashcard spawns |
| **Quiz agent** | Structured quiz generation + grading |
| **Progress** | Aggregates streaks, scores, topics |

### Shared library (`shared/agent_shared`)

Config, DB, Rabbit helpers, Redis/session context, idempotency, LLM helpers (LangChain structured output), schemas, ORM models, arena + ratings.

---

## Features

### Learning experience
- Study **path proposals** with lesson + quiz steps  
- **Proceed / Continue** pacing (Antigravity-style roadmap → teach)  
- Checkpoint quizzes as **separate sessions** (not one merged blob)  
- Wrong answers → **reteach** on Path → resume Quiz  
- Markdown-rendered lessons (bold, lists, code)  
- Gemini-style **thinking presence** while agents work  
- Flashcards auto-grown from lessons  
- Star **ratings** on plans, lessons, quizzes, arena, daily  

### Arena & daily
- Daily problem + daily concept  
- LLM picks **mcq / short / code** (user doesn’t configure format)  
- MCQ wrong → explanation in the **same tab**  
- Problem UI parsed into title / problem / hints (not raw LLM paste)  
- Temporary answer persistence across tab switches (sessionStorage)  

### Platform / engineering
- Docker Compose stack (Postgres, Redis, RabbitMQ, agents, Prometheus, Grafana)  
- Alembic migrations  
- Idempotent request handling  
- Circuit breaker + queue-depth degradation in router  
- Prometheus metrics + Grafana dashboard  
- GitHub Actions CI: lint, unit tests, Docker builds, **LLM-judge eval gate**  
- Chaos + load scripts under `scripts/`  
- Eval prompts + judge under `eval/`  

---

## Tech stack

**Frontend:** React 19, TypeScript, Vite  
**Backend:** FastAPI, LangChain / LangGraph, Pydantic  
**Data / messaging:** PostgreSQL, Redis, RabbitMQ  
**Ops:** Docker Compose, Alembic, Prometheus, Grafana, GitHub Actions  

---

## Quick start

```bash
git clone https://github.com/khanak0509/agent-mesh.git
cd agent-mesh
cp .env.example .env
# add OPENAI_API_KEY (or compatible key) to .env

cd infra
docker compose up --build
```

Open **[http://localhost:8000](http://localhost:8000)**

### Frontend hot reload

```bash
# stack must already be running on :8000
cd frontend
npm install
npm run dev
```

→ [http://localhost:5173](http://localhost:5173) (API + WebSocket proxied)

```bash
cd frontend && npm run build   # ships into gateway static/
```

### Useful ports

| Port | What |
| --- | --- |
| `8000` | Desk UI + gateway |
| `15672` | RabbitMQ management |
| `3000` | Grafana |
| `9090` | Prometheus |

---

## Project layout

```text
frontend/                 React + TypeScript app
services/
  gateway/                WS + HTTP + SPA
  router/                 Intent routing
  study-agent/            Plans, lessons, reteach
  quiz-agent/             Generate + grade quizzes
  progress/               Stats aggregation
shared/agent_shared/      Shared libs (LLM, DB, queues, schemas)
migrations/               Alembic
infra/                    Compose, Prometheus, Grafana
eval/                     LLM-judge eval gate
scripts/                  Chaos + load helpers
.github/workflows/        CI
```

---

## Design principles

- **Agents with jobs**, not one mega-prompt  
- **Curriculum before content** — roadmap first, then teach  
- **Quizzes are first-class** — their own tab and history  
- **Human UI** — thinking presence, markdown, no raw dumps  
- **Operable** — compose, metrics, migrations, CI, eval gate  

---

## Status

End-to-end runnable with Docker Compose — agents, queues, UI, metrics, and CI included.

Clone it, `docker compose up --build`, and walk Path → Proceed → Quiz → Cards.

---

<p align="center">
  <b>Desk</b> — study with a path, not a paste.
</p>
