"""Varre as turmas do SIGAA e extrai as tarefas de cada uma.

Pre-requisito: rodar sigaa_login.py antes (gera .tmp/sigaa_state.json).

Uso:
    python tools/sigaa_scrape.py

Saida: .tmp/tasks.json com a lista de tarefas (titulo, prazo, status, descricao, ids).
"""
import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
TMP = ROOT / ".tmp"
PORTAL_URL = "https://sigaa.ufpb.br/sigaa/portais/discente/beta/discente.jsf"
TURMA_SELECTOR = "a[onclick*=\"idTurma\"]:not([onclick*=\"'id':\"])"

load_dotenv(ROOT / ".env")

# JS que extrai as tarefas da tabela "listing" da pagina /sigaa/ava (Tarefas)
EXTRACT_JS = r"""
() => {
  const out = [];
  const table = document.querySelector('table.listing');
  if (!table) return out;
  const rows = [...table.querySelectorAll('tbody > tr')];
  for (let i = 0; i < rows.length; i++) {
    const r = rows[i];
    const tds = [...r.querySelectorAll('td')];
    const periodCell = tds.find(td => /\d{2}\/\d{2}\/\d{4}.*\dh\d{2}/.test(td.innerText));
    const titleCell = r.querySelector('td.first');
    if (!periodCell || !titleCell) continue;
    const title = titleCell.innerText.trim();
    const period = periodCell.innerText.replace(/\s+/g, ' ').trim();
    const nums = tds.filter(td => /^\d+$/.test(td.innerText.trim()));
    const envios = nums.length ? parseInt(nums[nums.length - 1].innerText.trim()) : 0;
    // entrega DO ALUNO = icone de papel (note.png) ou corrigida (accept.png) na linha.
    // envios e contador da TURMA TODA, nao serve pra isso.
    const imgs = [...r.querySelectorAll('td.icon img')].map(im => im.getAttribute('src') || '');
    const entregue = imgs.some(s => /note\.png|accept\.png/.test(s));
    let id = null;
    const link = r.querySelector('a[onclick*="\'id\':"]');
    if (link) { const m = link.getAttribute('onclick').match(/'id':'(\d+)'/); if (m) id = m[1]; }
    let desc = '';
    const nxt = rows[i + 1];
    if (nxt) {
      const d = nxt.querySelector('td.first');
      const style = d ? (d.getAttribute('style') || '') : '';
      if (d && !/font-weight:\s*bold/.test(style)) desc = d.innerText.trim();
    }
    out.push({ title, period, envios, entregue, id, desc });
  }
  return out;
}
"""


def parse_prazo(period: str):
    """Extrai a data/hora final do texto 'de ... a DD/MM/YYYY as HHhMM'."""
    m = re.search(r"a\s+(\d{2})/(\d{2})/(\d{4})\s+\S*\s*(\d{2})h(\d{2})", period)
    if not m:
        return None
    d, mo, y, h, mi = m.groups()
    return f"{y}-{mo}-{d}T{h}:{mi}:00"


def open_tarefas(page):
    page.locator('a:has(div.itemMenu:text-is("Tarefas"))').first.dispatch_event("click")
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1500)


def scrape_turma(page, idx):
    links = page.locator(TURMA_SELECTOR)
    name = links.nth(idx).inner_text().strip()
    links.nth(idx).click()
    page.wait_for_load_state("networkidle")
    open_tarefas(page)
    raw = page.evaluate(EXTRACT_JS)
    tasks = []
    for t in raw:
        tasks.append(
            {
                "disciplina": name,
                "titulo": t["title"],
                "prazo": parse_prazo(t["period"]),
                "periodo_raw": t["period"],
                "envios": t["envios"],
                "entregue": t["entregue"],
                "id": t["id"],
                "descricao": t["desc"],
            }
        )
    return name, tasks


def main():
    state = TMP / "sigaa_state.json"
    if not state.exists():
        raise SystemExit("ERRO: rode tools/sigaa_login.py primeiro (sessao nao encontrada).")
    headless = os.environ.get("HEADLESS", "true").lower() == "true"
    all_tasks = []

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
            name, tasks = scrape_turma(page, i)
            print(f"  [{i}] {name}: {len(tasks)} tarefa(s)")
            all_tasks.extend(tasks)

        browser.close()

    (TMP / "tasks.json").write_text(
        json.dumps(all_tasks, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nTotal: {len(all_tasks)} tarefas -> .tmp/tasks.json")


if __name__ == "__main__":
    main()
