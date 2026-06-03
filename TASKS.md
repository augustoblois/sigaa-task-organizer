# TASKS — sigaa-task-organizer

Checklist vivo. Marcar `[x]` ao concluir. Detalhe técnico mora no `CLAUDE.md`.

## ✅ Feito (MVP local — testado ponta a ponta)

- [x] Terreno: venv, `requirements.txt`, `.env`/`.env.example`, `.gitignore`, `config/disciplinas.yaml`
- [x] `tools/sigaa_login.py` — login Playwright (headless + `--disable-gpu`), sessão salva
- [x] `tools/sigaa_explore.py` — dump de HTML do SIGAA pra debug
- [x] `tools/sigaa_scrape.py` — varre 6 turmas → `.tmp/tasks.json`
  - [x] seletor turma (`idTurma` sem `'id':`)
  - [x] menu "Tarefas" oculto via `dispatch_event`
  - [x] parser exige data (anti tarefa-fantasma)
  - [x] `entregue` pelo ícone (não pelo contador `Envios` da turma)
- [x] `tools/push_tasks.py` — Google Tasks
  - [x] OAuth (reusa client do newsletter-ai)
  - [x] filtro pendente + janela `[ATRASADA]` (7 dias)
  - [x] dedup por tag `[sigaa:<id>]`
  - [x] grupo configurável (`GOOGLE_TASKLIST=Faculdade`)
  - [x] push ntfy de nova tarefa (`NTFY_TOPIC`)
- [x] `CLAUDE.md` (arquitetura + gotchas) + ntfy testado

## ✅ Fase 2 — automação remota (GitHub Actions) — LIVE (2026-06-03)

Roda sozinho 7h/13h/19h BRT, máquina desligada. 1º run manual: tudo verde.

- [x] **`tools/run.py`** — orquestra login → scrape → push via subprocess, aborta+reporta+ntfy em falha. Entrypoint do cron. Checa returncode E stdout (`LOGIN FALHOU` sai com código 0).
- [x] **`.github/workflows/daily.yml`** — cron `0 10,16,22 * * *` UTC (7h/13h/19h BRT) + `workflow_dispatch`, `playwright install --with-deps chromium`, `HEADLESS=true`
- [x] **Repo privado** github.com/augustoblois/sigaa-task-organizer + push
- [x] **Secrets**: `SIGAA_USER`, `SIGAA_PASS`, `GOOGLE_TASKLIST`, `NTFY_TOPIC`, `GOOGLE_CREDENTIALS`, `GOOGLE_TOKEN` (os 2 JSON escritos em arquivo no início do job)
- [x] **🔴 Risco nº1 testado** — login do IP do runner **NÃO** foi bloqueado. Plano B (Task Scheduler) não precisou.

## 🔒 Pendências de segurança

- [ ] **Rotacionar senha do SIGAA** (exposta em chat durante o build)
- [ ] Renovar `credentials.json` quando o `client_secret` do newsletter-ai for rotacionado

## 💡 Backlog (depois, opcional)

- [ ] LLM (gpt-4o-mini) baixa anexo da tarefa e resume na descrição (v2)
- [ ] Formalizar Workflows WAT (`workflows/*.md`) — hoje só os Tools existem
- [ ] Atualizar `config/disciplinas.yaml` a cada novo período letivo
