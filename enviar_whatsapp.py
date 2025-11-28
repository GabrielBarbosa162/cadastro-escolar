import sys
import time
import urllib.parse
import os

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager


PROFILE_DIR = r"C:/alunos_app/ChromeProfileWPP"


def criar_chrome(headless: bool) -> webdriver.Chrome:
    """Cria uma instância do Chrome com ou sem headless."""
    options = webdriver.ChromeOptions()

    # Perfil fixo para manter login do WhatsApp
    options.add_argument(f"--user-data-dir={PROFILE_DIR}")

    # Opções para evitar travamentos
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_experimental_option("excludeSwitches", ["enable-logging"])

    if headless:
        # Novo modo headless
        options.add_argument("--headless=new")

    print(f"Iniciando Chrome (headless={headless})...")
    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )
    return driver


def enviar_mensagem_whatsapp(numero: str, mensagem: str):
    texto = urllib.parse.quote(mensagem)
    url = f"https://web.whatsapp.com/send?phone={numero}&text={texto}"

    # Se o perfil ainda não existe, é a primeira vez -> abre visível
    primeira_vez = not os.path.exists(PROFILE_DIR)

    driver = criar_chrome(headless=not primeira_vez)

    try:
        driver.get(url)
        print("Carregando WhatsApp Web...")

        if primeira_vez:
            print("\n==== ATENÇÃO ====")
            print("Parece ser a primeira vez que você está usando este perfil.")
            print("Escaneie o QR Code no WhatsApp Web para logar.")
            print("Vou aguardar 30 segundos para você fazer o login...\n")
            time.sleep(30)
        else:
            # Já logado, só espera carregar chat
            time.sleep(12)

        # Aguarda mais um pouco pra garantir que o chat carregou
        time.sleep(5)

        # Tenta clicar no botão de enviar (ícone de aviãozinho)
        try:
            print("Tentando enviar pelo ícone de enviar...")
            btn = driver.find_element(By.CSS_SELECTOR, "span[data-icon='send']")
            btn.click()
            print("Mensagem enviada com sucesso (método 1).")
            time.sleep(4)
            return True
        except Exception as e1:
            print("Método 1 falhou:", e1)

        # Tenta via aria-label
        try:
            print("Tentando enviar pelo botão com aria-label...")
            btn = driver.find_element(
                By.XPATH, "//button[@aria-label='Enviar' or @aria-label='Send']"
            )
            btn.click()
            print("Mensagem enviada com sucesso (método 2).")
            time.sleep(4)
            return True
        except Exception as e2:
            print("Método 2 falhou:", e2)

        # Como último recurso, tenta simular ENTER no campo de mensagem
        try:
            print("Tentando enviar simulando ENTER no campo de mensagem...")
            campo = driver.find_element(By.XPATH, "//div[@title='Mensagem' or @title='Type a message']")
            campo.send_keys("\n")
            print("Mensagem enviada com sucesso (método 3).")
            time.sleep(4)
            return True
        except Exception as e3:
            print("Método 3 falhou:", e3)

        print("Não foi possível enviar a mensagem automaticamente.")
        return False

    finally:
        driver.quit()
        print("Chrome fechado.")


def main():
    if len(sys.argv) < 3:
        print("Uso: python enviar_whatsapp.py NUMERO MENSAGEM")
        sys.exit(1)

    numero = sys.argv[1]         # exemplo: 5533999999999
    mensagem = sys.argv[2]

    ok = enviar_mensagem_whatsapp(numero, mensagem)
    if ok:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
