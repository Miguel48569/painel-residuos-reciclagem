import dash
from dash import dcc, html, Input, Output
import dash_bootstrap_components as dbc
import plotly.graph_objs as go
import requests
import pandas as pd
from datetime import datetime, timedelta

# --- IMPORTS DO SISTEMA DE LOGIN (FLASK + MFA) ---
from flask import Flask, render_template, request, redirect, url_for, session, flash
import pyotp
import qrcode
import io
import base64
import os
from werkzeug.security import generate_password_hash, check_password_hash

# ==============================================================================
# 1. CONFIGURAÇÃO DO SERVIDOR FLASK (LOGIN & MFA)
# ==============================================================================

server = Flask(__name__)
# ⚠️ IMPORTANTE: Em produção, troque isso por uma chave aleatória segura!
server.secret_key = os.getenv("APP_SECRET", "chave_secreta_padrao_trocar_em_producao")

# Simulação de Banco de Dados em Memória (CUIDADO: Reseta ao reiniciar o servidor)
# O usuário 'demo' já vem criado para facilitar seus testes.
users = {
    "demo": {
        "password": generate_password_hash("password"),
        "mfa_secret": pyotp.random_base32(),
        "registered_at": datetime.utcnow().isoformat(),
        "mfa_validated": False # Controle de sessão
    }
}

# --- ROTAS DE AUTENTICAÇÃO (FLASK) ---

@server.route("/")
def index():
    # Se já estiver logado, manda direto pro Dash
    if session.get("username") and session.get("mfa_validated"):
        return redirect("/dashboard/")
    return redirect(url_for("login"))

@server.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        user = users.get(username)
        
        if not user or not check_password_hash(user["password"], password):
            flash("Usuário ou senha inválidos.", "danger")
            return redirect(url_for("login"))
        
        session["username"] = username
        session["mfa_validated"] = False # Ainda não validou o 2FA
        return redirect(url_for("mfa_verify"))
    
    return render_template("login.html")

@server.route("/mfa_verify", methods=["GET", "POST"])
def mfa_verify():
    username = session.get("username")
    if not username:
        return redirect(url_for("login"))
    
    user = users.get(username)
    
    if request.method == "POST":
        code = request.form["code"].strip()
        totp = pyotp.TOTP(user["mfa_secret"])
        
        if totp.verify(code, valid_window=1):
            session["mfa_validated"] = True
            flash("Login realizado com sucesso!", "success")
            return redirect("/dashboard/") # Redireciona para o Dash
        else:
            flash("Código inválido. Tente novamente.", "danger")
    
    return render_template("mfa_verify.html", username=username)

@server.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        
        if username in users:
            flash("Usuário já existe.", "warning")
            return redirect(url_for("register"))
        
        secret = pyotp.random_base32()
        users[username] = {
            "password": generate_password_hash(password),
            "mfa_secret": secret,
            "registered_at": datetime.utcnow().isoformat(),
            "mfa_validated": False
        }
        
        # Gera QR Code
        uri = pyotp.totp.TOTP(secret).provisioning_uri(name=username, issuer_name="Painel Residuos")
        img = qrcode.make(uri)
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        img_str = base64.b64encode(buffer.getvalue()).decode('utf-8')
        img_uri = "data:image/png;base64," + img_str
        
        return render_template("mfa_setup.html", img_uri=img_uri, secret=secret, username=username)
        
    return render_template("register.html")

@server.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# --- BLOQUEIO DE SEGURANÇA ---
# Antes de cada requisição, verifica se o usuário está tentando acessar o Dash sem logar
@server.before_request
def protect_dashboard():
    if request.path.startswith("/dashboard") and not request.path.startswith("/dashboard/assets"):
        if not (session.get("username") and session.get("mfa_validated")):
            return redirect(url_for("login"))

# ==============================================================================
# 2. CONFIGURAÇÃO DO DASHBOARD (DASH)
# ==============================================================================

CHANNEL_ID = '3178808'
READ_API_KEY = '' 
FONT_URL = "https://fonts.googleapis.com/css2?family=Montserrat:wght@300;400;700&display=swap"

def get_data(start_date=None, end_date=None):
    base_url = f"https://api.thingspeak.com/channels/{CHANNEL_ID}/feeds.json"
    params = {}
    if READ_API_KEY: params['api_key'] = READ_API_KEY
    if start_date and end_date:
        params['start'] = start_date + ' 00:00:00'
        params['end'] = end_date + ' 23:59:59'
    else:
        params['results'] = 100
    try:
        r = requests.get(base_url, params=params)
        d = r.json()
        if 'feeds' in d: return pd.DataFrame(d['feeds'])
    except Exception as e: print(e)
    return pd.DataFrame()

# Inicializa o Dash usando o 'server' do Flask configurado acima
# url_base_pathname='/dashboard/' empurra o painel para essa URL específica
app = dash.Dash(
    __name__, 
    server=server, 
    url_base_pathname='/dashboard/', 
    external_stylesheets=[dbc.themes.CYBORG, FONT_URL]
)

# Layout do Dashboard
app.layout = dbc.Container([
    # Cabeçalho com Botão de Logout
    dbc.Row([
        dbc.Col(html.H2("♻️ EcoBalance - Monitoramento Inteligente", className="text-primary mt-4"), width=8),
        dbc.Col(
            # Este botão agora redireciona para a rota Flask /logout
            html.A(dbc.Button("Sair (Logout)", color="danger", outline=True), href="/logout", className="mt-4 float-end"),
            width=4
        )
    ], className="mb-4"),

    # Área de Filtros e KPIs
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("Filtros"),
                dbc.CardBody([
                    html.Label("Período:"),
                    dcc.DatePickerRange(
                        id='date-picker',
                        display_format='DD/MM/YYYY',
                        style={'width': '100%', 'fontSize': '14px'}
                    ),
                    dbc.Button("Limpar / Ao Vivo", id='btn-reset', color="info", className="mt-3 w-100"),
                ])
            ], color="secondary", outline=True)
        ], width=12, md=4, className="mb-4"),

        dbc.Col([
            dbc.Row([
                dbc.Col(dbc.Card([
                    dbc.CardHeader("Orgânico Atual"),
                    dbc.CardBody(html.H3(id="kpi-organico", className="text-danger"))
                ], color="dark", inverse=True, style={'border': '1px solid #d63031'}), width=6),
                
                dbc.Col(dbc.Card([
                    dbc.CardHeader("Reciclável Atual"),
                    dbc.CardBody(html.H3(id="kpi-reciclavel", className="text-success"))
                ], color="dark", inverse=True, style={'border': '1px solid #00b894'}), width=6),
            ])
        ], width=12, md=8)
    ]),

    # Gráficos
    dbc.Row([
        dbc.Col(dbc.Card(dcc.Graph(id='grafico-organico', animate=True), body=True, color="dark"), width=12, lg=6, className="mb-4"),
        dbc.Col(dbc.Card(dcc.Graph(id='grafico-reciclavel', animate=True), body=True, color="dark"), width=12, lg=6, className="mb-4"),
    ]),

    dcc.Interval(id='intervalo', interval=5000, n_intervals=0),
], fluid=True)

# Callback do Dash (Inalterado, apenas indentado)
@app.callback(
    [Output('grafico-organico', 'figure'),
     Output('grafico-reciclavel', 'figure'),
     Output('kpi-organico', 'children'),
     Output('kpi-reciclavel', 'children'),
     Output('date-picker', 'start_date'),
     Output('date-picker', 'end_date')],
    [Input('intervalo', 'n_intervals'),
     Input('date-picker', 'start_date'),
     Input('date-picker', 'end_date'),
     Input('btn-reset', 'n_clicks')]
)
def atualizar(n, start, end, reset):
    ctx = dash.callback_context
    if ctx.triggered and 'btn-reset' in ctx.triggered[0]['prop_id']:
        start, end = None, None

    df = get_data(start, end)
    
    layout_base = dict(
        template='plotly_dark',
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(family="Montserrat, sans-serif"),
        margin={'l': 40, 'b': 40, 't': 40, 'r': 10},
        hovermode='x unified'
    )

    if df.empty:
        fig_vazia = go.Figure()
        fig_vazia.update_layout(title="Aguardando dados...", **layout_base)
        return fig_vazia, fig_vazia, "--", "--", start, end

    try:
        df['created_at'] = pd.to_datetime(df['created_at']) - timedelta(hours=3)
        df['field1'] = pd.to_numeric(df['field1'], errors='coerce')
        df['field2'] = pd.to_numeric(df['field2'], errors='coerce')

        last_org = f"{df['field1'].iloc[-1]:.1f}" if not df['field1'].empty else "-"
        last_rec = f"{df['field2'].iloc[-1]:.1f}" if not df['field2'].empty else "-"

        fig_org = go.Figure(go.Scatter(
            x=df['created_at'], y=df['field1'], mode='lines',
            line=dict(color='#ff7675', width=3, shape='spline'), fill='tozeroy', name='Orgânico'
        ))
        fig_org.update_layout(title='Nível Orgânico', **layout_base)

        fig_rec = go.Figure(go.Scatter(
            x=df['created_at'], y=df['field2'], mode='lines',
            line=dict(color='#55efc4', width=3, shape='spline'), fill='tozeroy', name='Reciclável'
        ))
        fig_rec.update_layout(title='Nível Reciclável', **layout_base)

        return fig_org, fig_rec, last_org, last_rec, start, end
    except Exception as e:
        print(f"Erro: {e}")
        fig_vazia = go.Figure()
        fig_vazia.update_layout(title="Erro de dados", **layout_base)
        return fig_vazia, fig_vazia, "Erro", "Erro", start, end

if __name__ == '__main__':
    # O Dash roda em cima do server.run
    server.run(debug=True, port=5000)