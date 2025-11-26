import dash
from dash import dcc, html, Input, Output
import dash_bootstrap_components as dbc
import plotly.graph_objs as go
import requests
import pandas as pd
from datetime import timedelta

# --- CONFIGURAÇÃO ---
CHANNEL_ID = '3178808'  # <--- COLOQUE SEU ID AQUI
READ_API_KEY = '' 

# URL da fonte (Montserrat) para garantir que carregue
FONT_URL = "https://fonts.googleapis.com/css2?family=Montserrat:wght@300;400;700&display=swap"

# --- FUNÇÕES AUXILIARES ---
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
        response = requests.get(base_url, params=params)
        data = response.json()
        if 'feeds' in data: return pd.DataFrame(data['feeds'])
    except Exception as e:
        print(f"Erro: {e}")
    return pd.DataFrame()

# --- APP SETUP ---
# Carrega o tema CYBORG e a fonte do Google
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.CYBORG, FONT_URL])

app.layout = dbc.Container([
    # Cabeçalho
    dbc.Row([
        dbc.Col(html.H2("♻️ Monitoramento Inteligente", className="text-center text-primary mb-4 mt-4"), width=12)
    ]),

    # Área de Filtros e KPIs
    dbc.Row([
        # Filtros
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

        # KPIs (Cards de Valor Atual)
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

# --- CALLBACKS ---
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
    
    # Layout padrão para gráficos vazios ou erro
    layout_base = dict(
        template='plotly_dark',
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(family="Montserrat, sans-serif"), # <--- FONTE NO GRÁFICO
        margin={'l': 40, 'b': 40, 't': 40, 'r': 10},
        hovermode='x unified'
    )

    if df.empty:
        fig_vazia = go.Figure()
        fig_vazia.update_layout(title="Aguardando dados...", **layout_base)
        return fig_vazia, fig_vazia, "--", "--", start, end

    # Tratamento
    df['created_at'] = pd.to_datetime(df['created_at']) - timedelta(hours=3)
    df['field1'] = pd.to_numeric(df['field1'], errors='coerce')
    df['field2'] = pd.to_numeric(df['field2'], errors='coerce')

    last_org = f"{df['field1'].iloc[-1]:.1f}" if not df['field1'].empty else "-"
    last_rec = f"{df['field2'].iloc[-1]:.1f}" if not df['field2'].empty else "-"

    # Gráfico Orgânico
    fig_org = go.Figure(go.Scatter(
        x=df['created_at'], y=df['field1'],
        mode='lines',
        line=dict(color='#ff7675', width=3, shape='spline'), # Cor suave
        fill='tozeroy',
        name='Orgânico'
    ))
    fig_org.update_layout(title='Nível Orgânico', **layout_base)

    # Gráfico Reciclável
    fig_rec = go.Figure(go.Scatter(
        x=df['created_at'], y=df['field2'],
        mode='lines',
        line=dict(color='#55efc4', width=3, shape='spline'), # Cor suave
        fill='tozeroy',
        name='Reciclável'
    ))
    fig_rec.update_layout(title='Nível Reciclável', **layout_base)

    return fig_org, fig_rec, last_org, last_rec, start, end

if __name__ == '__main__':
    app.run(debug=True)