import os
import pymongo
from dotenv import load_dotenv
from bson.objectid import ObjectId
from bson.errors import InvalidId


def conectar_db():
    """Conecta ao MongoDB e retorna as coleções necessárias."""
    load_dotenv()
    connection_string = os.getenv('MONGO_URI')
    try:
        client = pymongo.MongoClient(connection_string)
        client.admin.command('ping')
        db = client['bot_vendas']
        return db['mensagens'], client
    except Exception as e:
        print(f"❌ Não foi possível conectar ao MongoDB. Erro: {e}")
        return None, None


def listar_mensagens(collection):
    """Exibe todas as mensagens cadastradas."""
    print("\n--- Mensagens Cadastradas ---")
    mensagens = list(collection.find())
    if not mensagens:
        print("Nenhuma mensagem encontrada.")
        return

    for msg in mensagens:
        print(f"🆔 CÓDIGO (ID): {msg['_id']}")
        print(f"   Nome do Template: {msg['nome_template']}")
        print(f"   Ativo: {'Sim' if msg['ativo'] else 'Não'}")
        print(f"   Texto: \"{msg['texto'].replace('\n', ' ')}\"")
        print("-" * 20)


def adicionar_mensagem(collection):
    """Adiciona uma nova mensagem ao banco de dados."""
    print("\n--- Adicionar Nova Mensagem ---")
    print("Use {{cliente}} e {{vendedor}} para personalização.")

    nome = input("Nome do Template (ex: Saudacao FGTS): ")
    texto = input("Digite o texto completo da mensagem (use '\\n' para quebra de linha): ")
    texto = texto.replace('\\n', '\n')

    doc = {
        "nome_template": nome,
        "texto": texto,
        "ativo": True
    }
    result = collection.insert_one(doc)
    print(f"\n🎉 Mensagem '{nome}' adicionada com sucesso! ID: {result.inserted_id}")


def modificar_mensagem(collection):
    """Modifica uma mensagem existente."""
    listar_mensagens(collection)
    id_str = input("\nDigite o CÓDIGO (ID) da mensagem que deseja modificar: ")

    try:
        obj_id = ObjectId(id_str)
    except InvalidId:
        print("❌ ID inválido.")
        return

    msg = collection.find_one({"_id": obj_id})
    if not msg:
        print("❌ Mensagem não encontrada com este ID.")
        return

    print("\n--- Modificando Mensagem ---")
    print("Pressione ENTER para manter o valor atual.")

    novo_nome = input(f"Nome do Template atual: '{msg['nome_template']}'. Novo nome: ") or msg['nome_template']
    novo_texto_input = input(f"Texto atual: '{msg['texto']}'. Novo texto (use '\\n' para quebras de linha): ")
    novo_texto = novo_texto_input.replace('\\n', '\n') or msg['texto']

    ativo_input = input(f"Ativo atualmente: {'Sim' if msg['ativo'] else 'Não'}. Deseja alterar? (s/n): ").lower()
    novo_ativo = msg['ativo']
    if ativo_input == 's':
        novo_ativo = not msg['ativo']

    collection.update_one(
        {"_id": obj_id},
        {"$set": {"nome_template": novo_nome, "texto": novo_texto, "ativo": novo_ativo}}
    )
    print("\n✅ Mensagem atualizada com sucesso!")


def remover_mensagem(collection):
    """Remove uma mensagem do banco de dados."""
    listar_mensagens(collection)
    id_str = input("\nDigite o CÓDIGO (ID) da mensagem que deseja REMOVER: ")

    try:
        obj_id = ObjectId(id_str)
    except InvalidId:
        print("❌ ID inválido.")
        return

    msg = collection.find_one({"_id": obj_id})
    if not msg:
        print("❌ Mensagem não encontrada com este ID.")
        return

    confirmacao = input(
        f"Tem certeza que deseja remover a mensagem '{msg['nome_template']}'? Esta ação não pode ser desfeita. (s/n): ").lower()

    if confirmacao == 's':
        result = collection.delete_one({"_id": obj_id})
        if result.deleted_count > 0:
            print("\n🗑️ Mensagem removida com sucesso!")
        else:
            print("\n❌ Erro: Nenhuma mensagem foi removida.")
    else:
        print("\nOperação cancelada.")


def main():
    """Função principal que exibe o menu e gerencia as ações."""
    collection, client = conectar_db()

    # --- CORREÇÃO APLICADA AQUI ---
    if collection is None:
        return

    while True:
        print("\n--- Gerenciador de Mensagens do Bot ---")
        print("[1] Listar todas as mensagens")
        print("[2] Adicionar nova mensagem")
        print("[3] Modificar mensagem existente")
        print("[4] Remover mensagem existente")
        print("[5] Sair")

        escolha = input("Escolha uma opção: ")

        if escolha == '1':
            listar_mensagens(collection)
        elif escolha == '2':
            adicionar_mensagem(collection)
        elif escolha == '3':
            modificar_mensagem(collection)
        elif escolha == '4':
            remover_mensagem(collection)
        elif escolha == '5':
            break
        else:
            print("Opção inválida. Tente novamente.")

    if client:
        client.close()
        print("\nConexão com MongoDB fechada.")


if __name__ == "__main__":
    main()