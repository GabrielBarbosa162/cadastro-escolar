import secrets
from werkzeug.security import generate_password_hash, check_password_hash

def gerar_codigo_recuperacao():
    """
    Gera um código fácil de digitar e com poucos erros (sem O/0, I/1).
    Ex: K7QF-29XG
    """
    alfabeto = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    parte1 = "".join(secrets.choice(alfabeto) for _ in range(4))
    parte2 = "".join(secrets.choice(alfabeto) for _ in range(4))
    return f"{parte1}-{parte2}"

def gerar_3_codigos_recuperacao():
    return [gerar_codigo_recuperacao() for _ in range(3)]

def salvar_codigos_no_usuario(user, codigos_puros):
    """
    Salva no usuário apenas os HASHES (segurança).
    E marca que ainda não foram mostrados.
    """
    user.recovery_code1 = generate_password_hash(codigos_puros[0])
    user.recovery_code2 = generate_password_hash(codigos_puros[1])
    user.recovery_code3 = generate_password_hash(codigos_puros[2])
    user.recovery_codes_shown = False

def consumir_codigo(user, codigo_digitado) -> bool:
    """
    Se o código bater com algum hash, remove ele (queima) e retorna True.
    Senão retorna False.
    """
    codigo = (codigo_digitado or "").strip().upper()

    if user.recovery_code1 and check_password_hash(user.recovery_code1, codigo):
        user.recovery_code1 = None
        return True

    if user.recovery_code2 and check_password_hash(user.recovery_code2, codigo):
        user.recovery_code2 = None
        return True

    if user.recovery_code3 and check_password_hash(user.recovery_code3, codigo):
        user.recovery_code3 = None
        return True

    return False
