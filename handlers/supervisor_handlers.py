# handlers/supervisor_handlers.py

import logging
from datetime import datetime, time, UTC
import pytz
from collections import Counter
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from bson.objectid import ObjectId
from telegram.helpers import escape_markdown


async def gerar_relatorio_equipe(supervisor_id: ObjectId, context: ContextTypes.DEFAULT_TYPE) -> str:
    vendedores_collection = context.bot_data['vendedores_collection']
    clientes_collection = context.bot_data['clientes_collection']

    supervisor = vendedores_collection.find_one({"_id": supervisor_id})
    if not supervisor:
        return "Supervisor não encontrado."

    vendedores_da_equipe = list(vendedores_collection.find({"supervisor_id": supervisor_id}))
    ids_da_equipe = [v['_id'] for v in vendedores_da_equipe]
    ids_da_equipe.append(supervisor_id)

    tz = pytz.timezone('America/Sao_Paulo');
    hoje = datetime.now(tz).date()
    inicio_dia_utc = tz.localize(datetime.combine(hoje, time.min)).astimezone(pytz.utc)
    fim_dia_utc = tz.localize(datetime.combine(hoje, time.max)).astimezone(pytz.utc)

    pipeline = [
        {"$match": {
            "vendedor_atribuido": {"$in": ids_da_equipe},
            "data_finalizacao": {"$gte": inicio_dia_utc, "$lte": fim_dia_utc}
        }},
        {"$group": {
            "_id": "$vendedor_atribuido",
            "total_finalizados": {"$sum": 1},
            "status_counts": {"$push": "$status_final"}
        }}
    ]
    resultados = list(clientes_collection.aggregate(pipeline))

    nome_supervisor_escapado = escape_markdown(supervisor['nome_vendedor'], version=2)
    if not resultados:
        return f"A equipe de *{nome_supervisor_escapado}* não finalizou clientes hoje."

    nomes_vendedores = {str(v['_id']): v['nome_vendedor'] for v in vendedores_da_equipe}
    nomes_vendedores[str(supervisor_id)] = supervisor['nome_vendedor']

    relatorio = f"📊 *Desempenho da Equipe de {nome_supervisor_escapado} \\- {hoje.strftime('%d/%m/%Y')}*\n\n"
    total_geral = 0
    for res in resultados:
        vendedor_id_str = str(res['_id'])
        nome = nomes_vendedores.get(vendedor_id_str, "Desconhecido")
        total_finalizados = res['total_finalizados']
        total_geral += total_finalizados

        counts = Counter(res['status_counts'])
        detalhes = ", ".join(
            [f"{escape_markdown(status, version=2)}: {count}" for status, count in sorted(counts.items())])

        nome_escapado = escape_markdown(nome, version=2)

        relatorio += f"👤 *{nome_escapado}*: {total_finalizados} finalizados\n"
        relatorio += f"   ┕ {detalhes}\n"

    relatorio += f"\n*Total da Equipe:* {total_geral} clientes"
    return relatorio


async def supervisor_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    role = context.user_data.get('vendedor_logado', {}).get('role')
    if role not in ['supervisor', 'administrador']:
        await update.message.reply_text("Comando não reconhecido.")
        return

    keyboard = [[InlineKeyboardButton("📊 Desempenho da Equipe (Hoje)", callback_data="sup_desempenho_hoje")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    message_text = "🔰 *Painel de Supervisor*\n\nSelecione uma opção:"
    if update.callback_query:
        await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='MarkdownV2')
    else:
        await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode='MarkdownV2')


async def desempenho_equipe_hoje(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    supervisor_id = context.user_data['vendedor_logado']['id']
    relatorio = await gerar_relatorio_equipe(supervisor_id, context)

    keyboard = [[InlineKeyboardButton("⬅️ Voltar ao Painel Supervisor", callback_data="sup_back_to_main")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(relatorio, reply_markup=reply_markup, parse_mode='MarkdownV2')


async def supervisor_back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await supervisor_panel(update, context)