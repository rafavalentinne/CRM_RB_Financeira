# bot.py (versão corrigida e padronizada)

import os
import logging
from dotenv import load_dotenv
import pymongo
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

from handlers.common import *
from handlers.vendedor_handlers import *
from handlers.supervisor_handlers import *
from handlers.admin_handlers import *
from handlers.relatorios_handlers import *


def main() -> None:
    load_dotenv()
    TOKEN = os.getenv('TELEGRAM_TOKEN')
    MONGO_URI = os.getenv('MONGO_URI')

    application = Application.builder().token(TOKEN).build()

    try:
        client = pymongo.MongoClient(MONGO_URI)
        db = client['bot_vendas']

        application.bot_data['vendedores_collection'] = db['vendedores']
        application.bot_data['clientes_collection'] = db['clientes']
        application.bot_data['mensagens_collection'] = db['mensagens']
        application.bot_data['bases'] = db['bases']

        print("Conectado ao MongoDB para o bot.")
    except Exception as e:
        print(f"Erro ao conectar ao MongoDB: {e}")
        return

    # -------------------------------
    # Conversações
    # -------------------------------
    login_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("login", login_start)],
        states={
            USERNAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_username),
                MessageHandler(filters.COMMAND, login_unexpected_command)
            ],
            PASSWORD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_password),
                MessageHandler(filters.COMMAND, password_unexpected_command)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    search_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("buscar", buscar_start)],
        states={GET_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, buscar_telefone)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    consulta_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_consulta, pattern="^start_consulta_")],
        states={
            SELECT_BANK: [CallbackQueryHandler(select_bank, pattern="^banco_")],
            SELECT_RESULT: [CallbackQueryHandler(select_result, pattern="^resultado_")],
            GET_BALANCE_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_balance_amount)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    add_note_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_note_start, pattern="^add_note_")],
        states={GET_NOTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_note_text)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    admin_add_user_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_add_user_start, pattern="^admin_add_user$")],
        states={
            GET_NEW_USER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_new_user_name)],
            GET_NEW_USER_LOGIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_new_user_login)],
            GET_NEW_USER_PASS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_new_user_password)],
            GET_NEW_USER_ROLE: [CallbackQueryHandler(get_new_user_role, pattern="^role_")],
            GET_NEW_USER_SUPERVISOR: [CallbackQueryHandler(get_new_user_supervisor, pattern="^supervisor_")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    add_msg_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_add_message_start, pattern="^admin_add_msg$")],
        states={
            GET_MSG_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_msg_name)],
            GET_MSG_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_msg_text)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    edit_user_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_edit_user_start, pattern="^admin_edit_user$")],
        states={
            SELECT_USER_TO_EDIT: [CallbackQueryHandler(select_user_to_edit, pattern="^edit_user_")],
            CHOOSE_EDIT_ACTION: [
                CallbackQueryHandler(prompt_change_role, pattern="^edit_choice_role$"),
                CallbackQueryHandler(prompt_change_supervisor, pattern="^edit_choice_supervisor$"),
                CallbackQueryHandler(admin_edit_user_start, pattern="^admin_edit_user_start$")
            ],
            EDIT_USER_ROLE: [CallbackQueryHandler(update_user_role, pattern="^role_")],
            EDIT_USER_SUPERVISOR: [CallbackQueryHandler(update_user_supervisor, pattern="^new_supervisor_")],
        },
        fallbacks=[
            CallbackQueryHandler(admin_edit_user_end, pattern="^admin_manage_users$"),
            CommandHandler("cancel", cancel)
        ],
        per_message=False,
    )

    # -------------------------------
    # Registro de Handlers
    # -------------------------------
    application.add_handler(CommandHandler("start", start))
    application.add_handler(login_conv_handler)
    application.add_handler(search_conv_handler)
    application.add_handler(consulta_conv_handler)
    application.add_handler(add_note_conv_handler)
    application.add_handler(admin_add_user_conv_handler)
    application.add_handler(add_msg_conv_handler)
    application.add_handler(edit_user_conv_handler)
    application.add_handler(CommandHandler("proximo", proximo_cliente))
    application.add_handler(CommandHandler("meucliente", meu_cliente))
    application.add_handler(CommandHandler("hoje", clientes_hoje))
    application.add_handler(CommandHandler("filtrar", filtrar_start))
    application.add_handler(CommandHandler("supervisor", supervisor_panel))
    application.add_handler(CommandHandler("admin", admin_panel))
    application.add_handler(CommandHandler("logout", logout))
    application.add_handler(CommandHandler("relatorios", relatorios_panel_inicial))

    # -------------------------------
    # Callbacks
    # -------------------------------
    application.add_handler(CallbackQueryHandler(button_callback, pattern="^status_"))
    application.add_handler(CallbackQueryHandler(view_client_details, pattern="^view_client_"))
    application.add_handler(CallbackQueryHandler(listar_clientes_filtrados, pattern="^filtro_"))
    application.add_handler(CallbackQueryHandler(show_history, pattern="^show_history_"))
    application.add_handler(CallbackQueryHandler(desempenho_equipe_hoje, pattern="^sup_desempenho_hoje$"))
    application.add_handler(CallbackQueryHandler(supervisor_back_to_main, pattern="^sup_back_to_main$"))
    application.add_handler(CallbackQueryHandler(admin_stats_menu, pattern="^admin_stats_menu$"))
    application.add_handler(CallbackQueryHandler(admin_manage_users, pattern="^admin_manage_users$"))
    application.add_handler(CallbackQueryHandler(admin_manage_messages, pattern="^admin_manage_messages$"))
    application.add_handler(CallbackQueryHandler(admin_list_messages, pattern="^admin_list_msg$"))
    application.add_handler(CallbackQueryHandler(admin_back_to_menu, pattern="^admin_back_to_main$"))
    application.add_handler(CallbackQueryHandler(admin_stats_geral, pattern="^admin_stats_geral$"))
    application.add_handler(CallbackQueryHandler(admin_select_supervisor, pattern="^admin_select_supervisor$"))
    application.add_handler(CallbackQueryHandler(admin_show_supervisor_stats, pattern="^admin_sup_stats_"))
    application.add_handler(CallbackQueryHandler(admin_show_autonomos_stats, pattern="^admin_stats_autonomos$"))
    application.add_handler(CallbackQueryHandler(admin_toggle_base_status, pattern="^admin_toggle_base_"))
    application.add_handler(CallbackQueryHandler(admin_manage_bases, pattern="^admin_manage_bases$"))
    application.add_handler(CallbackQueryHandler(relatorios_panel_inicial, pattern="^relatorio_voltar_inicial$"))
    application.add_handler(CallbackQueryHandler(selecionar_periodo_para_relatorio, pattern="^relatorio_geral$"))
    application.add_handler(CallbackQueryHandler(selecionar_periodo_para_relatorio, pattern="^relatorio_totais$"))
    application.add_handler(CallbackQueryHandler(selecionar_supervisor_para_relatorio, pattern="^relatorio_por_supervisor$"))
    application.add_handler(CallbackQueryHandler(gerar_relatorio_geral, pattern="^gerar_relatorio_geral_"))
    application.add_handler(CallbackQueryHandler(gerar_relatorio_de_totais, pattern="^gerar_relatorio_totais_"))
    application.add_handler(CallbackQueryHandler(selecionar_periodo_para_supervisor, pattern="^selecionar_periodo_sup_"))
    application.add_handler(CallbackQueryHandler(gerar_relatorio_de_supervisor, pattern="^gerar_relatorio_sup_"))

    print("Bot iniciado. Pressione Ctrl+C para parar.")
    application.run_polling()


if __name__ == "__main__":
    main()
