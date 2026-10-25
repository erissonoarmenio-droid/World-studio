# Estúdio W-orld

Servidor do estúdio de influencers de IA para lojas: bot do Telegram, geração de fotos/vídeos/voz/artes e a Central.

- Especificação e mapa: `docs/spec/`
- Plano e tarefas: `tasks/plan.md`, `tasks/todo.md`

## Rodar no computador
```
uv sync
uv run uvicorn app.main:app --reload     # http://localhost:8000/saude
uv run pytest
uv run ruff check . && uv run ruff format --check .
```
Segredos ficam em variáveis de ambiente (ver `.env.example`). Nunca no código.
