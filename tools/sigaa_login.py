"""Loga no SIGAA UFPB e salva a sessao para reuso.

Uso:
    python tools/sigaa_login.py

Le SIGAA_USER / SIGAA_PASS / HEADLESS do .env.
Salva screenshot em .tmp/login_result.png e a sessao em .tmp/sigaa_state.json.
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
TMP = ROOT / ".tmp"
LOGIN_URL = "https://sigaa.ufpb.br/sigaa/logon.jsf"

load_dotenv(ROOT / ".env")


def login(page):
    page.goto(LOGIN_URL, wait_until="networkidle")
    # campos padrao do SIGAA; fallback por type caso o name mude
    user = os.environ["SIGAA_USER"]
    senha = os.environ["SIGAA_PASS"]
    try:
        page.fill('input[name="user.login"]', user)
        page.fill('input[name="user.senha"]', senha)
    except Exception:
        page.fill('input[type="text"]', user)
        page.fill('input[type="password"]', senha)
    page.press('input[type="password"]', "Enter")
    page.wait_for_load_state("networkidle")


def main():
    if os.environ.get("SIGAA_PASS", "").startswith("COLE_A_SENHA"):
        sys.exit("ERRO: preencha SIGAA_PASS no arquivo .env antes de rodar.")
    TMP.mkdir(exist_ok=True)
    headless = os.environ.get("HEADLESS", "false").lower() == "true"

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=["--disable-gpu", "--disable-dev-shm-usage", "--no-sandbox"],
        )
        ctx = browser.new_context(locale="pt-BR")
        page = ctx.new_page()
        login(page)

        shot = TMP / "login_result.png"
        page.screenshot(path=str(shot), full_page=True)
        ctx.storage_state(path=str(TMP / "sigaa_state.json"))

        print("URL final:", page.url)
        print("Titulo   :", page.title())
        print("Screenshot:", shot)
        ok = "logon" not in page.url.lower()
        print("LOGIN OK" if ok else "LOGIN FALHOU (ainda na pagina de login) - veja o screenshot")
        browser.close()


if __name__ == "__main__":
    main()
