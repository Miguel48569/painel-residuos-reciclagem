import os
import certifi  # <--- IMPORTANTE: Importamos o certificado aqui
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

mongo_uri = os.getenv("MONGO_URI")

# --- A MÁGICA ACONTECE AQUI ---
# Adicionamos tlsCAFile=certifi.where() para o Python confiar no MongoDB
client = MongoClient(mongo_uri, tlsCAFile=certifi.where())

db = client["balanca-iot"]
users_collection = db["usuarios"]

print("Conexão com MongoDB configurada com certificado SSL.")

# Nova coleção para guardar o histórico
sensor_collection = db["historico_sensores"]

def salvar_dados_thingpeak(df):
    """
    Recebe o DataFrame do ThingSpeak e salva no Mongo.
    Evita duplicatas checando o 'entry_id'.
    """
    if df.empty:
        return

    # Converte o DataFrame para uma lista de dicionários (formato JSON)
    dados = df.to_dict('records')

    # Itera sobre cada leitura e salva se não existir
    novos_registros = 0
    for leitura in dados:
        # O ThingSpeak tem um 'entry_id' único para cada dado.
        # Usamos update_one com upsert=True:
        # "Se achar esse entry_id, atualiza. Se não achar, cria novo."
        resultado = sensor_collection.update_one(
            {'entry_id': leitura['entry_id']}, # Busca por ID
            {'$set': leitura},                 # Dados para salvar
            upsert=True                        # Cria se não existir
        )
        
        if resultado.upserted_id:
            novos_registros += 1
            
    if novos_registros > 0:
        print(f"✅ {novos_registros} novos dados salvos no MongoDB!")