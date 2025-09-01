import os
import pandas as pd
import pymongo
from dotenv import load_dotenv
from tqdm import tqdm  # <-- NOVO IMPORT


def importar_clientes_do_excel():
    """
    Lê clientes de um arquivo Excel e os insere em massa no MongoDB,
    exibindo uma barra de progresso.
    """
    # --- 1. Conectar ao Banco de Dados ---
    load_dotenv()
    connection_string = os.getenv('MONGO_URI')

    if not connection_string:
        print("ERRO: MONGO_URI não encontrada. Verifique o arquivo .env.")
        return

    try:
        client = pymongo.MongoClient(connection_string)
        client.admin.command('ping')
        print("✅ Conexão com MongoDB estabelecida.")
    except Exception as e:
        print(f"❌ Não foi possível conectar ao MongoDB. Erro: {e}")
        return

    db = client['bot_vendas']
    collection_clientes = db['clientes']

    # --- 2. Ler o Arquivo Excel ---
    nome_arquivo_excel = 'base.xlsx'
    try:
        print(f"Lendo o arquivo '{nome_arquivo_excel}'...")
        df = pd.read_excel(nome_arquivo_excel, dtype=str)
        print(f"Encontrados {len(df)} clientes na planilha.")
    except FileNotFoundError:
        print(f"ERRO: Arquivo '{nome_arquivo_excel}' não encontrado.")
        client.close()
        return
    except Exception as e:
        print(f"ERRO ao ler o arquivo Excel: {e}")
        client.close()
        return

    # --- 3. Preparar os Dados para Inserção em Massa ---
    # Limpa a coleção antes de inserir para evitar duplicatas
    confirmacao = input("Deseja limpar a base de clientes existente antes de importar? (s/n): ").lower()
    if confirmacao == 's':
        print("Limpando a coleção de clientes antigos...")
        collection_clientes.delete_many({})
        print("Coleção limpa.")

    documentos_para_inserir = []
    # Usamos o tqdm para criar uma barra de progresso ao preparar os documentos
    for index, row in tqdm(df.iterrows(), total=df.shape[0], desc="Preparando Clientes"):
        cliente_doc = {
            "nome_cliente": row['NOME'],
            "cpf": row['CPF'],
            "telefone": row['TELEFONE'],
            "status": "Pendente",
            "vendedor_atribuído": None,
            "data_atribuicao": None,
            "status_final": None,
            "data_finalizacao": None,
            "observacoes": None
        }
        documentos_para_inserir.append(cliente_doc)

    # --- 4. Inserir todos os documentos de uma só vez ---
    if not documentos_para_inserir:
        print("Nenhum cliente para importar.")
    else:
        try:
            print(f"Inserindo {len(documentos_para_inserir)} clientes no banco de dados. Isso pode levar um momento...")
            collection_clientes.insert_many(documentos_para_inserir)
            print("\n--- ✅ Importação Concluída com Sucesso! ---")
            print(f"Total de clientes inseridos: {len(documentos_para_inserir)}")
        except Exception as e:
            print(f"\n❌ ERRO durante a inserção em massa. Erro: {e}")

    # Fecha a conexão
    client.close()
    print("Conexão com MongoDB fechada.")


# --- Roda a função principal ---
if __name__ == "__main__":
    importar_clientes_do_excel()