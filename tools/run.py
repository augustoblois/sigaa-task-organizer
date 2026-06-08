"""Orquestra o pipeline completo: login -> scrape -> push.

Entrypoint do cron (GitHub Actions). Roda os 3 tools em sequencia via
subprocess; aborta na primeira falha e notifica via ntfy.

Uso:
    python tools/run.py

Falha = exit 1 (Actions marca o run vermelho) + push de alerta no ntfy.
"""
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"

load_dotenv(ROOT / ".env")

# (script, frase no stdout que indica falha apesar de returncode 0).
# sigaa_login.py imprime "LOGIN FALHOU" mas sai com codigo 0 -> checar o texto.
STEPS = [
    ("sigaa_login.py", "LOGIN FALHOU"),
    ("sigaa_scrape.py", None),
    ("push_tasks.py", None),
]


def notify_ok():
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if not topic:
        return
    req = urllib.request.Request(
        f"https://ntfy.sh/{topic}",
        data=b"Sem tarefas novas.",
        headers={
            "Title": b"SIGAA: pipeline OK, nada novo",
            "Tags": "white_check_mark",
            "Priority": "min",
        },
    )
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"Falha ao notificar ntfy: {e}")


def notify_falha(etapa: str, detalhe: str):
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if not topic:
        return
    corpo = f"Pipeline SIGAA quebrou em {etapa}.\n{detalhe}".strip()
    req = urllib.request.Request(
        f"https://ntfy.sh/{topic}",
        data=corpo.encode("utf-8"),
        headers={
            "Title": b"SIGAA: pipeline falhou",
            "Tags": "warning",
            "Priority": "high",
        },
    )
    try:
        urllib.request.urlopen(req, timeout=10)
        print(f"Alerta de falha enviado (ntfy/{topic}).")
    except Exception as e:
        print(f"Falha ao notificar ntfy: {e}")


def run_step(script: str, fail_marker: str | None):
    print(f"\n=== {script} ===", flush=True)
    proc = subprocess.run(
        [sys.executable, str(TOOLS / script)],
        capture_output=True,
        text=True,
    )
    print(proc.stdout, end="")
    if proc.stderr:
        print(proc.stderr, end="", file=sys.stderr)

    if proc.returncode != 0:
        return f"returncode {proc.returncode}", proc.stdout
    if fail_marker and fail_marker in proc.stdout:
        return fail_marker, proc.stdout
    return None, proc.stdout


def main():
    last_stdout = ""
    for script, fail_marker in STEPS:
        erro, stdout = run_step(script, fail_marker)
        last_stdout = stdout
        if erro:
            print(f"\nABORTOU em {script}: {erro}")
            notify_falha(script, erro)
            sys.exit(1)
    print("\nPipeline OK.")
    if "[PIPELINE] novos=0" in last_stdout:
        notify_ok()


if __name__ == "__main__":
    main()
