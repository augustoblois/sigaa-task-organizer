"""Registra tarefas e avaliacoes pendentes do SIGAA no Google Tasks.

Pre-requisito:
  - .tmp/tasks.json e .tmp/provas.json gerados por sigaa_scrape.py
  - credentials.json (OAuth client do Google Cloud, Tasks API habilitada)

Filtro tarefas:    NAO entregues, prazo >= hoje (ou ate GRACE_DAYS atras = [ATRASADA]).
Filtro avaliacoes: data >= hoje (so futuras).
Dedup: tag [sigaa:<id>] (tarefa) ou [prova:<hash>] (avaliacao) na nota;
       Google Tasks e a fonte da verdade (inclui concluidas).
"""
import hashlib
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
    """Tags ja registradas (inclui concluidas): ids de tarefa ([sigaa:]) e
    chaves de avaliacao ([prova:]). Retorna (set_tarefas, set_provas)."""
    tarefas, provas = set(), set()
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
                tarefas.add(notes.split("[sigaa:")[1].split("]")[0])
            if "[prova:" in notes:
                provas.add(notes.split("[prova:")[1].split("]")[0])
        page_token = resp.get("nextToken")
        if not page_token:
            break
    return tarefas, provas


def prova_key(p):
    """Chave de dedup estavel (avaliacao nao tem id confiavel no SIGAA)."""
    base = f"{p['disciplina']}|{p['data']}|{p['descricao']}"
    return hashlib.md5(base.encode("utf-8")).hexdigest()[:10]


def prova_pendente(p):
    """True se a prova tem prazo valido e ainda nao aconteceu (data >= hoje)."""
    if not p["prazo"]:
        return False
    return datetime.fromisoformat(p["prazo"]).date() >= date.today()


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


def load_json(name):
    path = TMP / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def main():
    tasks = load_json("tasks.json")
    provas = load_json("provas.json")
    pending = [(t, s) for t in tasks if (s := task_status(t))]
    prov_pending = [p for p in provas if prova_pendente(p)]
    print(f"{len(tasks)} tarefas, {len(pending)} a registrar (no prazo + atrasadas ate {GRACE_DAYS}d).")
    print(f"{len(provas)} avaliacoes, {len(prov_pending)} a registrar (futuras).")
    if not pending and not prov_pending:
        print("Nada a registrar.")
        print("[PIPELINE] novos=0")
        return

    service = get_service()
    tasklist = resolve_tasklist(service)
    tarefas_tags, provas_tags = existing_tags(service, tasklist)

    novas_titulos = []
    for t, status in pending:
        if t["id"] in tarefas_tags:
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

    for p in prov_pending:
        key = prova_key(p)
        if key in provas_tags:
            print(f"  - ja registrada: prova {p['disciplina']} {p['data']}")
            continue
        due = datetime.fromisoformat(p["prazo"]).strftime("%Y-%m-%dT00:00:00.000Z")
        notes = f"{p['descricao']}\n\nData: {p['data']} as {p['hora']}\n[prova:{key}]"
        titulo = f"Prova de {p['disciplina'].upper()} — {p['descricao']}"
        body = {"title": titulo, "notes": notes, "due": due}
        service.tasks().insert(tasklist=tasklist, body=body).execute()
        print(f"  + prova: {p['disciplina']} {p['data']} ({p['descricao']})")
        novas_titulos.append(f"{titulo} ({p['data']})")

    print(f"\n{len(novas_titulos)} novo(s) item(ns) no Google Tasks.")
    print(f"[PIPELINE] novos={len(novas_titulos)}")
    notify_ntfy(novas_titulos)


if __name__ == "__main__":
    main()
