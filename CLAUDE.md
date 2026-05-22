# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Token Burner - Flask web app that consumes Alibaba Cloud Bailian API tokens at scale. Targets ¥2000 in 5 days with real-time monitoring.

## Commands

- **Run app:** `python3 app.py` (serves on http://127.0.0.1:5000)
- **Install deps:** `pip3 install --break-system-packages -r requirements.txt`
- **View git log:** `git log --oneline`

## Architecture

- `app.py` — Single Flask backend (~370 lines). Routes: `/`, `/api/config`, `/api/models`, `/api/start`, `/api/stop`, `/api/status`, `/api/events` (SSE), `/api/history`
- `templates/index.html` — Single-page frontend with Chart.js dashboard, dark theme, real-time SSE updates
- `burner.db` — SQLite (auto-created), stores burn_records and config tables

## Key Design Decisions

- Dual provider support: Bailian (DashScope SDK) and DeepSeek (OpenAI-compatible REST API), selected via `state['provider']`
- Provider-agnostic API dispatch via `api_call()` function routing to `call_bailian()` or `call_deepseek()`
- Model pricing in `MODEL_PRICES` dict with prefix-based fallback (models not in dict use `deepseek-*` or `qwen-*` pricing)
- Concurrent request engine with exponential backoff retry (3 retries: 1s, 2s, 4s)
- Runtime model switching (reads `state['model']` on each request batch)
- Auto-stop when target amount reached
- SSE pushes stats every 1 second with running 60s rate window
- SQLite persists history and config across restarts
- Models API falls back to hardcoded list when upstream API unavailable
