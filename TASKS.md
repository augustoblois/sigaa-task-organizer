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

## ⏳ Fase 2 — automação remota (GitHub Actions)

Objetivo: rodar sozinho toda manhã, máquina desligada.

- [ ] **`tools/run.py`** — orquestra login → scrape → push em sequência, aborta+reporta em falha. Entrypoint do cron.
- [ ] **`.github/workflows/daily.yml`** — cron manhã BRT (UTC-3, ex `0 9 * * *`), instala `chromium` headless, roda `run.py`
- [ ] **Repo privado** no GitHub + push do código
- [ ] **Secrets**: `SIGAA_USER`, `SIGAA_PASS`, `GOOGLE_TASKLIST`, `NTFY_TOPIC`, `credentials.json`, `token.json` (escrever os JSON em arquivo no início do job). Molde: `newsletter-ai`.
- [ ] **🔴 Testar risco nº1** no 1º run: login SIGAA do IP do runner (datacenter US) pode ser bloqueado
  - [ ] se bloquear → **plano B: Windows Task Scheduler** (local, PC ligado; sem risco de IP)

## 🔒 Pendências de segurança

- [ ] **Rotacionar senha do SIGAA** (exposta em chat durante o build)
- [ ] Renovar `credentials.json` quando o `client_secret` do newsletter-ai for rotacionado

## 💡 Backlog (depois, opcional)

- [ ] LLM (gpt-4o-mini) baixa anexo da tarefa e resume na descrição (v2)
- [ ] Formalizar Workflows WAT (`workflows/*.md`) — hoje só os Tools existem
- [ ] Atualizar `config/disciplinas.yaml` a cada novo período letivo
