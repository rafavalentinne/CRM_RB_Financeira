# handlers/admin_handlers.py

import logging
from datetime import datetime, time
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from bson.objectid import ObjectId
from werkzeug.security import generate_password_hash
from telegram.helpers import escape_markdown

from .common import is_admin, GET_NEW_USER_NAME, GET_NEW_USER_LOGIN, GET_NEW_USER_PASS, GET_NEW_USER_ROLE, \
    GET_NEW_USER_SUPERVISOR, GET_MSG_NAME, GET_MSG_TEXT
from .supervisor_handlers import gerar_relatorio_equipe


async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    source_update = update.callback_query or update
    if not is_admin(context):
        if hasattr(source_update, 'message'):
            await source_update.message.reply_text("Comando não reconhecido.")
        return

    if update.callback_query:
        await update.callback_query.answer()

    admin_keyboard = [
        [InlineKeyboardButton("📊 Estatísticas do Dia", callback_data="admin_stats_menu")],
        [InlineKeyboardButton("👤 Gerenciar Usuários", callback_data="admin_manage_users")],
        [InlineKeyboardButton("✉️ Gerenciar Mensagens", callback_data="admin_manage_messages")]
    ]
    reply_markup = InlineKeyboardMarkup(admin_keyboard)
    message_text = "👑 *Painel de Administração*\n\nSelecione uma opção:"

    if update.callback_query:
        await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='MarkdownV2')
    else:
        await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode='MarkdownV2')


async def admin_manage_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(context):
        await query.edit_message_text("Você não tem permissão.")
        return
    keyboard = [
        [InlineKeyboardButton("➕ Adicionar Usuário", callback_data="admin_add_user")],
        [InlineKeyboardButton("⬅️ Voltar ao Menu Admin", callback_data="admin_back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("👤 *Gerenciamento de Usuários*\n\nSelecione uma opção:", reply_markup=reply_markup,
                                  parse_mode='MarkdownV2')


async def admin_add_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data['new_user_info'] = {}
    await query.message.reply_text("Ok, vamos adicionar um novo usuário.\n\nQual o **nome completo** dele?",
                                   parse_mode='Markdown')
    return GET_NEW_USER_NAME


async def get_new_user_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['new_user_info']['nome'] = update.message.text
    await update.message.reply_text(
        "Nome definido. Agora, qual será o **usuário de login**? (ex: joao.silva, tudo minúsculo)",
        parse_mode='Markdown')
    return GET_NEW_USER_LOGIN


async def get_new_user_login(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    login = update.message.text.lower()
    if context.bot_data['vendedores_collection'].find_one({"usuario_login": login}):
        await update.message.reply_text("❌ Este login já existe. Por favor, escolha outro.")
        return GET_NEW_USER_LOGIN
    context.user_data['new_user_info']['login'] = login
    await update.message.reply_text("Login definido. Agora, digite uma **senha** para este usuário.",
                                    parse_mode='Markdown')
    return GET_NEW_USER_PASS


async def get_new_user_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['new_user_info']['senha'] = update.message.text
    keyboard = [
        [InlineKeyboardButton("Vendedor", callback_data="role_vendedor")],
        [InlineKeyboardButton("Supervisor", callback_data="role_supervisor")],
        [InlineKeyboardButton("Administrador", callback_data="role_administrador")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Senha definida. Qual será a **função (role)** deste usuário?",
                                    reply_markup=reply_markup, parse_mode='Markdown')
    return GET_NEW_USER_ROLE


async def get_new_user_role(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    role = query.data.split('_', 1)[1]
    context.user_data['new_user_info']['role'] = role
    if role == 'vendedor':
        supervisores = list(context.bot_data['vendedores_collection'].find({"role": "supervisor"}))
        if not supervisores:
            return await finalize_user_creation(update, context, None)
        keyboard = []
        for sup in supervisores:
            keyboard.append([InlineKeyboardButton(sup['nome_vendedor'], callback_data=f"supervisor_{sup['_id']}")])
        keyboard.append([InlineKeyboardButton("Nenhum/Independente", callback_data="supervisor_None")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Função definida. Agora, selecione o **supervisor** deste vendedor:",
                                      reply_markup=reply_markup, parse_mode='Markdown')
        return GET_NEW_USER_SUPERVISOR
    else:
        return await finalize_user_creation(update, context, None)


async def get_new_user_supervisor(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    supervisor_id_str = query.data.split('_', 1)[1]
    supervisor_id = None if supervisor_id_str == 'None' else ObjectId(supervisor_id_str)
    return await finalize_user_creation(update, context, supervisor_id)


async def finalize_user_creation(update: Update, context: ContextTypes.DEFAULT_TYPE, supervisor_id):
    info = context.user_data['new_user_info']
    vendedor_doc = {
        "nome_vendedor": info['nome'], "usuario_login": info['login'],
        "senha_hash": generate_password_hash(info['senha']), "role": info['role'],
        "supervisor_id": supervisor_id, "usuario_telegram": None,
        "cliente_atual_id": None, "observacoes": []
    }
    context.bot_data['vendedores_collection'].insert_one(vendedor_doc)
    confirmation_message = (
        f"✅ *Usuário Criado com Sucesso!*\n\n*Nome:* {info['nome']}\n*Login:* {info['login']}\n*Função:* {info['role'].capitalize()}")
    context.user_data.pop('new_user_info', None)
    if update.callback_query:
        await update.callback_query.edit_message_text(confirmation_message, parse_mode='Markdown')
    else:
        await update.message.reply_text(confirmation_message, parse_mode='Markdown')
    await admin_manage_users(update, context)
    return ConversationHandler.END


async def admin_stats_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(context):
        await query.edit_message_text("Você não tem permissão.")
        return
    keyboard = [
        [InlineKeyboardButton("🌎 Visão Geral", callback_data="admin_stats_geral")],
        [InlineKeyboardButton("👥 Ver por Supervisor", callback_data="admin_select_supervisor")],
        [InlineKeyboardButton("👤 Ver Vendedores Autônomos", callback_data="admin_stats_autonomos")],
        [InlineKeyboardButton("⬅️ Voltar ao Menu Admin", callback_data="admin_back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("📊 *Estatísticas do Dia*\n\nEscolha o tipo de visualização:",
                                  reply_markup=reply_markup, parse_mode='MarkdownV2')


async def admin_stats_geral(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(context):
        await query.edit_message_text("Você não tem permissão para ver isso.")
        return
    clientes_collection = context.bot_data['clientes_collection']
    tz = pytz.timezone('America/Sao_Paulo')
    hoje = datetime.now(tz).date()
    inicio_dia_utc = tz.localize(datetime.combine(hoje, time.min)).astimezone(pytz.utc)
    fim_dia_utc = tz.localize(datetime.combine(hoje, time.max)).astimezone(pytz.utc)
    pendentes = clientes_collection.count_documents({"status": "Pendente"})
    pipeline = [{"$match": {"data_finalizacao": {"$gte": inicio_dia_utc, "$lte": fim_dia_utc}}},
                {"$group": {"_id": "$status_final", "count": {"$sum": 1}}}]
    resultados = list(clientes_collection.aggregate(pipeline))
    total_finalizados = sum(item['count'] for item in resultados)
    relatorio = f"📊 *Resumo Geral \\- {hoje.strftime('%d/%m/%Y')}*\n\n"
    relatorio += f"🔸 *Fila de Atendimento:* {pendentes} clientes pendentes\n\n"
    relatorio += f"🔹 *Total Finalizados Hoje:* {total_finalizados}\n"
    if resultados:
        for item in sorted(resultados, key=lambda x: x['_id'] or ''):
            status_escapado = escape_markdown(item['_id'] or 'Sem Status', version=2)
            relatorio += f"  \\- {status_escapado}: {item['count']}\n"
    keyboard = [[InlineKeyboardButton("⬅️ Voltar", callback_data="admin_stats_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(relatorio, reply_markup=reply_markup, parse_mode='MarkdownV2')


async def admin_select_supervisor(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(context):
        await query.edit_message_text("Você não tem permissão.")
        return
    vendedores_collection = context.bot_data['vendedores_collection']
    supervisores = list(vendedores_collection.find({"role": "supervisor"}))
    if not supervisores:
        await query.edit_message_text("Nenhum supervisor encontrado.", reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⬅️ Voltar", callback_data="admin_stats_menu")]]))
        return
    keyboard = []
    for sup in supervisores:
        keyboard.append([InlineKeyboardButton(sup['nome_vendedor'], callback_data=f"admin_sup_stats_{sup['_id']}")])
    keyboard.append([InlineKeyboardButton("⬅️ Voltar", callback_data="admin_stats_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("Selecione um supervisor para ver o desempenho da equipe:", reply_markup=reply_markup)


async def admin_show_supervisor_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(context):
        await query.edit_message_text("Você não tem permissão.")
        return

    supervisor_id = ObjectId(query.data.split('_', 3)[3])
    relatorio = await gerar_relatorio_equipe(supervisor_id, context)

    keyboard = [[InlineKeyboardButton("⬅️ Voltar para Seleção", callback_data="admin_select_supervisor")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(relatorio, reply_markup=reply_markup, parse_mode='HTML')


async def admin_show_autonomos_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(context):
        await query.edit_message_text("Você não tem permissão.")
        return
    vendedores_collection = context.bot_data['vendedores_collection']
    clientes_collection = context.bot_data['clientes_collection']
    autonomos = list(vendedores_collection.find({"role": "vendedor", "supervisor_id": None}))
    if not autonomos:
        await query.edit_message_text("Nenhum vendedor autônomo encontrado.", reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⬅️ Voltar", callback_data="admin_stats_menu")]]))
        return
    ids_autonomos = [v['_id'] for v in autonomos]
    nomes_autonomos = {str(v['_id']): v['nome_vendedor'] for v in autonomos}
    tz = pytz.timezone('America/Sao_Paulo')
    hoje = datetime.now(tz).date()
    inicio_dia_utc = tz.localize(datetime.combine(hoje, time.min)).astimezone(pytz.utc)
    fim_dia_utc = tz.localize(datetime.combine(hoje, time.max)).astimezone(pytz.utc)
    pipeline = [
        {"$match": {"vendedor_atribuido": {"$in": ids_autonomos},
                    "data_finalizacao": {"$gte": inicio_dia_utc, "$lte": fim_dia_utc}}},
        {"$group": {"_id": "$vendedor_atribuido", "total_finalizados": {"$sum": 1}}}
    ]
    resultados = list(clientes_collection.aggregate(pipeline))
    relatorio = f"👤 <b>Desempenho de Vendedores Autônomos - {hoje.strftime('%d/%m/%Y')}</b>\n\n"
    if not resultados:
        relatorio += "Nenhum cliente finalizado por vendedores autônomos hoje."
    else:
        for res in resultados:
            nome = nomes_autonomos.get(str(res['_id']), "Desconhecido")
            relatorio += f"▪️ <b>{nome}</b>: {res['total_finalizados']} finalizados\n"
    keyboard = [[InlineKeyboardButton("⬅️ Voltar", callback_data="admin_stats_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(relatorio, reply_markup=reply_markup, parse_mode='HTML')


async def admin_back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await admin_panel(update, context)


async def admin_manage_messages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(context):
        await query.edit_message_text("Você não tem permissão.")
        return

    keyboard = [
        [InlineKeyboardButton("📜 Listar Mensagens", callback_data="admin_list_msg")],
        [InlineKeyboardButton("➕ Adicionar Mensagem", callback_data="admin_add_msg")],
        [InlineKeyboardButton("⬅️ Voltar ao Menu Admin", callback_data="admin_back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("✉️ *Gerenciamento de Mensagens*\n\nSelecione uma opção:", reply_markup=reply_markup,
                                  parse_mode='MarkdownV2')


async def admin_list_messages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(context):
        await query.edit_message_text("Você não tem permissão.")
        return

    mensagens_collection = context.bot_data['mensagens_collection']
    mensagens = list(mensagens_collection.find())

    if not mensagens:
        texto_resposta = "Nenhuma mensagem cadastrada."
    else:
        texto_resposta = "✉️ *Mensagens Cadastradas*\n\n"
        for msg in mensagens:
            nome_template_escapado = escape_markdown(msg['nome_template'], version=2)
            texto_escapado = escape_markdown(msg['texto'], version=2)
            texto_resposta += f"📝 *Template:* {nome_template_escapado}\n"
            texto_resposta += f"*ID:* `{msg['_id']}`\n"
            texto_resposta += f"*Texto:* _{texto_escapado}_\n\n"

    keyboard = [[InlineKeyboardButton("⬅️ Voltar", callback_data="admin_manage_messages")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(texto_resposta, reply_markup=reply_markup, parse_mode='MarkdownV2')


async def admin_add_message_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data['new_message_info'] = {}
    await query.message.reply_text("Qual o **nome do template** para esta mensagem? (ex: Saudação FGTS)",
                                   parse_mode='Markdown')
    return GET_MSG_NAME


async def get_msg_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['new_message_info']['nome'] = update.message.text
    await update.message.reply_text(
        "Nome definido. Agora, digite o **texto da mensagem**.\n"
        "Use `{{cliente}}` e `{{vendedor}}` para personalização. Use quebras de linha normalmente.",
        parse_mode='Markdown'
    )
    return GET_MSG_TEXT


async def get_msg_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    info = context.user_data['new_message_info']
    info['texto'] = update.message.text

    msg_doc = {
        "nome_template": info['nome'],
        "texto": info['texto'],
        "ativo": True
    }
    context.bot_data['mensagens_collection'].insert_one(msg_doc)

    await update.message.reply_text(f"✅ Mensagem '{info['nome']}' salva com sucesso!")

    context.user_data.pop('new_message_info', None)
    await admin_manage_messages(update, context)
    return ConversationHandler.END