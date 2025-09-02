# handlers/vendedor_handlers.py

import re
import logging
from datetime import datetime, time, UTC
import pytz
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, \
    InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from pymongo.collection import ReturnDocument
from bson.objectid import ObjectId
from bson.errors import InvalidId
from werkzeug.security import check_password_hash

from .common import _enviar_info_cliente, STATUS_MAP, USERNAME, PASSWORD, GET_PHONE, SELECT_BANK, SELECT_RESULT, \
    GET_NOTE, GET_BALANCE_AMOUNT


# ... (todas as outras funções, como start, login, buscar, etc., permanecem as mesmas)
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
        context.user_data['vendedor_logado'] = {"id": vendedor['_id'], "nome": vendedor['nome_vendedor'],
                                                "role": vendedor.get('role', 'vendedor')}
        vendedores_collection.update_one({"_id": vendedor['_id']}, {"$set": {"usuario_telegram": user.id}})
        role = context.user_data['vendedor_logado']['role']
        main_keyboard = [[KeyboardButton("/proximo"), KeyboardButton("/meucliente")],
                         [KeyboardButton("/hoje"), KeyboardButton("/buscar"), KeyboardButton("/filtrar")], ]
        if role in ['supervisor', 'administrador']: main_keyboard.append(
            [KeyboardButton("/supervisor"), KeyboardButton("/admin")])
        main_keyboard.append([KeyboardButton("/logout")])
        reply_markup = ReplyKeyboardMarkup(main_keyboard, resize_keyboard=True)
        await update.message.reply_text(
            f"Login bem-sucedido! Bem-vindo, {vendedor['nome_vendedor']}.\n\nFunção: {role.capitalize()}",
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
        numero_como_int = int(numero_limpo); cliente_encontrado = clientes_collection.find_one(
            {"telefone": {"$in": [numero_limpo, numero_como_int]}})
    except ValueError:
        cliente_encontrado = clientes_collection.find_one({"telefone": numero_limpo})
    if not cliente_encontrado: regex_inteligente = ".*".join(
        list(numero_limpo)); cliente_encontrado = clientes_collection.find_one(
        {"telefone": {"$regex": regex_inteligente}})
    if cliente_encontrado:
        texto_intro = "Cliente encontrado:"
        if cliente_encontrado.get('status') == 'Concluido':
            vendedor_id = context.user_data['vendedor_logado']['id']
            clientes_collection.update_one({"_id": cliente_encontrado['_id']},
                                           {"$set": {"status": "Em_Atendimento", "vendedor_atribuido": vendedor_id},
                                            "$unset": {"status_final": "", "data_finalizacao": ""}});
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
    context.user_data['consulta_resultado'] = resultado_final
    if resultado_final == "Possui Saldo":
        texto_cliente_original = query.message.text_html.split("\n\n--------------------\n")[0];
        banco = context.user_data.get('consulta_banco')
        novo_texto = f"{texto_cliente_original}\n\n--------------------\n<b>Banco:</b> {banco}\n<b>Resultado:</b> Possui Saldo\n\n<b>Qual o valor do saldo?</b> (ex: 1500.50)"
        await query.edit_message_text(text=novo_texto, parse_mode='HTML');
        return GET_BALANCE_AMOUNT
    else:
        return await finalize_consulta(update, context)


async def get_balance_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    saldo_texto = update.message.text
    try:
        saldo_valor = float(saldo_texto.replace("R$", "").replace(".", "").replace(",", ".").strip());
        context.user_data['consulta_saldo'] = saldo_valor
    except ValueError:
        await update.message.reply_text(
            "❌ Valor inválido. Por favor, digite apenas números (ex: 1500.50)."); return GET_BALANCE_AMOUNT
    return await finalize_consulta(update, context)


async def finalize_consulta(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    cliente_id = context.user_data.get('consulta_cliente_id');
    banco = context.user_data.get('consulta_banco');
    resultado = context.user_data.get('consulta_resultado');
    saldo = context.user_data.get('consulta_saldo');
    source = update.callback_query or update
    if not cliente_id or not banco or not resultado: await source.message.reply_text(
        "Ocorreu um erro de sessão. Por favor, inicie o processo novamente."); return ConversationHandler.END
    clientes_collection = context.bot_data['clientes_collection']
    update_doc = {"$set": {"status": "Concluido", "status_final": "Consulta Realizada", "banco_consulta": banco,
                           "resultado_consulta": resultado, "data_finalizacao": datetime.now(UTC)}, "$push": {
        "observacoes": {"nota": f"Consulta no banco {banco} com resultado: {resultado}",
                        "vendedor_nome": context.user_data.get('vendedor_logado', {}).get('nome', 'Desconhecido'),
                        "data": datetime.now(UTC)}}}
    if saldo is not None: update_doc["$set"]["saldo_consulta"] = saldo; update_doc["$push"]["observacoes"][
        "nota"] += f" | Saldo: {saldo:.2f}"
    clientes_collection.update_one({"_id": ObjectId(cliente_id)}, update_doc)
    for key in ['consulta_cliente_id', 'consulta_banco', 'consulta_resultado', 'consulta_saldo']: context.user_data.pop(
        key, None)
    texto_confirmacao = f"Consulta registrada com sucesso!\n<b>Banco:</b> {banco}\n<b>Resultado:</b> {resultado}";
    if saldo is not None: texto_confirmacao += f"\n<b>Saldo:</b> R$ {saldo:.2f}"
    texto_confirmacao += "\n\nUse /proximo para um novo cliente."
    if isinstance(source, Update):
        await source.message.reply_text(texto_confirmacao, parse_mode='HTML')
    else:
        await source.edit_message_text(text=texto_confirmacao, parse_mode='HTML')
    return ConversationHandler.END


async def add_note_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query;
    await query.answer();
    client_id = query.data.split('_', 2)[2];
    context.user_data['note_client_id'] = client_id;
    texto_cliente_original = query.message.text_html
    novo_texto = f"{texto_cliente_original}\n\n--------------------\n<b>Digite a observação que deseja adicionar:</b>";
    await query.edit_message_text(text=novo_texto, parse_mode='HTML');
    return GET_NOTE


async def get_note_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    nota_texto = update.message.text;
    cliente_id = context.user_data.get('note_client_id');
    vendedor_nome = context.user_data.get('vendedor_logado', {}).get('nome', 'Desconhecido')
    if not cliente_id: await update.message.reply_text(
        "Ocorreu um erro de sessão. Por favor, localize o cliente novamente."); return ConversationHandler.END
    nova_nota = {"nota": nota_texto, "vendedor_nome": vendedor_nome, "data": datetime.now(UTC)}
    clientes_collection = context.bot_data['clientes_collection'];
    clientes_collection.update_one({"_id": ObjectId(cliente_id)}, {"$push": {"observacoes": nova_nota}})
    await update.message.reply_text("✅ Nota adicionada com sucesso!")
    cliente_atualizado = clientes_collection.find_one({"_id": ObjectId(cliente_id)})
    if cliente_atualizado: await _enviar_info_cliente(update, context, cliente_atualizado,
                                                      "Cliente atualizado com a nova nota:")
    del context.user_data['note_client_id'];
    return ConversationHandler.END


async def show_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query;
    await query.answer();
    client_id_str = query.data.split('_', 2)[2];
    cliente_id = ObjectId(client_id_str)
    clientes_collection = context.bot_data['clientes_collection'];
    cliente = clientes_collection.find_one({"_id": cliente_id})
    if not cliente: await query.message.reply_text("Cliente não encontrado."); return
    tz = pytz.timezone('America/Sao_Paulo');
    historico_texto = f"📜 <b>Histórico de {cliente['nome_cliente']}</b>\n\n"
    if 'observacoes' in cliente and cliente['observacoes']:
        historico_texto += "<b>--- Observações e Consultas ---</b>\n"
        for nota in sorted(cliente['observacoes'], key=lambda x: x['data']): data_local = nota['data'].astimezone(
            tz).strftime(
            '%d/%m/%Y %H:%M'); historico_texto += f"<b>{data_local}</b> por <i>{nota['vendedor_nome']}</i>:\n - {nota['nota']}\n"
        historico_texto += "\n"
    if cliente.get('status_final') and cliente.get(
        'status') == 'Concluido': historico_texto += f"<b>Status Final:</b> {cliente['status_final']}\n"; historico_texto += f"<b>Finalizado em:</b> {cliente['data_finalizacao'].astimezone(tz).strftime('%d/%m/%Y %H:%M')}\n"
    if len(
        historico_texto.strip()) <= 50: historico_texto = f"Nenhum histórico de observações ou consultas para {cliente['nome_cliente']}."
    keyboard = [[InlineKeyboardButton("⬅️ Voltar ao Cliente", callback_data=f"view_client_{cliente_id}")]];
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text=historico_texto, reply_markup=reply_markup, parse_mode='HTML')


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


# --- FUNÇÃO /PROXIMO ATUALIZADA com lógica de distribuição aleatória ---
async def proximo_cliente(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if 'vendedor_logado' not in context.user_data:
        await update.message.reply_text("Você não está logado.")
        return

    vendedor_id = context.user_data['vendedor_logado']['id']
    clientes_collection = context.bot_data['clientes_collection']

    # Verifica se o vendedor já tem um cliente ativo
    cliente_ativo = clientes_collection.find_one({"vendedor_atribuido": vendedor_id, "status": "Em_Atendimento"})
    if cliente_ativo:
        texto_intro = "Você já tem um cliente em atendimento."
        await _enviar_info_cliente(update, context, cliente_ativo, texto_intro)
        return

    # Tenta pegar um cliente aleatório e travá-lo. Tenta até 3 vezes em caso de colisão.
    for _ in range(3):
        # 1. Seleciona um cliente pendente aleatoriamente
        pipeline = [{"$match": {"status": "Pendente"}}, {"$sample": {"size": 1}}]
        random_clients = list(clientes_collection.aggregate(pipeline))

        if not random_clients:
            await update.message.reply_text("Parabéns! Não há mais clientes pendentes na fila.")
            return

        cliente_candidato = random_clients[0]

        # 2. Tenta "travar" esse cliente específico de forma atômica
        cliente_novo = clientes_collection.find_one_and_update(
            {"_id": cliente_candidato['_id'], "status": "Pendente"},  # Garante que ninguém pegou nesse meio tempo
            {"$set": {
                "status": "Em_Atendimento",
                "vendedor_atribuido": vendedor_id,
                "data_atribuicao": datetime.now(UTC)
            }},
            return_document=ReturnDocument.AFTER
        )

        # Se a operação teve sucesso, o cliente é nosso!
        if cliente_novo:
            context.user_data['cliente_atual_id'] = cliente_novo['_id']
            texto_intro = "<b>Novo Cliente Atribuído!</b>"
            await _enviar_info_cliente(update, context, cliente_novo, texto_intro)
            return  # Sai da função com sucesso

    # Se o loop terminar sem sucesso (3 colisões seguidas, muito raro)
    await update.message.reply_text("A fila está muito concorrida! Tente novamente em alguns segundos.")


async def meu_cliente(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if 'vendedor_logado' not in context.user_data:
        await update.message.reply_text("Você não está logado.")
        return

    vendedor_id = context.user_data['vendedor_logado']['id']
    clientes_collection = context.bot_data['clientes_collection']
    cliente_ativo = clientes_collection.find_one({"vendedor_atribuido": vendedor_id, "status": "Em_Atendimento"})

    if cliente_ativo:
        context.user_data['cliente_atual_id'] = cliente_ativo['_id']
        texto_intro = "Este é o seu cliente atual:"
        await _enviar_info_cliente(update, context, cliente_ativo, texto_intro)
    else:
        await update.message.reply_text("Você não tem nenhum cliente em atendimento no momento. Use /proximo.")


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    if 'vendedor_logado' not in context.user_data or 'cliente_atual_id' not in context.user_data:
        await query.edit_message_text(text="Ocorreu um erro de sessão. Use /proximo ou /buscar novamente.")
        return

    cliente_id = context.user_data['cliente_atual_id']
    callback_status = query.data
    status_final_texto = STATUS_MAP.get(callback_status, "Status Desconhecido")
    clientes_collection = context.bot_data['clientes_collection']

    try:
        clientes_collection.update_one(
            {"_id": ObjectId(cliente_id)},
            {"$set": {"status": "Concluido", "status_final": status_final_texto, "data_finalizacao": datetime.now(UTC)}}
        )
        del context.user_data['cliente_atual_id']
        texto_confirmacao = (
            f"Cliente finalizado com sucesso!\n<b>Status Final:</b> {status_final_texto}\n\n"
            f"Ótimo trabalho! Use /proximo para pegar um novo cliente."
        )
        await query.edit_message_text(text=texto_confirmacao, parse_mode='HTML')
    except Exception as e:
        logging.error(f"Erro ao atualizar cliente: {e}")
        await query.edit_message_text(text="Ocorreu um erro ao atualizar o status.")


async def filtrar_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if 'vendedor_logado' not in context.user_data:
        await update.message.reply_text("Você precisa estar logado para filtrar clientes. Use /login.")
        return

    filtro_keyboard = [
        [InlineKeyboardButton("✅ Com Saldo", callback_data="filtro_com_saldo")],
        [InlineKeyboardButton("Não Autorizado", callback_data="filtro_Nao Autorizado")],
        [InlineKeyboardButton("Sem Saldo", callback_data="filtro_Sem Saldo")],
        [InlineKeyboardButton("Não Elegível", callback_data="filtro_Nao Elegivel")]
    ]
    reply_markup = InlineKeyboardMarkup(filtro_keyboard)
    await update.message.reply_text("Selecione um filtro para listar os clientes:", reply_markup=reply_markup)


async def listar_clientes_filtrados(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if 'vendedor_logado' not in context.user_data:
        await query.edit_message_text("Sessão expirada. Por favor, faça login novamente com /login.")
        return

    vendedor_id = context.user_data['vendedor_logado']['id']
    filtro_selecionado = query.data.split('_', 1)[1]
    clientes_collection = context.bot_data['clientes_collection']

    db_query = {"vendedor_atribuido": vendedor_id}
    titulo = ""
    if filtro_selecionado == "com_saldo":
        db_query["saldo_consulta"] = {"$gt": 0}
        titulo = "Clientes com Saldo Disponível"
    else:
        db_query["resultado_consulta"] = filtro_selecionado
        titulo = f"Clientes com status '{filtro_selecionado}'"

    clientes_encontrados = list(clientes_collection.find(db_query))

    if not clientes_encontrados:
        await query.edit_message_text(f"Nenhum cliente encontrado para o filtro selecionado.")
        return

    keyboard = []
    for cliente in clientes_encontrados:
        texto_botao = f"{cliente['nome_cliente']}"
        if 'saldo_consulta' in cliente:
            texto_botao += f" (R$ {cliente.get('saldo_consulta', 0):.2f})"
        keyboard.append([InlineKeyboardButton(texto_botao, callback_data=f"view_client_{cliente['_id']}")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(f"<b>{titulo}:</b>\nSelecione um para ver os detalhes.", reply_markup=reply_markup,
                                  parse_mode='HTML')