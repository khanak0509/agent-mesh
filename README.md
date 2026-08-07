# Desk

**Learn AI/ML like a path — not a chat dump.**

Desk is a multi-agent study workspace. You pick a topic. It builds a full roadmap. Lessons unlock step by step. Quizzes appear at checkpoints. Flashcards pile up as you go. Daily practice keeps you sharp.

---

## Why Desk

Most AI tutors dump a wall of text and hope you remember it. Desk treats learning as a product:

- **Roadmap first** — see the whole journey before you start
- **Proceed at your pace** — one lesson, then Continue
- **Real checkpoints** — quizzes live in their own tab, not mashed into chat
- **Practice arena** — MCQ, short answer, or code (the model chooses)
- **Daily concept** — one sharp idea every day

---

## What’s inside

| Space | What you get |
| --- | --- |
| **Path** | Study plans, lessons, reteach when you miss a quiz |
| **Quiz** | Separate checkpoint quizzes — never merged |
| **Cards** | Flashcards that grow from every lesson |
| **Problems** | Arena practice with same-tab feedback |
| **Daily** | One concept to keep the streak alive |
| **Progress** | Streaks, scores, topics you’ve touched |

Under the hood it’s a small mesh of agents (router, study, quiz, progress) talking over queues — so each job stays focused instead of one giant prompt.

---

## Try it locally

**1. Env**

```bash
cp .env.example .env
# put your OPENAI_API_KEY in .env
```

**2. Run the stack**

```bash
cd infra
docker compose up --build
```

**3. Open Desk**

[http://localhost:8000](http://localhost:8000)

That’s it. Start with Path → *“I want to study machine learning”* → review the roadmap → **Proceed**.

---

## Frontend (hot reload)

With the stack already up on `:8000`:

```bash
cd frontend
npm install
npm run dev
```

→ [http://localhost:5173](http://localhost:5173) (API + WebSocket proxied)

Ship UI into the gateway:

```bash
cd frontend && npm run build
```

---

## How a session feels

1. Ask to study something  
2. Get a **full roadmap** (lessons + quiz checkpoints)  
3. Hit **Proceed** — teaching starts  
4. **Continue** after each lesson  
5. When a quiz unlocks, open **Quiz** and finish it  
6. Cards collect in the background — review anytime  

Miss a question? Desk reteaches that idea on Path, then you jump back to the quiz.

---

## Stack at a glance

React + TypeScript UI · FastAPI agents · RabbitMQ · Postgres · Redis · Docker Compose

Ops extras (optional while developing): RabbitMQ UI `:15672` · Grafana `:3000`

---

Built to feel calm, clear, and actually usable — a study product, not a demo dump.
