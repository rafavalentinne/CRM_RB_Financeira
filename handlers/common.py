# handlers/common.py
import re
import os
import random
import logging
from urllib.parse import quote
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

(USERNAME, PASSWORD, GET_PHONE, SELECT_BANK, SELECT_RESULT, GET_NOTE) = range(6)
(GET_NEW_USER_NAME, GET_NEW_USER_LOGIN, GET_NEW_USER_PASS, GET_NEW_USER_ROLE, GET_NEW_USER_SUPERVISOR) = range(6, 11)
GET_MSG_NAME, GET_MSG_TEXT = range(11, 13)
GET_BALANCE_AMOUNT = range(13, 14)
SELECT_USER_TO_EDIT, CHOOSE_EDIT_ACTION, EDIT_USER_ROLE, EDIT_USER_SUPERVISOR = range(14, 18)

STATUS_MAP = {"status_contatado": "✅ Contatado", "status_venda_fechada": "💰 Venda Fechada",
              "status_sem_interesse": "❌ Sem Interesse", "status_sem_whatsapp": "📵 Sem WhatsApp"}


def is_admin(context: ContextTypes.DEFAULT_TYPE) -> bool:
    if 'vendedor_logado' in context.user_data:
        if context.user_data ['vendedor_logado'].get('role') == 'administrador': return True
    return False


async def _enviar_info_cliente(update: Update, context: ContextTypes.DEFAULT_TYPE, cliente: dict,
                               texto_introducao: str):
    telefone_bruto = cliente ['telefone'];
    numero_limpo = re.sub(r'\D', '', str(telefone_bruto));
    whatsapp_url = f"https://wa.me/55{numero_limpo}"
    mensagens_collection = context.bot_data.get('mensagens_collection')
    if mensagens_collection is not None:
        mensagens_ativas = list(mensagens_collection.find({"ativo": True}))
        if mensagens_ativas:
            mensagem_escolhida = random.choice(mensagens_ativas) ['texto'];
            primeiro_nome_cliente = str(cliente.get('nome_cliente', '')).split() [0] if cliente.get(
                'nome_cliente') else "Cliente";
            primeiro_nome_vendedor = context.user_data ['vendedor_logado'] ['nome'].split() [0]
            mensagem_personalizada = mensagem_escolhida.replace("{{cliente}}", primeiro_nome_cliente).replace(
                "{{vendedor}}", primeiro_nome_vendedor);
            mensagem_codificada = quote(mensagem_personalizada);
            whatsapp_url = f"https://wa.me/55{numero_limpo}?text={mensagem_codificada}"

    texto_principal = (
        f"<b>Nome:</b> {cliente.get('nome_cliente', 'N/A')}\n<b>CPF:</b> <code>{cliente.get('cpf', 'N/A')}</code>\n<b>Telefone:</b> <code>{cliente.get('telefone', 'N/A')}</code>")
    texto_final = f"{texto_introducao}\n\n{texto_principal}"
    keyboard = [[InlineKeyboardButton("🟢 Chamar no WhatsApp", url=whatsapp_url),
                 InlineKeyboardButton("📵 Sem WhatsApp", callback_data="status_sem_whatsapp")],
                [InlineKeyboardButton("🔍 Consultar no Banco", callback_data=f"start_consulta_{cliente ['_id']}")],
                [InlineKeyboardButton("✅ Contatado", callback_data="status_contatado"),
                 InlineKeyboardButton("❌ Sem Interesse", callback_data="status_sem_interesse")],
                [InlineKeyboardButton("💰 Venda Fechada", callback_data="status_venda_fechada")],
                [InlineKeyboardButton("📜 Ver Histórico", callback_data=f"show_history_{cliente ['_id']}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(texto_final, reply_markup=reply_markup, parse_mode='HTML')
        except Exception as e:
            logging.warning(f"Não foi possível editar a mensagem: {e}"); await update.callback_query.message.reply_text(
                texto_final, reply_markup=reply_markup, parse_mode='HTML')
    else:
        await update.message.reply_text(texto_final, reply_markup=reply_markup, parse_mode='HTML')


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from handlers.admin_handlers import admin_panel
    query = update.callback_query
    if query:
        if "admin_" in query.data or "edit_user" in query.data or "role_" in query.data or "supervisor_" in query.data:
            await admin_panel(update, context)
        else:
            await query.edit_message_text(text="Operação cancelada.")
    else:
        await update.message.reply_text("Operação cancelada.")
    return ConversationHandler.END