Desk (study-agent platform)
===========================

React + TypeScript UI, path-based study, Arena practice, Daily concepts, ratings.

Run
1. Fill `.env`
2. `cd infra && docker compose up --build`
3. Open http://localhost:8000

Frontend (local hot reload)
- Stack must be up on :8000
- `cd frontend && npm install && npm run dev` → http://localhost:5173 (proxies API/WS)

Build UI into gateway static
- `cd frontend && npm run build`

Flow
- Path: “I want to study X” → plan → Start path → lessons → checkpoint quizzes
- Cards accumulate after lessons
- Arena / Daily for practice + daily concept
- Star ratings on plans, lessons, quizzes, arena problems, daily concepts

Ops
- RabbitMQ :15672 · Grafana :3000
- Scripts under `scripts/` · eval under `eval/`
