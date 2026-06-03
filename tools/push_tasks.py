"""Registra as tarefas pendentes do SIGAA no Google Tasks.

Pre-requisito:
  - .tmp/tasks.json gerado por sigaa_scrape.py
  - credentials.json (OAuth client do Google Cloud, Tasks API habilitada)

Uso:
    python tools/push_tasks.py

Filtro: registra so tarefas NAO entregues (envios=0) com prazo >= hoje.
Dedup: tag [sigaa:<id>] na nota; Google Tasks e a fonte da verdade (inclui concluidas).
"""
import json
import os
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

ROOT = Path(__file__).resolve().parent.parent
TMP = ROOT / ".tmp"
CRED = ROOT / "credentials.json"
TOKEN = ROOT / "token.json"
SCOPES = ["https://www.googleapis.com/auth/tasks"]
GRACE_DAYS = 7  # vencida nao-enviada: registra como [ATRASADA] se venceu ate N dias atras

load_dotenv(ROOT / ".env")


def get_service():
    creds = None
    if TOKEN.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CRED.exists():
                raise SystemExit(
                    "ERRO: credentials.json nao encontrado. Crie um OAuth client no "
                    "Google Cloud (Tasks API) e salve como credentials.json na raiz."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(CRED), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN.write_text(creds.to_json(), encoding="utf-8")
    return build("tasks", "v1", credentials=creds)


def notify_ntfy(titulos):
    """Push via ntfy.sh se NTFY_TOPIC estiver definido no .env."""
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if not topic or not titulos:
        return
    corpo = "\n".join(f"- {t}" for t in titulos)
    req = urllib.request.Request(
        f"https://ntfy.sh/{topic}",
        data=corpo.encode("utf-8"),
        headers={
            "Title": f"SIGAA: {len(titulos)} nova(s) tarefa(s)".encode("ascii", "ignore"),
            "Tags": "books",
        },
    )
    try:
        urllib.request.urlopen(req, timeout=10)
        print(f"Notificacao enviada (ntfy/{topic}).")
    except Exception as e:
        print(f"Falha ao notificar ntfy: {e}")


def resolve_tasklist(service):
    """Resolve a lista do Google Tasks pelo nome em GOOGLE_TASKLIST (.env).
    Vazio -> @default. Nome nao encontrado -> erro listando os disponiveis."""
    name = os.environ.get("GOOGLE_TASKLIST", "").strip()
    if not name:
        return "@default"
    resp = service.tasklists().list(maxResults=100).execute()
    listas = resp.get("items", [])
    for item in listas:
        if item["title"].strip().lower() == name.lower():
            return item["id"]
    nomes = ", ".join(repr(i["title"]) for i in listas)
    raise SystemExit(f"Lista '{name}' nao encontrada. Disponiveis: {nomes}")


def existing_tags(service, tasklist):
    """IDs do SIGAA ja registrados (inclui tarefas concluidas)."""
    tags = set()
    page_token = None
    while True:
        resp = (
            service.tasks()
            .list(tasklist=tasklist, showCompleted=True, showHidden=True,
                  maxResults=100, pageToken=page_token)
            .execute()
        )
        for t in resp.get("items", []):
            notes = t.get("notes", "")
            if "[sigaa:" in notes:
                tags.add(notes.split("[sigaa:")[1].split("]")[0])
        page_token = resp.get("nextToken")
        if not page_token:
            break
    return tags


def task_status(t):
    """Retorna 'ok' (no prazo), 'atrasada' (vencida dentro da carencia) ou None (ignorar)."""
    if t["entregue"] or not t["id"] or not t["prazo"]:
        return None
    prazo = datetime.fromisoformat(t["prazo"]).date()
    hoje = date.today()
    if prazo >= hoje:
        return "ok"
    if prazo >= hoje - timedelta(days=GRACE_DAYS):
        return "atrasada"
    return None


def main():
    tasks = json.loads((TMP / "tasks.json").read_text(encoding="utf-8"))
    pending = [(t, s) for t in tasks if (s := task_status(t))]
    print(f"{len(tasks)} tarefas, {len(pending)} a registrar (no prazo + atrasadas ate {GRACE_DAYS}d).")
    if not pending:
        print("Nada a registrar.")
        return

    service = get_service()
    tasklist = resolve_tasklist(service)
    already = existing_tags(service, tasklist)

    novas_titulos = []
    for t, status in pending:
        if t["id"] in already:
            print(f"  - ja registrada: {t['titulo']}")
            continue
        disciplina = t["disciplina"].title()
        prefix = "[ATRASADA] " if status == "atrasada" else ""
        due = datetime.fromisoformat(t["prazo"]).strftime("%Y-%m-%dT00:00:00.000Z")
        notes = f"{t['descricao']}\n\nPrazo: {t['periodo_raw']}\n[sigaa:{t['id']}]"
        titulo = f"{prefix}[{disciplina}] {t['titulo']}"
        body = {"title": titulo, "notes": notes, "due": due}
        service.tasks().insert(tasklist=tasklist, body=body).execute()
        print(f"  + {status}: {t['titulo']} (prazo {t['prazo'][:10]})")
        novas_titulos.append(f"{titulo} (ate {t['prazo'][:10]})")

    print(f"\n{len(novas_titulos)} nova(s) tarefa(s) no Google Tasks.")
    notify_ntfy(novas_titulos)


if __name__ == "__main__":
    main()
