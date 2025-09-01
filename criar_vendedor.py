import os
import pymongo
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash
import getpass  # Para digitar a senha de forma segura, sem aparecer no terminal


def cadastrar_novo_vendedor():
    """
    Script para cadastrar um novo vendedor diretamente no MongoDB.
    """
    # --- 1. Conectar ao Banco de Dados ---
    try:
        load_dotenv()
        connection_string = os.getenv('MONGO_URI')
        client = pymongo.MongoClient(connection_string)
        db = client['bot_vendas']
        collection_vendedores = db['vendedores']
        # Testa a conexão
        client.admin.command('ping')
        print("✅ Conexão com MongoDB estabelecida.")
    except Exception as e:
        print(f"❌ Não foi possível conectar ao MongoDB. Erro: {e}")
        return  # Encerra o script se não conseguir conectar

    # --- 2. Coletar os Dados ---
    print("\n--- Cadastro de Novo Vendedor ---")
    nome = input("Nome completo do vendedor: ")
    usuario_login = input("Defina um usuário de login (ex: joao.silva): ").lower()

    # Verifica se o usuário de login já existe
    if collection_vendedores.find_one({"usuario_login": usuario_login}):
        print(f"\n❌ ERRO: O usuário de login '{usuario_login}' já existe. Tente outro.")
        client.close()
        return

    senha = getpass.getpass("Defina uma senha para ele (não vai aparecer enquanto digita): ")
    senha_confirm = getpass.getpass("Confirme a senha: ")

    if senha != senha_confirm:
        print("\n❌ ERRO: As senhas não coincidem.")
        client.close()
        return

    # --- 3. Preparar e Inserir o Documento ---
    try:
        # Gera o hash seguro da senha
        senha_hash = generate_password_hash(senha)

        vendedor_doc = {
            "nome_vendedor": nome,
            "usuario_login": usuario_login,
            "senha_hash": senha_hash,
            "usuario_telegram": None,  # O bot preencherá isso no primeiro login
            "cliente_atual_id": None  # Campo para controlar o cliente em atendimento
        }

        # Insere o documento na coleção
        collection_vendedores.insert_one(vendedor_doc)

        print("\n🎉 Vendedor cadastrado com sucesso no MongoDB!")

    except Exception as e:
        print(f"\n❌ ERRO ao tentar inserir o vendedor no banco de dados. Erro: {e}")

    finally:
        # Garante que a conexão com o banco seja sempre fechada
        client.close()
        print("Conexão com MongoDB fechada.")


# --- Roda a função principal ---
if __name__ == "__main__":
    cadastrar_novo_vendedor()