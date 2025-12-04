import smtplib
from email.mime.text import MIMEText

# ==============================
# CONFIGURAÇÃO DO SMTP (remetente fixo)
# ==============================
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USE_TLS = True

SMTP_USER = "seuemail@gmail.com"      # SUA conta que vai enviar
SMTP_PASS = "SENHA_DE_APP_AQUI"       # senha de app ou senha do e-mail

def enviar_email(destinatarios, assunto, corpo):
    """
    destinatarios pode ser:
    - uma string: "cliente@exemplo.com"
    - uma lista: ["cli1@ex.com", "cli2@ex.com"]
    """

    # Se o usuário passar só uma string, transformamos em lista
    if isinstance(destinatarios, str):
        destinatarios = [destinatarios]

    # Monta a mensagem
    msg = MIMEText(corpo, "plain", "utf-8")
    msg["From"] = SMTP_USER
    msg["To"] = ", ".join(destinatarios)
    msg["Subject"] = assunto

    # Conecta e envia
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        if SMTP_USE_TLS:
            server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_USER, destinatarios, msg.as_string())

    print("E-mail enviado para:", destinatarios)


# EXEMPLOS DE USO:

# 1) Um único e-mail (ex: digitado em um campo)
# enviar_email("cliente1@exemplo.com", "Assunto teste", "Corpo da mensagem")

# 2) Vários e-mails
# lista_destinos = ["cli1@exemplo.com", "cli2@exemplo.com", "cli3@exemplo.com"]
# enviar_email(lista_destinos, "Assunto para vários", "Mensagem para todos")
