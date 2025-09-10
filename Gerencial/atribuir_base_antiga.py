# atribuir_base_antiga.py (versão corrigida)
import os
import pymongo
from dotenv import load_dotenv
from datetime import datetime, UTC


def atribuir_nome_para_base_antiga():
    print("Iniciando script para atribuir nome a leads antigos...")
    load_dotenv()
    connection_string = os.getenv('MONGO_URI')
    if not connection_string: print("ERRO: MONGO_URI não encontrada."); return

    client = None
    try:
        client = pymongo.MongoClient(connection_string)
        db = client ['bot_vendas']
        collection_clientes = db ['clientes']
        collection_bases = db ['bases']
        client.admin.command('ping')
        print("✅ Conectado ao MongoDB.")

        nome_base_antiga = input(
            "\nDigite o nome que você quer dar para a base de clientes antiga (ex: Base Legado): ").strip()
        if not nome_base_antiga:
            print("❌ O nome não pode ser vazio.");
            client.close();
            return

        if collection_bases.find_one({"nome_base": nome_base_antiga}):
            print(f"❌ Já existe uma campanha com o nome '{nome_base_antiga}'. Operação cancelada.");
            client.close();
            return

        # Filtro corrigido para encontrar campos nulos OU inexistentes
        filtro = {"$or": [{"nome_base": {"$exists": False}}, {"nome_base": None}, {"nome_base": ""}]}
        atualizacao = {"$set": {"nome_base": nome_base_antiga}}

        print(f"\nProcurando por clientes sem nome de base para atribuir '{nome_base_antiga}'...")
        result = collection_clientes.update_many(filtro, atualizacao)

        print("\n--- Atualização de Clientes Finalizada ---")
        print(f"Total de registros de clientes atualizados: {result.modified_count}")

        # Se algum cliente foi atualizado, cria o registro da campanha
        if result.modified_count > 0:
            print(f"Criando registro da campanha '{nome_base_antiga}'...")
            base_doc = {
                "nome_base": nome_base_antiga,
                "data_importacao": datetime.now(UTC),
                "total_clientes": result.modified_count,
                "ativa": True,
                "atribuicao": {"tipo": "geral", "supervisor_id": None}
            }
            collection_bases.insert_one(base_doc)
            print("✅ Registro da campanha criado com sucesso.")
        else:
            print("Nenhum registro precisou de atualização.")

    except Exception as e:
        print(f"❌ Ocorreu um erro durante o processo: {e}")
    finally:
        if client:
            client.close()
            print("Conexão com MongoDB fechada.")


if __name__ == "__main__":
    atribuir_nome_para_base_antiga()