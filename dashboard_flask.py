import os
import dash
from dash import dcc, html, Input, Output
import dash_bootstrap_components as dbc
import plotly.graph_objs as go
import pandas as pd
import requests
from datetime import timedelta
from flask import Flask, session, redirect, url_for, request

# --- IMPORTS LOCAIS ---
from routes import auth_bp 
from database import salvar_dados_thingpeak  # Importa a função que salva no banco

# --- CONFIGURAÇÃO DO SERVIDOR ---
server = Flask(__name__)
# Chave secreta para a sessão (MFA e Login)
server.secret_key = os.getenv("APP_SECRET", "chave_secreta_segura")

# Registra as rotas de login (que estão no routes.py)
server.register_blueprint(auth_bp)

# --- BLOQUEIO DE SEGURANÇA ---
@server.before_request
def protect_dashboard():
    # Se tentar acessar o painel sem logar, manda pro login
    if request.path.startswith("/dashboard") and not request.path.startswith("/dashboard/assets"):
        if not (session.get("username") and session.get("mfa_validated")):
            return redirect(url_for("auth.login"))

# --- CONFIGURAÇÃO DO DASHBOARD ---
CHANNEL_ID = '3178808' # Seu ID do ThingSpeak
READ_API_KEY = ''      # Se tiver chave de leitura, coloque aqui
FONT_URL = "https://fonts.googleapis.com/css2?family=Montserrat:wght@300;400;700&display=swap"

# Função que busca os dados e SALVA NO MONGO
def get_data(start_date=None, end_date=None):
    base_url = f"https://api.thingspeak.com/channels/{CHANNEL_ID}/feeds.json"
    params = {}
    if READ_API_KEY: params['api_key'] = READ_API_KEY
    
    # Se tiver datas selecionadas no filtro
    if start_date and end_date:
        params['start'] = start_date + ' 00:00:00'
        params['end'] = end_date + ' 23:59:59'
    else:
        params['results'] = 100 # Pega os últimos 100 dados se não tiver filtro

    try:
        r = requests.get(base_url, params=params)
        d = r.json()
        if 'feeds' in d: 
            df = pd.DataFrame(d['feeds'])
            
            # --- SALVAMENTO AUTOMÁTICO NO MONGODB ---
            try:
                # Chama a função do database.py para salvar sem duplicar
                salvar_dados_thingpeak(df)
            except Exception as e_db:
                # Apenas printa o erro no console, não para o dashboard
                print(f"⚠️ Erro ao salvar histórico no MongoDB: {e_db}")
            # ----------------------------------------

            return df
    except Exception as e: 
        print(f"Erro ao buscar dados do ThingSpeak: {e}")
    return pd.DataFrame()

app = dash.Dash(
    __name__, 
    server=server, 
    url_base_pathname='/dashboard/', 
    external_stylesheets=[dbc.themes.CYBORG, FONT_URL]
)

# === LAYOUT ===
app.layout = dbc.Container([
    # Cabeçalho
    dbc.Row([
        dbc.Col(html.H2("♻️ EcoBalance - Monitoramento Inteligente", className="text-primary mt-4"), width=8),
        dbc.Col(
            html.A(dbc.Button("Sair (Logout)", color="danger", outline=True), href="/logout", className="mt-4 float-end"),
            width=4
        )
    ], className="mb-4"),

    # Filtros e KPIs
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

    # Intervalo de Atualização (5 segundos)
    dcc.Interval(id='intervalo', interval=5000, n_intervals=0),
], fluid=True)

# === CALLBACKS (Lógica dos Gráficos) ===
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

    # Aqui ele busca os dados e o salvamento ocorre automaticamente dentro da função
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
        # Tratamento dos dados
        df['created_at'] = pd.to_datetime(df['created_at']) - timedelta(hours=3)
        df['field1'] = pd.to_numeric(df['field1'], errors='coerce')
        df['field2'] = pd.to_numeric(df['field2'], errors='coerce')

        last_org = f"{df['field1'].iloc[-1]:.1f}" if not df['field1'].empty else "-"
        last_rec = f"{df['field2'].iloc[-1]:.1f}" if not df['field2'].empty else "-"

        # Gráfico Orgânico
        fig_org = go.Figure(go.Scatter(
            x=df['created_at'], y=df['field1'], mode='lines',
            line=dict(color='#ff7675', width=3, shape='spline'), fill='tozeroy', name='Orgânico'
        ))
        fig_org.update_layout(title='Nível Orgânico', **layout_base)

        # Gráfico Reciclável
        fig_rec = go.Figure(go.Scatter(
            x=df['created_at'], y=df['field2'], mode='lines',
            line=dict(color='#55efc4', width=3, shape='spline'), fill='tozeroy', name='Reciclável'
        ))
        fig_rec.update_layout(title='Nível Reciclável', **layout_base)

        return fig_org, fig_rec, last_org, last_rec, start, end
    except Exception as e:
        print(f"Erro processando gráficos: {e}")
        fig_vazia = go.Figure()
        fig_vazia.update_layout(title="Erro de dados", **layout_base)
        return fig_vazia, fig_vazia, "Erro", "Erro", start, end

if __name__ == '__main__':
    server.run(debug=True, port=5000)