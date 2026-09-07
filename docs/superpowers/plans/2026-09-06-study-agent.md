# StudyAgent V1 Implementation Plan

> **For agentic workers:** Execute inline in this session with test checkpoints.

**Goal:** Build a locally runnable StudyAgent V1 slice that covers authenticated knowledge bases, real file ingestion, citation-backed mock RAG chat, study plans, quizzes, mastery, and a usable uni-app-compatible web client.

**Architecture:** FastAPI exposes `/api/v1` JSON APIs backed by SQLAlchemy with SQLite as the zero-credential development default and MySQL-compatible configuration for deployment. AI and vector operations sit behind provider interfaces with deterministic fake providers in DEV_MODE. The frontend is a Vue 3 + TypeScript Vite app using the same API contracts and a mobile-first StudyAgent shell.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, SQLAlchemy, Alembic, JWT-compatible signed tokens, Vue 3, TypeScript, Vite, Pinia, SCSS, Docker Compose.

### Task 1: Bootstrap backend and failing unit tests
- Add backend package, settings, database models, migration, health/auth endpoints, and tests for ownership and mastery.
- Run tests red first, then implement the minimum API and domain behavior.

### Task 2: Knowledge/document/RAG APIs
- Add owned knowledge-base CRUD, secure uploads, text extraction/chunking, deterministic embeddings, citations, conversations, and chat endpoints.
- Verify upload validation, IDOR, citation presence, and insufficient-context behavior.

### Task 3: Plans, quizzes, agent tools
- Add study plan drafts/activation, task completion, quiz generation/submission, wrong-question and mastery updates, and a whitelist-only agent facade.
- Verify answer redaction and duplicate-submit protection.

### Task 4: Frontend and delivery
- Add Vue pages/components, centralized HTTP client and Pinia stores, loading/empty/error states, Docker Compose, CI, `.env.example`, and README.
- Run Python tests, frontend typecheck/build, API smoke flow, and Playwright UI checks.
