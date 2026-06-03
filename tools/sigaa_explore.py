"""Explora o portal discente reusando a sessao salva.

Pre-requisito: rodar sigaa_login.py antes (gera .tmp/sigaa_state.json).

Uso:
    python tools/sigaa_explore.py

Salva o HTML do portal em .tmp/portal.html e um screenshot, para inspecao.
"""
import os
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
TMP = ROOT / ".tmp"
PORTAL_URL = "https://sigaa.ufpb.br/sigaa/portais/discente/beta/discente.jsf"

load_dotenv(ROOT / ".env")


def main():
    state = TMP / "sigaa_state.json"
    if not state.exists():
        raise SystemExit("ERRO: rode tools/sigaa_login.py primeiro (sessao nao encontrada).")
    headless = os.environ.get("HEADLESS", "true").lower() == "true"

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=["--disable-gpu", "--disable-dev-shm-usage", "--no-sandbox"],
        )
        ctx = browser.new_context(storage_state=str(state), locale="pt-BR")
        page = ctx.new_page()
        page.goto(PORTAL_URL, wait_until="networkidle")

        html = page.content()
        (TMP / "portal.html").write_text(html, encoding="utf-8")
        page.screenshot(path=str(TMP / "portal.png"), full_page=True)
        print("PORTAL:", page.url, "|", f"{len(html)} chars")

        # links do nome da turma: tem idTurma e NAO tem 'id': (esses sao sub-links)
        turma_links = page.locator(
            "a[onclick*=\"idTurma\"]:not([onclick*=\"'id':\"])"
        )
        n = turma_links.count()
        print(f"Turmas encontradas: {n}")
        for i in range(n):
            print(f"  [{i}]", turma_links.nth(i).inner_text().strip())

        # entra na PRIMEIRA turma e despeja o HTML dela
        turma_links.first.click()
        page.wait_for_load_state("networkidle")
        turma_html = page.content()
        (TMP / "turma.html").write_text(turma_html, encoding="utf-8")
        page.screenshot(path=str(TMP / "turma.png"), full_page=True)
        print("TURMA :", page.url, "|", f"{len(turma_html)} chars")

        # "Tarefas" fica em submenu oculto (display:none). dispatch_event roda o
        # onclick JSF direto, sem exigir visibilidade. Miro o <a> que contem o div.
        page.locator('a:has(div.itemMenu:text-is("Tarefas"))').first.dispatch_event("click")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        tarefas_html = page.content()
        (TMP / "tarefas.html").write_text(tarefas_html, encoding="utf-8")
        page.screenshot(path=str(TMP / "tarefas.png"), full_page=True)
        print("TAREFAS:", page.url, "|", f"{len(tarefas_html)} chars")
        print("Salvos: .tmp/portal.html, turma.html, tarefas.html (+ .png)")
        browser.close()


if __name__ == "__main__":
    main()
