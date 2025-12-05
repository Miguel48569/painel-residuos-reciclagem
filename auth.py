import bcrypt
import os
import pyotp
from database import users_collection  # Importa a conexão do arquivo anterior

def buscar_usuario(username):
    return users_collection.find_one({"username": username})

def criar_usuario_db(username, senha_texto, mfa_secret):
    if buscar_usuario(username):
        return False, "Usuário já existe!"

    # Criptografia
    bytes_senha = senha_texto.encode('utf-8')
    salt = bcrypt.gensalt()
    senha_hash = bcrypt.hashpw(bytes_senha, salt)

    novo_usuario = {
        "username": username,
        "password": senha_hash,
        "mfa_secret": mfa_secret,
        "created_at": os.path.getmtime(__file__)
    }
    
    users_collection.insert_one(novo_usuario)
    return True, "Usuário registrado com sucesso!"

def validar_credenciais(username, senha_texto):
    user = buscar_usuario(username)
    if not user:
        return False
    
    senha_guardada = user['password']
    return bcrypt.checkpw(senha_texto.encode('utf-8'), senha_guardada)