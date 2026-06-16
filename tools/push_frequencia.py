"""Frequencia no Google Tasks: uma task por disciplina + alerta nas em risco.

Pre-requisito:
  - .tmp/frequencia.json gerado por sigaa_frequencia.py
  - credentials.json / token.json (Google Tasks), igual push_tasks.py

Cria/atualiza UMA task por disciplina (visibilidade da contagem n/max). Marca
⚠️ e notifica via ntfy as que estao "em risco": faltas >= FREQ_ABS (absoluto)
OU >= FREQ_PCT do maximo OU restantes <= FREQ_RESTANTES.
Dedup/atualizacao por tag [freq:<disciplina>] na nota -> a task existente e
atualizada (faltas crescem ao longo do periodo).
Imprime '[PIPELINE] novos=N' (N = em risco) que run.py usa pro heartbeat ntfy.
"""
import json
import os
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

# get_service/resolve_tasklist sao do push_tasks (mesmo dir; sys.path[0] = tools/
# quando rodado direto). Reuso a auth do Google Tasks ja existente.
from push_tasks import get_service, resolve_tasklist

ROOT = Path(__file__).resolve().parent.parent
TMP = ROOT / ".tmp"

load_dotenv(ROOT / ".env")

FREQ_PCT = float(os.environ.get("FREQ_PCT", "0.70"))
FREQ_RESTANTES = int(os.environ.get("FREQ_RESTANTES", "3"))
FREQ_ABS = int(os.environ.get("FREQ_ABS", "8"))


def em_risco(f):
    """True se faltas >= FREQ_ABS (absoluto) OU >= FREQ_PCT do limite OU restam
    poucas faltas. max ausente (extracao falhou) -> nao alerta."""
    total, mx = f["total_faltas"], f["max_faltas"]
    if total is None or not mx:
        return False
    return total >= FREQ_ABS or (total / mx) >= FREQ_PCT or (mx - total) <= FREQ_RESTANTES


def find_existing(service, tasklist):
    """Mapa {tag_disciplina: task_id} das tasks de frequencia ja criadas
    (inclui concluidas/ocultas, pra nao duplicar)."""
    found = {}
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
            if "[freq:" in notes:
                found[notes.split("[freq:")[1].split("]")[0]] = t["id"]
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return found


def notify_ntfy(linhas):
    """Push via ntfy.sh se NTFY_TOPIC estiver definido no .env."""
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if not topic or not linhas:
        return
    corpo = "\n".join(linhas)
    req = urllib.request.Request(
        f"https://ntfy.sh/{topic}",
        data=corpo.encode("utf-8"),
        headers={
            "Title": f"SIGAA: {len(linhas)} disciplina(s) perto do limite de faltas".encode("ascii", "ignore"),
            "Tags": "warning",
            "Priority": "high",
        },
    )
    try:
        urllib.request.urlopen(req, timeout=10)
        print(f"Notificacao enviada (ntfy/{topic}).")
    except Exception as e:
        print(f"Falha ao notificar ntfy: {e}")


def load_json(name):
    path = TMP / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def main():
    freq = load_json("frequencia.json")
    # so disciplinas com max conhecido (extracao ok) viram task
    validas = [f for f in freq if f["max_faltas"] and f["total_faltas"] is not None]
    risco = [f for f in validas if em_risco(f)]
    print(f"{len(freq)} turmas, {len(validas)} validas, {len(risco)} em risco "
          f"(abs>={FREQ_ABS} ou pct>={FREQ_PCT} ou restantes<={FREQ_RESTANTES}).")
    if not validas:
        print("Nenhuma frequencia extraida.")
        print("[PIPELINE] novos=0")
        return

    service = get_service()
    tasklist = resolve_tasklist(service)
    existentes = find_existing(service, tasklist)

    linhas = []
    for f in validas:
        disc = f["disciplina"].title()
        total, mx = f["total_faltas"], f["max_faltas"]
        restantes = mx - total
        alerta = em_risco(f)
        key = f["disciplina"]  # tag estavel = nome bruto da disciplina
        prefixo = "⚠️ " if alerta else ""
        titulo = f"{prefixo}Frequência: {disc} — {total}/{mx} faltas (sobram {restantes})"
        notes = f"Faltas: {total} de {mx} permitidas. Sobram {restantes}.\n[freq:{key}]"
        body = {"title": titulo, "notes": notes}
        if key in existentes:
            service.tasks().patch(tasklist=tasklist, task=existentes[key], body=body).execute()
            print(f"  ~ atualizada: {disc} ({total}/{mx}){' [risco]' if alerta else ''}")
        else:
            service.tasks().insert(tasklist=tasklist, body=body).execute()
            print(f"  + nova: {disc} ({total}/{mx}){' [risco]' if alerta else ''}")
        if alerta:
            linhas.append(f"- {disc}: {total}/{mx} (sobram {restantes})")

    print(f"\n{len(linhas)} alerta(s) de frequencia.")
    print(f"[PIPELINE] novos={len(linhas)}")
    notify_ntfy(linhas)


if __name__ == "__main__":
    main()
