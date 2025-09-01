import os
import pandas as pd
import pymongo
from dotenv import load_dotenv
from datetime import timedelta


def formatar_timedelta(delta):
    """Formata a diferença de tempo de forma legível."""
    if not isinstance(delta, timedelta):
        return "N/D"

    dias = delta.days
    horas, resto = divmod(delta.seconds, 3600)
    minutos, segundos = divmod(resto, 60)

    resultado = []
    if dias > 0:
        resultado.append(f"{dias}d")
    if horas > 0:
        resultado.append(f"{horas}h")
    if minutos > 0:
        resultado.append(f"{minutos}m")
    if segundos > 0 or not resultado:
        resultado.append(f"{segundos}s")

    return " ".join(resultado)


def exportar_relatorio():
    """
    Gera um relatório em Excel com o desempenho dos vendedores,
    incluindo os dados da consulta de banco.
    """
    # --- 1. Conectar ao Banco de Dados ---
    load_dotenv()
    connection_string = os.getenv('MONGO_URI')

    if not connection_string:
        print("ERRO: MONGO_URI não encontrada. Verifique o arquivo .env.")
        return

    try:
        client = pymongo.MongoClient(connection_string)
        db = client['bot_vendas']
        collection_clientes = db['clientes']
        collection_vendedores = db['vendedores']
        client.admin.command('ping')
        print("✅ Conexão com MongoDB estabelecida.")
    except Exception as e:
        print(f"❌ Não foi possível conectar ao MongoDB. Erro: {e}")
        return

    # --- 2. Buscar e Preparar os Dados ---
    print("Buscando dados dos vendedores...")
    vendedores_map = {v['_id']: v['nome_vendedor'] for v in collection_vendedores.find()}

    print("Buscando clientes finalizados...")
    clientes_finalizados = list(collection_clientes.find({"status": "Concluido"}))

    if not clientes_finalizados:
        print("Nenhum cliente finalizado encontrado para gerar o relatório.")
        client.close()
        return

    print(f"Processando {len(clientes_finalizados)} registros...")
    dados_para_excel = []
    for cliente in clientes_finalizados:
        vendedor_id = cliente.get('vendedor_atribuido')
        nome_vendedor = vendedores_map.get(vendedor_id, "Vendedor não encontrado")

        tempo_atendimento = "N/D"
        if cliente.get('data_atribuicao') and cliente.get('data_finalizacao'):
            delta = cliente['data_finalizacao'] - cliente['data_atribuicao']
            tempo_atendimento = formatar_timedelta(delta)

        # --- LINHA DO RELATÓRIO ATUALIZADA ---
        # Adicionamos os novos campos da consulta usando .get()
        # para que não dê erro se um cliente não tiver passado por esse fluxo.
        linha_relatorio = {
            "Nome do Cliente": cliente.get('nome_cliente'),
            "CPF": cliente.get('cpf'),
            "Telefone": cliente.get('telefone'),
            "Status Final": cliente.get('status_final'),
            "Nome do Vendedor": nome_vendedor,
            "Banco da Consulta": cliente.get('banco_consulta'),  # <-- NOVO CAMPO
            "Resultado da Consulta": cliente.get('resultado_consulta'),  # <-- NOVO CAMPO
            "Data de Atribuição": cliente.get('data_atribuicao'),
            "Data de Finalização": cliente.get('data_finalizacao'),
            "Tempo de Atendimento": tempo_atendimento,
        }
        dados_para_excel.append(linha_relatorio)

    # --- 3. Gerar o Arquivo Excel ---
    try:
        print("Gerando o arquivo Excel...")
        df = pd.DataFrame(dados_para_excel)

        if "Data de Atribuição" in df.columns:
            df['Data de Atribuição'] = pd.to_datetime(df['Data de Atribuição']).dt.strftime('%d/%m/%Y %H:%M:%S')
        if "Data de Finalização" in df.columns:
            df['Data de Finalização'] = pd.to_datetime(df['Data de Finalização']).dt.strftime('%d/%m/%Y %H:%M:%S')

        nome_arquivo_saida = 'relatorio_desempenho.xlsx'
        df.to_excel(nome_arquivo_saida, index=False, engine='openpyxl')

        print("\n--- Relatório Gerado com Sucesso! ---")
        print(f"O arquivo '{nome_arquivo_saida}' foi salvo na pasta do projeto.")

    except Exception as e:
        print(f"ERRO ao gerar o arquivo Excel: {e}")

    finally:
        client.close()
        print("Conexão com MongoDB fechada.")


# --- Roda a função principal ---
if __name__ == "__main__":
    exportar_relatorio()