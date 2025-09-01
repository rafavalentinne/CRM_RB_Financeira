import os
import re
import random
import logging
from datetime import datetime, time, UTC
import pytz
from urllib.parse import quote
from dotenv import load_dotenv
import pymongo
from pymongo.collection import ReturnDocument
from bson.objectid import ObjectId
from bson.errors import InvalidId
from werkzeug.security import check_password_hash

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, \
    ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
)

# Configuração de logging
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

# Estados das conversas
USERNAME, PASSWORD, GET_PHONE, SELECT_BANK, SELECT_RESULT = range(5)

# Mapeamento de Status
STATUS_MAP = {
    "status_contatado": "✅ Contatado",
    "status_venda_fechada": "💰 Venda Fechada",
    "status_sem_interesse": "❌ Sem Interesse",
    "status_sem_whatsapp": "📵 Sem WhatsApp"
}


# --- FUNÇÃO AUXILIAR (sem botões de nota/histórico) ---
async def _enviar_info_cliente(update: Update, context: ContextTypes.DEFAULT_TYPE, cliente: dict,
                               texto_introducao: str):
    telefone_bruto = cliente['telefone'];
    numero_limpo = re.sub(r'\D', '', str(telefone_bruto));
    whatsapp_url = f"https://wa.me/55{numero_limpo}"
    mensagens_collection = context.bot_data.get('mensagens_collection')
    if mensagens_collection is not None:
        mensagens_ativas = list(mensagens_collection.find({"ativo": True}))
        if mensagens_ativas:
            mensagem_escolhida = random.choice(mensagens_ativas)['texto'];
            primeiro_nome_cliente = cliente['nome_cliente'].split()[0];
            primeiro_nome_vendedor = context.user_data['vendedor_logado']['nome'].split()[0]
            mensagem_personalizada = mensagem_escolhida.replace("{{cliente}}", primeiro_nome_cliente).replace(
                "{{vendedor}}", primeiro_nome_vendedor);
            mensagem_codificada = quote(mensagem_personalizada);
            whatsapp_url = f"https://wa.me/55{numero_limpo}?text={mensagem_codificada}"

    texto_principal = (
        f"<b>Nome:</b> {cliente['nome_cliente']}\n<b>CPF:</b> <code>{cliente['cpf']}</code>\n<b>Telefone:</b> <code>{cliente['telefone']}</code>")
    texto_final = f"{texto_introducao}\n\n{texto_principal}"

    keyboard = [
        [
            InlineKeyboardButton("🟢 Chamar no WhatsApp", url=whatsapp_url),
            InlineKeyboardButton("📵 Sem WhatsApp", callback_data="status_sem_whatsapp")
        ],
        [
            InlineKeyboardButton("🔍 Consultar no Banco", callback_data=f"start_consulta_{cliente['_id']}")
        ],
        [
            InlineKeyboardButton("✅ Contatado", callback_data="status_contatado"),
            InlineKeyboardButton("❌ Sem Interesse", callback_data="status_sem_interesse")
        ],
        [
            InlineKeyboardButton("💰 Venda Fechada", callback_data="status_venda_fechada")
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(texto_final, reply_markup=reply_markup, parse_mode='HTML')
        except Exception as e:
            logging.warning(f"Não foi possível editar a mensagem: {e}")
            await update.callback_query.message.reply_text(texto_final, reply_markup=reply_markup, parse_mode='HTML')
    else:
        await update.message.reply_text(texto_final, reply_markup=reply_markup, parse_mode='HTML')


# --- Funções de Login, Busca, etc. ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user;
    await update.message.reply_html(
        f"Olá {user.mention_html()}! Bem-vindo ao Bot de Vendas.\n\nUse o comando /login para entrar no sistema.")


async def login_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Olá! Por favor, digite seu nome de usuário de login:");
    return USERNAME


async def get_username(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['login_username'] = update.message.text.lower();
    await update.message.reply_text("Obrigado. Agora, por favor, digite sua senha:");
    return PASSWORD


async def get_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    login_username = context.user_data.get('login_username');
    password = update.message.text;
    user = update.effective_user
    if not login_username: await update.message.reply_text(
        "Ocorreu um erro. Por favor, inicie o login novamente com /login."); return ConversationHandler.END
    vendedores_collection = context.bot_data['vendedores_collection'];
    vendedor = vendedores_collection.find_one({"usuario_login": login_username})
    if vendedor and check_password_hash(vendedor['senha_hash'], password):
        context.user_data['vendedor_logado'] = {"id": vendedor['_id'], "nome": vendedor['nome_vendedor']}
        vendedores_collection.update_one({"_id": vendedor['_id']}, {"$set": {"usuario_telegram": user.id}})
        main_keyboard = [[KeyboardButton("/proximo"), KeyboardButton("/meucliente")],
                         [KeyboardButton("/hoje"), KeyboardButton("/buscar")], [KeyboardButton("/filtrar")],
                         [KeyboardButton("/logout")]]
        reply_markup = ReplyKeyboardMarkup(main_keyboard, resize_keyboard=True)
        await update.message.reply_text(
            f"Login bem-sucedido! Bem-vindo, {vendedor['nome_vendedor']}.\n\nUse os botões do menu abaixo para começar.",
            reply_markup=reply_markup)
        return ConversationHandler.END
    else:
        await update.message.reply_text(
            "Usuário ou senha incorretos. Tente novamente com /login."); return ConversationHandler.END


async def buscar_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if 'vendedor_logado' not in context.user_data: await update.message.reply_text(
        "Você precisa estar logado para buscar um cliente. Use /login."); return ConversationHandler.END
    await update.message.reply_text("Digite o número de telefone do cliente que deseja buscar:");
    return GET_PHONE


async def buscar_telefone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    telefone_input = update.message.text;
    numero_limpo = re.sub(r'\D', '', telefone_input)
    if not numero_limpo: await update.message.reply_text(
        "Número de telefone inválido. Tente novamente com /buscar."); return ConversationHandler.END
    clientes_collection = context.bot_data['clientes_collection'];
    cliente_encontrado = None
    try:
        numero_como_int = int(numero_limpo)
        cliente_encontrado = clientes_collection.find_one({"telefone": {"$in": [numero_limpo, numero_como_int]}})
    except ValueError:
        cliente_encontrado = clientes_collection.find_one({"telefone": numero_limpo})
    if not cliente_encontrado:
        regex_inteligente = ".*".join(list(numero_limpo))
        cliente_encontrado = clientes_collection.find_one({"telefone": {"$regex": regex_inteligente}})
    if cliente_encontrado:
        texto_intro = "Cliente encontrado:"
        if cliente_encontrado.get('status') == 'Concluido':
            vendedor_id = context.user_data['vendedor_logado']['id']
            clientes_collection.update_one(
                {"_id": cliente_encontrado['_id']},
                {"$set": {"status": "Em_Atendimento", "vendedor_atribuido": vendedor_id},
                 "$unset": {"status_final": "", "data_finalizacao": ""}})
            texto_intro = "Cliente finalizado foi REABERTO para você:"
        context.user_data['cliente_atual_id'] = cliente_encontrado['_id'];
        await _enviar_info_cliente(update, context, cliente_encontrado, texto_intro)
    else:
        await update.message.reply_text(
            f"Nenhum cliente encontrado com o telefone que contém os números: {numero_limpo}")
    return ConversationHandler.END


async def start_consulta(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query;
    await query.answer();
    client_id = query.data.split('_', 2)[2];
    context.user_data['consulta_cliente_id'] = client_id;
    texto_original = query.message.text_html
    bancos_keyboard = [[InlineKeyboardButton("DREX Pix", callback_data="banco_DREX Pix"),
                        InlineKeyboardButton("Simplix", callback_data="banco_Simplix")],
                       [InlineKeyboardButton("GRANAPIX", callback_data="banco_GRANAPIX"),
                        InlineKeyboardButton("LOTUS", callback_data="banco_LOTUS")],
                       [InlineKeyboardButton("Grandino", callback_data="banco_Grandino"),
                        InlineKeyboardButton("V8", callback_data="banco_V8")],
                       [InlineKeyboardButton("PH Tech", callback_data="banco_PH Tech")]]
    reply_markup = InlineKeyboardMarkup(bancos_keyboard);
    novo_texto = f"{texto_original}\n\n--------------------\n<b>Consulta iniciada. Selecione o banco:</b>";
    await query.edit_message_text(text=novo_texto, reply_markup=reply_markup, parse_mode='HTML');
    return SELECT_BANK


async def select_bank(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query;
    await query.answer();
    banco_selecionado = query.data.split('_', 1)[1];
    context.user_data['consulta_banco'] = banco_selecionado;
    texto_cliente_original = query.message.text_html.split("\n\n--------------------\n")[0]
    resultados_keyboard = [[InlineKeyboardButton("Possui Saldo", callback_data="resultado_Possui Saldo")],
                           [InlineKeyboardButton("Não Autorizado", callback_data="resultado_Nao Autorizado")],
                           [InlineKeyboardButton("Sem Saldo", callback_data="resultado_Sem Saldo")],
                           [InlineKeyboardButton("Não Elegível", callback_data="resultado_Nao Elegivel")]]
    reply_markup = InlineKeyboardMarkup(resultados_keyboard);
    novo_texto = f"{texto_cliente_original}\n\n--------------------\n<b>Banco:</b> {banco_selecionado}\n<b>Qual o resultado da consulta?</b>";
    await query.edit_message_text(text=novo_texto, reply_markup=reply_markup, parse_mode='HTML');
    return SELECT_RESULT


async def select_result(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query;
    await query.answer();
    resultado_final = query.data.split('_', 1)[1];
    cliente_id = context.user_data.get('consulta_cliente_id');
    banco = context.user_data.get('consulta_banco')
    if not cliente_id or not banco: await query.edit_message_text(
        text="Ocorreu um erro de sessão. Por favor, inicie o processo novamente."); return ConversationHandler.END
    clientes_collection = context.bot_data['clientes_collection']
    clientes_collection.update_one(
        {"_id": ObjectId(cliente_id)},
        {"$set": {
            "status": "Concluido", "status_final": "Consulta Realizada",
            "banco_consulta": banco, "resultado_consulta": resultado_final,
            "data_finalizacao": datetime.now(UTC)
        }}
    )
    del context.user_data['consulta_cliente_id'];
    del context.user_data['consulta_banco']
    await query.edit_message_text(
        text=f"Consulta registrada com sucesso!\n<b>Banco:</b> {banco}\n<b>Resultado:</b> {resultado_final}\n\nUse /proximo para um novo cliente.",
        parse_mode='HTML');
    return ConversationHandler.END


async def clientes_hoje(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if 'vendedor_logado' not in context.user_data: await update.message.reply_text("Você não está logado."); return
    vendedor_id = context.user_data['vendedor_logado']['id'];
    clientes_collection = context.bot_data['clientes_collection'];
    tz = pytz.timezone('America/Sao_Paulo');
    hoje = datetime.now(tz).date();
    inicio_dia_utc = tz.localize(datetime.combine(hoje, time.min)).astimezone(pytz.utc);
    fim_dia_utc = tz.localize(datetime.combine(hoje, time.max)).astimezone(pytz.utc)
    query = {"vendedor_atribuido": vendedor_id, "data_finalizacao": {"$gte": inicio_dia_utc, "$lte": fim_dia_utc}};
    clientes_do_dia = list(clientes_collection.find(query).sort("data_finalizacao", -1))
    if not clientes_do_dia: await update.message.reply_text("Você ainda não finalizou nenhum cliente hoje."); return
    keyboard = [];
    [keyboard.append(
        [InlineKeyboardButton(f"{c['nome_cliente']} ({c['status_final']})", callback_data=f"view_client_{c['_id']}")])
     for c in clientes_do_dia]
    reply_markup = InlineKeyboardMarkup(keyboard);
    await update.message.reply_text(
        f"<b>Clientes finalizados hoje ({hoje.strftime('%d/%m/%Y')}):</b>\nSelecione um cliente para ver os detalhes:",
        reply_markup=reply_markup, parse_mode='HTML')


async def view_client_details(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query;
    await query.answer()
    try:
        client_id_str = query.data.split('_', 2)[2]; cliente_id = ObjectId(client_id_str)
    except (IndexError, TypeError, InvalidId):
        await query.message.reply_text("Erro: ID do cliente inválido."); return
    clientes_collection = context.bot_data['clientes_collection'];
    cliente = clientes_collection.find_one({"_id": cliente_id})
    if cliente:
        context.user_data['cliente_atual_id'] = cliente['_id']; await _enviar_info_cliente(update, context, cliente,
                                                                                           "Detalhes do cliente selecionado:")
    else:
        await query.message.reply_text("Cliente não encontrado.")


async def logout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if 'vendedor_logado' not in context.user_data: await update.message.reply_text("Você já não está logado."); return
    context.user_data.clear();
    await update.message.reply_text("Você foi desconectado. Use /login para entrar.",
                                    reply_markup=ReplyKeyboardRemove())


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.edit_message_text(text="Operação cancelada.")
    else:
        await update.message.reply_text("Operação cancelada.")
    return ConversationHandler.END


async def proximo_cliente(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if 'vendedor_logado' not in context.user_data: await update.message.reply_text("Você não está logado."); return
    vendedor_id = context.user_data['vendedor_logado']['id'];
    clientes_collection = context.bot_data['clientes_collection']
    cliente_ativo = clientes_collection.find_one({"vendedor_atribuido": vendedor_id, "status": "Em_Atendimento"})
    if cliente_ativo: context.user_data['cliente_atual_id'] = cliente_ativo[
        '_id']; texto_intro = "Você já tem um cliente em atendimento."; await _enviar_info_cliente(update, context,
                                                                                                   cliente_ativo,
                                                                                                   texto_intro); return
    cliente_novo = clientes_collection.find_one_and_update(
        {"status": "Pendente"},
        {"$set": {"status": "Em_Atendimento", "vendedor_atribuido": vendedor_id, "data_atribuicao": datetime.now(UTC)}},
        return_document=ReturnDocument.AFTER)
    if cliente_novo:
        context.user_data['cliente_atual_id'] = cliente_novo[
            '_id']; texto_intro = "<b>Novo Cliente Atribuído!</b>"; await _enviar_info_cliente(update, context,
                                                                                               cliente_novo,
                                                                                               texto_intro)
    else:
        await update.message.reply_text("Parabéns! Não há mais clientes na fila.")


async def meu_cliente(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if 'vendedor_logado' not in context.user_data: await update.message.reply_text("Você não está logado."); return
    vendedor_id = context.user_data['vendedor_logado']['id'];
    clientes_collection = context.bot_data['clientes_collection']
    cliente_ativo = clientes_collection.find_one({"vendedor_atribuido": vendedor_id, "status": "Em_Atendimento"})
    if cliente_ativo:
        context.user_data['cliente_atual_id'] = cliente_ativo[
            '_id']; texto_intro = "Este é o seu cliente atual:"; await _enviar_info_cliente(update, context,
                                                                                            cliente_ativo, texto_intro)
    else:
        await update.message.reply_text("Você não tem nenhum cliente em atendimento no momento. Use /proximo.")


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query;
    await query.answer()
    if 'vendedor_logado' not in context.user_data or 'cliente_atual_id' not in context.user_data:
        await query.edit_message_text(text="Ocorreu um erro de sessão. Use /proximo ou /buscar novamente.");
        return
    cliente_id = context.user_data['cliente_atual_id'];
    callback_status = query.data;
    status_final_texto = STATUS_MAP.get(callback_status, "Status Desconhecido");
    clientes_collection = context.bot_data['clientes_collection']
    try:
        clientes_collection.update_one(
            {"_id": ObjectId(cliente_id)},
            {"$set": {"status": "Concluido", "status_final": status_final_texto, "data_finalizacao": datetime.now(UTC)}}
        )
        del context.user_data['cliente_atual_id']
        texto_confirmacao = (
            f"Cliente finalizado com sucesso!\n<b>Status Final:</b> {status_final_texto}\n\nÓtimo trabalho! Use /proximo para pegar um novo cliente.")
        await query.edit_message_text(text=texto_confirmacao, parse_mode='HTML')
    except Exception as e:
        logging.error(f"Erro ao atualizar cliente: {e}");
        await query.edit_message_text(text="Ocorreu um erro ao atualizar o status.")


async def filtrar_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if 'vendedor_logado' not in context.user_data: await update.message.reply_text(
        "Você precisa estar logado para filtrar clientes. Use /login."); return
    filtro_keyboard = [[InlineKeyboardButton("Possui Saldo", callback_data="filtro_Possui Saldo")],
                       [InlineKeyboardButton("Não Autorizado", callback_data="filtro_Nao Autorizado")],
                       [InlineKeyboardButton("Sem Saldo", callback_data="filtro_Sem Saldo")],
                       [InlineKeyboardButton("Não Elegível", callback_data="filtro_Nao Elegivel")]]
    reply_markup = InlineKeyboardMarkup(filtro_keyboard);
    await update.message.reply_text("Selecione um status de consulta para listar os clientes:",
                                    reply_markup=reply_markup)


async def listar_clientes_filtrados(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query;
    await query.answer()
    if 'vendedor_logado' not in context.user_data: await query.edit_message_text(
        "Sessão expirada. Por favor, faça login novamente com /login."); return
    vendedor_id = context.user_data['vendedor_logado']['id'];
    filtro_selecionado = query.data.split('_', 1)[1]
    clientes_collection = context.bot_data['clientes_collection'];
    db_query = {"vendedor_atribuido": vendedor_id, "resultado_consulta": filtro_selecionado};
    clientes_encontrados = list(clientes_collection.find(db_query))
    if not clientes_encontrados: await query.edit_message_text(
        f"Nenhum cliente encontrado para o filtro: <b>{filtro_selecionado}</b>", parse_mode='HTML'); return
    keyboard = [];
    [keyboard.append(
        [InlineKeyboardButton(f"{cliente['nome_cliente']}", callback_data=f"view_client_{cliente['_id']}")]) for cliente
     in clientes_encontrados]
    reply_markup = InlineKeyboardMarkup(keyboard);
    await query.edit_message_text(
        f"Clientes com status '<b>{filtro_selecionado}</b>':\nSelecione um para ver os detalhes.",
        reply_markup=reply_markup, parse_mode='HTML')


def main() -> None:
    load_dotenv();
    TOKEN = os.getenv('TELEGRAM_TOKEN');
    MONGO_URI = os.getenv('MONGO_URI');
    application = Application.builder().token(TOKEN).build()
    try:
        client = pymongo.MongoClient(MONGO_URI);
        client.admin.command('ping');
        db = client['bot_vendas']
        application.bot_data['vendedores_collection'] = db['vendedores'];
        application.bot_data['clientes_collection'] = db['clientes'];
        application.bot_data['mensagens_collection'] = db['mensagens']
        print("Conectado ao MongoDB para o bot.")
    except Exception as e:
        print(f"Erro ao conectar ao MongoDB para o bot: {e}"); return

    login_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("login", login_start)],
        states={USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_username)],
                PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_password)], },
        fallbacks=[CommandHandler("cancel", cancel)], )

    search_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("buscar", buscar_start)],
        states={GET_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, buscar_telefone)]},
        fallbacks=[CommandHandler("cancel", cancel)], )

    consulta_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_consulta, pattern="^start_consulta_")],
        states={SELECT_BANK: [CallbackQueryHandler(select_bank, pattern="^banco_")],
                SELECT_RESULT: [CallbackQueryHandler(select_result, pattern="^resultado_")], },
        fallbacks=[CommandHandler("cancel", cancel)], )

    # Registro de Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(login_conv_handler)
    application.add_handler(search_conv_handler)
    application.add_handler(consulta_conv_handler)
    application.add_handler(CommandHandler("proximo", proximo_cliente))
    application.add_handler(CommandHandler("meucliente", meu_cliente))
    application.add_handler(CommandHandler("hoje", clientes_hoje))
    application.add_handler(CommandHandler("filtrar", filtrar_start))
    application.add_handler(CommandHandler("logout", logout))

    application.add_handler(CallbackQueryHandler(button_callback, pattern="^status_"))
    application.add_handler(CallbackQueryHandler(view_client_details, pattern="^view_client_"))
    application.add_handler(CallbackQueryHandler(listar_clientes_filtrados, pattern="^filtro_"))

    print("Bot iniciado. Pressione Ctrl+C para parar.");
    application.run_polling()


if __name__ == "__main__":
    main()