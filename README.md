# sigaa-task-organizer

Scraper que loga no SIGAA UFPB, varre as turmas do discente, extrai as tarefas
pendentes e as avaliações futuras, e registra cada uma no Google Tasks. Roda
via GitHub Actions (cron) e notifica novidades/falhas via ntfy.sh. Comentários
e prints em pt-BR.

## Setup

```bash
pip install -r requirements.txt
playwright install --with-deps chromium     # baixa o Chromium do Playwright
cp .env.example .env                          # preencher SIGAA_USER / SIGAA_PASS
```

## Uso

```bash
# Pipeline completo (entrypoint do cron) — MODE escolhe o pipeline
python tools/run.py                    # MODE=tarefas (default): tarefas + avaliações
MODE=frequencia python tools/run.py    # alerta de faltas

# Rodar etapas isoladas (ordem importa — cada uma consome o output da anterior)
python tools/sigaa_login.py       # -> .tmp/sigaa_state.json + .tmp/login_result.png
python tools/sigaa_scrape.py      # -> .tmp/tasks.json + .tmp/provas.json (exige state.json)
python tools/push_tasks.py        # lê tasks.json/provas.json -> Google Tasks (exige credentials.json)

python tools/sigaa_frequencia.py  # -> .tmp/frequencia.json (exige state.json)
python tools/push_frequencia.py   # lê frequencia.json -> Google Tasks

# Debug: HEADLESS=false no .env abre o navegador. sigaa_login.py salva
# .tmp/login_result.png pra inspecionar o resultado do login.
```

Sem testes, linter ou build — projeto é os scripts em `tools/` + orquestrador.

## Arquitetura

Pipelines encadeados por `tools/run.py` via `subprocess`, escolhidos por
`MODE` (`.env`/env var). **O estado flui por arquivos em `.tmp/`, não por
imports** — cada etapa é um script standalone que lê o arquivo da anterior:

```
MODE=tarefas (default, 6x/dia):
  sigaa_login.py  --(.tmp/sigaa_state.json: cookies Playwright)-->
  sigaa_scrape.py --(.tmp/tasks.json + .tmp/provas.json)-->
  push_tasks.py   --> Google Tasks API

MODE=frequencia (1-2x/semana, workflow separado):
  sigaa_login.py      --(.tmp/sigaa_state.json)-->
  sigaa_frequencia.py --(.tmp/frequencia.json)-->
  push_frequencia.py  --> Google Tasks API
```

`run.py` aborta na primeira falha (exit 1 = run vermelho no Actions) e dispara
ntfy. **Detalhe não-óbvio:** `sigaa_login.py` sai com returncode 0 mesmo quando o
login falha — imprime `"LOGIN FALHOU"` no stdout. Por isso `run.py` checa o texto
do stdout (`fail_marker`), não só o exit code.

### Estágios

- **sigaa_login.py** — Playwright síncrono. Preenche `user.login`/`user.senha`
  (com fallback por `type` se o name mudar), submete, e persiste a sessão com
  `storage_state`. Detecta sucesso por `"logon" not in page.url`.
- **sigaa_scrape.py** — reusa a sessão salva. Itera todas as turmas do portal
  discente; em cada uma abre o submenu lateral (`open_menu`) e raspa duas abas:
  **Tarefas** (`EXTRACT_JS`) e **Avaliações** (`EXTRACT_AVALIACOES_JS`), ambas
  sobre a `table.listing`. **JSF dispara navegação extra depois do `networkidle`**
  e destrói o contexto do `evaluate` — daí `evaluate_retry`. "Entregue" do aluno =
  ícone `note.png`/`accept.png` na linha; a coluna `envios` é o contador da turma
  toda e **não** indica entrega individual.
- **push_tasks.py** — OAuth do Google Tasks. **Dedup pela tag na nota** —
  `[sigaa:<id>]` (tarefa) ou `[prova:<hash>]` (avaliação; hash md5 de
  disciplina+data+descrição, porque avaliação não tem id estável no SIGAA). O
  Google Tasks é a fonte da verdade (lê com `showCompleted`/`showHidden`, então
  item concluído não é recriado). Tarefas: não entregues, prazo ≥ hoje ou vencidas
  até `GRACE_DAYS=7` (`[ATRASADA]`). Avaliações: só futuras (data ≥ hoje), título
  `Prova de <NOME> — <descrição>`. Imprime `[PIPELINE] novos=N` que `run.py` usa
  pra decidir o heartbeat ntfy.
- **sigaa_frequencia.py** — reusa a sessão salva. Raspa o mapa de faltas de cada
  turma e grava `.tmp/frequencia.json`.
- **push_frequencia.py** — cria/atualiza uma task por disciplina no Google Tasks
  com a contagem de faltas (n/max). Dedup por tag `[freq:<disciplina>]`. Marca
  ⚠️ as em risco: faltas ≥ `FREQ_ABS` (8) ou ≥ `FREQ_PCT` do máximo ou faltas
  restantes ≤ `FREQ_RESTANTES`.

### Auth / segredos

- **SIGAA:** `SIGAA_USER`/`SIGAA_PASS` no `.env` (local) ou secrets (CI).
- **Google:** `credentials.json` (OAuth client, Tasks API) na raiz. Primeira run
  local abre browser pro consentimento e grava `token.json`. No CI, ambos são
  injetados de secrets (`GOOGLE_CREDENTIALS`/`GOOGLE_TOKEN`) por `printf` antes da run.
- `GOOGLE_TASKLIST` (.env) escolhe a lista por nome; vazio = `@default`.
- `NTFY_TOPIC` (.env/secret) liga as notificações; vazio = silencioso.

## CI

- `.github/workflows/daily.yml`: cron `0 9,12,15,18,21,0 UTC` (= 6/9/12/15/18/21h
  BRT), `MODE=tarefas`. `HEADLESS=true` em produção. `workflow_dispatch` permite
  disparo manual. `concurrency` impede runs simultâneas.
- `.github/workflows/frequencia.yml`: cron separado, `MODE=frequencia`.

## Notas

- `config/disciplinas.yaml` é referência manual do período atual — o scrape varre
  todas as turmas, não filtra por esse arquivo. Atualizar ao trocar de período.
- `tools/debug/sigaa_explore.py` é utilitário de exploração/debug do DOM, fora do pipeline.
- `.tmp/` é efêmero (não commitado); regenerado a cada run.
