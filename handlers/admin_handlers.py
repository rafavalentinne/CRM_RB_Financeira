# handlers/admin_handlers.py
import logging
from datetime import datetime, time, UTC
import pytz
from collections import Counter
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from bson.objectid import ObjectId
from werkzeug.security import generate_password_hash
from telegram.helpers import escape_markdown

from .common import (
    is_admin, GET_NEW_USER_NAME, GET_NEW_USER_LOGIN, GET_NEW_USER_PASS,
    GET_NEW_USER_ROLE, GET_NEW_USER_SUPERVISOR, GET_MSG_NAME, GET_MSG_TEXT,
    SELECT_USER_TO_EDIT, CHOOSE_EDIT_ACTION, EDIT_USER_ROLE, EDIT_USER_SUPERVISOR
)
from handlers.relatorios_handlers import gerar_relatorio_equipe


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
        [InlineKeyboardButton("✉️ Gerenciar Mensagens", callback_data="admin_manage_messages")],
        [InlineKeyboardButton("🗂️ Gerenciar Bases de Leads", callback_data="admin_manage_bases")]
    ]
    reply_markup = InlineKeyboardMarkup(admin_keyboard)

    message_text = "👑 <b>Painel de Administração</b>\n\nSelecione uma opção:"
    if update.callback_query:
        await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='HTML')
    else:
        await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode='HTML')

async def admin_manage_bases(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(context):
        await query.edit_message_text("Você não tem permissão.")
        return

    bases_collection = context.bot_data['bases']
    todas_as_bases = list(bases_collection.find().sort("data_importacao", -1))
    texto = "<b>🗂️ Gerenciamento de Bases de Leads</b>\n\n"
    keyboard = []

    if not todas_as_bases:
        texto += "_Nenhuma base de leads foi importada ainda._"
    else:
        texto += "Selecione uma base para ativar ou inativar a distribuição:\n\n"
        for base in todas_as_bases:
            status_emoji = "🟢 Ativa" if base.get('ativa', False) else "🔴 Inativa"
            nome_base = base['nome_base']
            texto_botao = f"{status_emoji} - {nome_base}"
            novo_status = not base.get('ativa', False)
            callback = f"admin_toggle_base_{base['_id']}_{novo_status}"
            keyboard.append([InlineKeyboardButton(texto_botao, callback_data=callback)])

    keyboard.append([InlineKeyboardButton("⬅️ Voltar ao Menu Admin", callback_data="admin_back_to_main")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(texto, reply_markup=reply_markup, parse_mode='HTML')


async def admin_toggle_base_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(context):
        await query.edit_message_text("Você não tem permissão.")
        return

    try:
        parts = query.data.split('_')
        novo_status_str = parts[-1]
        base_id_str = parts[-2]
        base_id = ObjectId(base_id_str)
        novo_status = True if novo_status_str == 'True' else False
    except (ValueError, IndexError):
        await query.message.reply_text("Erro ao processar a ação. Tente novamente.")
        await admin_manage_bases(update, context)
        return

    bases_collection = context.bot_data['bases']
    bases_collection.update_one({"_id": base_id}, {"$set": {"ativa": novo_status}})
    await admin_manage_bases(update, context)


async def admin_manage_messages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    source = query or update.message
    if query:
        await query.answer()

    if not is_admin(context):
        await source.reply_text("Você não tem permissão.")
        return

    keyboard = [
        [InlineKeyboardButton("📜 Listar Mensagens", callback_data="admin_list_msg")],
        [InlineKeyboardButton("➕ Adicionar Mensagem", callback_data="admin_add_msg")],
        [InlineKeyboardButton("⬅️ Voltar ao Menu Admin", callback_data="admin_back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    message_text = "<b>✉️ Gerenciamento de Mensagens</b>\n\nSelecione uma opção:"
    if query:
        await query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='HTML')
    else:
        await source.reply_text(message_text, reply_markup=reply_markup, parse_mode='HTML')


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
        texto_resposta = "<b>✉️ Mensagens Cadastradas</b>\n\n"
        for msg in mensagens:
            texto_resposta += (
                f"📝 <b>Template:</b> {msg['nome_template']}<br>"
                f"<b>ID:</b> <code>{msg['_id']}</code><br>"
                f"<b>Texto:</b> {msg['texto']}<br><br>"
            )

    keyboard = [[InlineKeyboardButton("⬅️ Voltar", callback_data="admin_manage_messages")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(texto_resposta, reply_markup=reply_markup, parse_mode='HTML')

async def admin_add_message_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data['new_message_info'] = {}
    await query.message.reply_text(
        "Qual o <b>nome do template</b> para esta mensagem? (ex: Saudação FGTS)",
        parse_mode='HTML'
    )
    return GET_MSG_NAME


async def get_msg_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['new_message_info']['nome'] = update.message.text
    await update.message.reply_text(
        "Nome definido. Agora, digite o <b>texto da mensagem</b>.\nUse <code>{{cliente}}</code> e <code>{{vendedor}}</code> para personalização.",
        parse_mode='HTML'
    )
    return GET_MSG_TEXT


async def get_msg_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    info = context.user_data['new_message_info']
    info['texto'] = update.message.text
    msg_doc = {"nome_template": info['nome'], "texto": info['texto'], "ativo": True}

    context.bot_data['mensagens_collection'].insert_one(msg_doc)

    await update.message.reply_text(f"✅ Mensagem '{info['nome']}' salva com sucesso!")
    context.user_data.pop('new_message_info', None)
    await admin_manage_messages(update, context)
    return ConversationHandler.END


async def admin_manage_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(context):
        await query.edit_message_text("Você não tem permissão.")
        return

    keyboard = [
        [InlineKeyboardButton("➕ Adicionar Usuário", callback_data="admin_add_user")],
        [InlineKeyboardButton("✏️ Modificar Usuário", callback_data="admin_edit_user")],
        [InlineKeyboardButton("⬅️ Voltar ao Menu Admin", callback_data="admin_back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        "👤 <b>Gerenciamento de Usuários</b>\n\nSelecione uma opção:",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )


async def admin_add_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data['new_user_info'] = {}
    await query.message.reply_text(
        "Ok, vamos adicionar um novo usuário.\n\nQual o <b>nome completo</b> dele?",
        parse_mode='HTML'
    )
    return GET_NEW_USER_NAME


async def get_new_user_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['new_user_info']['nome'] = update.message.text
    await update.message.reply_text(
        "Nome definido. Agora, qual será o <b>usuário de login</b>? (ex: joao.silva, tudo minúsculo)",
        parse_mode='HTML'
    )
    return GET_NEW_USER_LOGIN

async def get_new_user_login(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    login = update.message.text.lower()
    if context.bot_data['vendedores_collection'].find_one({"usuario_login": login}):
        await update.message.reply_text("❌ Este login já existe. Por favor, escolha outro.")
        return GET_NEW_USER_LOGIN

    context.user_data['new_user_info']['login'] = login
    await update.message.reply_text(
        "Login definido. Agora, digite uma <b>senha</b> para este usuário.",
        parse_mode='HTML'
    )
    return GET_NEW_USER_PASS


async def get_new_user_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['new_user_info']['senha'] = update.message.text

    keyboard = [
        [InlineKeyboardButton("Vendedor", callback_data="role_vendedor")],
        [InlineKeyboardButton("Supervisor", callback_data="role_supervisor")],
        [InlineKeyboardButton("Administrador", callback_data="role_administrador")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "Senha definida. Qual será a <b>função (role)</b> deste usuário?",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )
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

        keyboard = [
            [InlineKeyboardButton(sup['nome_vendedor'], callback_data=f"supervisor_{sup['_id']}")]
            for sup in supervisores
        ]
        keyboard.append([InlineKeyboardButton("Nenhum/Independente", callback_data="supervisor_None")])
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "Função definida. Agora, selecione o <b>supervisor</b> deste vendedor:",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
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
        "nome_vendedor": info['nome'],
        "usuario_login": info['login'],
        "senha_hash": generate_password_hash(info['senha']),
        "role": info['role'],
        "supervisor_id": supervisor_id,
        "usuario_telegram": None,
        "cliente_atual_id": None,
        "observacoes": []
    }

    context.bot_data['vendedores_collection'].insert_one(vendedor_doc)

    confirmation_message = (
        f"✅ <b>Usuário Criado com Sucesso!</b>\n\n"
        f"<b>Nome:</b> {info['nome']}\n"
        f"<b>Login:</b> {info['login']}\n"
        f"<b>Função:</b> {info['role'].capitalize()}"
    )
    context.user_data.pop('new_user_info', None)

    if update.callback_query:
        await update.callback_query.edit_message_text(confirmation_message, parse_mode='HTML')
    else:
        await update.message.reply_text(confirmation_message, parse_mode='HTML')

    await admin_manage_users(update, context)
    return ConversationHandler.END

async def admin_edit_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if not is_admin(context):
        await query.edit_message_text("Você não tem permissão.")
        return ConversationHandler.END

    vendedores = list(context.bot_data['vendedores_collection'].find())
    if not vendedores:
        await query.edit_message_text(
            "Nenhum usuário cadastrado.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Voltar", callback_data="admin_manage_users")]])
        )
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton(f"{v['nome_vendedor']} ({v.get('role', 'N/D')})", callback_data=f"edit_user_{v['_id']}")]
        for v in vendedores
    ]
    keyboard.append([InlineKeyboardButton("⬅️ Voltar", callback_data="admin_manage_users")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text("Selecione o usuário que deseja modificar:", reply_markup=reply_markup)
    return SELECT_USER_TO_EDIT


async def select_user_to_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = ObjectId(query.data.split('_', 2)[2])
    context.user_data['edit_user_id'] = user_id
    await _show_user_edit_menu(update, context, "O que você deseja alterar?")
    return CHOOSE_EDIT_ACTION


async def _show_user_edit_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, intro_text: str):
    user_id = context.user_data.get('edit_user_id')
    if not user_id:
        return

    vendedores_collection = context.bot_data['vendedores_collection']
    user_data = vendedores_collection.find_one({"_id": user_id})

    supervisor_id = user_data.get('supervisor_id')
    supervisor_name = "Nenhum/Autônomo"
    if supervisor_id:
        supervisor = vendedores_collection.find_one({"_id": supervisor_id})
        if supervisor:
            supervisor_name = supervisor['nome_vendedor']

    user_details = (
        f"👤 <b>Editando Usuário</b>\n\n"
        f"<b>Nome:</b> {user_data['nome_vendedor']}\n"
        f"<b>Login:</b> {user_data['usuario_login']}\n"
        f"<b>Função:</b> {user_data.get('role', 'N/D').capitalize()}\n"
        f"<b>Supervisor:</b> {supervisor_name}\n\n"
        f"{intro_text}"
    )

    keyboard = [
        [InlineKeyboardButton("Alterar Função", callback_data="edit_choice_role")],
        [InlineKeyboardButton("Alterar Supervisor", callback_data="edit_choice_supervisor")],
        [InlineKeyboardButton("⬅️ Voltar à Lista", callback_data="admin_edit_user_start")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.callback_query.edit_message_text(text=user_details, reply_markup=reply_markup, parse_mode='HTML')


async def prompt_change_role(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    keyboard = [
        [InlineKeyboardButton("Vendedor", callback_data="role_vendedor")],
        [InlineKeyboardButton("Supervisor", callback_data="role_supervisor")],
        [InlineKeyboardButton("Administrador", callback_data="role_administrador")],
        [InlineKeyboardButton("⬅️ Cancelar", callback_data=f"edit_user_{context.user_data['edit_user_id']}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text("Selecione a nova função:", reply_markup=reply_markup)
    return EDIT_USER_ROLE


async def update_user_role(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    new_role = query.data.split('_', 1)[1]
    user_id = context.user_data.get('edit_user_id')

    context.bot_data['vendedores_collection'].update_one({"_id": user_id}, {"$set": {"role": new_role}})

    await _show_user_edit_menu(update, context, f"✅ Função alterada para {new_role.capitalize()}!")
    return CHOOSE_EDIT_ACTION


async def prompt_change_supervisor(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    supervisores = list(context.bot_data['vendedores_collection'].find({"role": "supervisor"}))

    keyboard = [
        [InlineKeyboardButton(sup['nome_vendedor'], callback_data=f"new_supervisor_{sup['_id']}")]
        for sup in supervisores
    ]
    keyboard.append([InlineKeyboardButton("Nenhum/Autônomo", callback_data="new_supervisor_None")])
    keyboard.append([InlineKeyboardButton("⬅️ Cancelar", callback_data=f"edit_user_{context.user_data['edit_user_id']}")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text("Selecione o novo supervisor:", reply_markup=reply_markup)
    return EDIT_USER_SUPERVISOR


async def update_user_supervisor(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    try:
        new_sup_id_str = query.data.split('_', 2)[2]
        new_sup_id = None if new_sup_id_str == 'None' else ObjectId(new_sup_id_str)
    except Exception:
        # ID malformatado ou split inesperado
        await query.edit_message_text("ID de supervisor inválido. Tente novamente.")
        return await prompt_change_supervisor(update, context)

    user_id = context.user_data.get('edit_user_id')
    context.bot_data['vendedores_collection'].update_one(
        {"_id": user_id},
        {"$set": {"supervisor_id": new_sup_id}}
    )

    await _show_user_edit_menu(update, context, "✅ Supervisor alterado com sucesso!")
    return CHOOSE_EDIT_ACTION


async def admin_edit_user_end(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
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

    await query.edit_message_text(
        "📊 <b>Estatísticas do Dia</b>\n\nEscolha o tipo de visualização:",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )


async def admin_stats_geral(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(context):
        await query.edit_message_text("Você não tem permissão para ver isso.")
        return

    bases_collection = context.bot_data['bases']
    clientes_collection = context.bot_data['clientes_collection']

    bases_ativas_docs = list(bases_collection.find({"ativa": True}))
    nomes_bases_ativas = [base['nome_base'] for base in bases_ativas_docs]

    filtro_clientes_pendentes = {"status": "Pendente", "nome_base": {"$in": nomes_bases_ativas}}
    pendentes = clientes_collection.count_documents(filtro_clientes_pendentes)

    tz = pytz.timezone('America/Sao_Paulo')
    hoje = datetime.now(tz).date()
    inicio_dia_utc = tz.localize(datetime.combine(hoje, time.min)).astimezone(UTC)
    fim_dia_utc = tz.localize(datetime.combine(hoje, time.max)).astimezone(UTC)

    pipeline = [
        {"$match": {"data_finalizacao": {"$gte": inicio_dia_utc, "$lte": fim_dia_utc}}},
        {"$group": {"_id": "$status_final", "count": {"$sum": 1}}}
    ]
    resultados = list(clientes_collection.aggregate(pipeline))
    total_finalizados = sum(item['count'] for item in resultados)

    relatorio = f"📊 <b>Resumo Geral - {hoje.strftime('%d/%m/%Y')}</b>\n\n"
    relatorio += f"🔸 <b>Fila de Atendimento (Bases Ativas):</b> {pendentes} clientes pendentes\n\n"
    relatorio += f"🔹 <b>Total Finalizados Hoje:</b> {total_finalizados}\n"
    if resultados:
        for item in sorted(resultados, key=lambda x: x['_id'] or ''):
            relatorio += f"  - {item['_id'] or 'Sem Status'}: {item['count']}\n"

    keyboard = [[InlineKeyboardButton("⬅️ Voltar", callback_data="admin_stats_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(relatorio, reply_markup=reply_markup, parse_mode='HTML')


async def admin_select_supervisor(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(context):
        await query.edit_message_text("Você não tem permissão.")
        return

    vendedores_collection = context.bot_data['vendedores_collection']
    supervisores = list(vendedores_collection.find({"role": "supervisor"}))

    if not supervisores:
        await query.edit_message_text(
            "Nenhum supervisor encontrado.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Voltar", callback_data="admin_stats_menu")]])
        )
        return

    keyboard = [
        [InlineKeyboardButton(sup['nome_vendedor'], callback_data=f"admin_sup_stats_{sup['_id']}")]
        for sup in supervisores
    ]
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
    relatorio = await gerar_relatorio_equipe(supervisor_id, context, "hoje")

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
        await query.edit_message_text(
            "Nenhum vendedor autônomo encontrado.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Voltar", callback_data="admin_stats_menu")]])
        )
        return

    ids_autonomos = [v['_id'] for v in autonomos]
    nomes_autonomos = {str(v['_id']): v['nome_vendedor'] for v in autonomos}

    tz = pytz.timezone('America/Sao_Paulo')
    hoje = datetime.now(tz).date()
    inicio_dia_utc = tz.localize(datetime.combine(hoje, time.min)).astimezone(UTC)
    fim_dia_utc = tz.localize(datetime.combine(hoje, time.max)).astimezone(UTC)

    pipeline = [
        {"$match": {"vendedor_atribuido": {"$in": ids_autonomos}, "data_finalizacao": {"$gte": inicio_dia_utc, "$lte": fim_dia_utc}}},
        {"$group": {"_id": "$vendedor_atribuido", "total_finalizados": {"$sum": 1}, "status_counts": {"$push": "$status_final"}}}
    ]
    resultados = list(clientes_collection.aggregate(pipeline))

    relatorio = f"👤 <b>Desempenho de Vendedores Autônomos - {hoje.strftime('%d/%m/%Y')}</b>\n\n"
    if not resultados:
        relatorio += "Nenhum cliente finalizado por vendedores autônomos hoje."
    else:
        for res in resultados:
            nome = nomes_autonomos.get(str(res['_id']), "Desconhecido")
            total = res['total_finalizados']
            counts = Counter(res['status_counts'])
            detalhes = ", ".join([f"{status}: {count}" for status, count in sorted(counts.items())])
            relatorio += f"▪️ <b>{nome}</b>: {total} finalizados\n   - {detalhes}\n"

    keyboard = [[InlineKeyboardButton("⬅️ Voltar", callback_data="admin_stats_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(relatorio, reply_markup=reply_markup, parse_mode='HTML')


async def admin_back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await admin_panel(update, context)

