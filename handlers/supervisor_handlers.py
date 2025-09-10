# handlers/supervisor_handlers.py

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from handlers.relatorios_handlers import gerar_relatorio_equipe


async def supervisor_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    role = context.user_data.get('vendedor_logado', {}).get('role')
    if role not in ['supervisor', 'administrador']:
        await update.message.reply_text("Comando não reconhecido.")
        return

    keyboard = [[InlineKeyboardButton("📊 Desempenho da Equipe (Hoje)", callback_data="sup_desempenho_hoje")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    message_text = "🔰 <b>Painel de Supervisor</b>\n\nSelecione uma opção:"

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='HTML')
    else:
        await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode='HTML')


async def desempenho_equipe_hoje(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    supervisor_id = context.user_data['vendedor_logado']['_id']
    relatorio = await gerar_relatorio_equipe(supervisor_id, context, "hoje")

    keyboard = [[InlineKeyboardButton("⬅️ Voltar ao Painel Supervisor", callback_data="sup_back_to_main")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(relatorio, reply_markup=reply_markup, parse_mode='MarkdownV2')


async def supervisor_back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await supervisor_panel(update, context)
