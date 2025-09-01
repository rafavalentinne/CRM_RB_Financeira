import os
from dotenv import load_dotenv
import pymongo
from pymongo.errors import ConnectionFailure

# --- 1. Carregar a String de Conexão ---
# Carrega as variáveis do arquivo .env para o ambiente
load_dotenv()
connection_string = os.getenv('MONGO_URI')

# Verifica se a string de conexão foi carregada
if not connection_string:
    print("ERRO: Variável de ambiente MONGO_URI não encontrada.")
    print("Verifique se o arquivo .env existe e contém a variável.")
    exit()

# --- 2. Tentar a Conexão ---
# Criamos um "cliente" para se conectar ao nosso cluster
try:
    print("Tentando conectar ao MongoDB Atlas...")
    client = pymongo.MongoClient(connection_string)

    # O comando 'ping' é uma forma simples e leve de verificar
    # se a conexão com o servidor foi bem-sucedida e se a
    # autenticação (usuário/senha) está correta.
    client.admin.command('ping')

    print("✅ Conexão com o MongoDB estabelecida com sucesso!")

except ConnectionFailure as e:
    print("❌ Falha na conexão com o MongoDB.")
    print("------------------------------------------")
    print("Possíveis causas:")
    print("1. Senha incorreta na sua string de conexão (o erro mais comum).")
    print("2. O IP da sua máquina não está liberado no 'Network Access' do MongoDB Atlas.")
    print("3. Erro de digitação na string de conexão.")
    print("------------------------------------------")
    print(f"Detalhes do erro: {e}")

except Exception as e:
    print(f"Ocorreu um erro inesperado: {e}")