from flask import Blueprint, render_template, request, redirect, url_for, session, flash
import pyotp
import qrcode
import io
import base64
from auth import buscar_usuario, criar_usuario_db, validar_credenciais

# Cria o "grupo" de rotas chamado 'auth'
auth_bp = Blueprint('auth', __name__)

@auth_bp.route("/")
def index():
    # Se já logado, vai pro dash
    if session.get("username") and session.get("mfa_validated"):
        return redirect("/dashboard/")
    return redirect(url_for("auth.login"))

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        
        if validar_credenciais(username, password):
            session["username"] = username
            session["mfa_validated"] = False
            return redirect(url_for("auth.mfa_verify"))
        else:
            flash("Usuário ou senha inválidos.", "danger")
    
    return render_template("login.html")

@auth_bp.route("/mfa_verify", methods=["GET", "POST"])
def mfa_verify():
    username = session.get("username")
    if not username: return redirect(url_for("auth.login"))
    
    if request.method == "POST":
        code = request.form["code"].strip()
        user = buscar_usuario(username)
        totp = pyotp.TOTP(user["mfa_secret"])
        
        if totp.verify(code, valid_window=1):
            session["mfa_validated"] = True
            return redirect("/dashboard/")
        else:
            flash("Código inválido.", "danger")
    
    return render_template("mfa_verify.html", username=username)

@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        secret = pyotp.random_base32()
        
        sucesso, msg = criar_usuario_db(username, password, secret)
        
        if sucesso:
            uri = pyotp.totp.TOTP(secret).provisioning_uri(name=username, issuer_name="EcoBalance")
            img = qrcode.make(uri)
            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            img_str = base64.b64encode(buffer.getvalue()).decode('utf-8')
            
            return render_template("mfa_setup.html", img_uri=f"data:image/png;base64,{img_str}", secret=secret, username=username)
        else:
            flash(msg, "warning")
            
    return render_template("register.html")

@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))