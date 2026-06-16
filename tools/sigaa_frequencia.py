"""Varre as turmas do SIGAA e extrai o mapa de frequencia (faltas) de cada uma.

Pre-requisito: rodar sigaa_login.py antes (gera .tmp/sigaa_state.json).

Uso:
    python tools/sigaa_frequencia.py

Saida:
  - .tmp/frequencia.json : por turma -> disciplina, total_faltas, justificadas, max_faltas.
"""
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
TMP = ROOT / ".tmp"
PORTAL_URL = "https://sigaa.ufpb.br/sigaa/portais/discente/beta/discente.jsf"
TURMA_SELECTOR = "a[onclick*=\"idTurma\"]:not([onclick*=\"'id':\"])"

load_dotenv(ROOT / ".env")

# Le os totais do rodape da pagina "Mapa de Frequencias". Sao texto bold ABAIXO
# da table.listing (nao estao na tabela), por isso regex no innerText do body.
# "Total de Faltas:" nao colide com "Total de Faltas Justificadas:" pois o
# segundo nao tem ':' logo apos "Faltas".
EXTRACT_FREQ_JS = r"""
() => {
  const txt = document.body.innerText;
  const num = (re) => { const m = txt.match(re); return m ? parseInt(m[1]) : null; };
  return {
    total: num(/Total de Faltas:\s*(\d+)/),
    justificadas: num(/Total de Faltas Justificadas:\s*(\d+)/),
    max: num(/M[aá]ximo de Faltas Permitido:\s*(\d+)/),
  };
}
"""


def open_menu(page, label):
    """Abre um item do submenu lateral da turma virtual (ex: 'Frequência').
    Fica em submenu oculto -> dispatch_event roda o onclick JSF."""
    page.locator(f'a:has(div.itemMenu:text-is("{label}"))').first.dispatch_event("click")
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1500)


def evaluate_retry(page, js):
    """JSF pode disparar navegacao extra apos networkidle e destruir o contexto
    do evaluate; aguarda e retenta uma vez."""
    try:
        return page.evaluate(js)
    except Exception:
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        return page.evaluate(js)


def scrape_turma(page, idx):
    links = page.locator(TURMA_SELECTOR)
    name = links.nth(idx).inner_text().strip()
    links.nth(idx).click()
    page.wait_for_load_state("networkidle")

    open_menu(page, "Frequência")
    raw = evaluate_retry(page, EXTRACT_FREQ_JS)
    return {
        "disciplina": name,
        "total_faltas": raw["total"],
        "justificadas": raw["justificadas"],
        "max_faltas": raw["max"],
    }


def main():
    state = TMP / "sigaa_state.json"
    if not state.exists():
        raise SystemExit("ERRO: rode tools/sigaa_login.py primeiro (sessao nao encontrada).")
    headless = os.environ.get("HEADLESS", "true").lower() == "true"
    freq = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=["--disable-gpu", "--disable-dev-shm-usage", "--no-sandbox"],
        )
        ctx = browser.new_context(storage_state=str(state), locale="pt-BR")
        page = ctx.new_page()

        page.goto(PORTAL_URL, wait_until="networkidle")
        if "logon" in page.url.lower():
            raise SystemExit("Sessao expirou. Rode tools/sigaa_login.py de novo.")
        n = page.locator(TURMA_SELECTOR).count()
        print(f"{n} turmas encontradas.")

        for i in range(n):
            page.goto(PORTAL_URL, wait_until="networkidle")
            f = scrape_turma(page, i)
            print(f"  [{i}] {f['disciplina']}: {f['total_faltas']}/{f['max_faltas']} faltas")
            freq.append(f)

        browser.close()

    (TMP / "frequencia.json").write_text(
        json.dumps(freq, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nTotal: {len(freq)} turmas -> .tmp/frequencia.json")


if __name__ == "__main__":
    main()
