# handlers/relatorios_handlers.py

import logging
from datetime import datetime, timedelta, time
from collections import Counter
from bson.objectid import ObjectId
import pytz
from bson.objectid import ObjectId, InvalidId
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.helpers import escape_markdown
from telegram.error import BadRequest
from bson.objectid import ObjectId

def get_date_ranges():
    tz = pytz.timezone('America/Sao_Paulo')
    today = datetime.now(tz).date()

    # Hoje
    start_of_today = tz.localize(datetime.combine(today, time.min))
    end_of_today = tz.localize(datetime.combine(today, time.max))

    ranges = {
        "hoje": {"start": start_of_today, "end": end_of_today}
    }

    # Ontem
    yesterday = today - timedelta(days=1)
    ranges["ontem"] = {
        "start": tz.localize(datetime.combine(yesterday, time.min)),
        "end": tz.localize(datetime.combine(yesterday, time.max))
    }

    # Semana atual (seg a dom)
    start_of_week = today - timedelta(days=today.weekday())
    end_of_week = start_of_week + timedelta(days=6)
    ranges["semana_atual"] = {
        "start": tz.localize(datetime.combine(start_of_week, time.min)),
        "end": tz.localize(datetime.combine(end_of_week, time.max))
    }

    # Semana passada
    start_of_last_week = start_of_week - timedelta(days=7)
    end_of_last_week = start_of_week - timedelta(days=1)
    ranges["semana_passada"] = {
        "start": tz.localize(datetime.combine(start_of_last_week, time.min)),
        "end": tz.localize(datetime.combine(end_of_last_week, time.max))
    }

    # Mês atual
    start_of_month = today.replace(day=1)
    next_month_start = (start_of_month + timedelta(days=32)).replace(day=1)
    end_of_month = next_month_start - timedelta(days=1)
    ranges["mes_atual"] = {
        "start": tz.localize(datetime.combine(start_of_month, time.min)),
        "end": tz.localize(datetime.combine(end_of_month, time.max))
    }

    # Mês passado
    end_of_last_month = start_of_month - timedelta(days=1)
    start_of_last_month = end_of_last_month.replace(day=1)
    ranges["mes_passado"] = {
        "start": tz.localize(datetime.combine(start_of_last_month, time.min)),
        "end": tz.localize(datetime.combine(end_of_last_month, time.max))
    }

    return ranges


def _extract_period_from_callback(data: str) -> str:
    """
    Extrai o período do callback_data dos botões de relatório.
    Exemplos de data:
      gerar_relatorio_geral_hoje -> 'hoje'
      gerar_relatorio_geral_semana_atual -> 'semana_atual'
      gerar_relatorio_totais_mes_passado -> 'mes_passado'
    """
    parts = data.split('_')
    # Padrões esperados:
    # ['gerar','relatorio','geral','hoje']
    # ['gerar','relatorio','geral','semana','atual']
    # ['gerar','relatorio','totais','mes','passado']
    if len(parts) >= 5 and parts[-2] in ('semana', 'mes'):
        return f"{parts[-2]}_{parts[-1]}"
    return parts[-1]


async def relatorios_panel_inicial(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_role = context.user_data.get('vendedor_logado', {}).get('role')
    if user_role not in ['supervisor', 'administrador']:
        # Caso alguém sem permissão chame /relatorios
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text("Comando não reconhecido.")
        else:
            await update.message.reply_text("Comando não reconhecido.")
        return

    keyboard = []

    if user_role == 'administrador':
        keyboard.append([InlineKeyboardButton("📊 Relatório Geral (por Vendedor)", callback_data="relatorio_geral")])
        keyboard.append([InlineKeyboardButton("📈 Relatório de Totais (por Status)", callback_data="relatorio_totais")])
        keyboard.append([InlineKeyboardButton("👥 Relatório por Supervisor", callback_data="relatorio_por_supervisor")])
    else:
        # Supervisor: mostra o "Geral" filtrado pela própria equipe + Totais
        keyboard.append([InlineKeyboardButton("📊 Relatório da Minha Equipe (por Vendedor)", callback_data="relatorio_geral")])
        keyboard.append([InlineKeyboardButton("📈 Relatório de Totais (por Status)", callback_data="relatorio_totais")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    message_text = "Selecione o tipo de relatório que deseja gerar:"

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(message_text, reply_markup=reply_markup)


async def selecionar_periodo_para_relatorio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    report_type = query.data  # "relatorio_geral" OU "relatorio_totais"

    keyboard = [
        [InlineKeyboardButton("Hoje", callback_data=f"gerar_{report_type}_hoje"),
         InlineKeyboardButton("Ontem", callback_data=f"gerar_{report_type}_ontem")],
        [InlineKeyboardButton("Esta Semana", callback_data=f"gerar_{report_type}_semana_atual"),
         InlineKeyboardButton("Semana Passada", callback_data=f"gerar_{report_type}_semana_passada")],
        [InlineKeyboardButton("Este Mês", callback_data=f"gerar_{report_type}_mes_atual"),
         InlineKeyboardButton("Mês Passado", callback_data=f"gerar_{report_type}_mes_passado")],
        [InlineKeyboardButton("⬅️ Voltar", callback_data="relatorio_voltar_inicial")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("Selecione o período do relatório:", reply_markup=reply_markup)


from telegram.error import BadRequest  # garanta que este import exista no topo do arquivo


async def gerar_relatorio_geral(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    periodo = _extract_period_from_callback(query.data)

    ranges = get_date_ranges()
    date_range = ranges.get(periodo)
    if not date_range:
        await query.edit_message_text("Período inválido.")
        return

    start_date_utc = date_range['start'].astimezone(pytz.utc)
    end_date_utc = date_range['end'].astimezone(pytz.utc)

    clientes_collection = context.bot_data['clientes_collection']
    vendedores_collection = context.bot_data['vendedores_collection']

    # --- Novo: se for supervisor, restringe aos vendedores da própria equipe (aceitando 'id' ou '_id')
    user_ctx = context.user_data.get('vendedor_logado', {}) or {}
    user_role = user_ctx.get('role')

    def _as_object_id(x):
        if isinstance(x, ObjectId):
            return x
        try:
            return ObjectId(x)
        except Exception:
            return x  # deixa como está; se não for ObjectId válido, o match resultará vazio

    if user_role == 'supervisor':
        sup_id = user_ctx.get('id') or user_ctx.get('_id')
        sup_id = _as_object_id(sup_id)
        todos_vendedores = list(
            vendedores_collection.find({"supervisor_id": sup_id}, {"_id": 1, "nome_vendedor": 1})
        )
    else:
        todos_vendedores = list(
            vendedores_collection.find({}, {"_id": 1, "nome_vendedor": 1})
        )

    ids_para_buscar = [v['_id'] for v in todos_vendedores]
    vendedores_map = {str(v['_id']): v.get('nome_vendedor', 'Desconhecido') for v in todos_vendedores}

    # Se a equipe do supervisor estiver vazia, já responde algo amigável
    if user_role == 'supervisor' and not ids_para_buscar:
        keyboard = [[InlineKeyboardButton("⬅️ Voltar", callback_data="relatorio_geral")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        relatorio = (
            f"📊 <b>Relatório da Minha Equipe (por Vendedor)</b>\n"
            f"<b>Período:</b> {periodo.replace('_', ' ').capitalize()} "
            f"({date_range['start'].strftime('%d/%m')} a {date_range['end'].strftime('%d/%m')})\n\n"
            "Nenhum vendedor está associado a você no momento."
        )
        try:
            await query.edit_message_text(relatorio, reply_markup=reply_markup, parse_mode='HTML')
        except BadRequest as e:
            if "Message is not modified" in str(e):
                await query.edit_message_text(relatorio + "\u2060", reply_markup=reply_markup, parse_mode='HTML')
            else:
                raise
        return

    pipeline = [
        {"$match": {
            "vendedor_atribuido": {"$in": ids_para_buscar},
            "data_finalizacao": {"$gte": start_date_utc, "$lte": end_date_utc}
        }},
        {"$group": {
            "_id": "$vendedor_atribuido",
            "total_finalizados": {"$sum": 1},
            "status_counts": {"$push": "$status_final"}
        }},
        {"$sort": {"total_finalizados": -1}}
    ]
    resultados = list(clientes_collection.aggregate(pipeline))

    periodo_str = periodo.replace('_', ' ').capitalize()
    titulo = "Relatório da Minha Equipe (por Vendedor)" if user_role == 'supervisor' else "Relatório Geral por Vendedor"
    relatorio = (
        f"📊 <b>{titulo}</b>\n"
        f"<b>Período:</b> {periodo_str} ({date_range['start'].strftime('%d/%m')} a {date_range['end'].strftime('%d/%m')})\n\n"
    )

    if not resultados:
        relatorio += "Nenhuma atividade registrada neste período."
    else:
        from collections import Counter
        total_geral = 0
        for res in resultados:
            vendedor_id_str = str(res['_id'])
            nome_v = vendedores_map.get(vendedor_id_str, "Desconhecido")
            total_finalizados = res['total_finalizados']
            total_geral += total_finalizados
            counts = Counter(res['status_counts'])
            detalhes = ", ".join([f"{(s or 'Sem Status')}: {c}" for s, c in sorted(counts.items())])
            relatorio += f"👤 <b>{nome_v}</b>: {total_finalizados} finalizados\n   - {detalhes}\n"
        relatorio += f"\n<b>Total Geral:</b> {total_geral} clientes finalizados"

    keyboard = [[InlineKeyboardButton("⬅️ Voltar", callback_data="relatorio_geral")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await query.edit_message_text(relatorio, reply_markup=reply_markup, parse_mode='HTML')
    except BadRequest as e:
        if "Message is not modified" in str(e):
            await query.edit_message_text(relatorio + "\u2060", reply_markup=reply_markup, parse_mode='HTML')
        else:
            raise


async def gerar_relatorio_de_totais(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    periodo = _extract_period_from_callback(query.data)

    ranges = get_date_ranges()
    date_range = ranges.get(periodo)
    if not date_range:
        await query.edit_message_text("Período inválido.")
        return

    start_date_utc = date_range['start'].astimezone(pytz.utc)
    end_date_utc = date_range['end'].astimezone(pytz.utc)

    clientes_collection = context.bot_data['clientes_collection']
    pipeline = [
        {"$match": {"data_finalizacao": {"$gte": start_date_utc, "$lte": end_date_utc}}},
        {"$group": {"_id": "$status_final", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ]
    resultados = list(clientes_collection.aggregate(pipeline))

    periodo_str = periodo.replace('_', ' ').capitalize()
    relatorio = (
        f"📈 <b>Relatório de Totais por Status</b>\n"
        f"<b>Período:</b> {periodo_str} ({date_range['start'].strftime('%d/%m')} a {date_range['end'].strftime('%d/%m')})\n\n"
    )

    if not resultados:
        relatorio += "Nenhuma atividade registrada neste período."
    else:
        total_geral = sum(item['count'] for item in resultados)
        relatorio += f"<b>Total de Clientes Finalizados:</b> {total_geral}\n\n<b>Detalhes:</b>\n"
        for item in resultados:
            status = item['_id'] or "Não especificado"
            relatorio += f"  - {status}: {item['count']}\n"

    keyboard = [[InlineKeyboardButton("⬅️ Voltar", callback_data="relatorio_totais")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await query.edit_message_text(relatorio, reply_markup=reply_markup, parse_mode='HTML')
    except BadRequest as e:
        if "Message is not modified" in str(e):
            await query.edit_message_text(relatorio + "\u2060", reply_markup=reply_markup, parse_mode='HTML')
        else:
            raise



async def selecionar_supervisor_para_relatorio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    vendedores_collection = context.bot_data['vendedores_collection']
    supervisores = list(vendedores_collection.find({"role": "supervisor"}))

    if not supervisores:
        await query.edit_message_text(
            "Nenhum supervisor encontrado.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Voltar", callback_data="relatorio_voltar_inicial")]])
        )
        return

    keyboard = []
    for sup in supervisores:
        keyboard.append([InlineKeyboardButton(sup['nome_vendedor'], callback_data=f"selecionar_periodo_sup_{sup['_id']}")])
    keyboard.append([InlineKeyboardButton("⬅️ Voltar", callback_data="relatorio_voltar_inicial")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("Selecione um supervisor para ver o relatório da equipe:", reply_markup=reply_markup)


async def selecionar_periodo_para_supervisor(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    supervisor_id = query.data.split('_', 3)[3]
    keyboard = [
        [InlineKeyboardButton("Hoje", callback_data=f"gerar_relatorio_sup_{supervisor_id}_hoje"),
         InlineKeyboardButton("Ontem", callback_data=f"gerar_relatorio_sup_{supervisor_id}_ontem")],
        [InlineKeyboardButton("Esta Semana", callback_data=f"gerar_relatorio_sup_{supervisor_id}_semana_atual"),
         InlineKeyboardButton("Semana Passada", callback_data=f"gerar_relatorio_sup_{supervisor_id}_semana_passada")],
        [InlineKeyboardButton("Este Mês", callback_data=f"gerar_relatorio_sup_{supervisor_id}_mes_atual"),
         InlineKeyboardButton("Mês Passado", callback_data=f"gerar_relatorio_sup_{supervisor_id}_mes_passado")],
        [InlineKeyboardButton("⬅️ Voltar para Supervisores", callback_data="relatorio_por_supervisor")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("Selecione o período do relatório para esta equipe:", reply_markup=reply_markup)


async def gerar_relatorio_de_supervisor(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    try:
        parts = query.data.split('_')  # gerar_relatorio_sup_<id>_<periodo...>
        supervisor_id = ObjectId(parts[3])
        periodo = "_".join(parts[4:])
    except (IndexError, InvalidId):
        await query.edit_message_text("Erro ao processar o relatório. Tente novamente.")
        return

    relatorio_texto = await gerar_relatorio_equipe(supervisor_id, context, periodo)

    keyboard = [[InlineKeyboardButton("⬅️ Voltar para Períodos", callback_data=f"selecionar_periodo_sup_{supervisor_id}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Agora usamos HTML para evitar problemas com MarkdownV2
    try:
        await query.edit_message_text(relatorio_texto, reply_markup=reply_markup, parse_mode='HTML')
    except BadRequest as e:
        if "Message is not modified" in str(e):
            await query.edit_message_text(relatorio_texto + "\u2060", reply_markup=reply_markup, parse_mode='HTML')
        else:
            raise


async def gerar_relatorio_equipe(supervisor_id, context: ContextTypes.DEFAULT_TYPE, periodo: str) -> str:
    """
    Gera relatório da equipe de um supervisor para o período informado.
    Retorna string formatada em HTML (robusto à presença de '.', '-', etc.).
    """
    try:
        ranges = get_date_ranges()
        date_range = ranges.get(periodo)
        if not date_range:
            return "❌ Período inválido."

        start_date_utc = date_range['start'].astimezone(pytz.utc)
        end_date_utc = date_range['end'].astimezone(pytz.utc)

        vendedores_collection = context.bot_data['vendedores_collection']
        clientes_collection = context.bot_data['clientes_collection']

        equipe = list(vendedores_collection.find({"supervisor_id": supervisor_id}))
        if not equipe:
            return "Nenhum vendedor encontrado para este supervisor."

        ids_vendedores = [v['_id'] for v in equipe]
        nomes_vendedores = {str(v['_id']): v['nome_vendedor'] for v in equipe}

        pipeline = [
            {"$match": {
                "vendedor_atribuido": {"$in": ids_vendedores},
                "data_finalizacao": {"$gte": start_date_utc, "$lte": end_date_utc}
            }},
            {"$group": {
                "_id": "$vendedor_atribuido",
                "total_finalizados": {"$sum": 1},
                "status_counts": {"$push": "$status_final"}
            }},
            {"$sort": {"total_finalizados": -1}}
        ]

        resultados = list(clientes_collection.aggregate(pipeline))
        periodo_str = periodo.replace("_", " ").capitalize()

        rel = f"📊 <b>Desempenho da Equipe</b>\n<b>Período:</b> {periodo_str}\n\n"

        if not resultados:
            rel += "Nenhuma atividade registrada neste período."
        else:
            for res in resultados:
                vendedor_id = str(res['_id'])
                nome = nomes_vendedores.get(vendedor_id, "Desconhecido")
                total = res['total_finalizados']
                counts = Counter(res['status_counts'])
                detalhes = ", ".join([f"{(s or 'Sem Status')}: {c}" for s, c in sorted(counts.items())])
                rel += f"👤 <b>{nome}</b>: {total} finalizados\n   - {detalhes}\n"

        return rel

    except Exception as e:
        logging.error(f"Erro em gerar_relatorio_equipe: {e}")
        return "⚠️ Ocorreu um erro ao gerar o relatório da equipe."
