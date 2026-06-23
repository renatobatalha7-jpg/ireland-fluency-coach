import streamlit as st
from google import genai
from google.genai import types
import sqlite3
from datetime import datetime, timedelta

# --- CONFIGURAÇÃO MOBILE ---
# Alterado para layout='centered' e sidebar inicial fechada para melhor uso no celular
# --- CONFIGURAÇÃO MOBILE ---
st.set_page_config(page_title="Ireland Fluency Coach", layout="centered", initial_sidebar_state="collapsed")
client = genai.Client(api_key=st.secrets["API_KEY"])

# --- BANCO DE DADOS (Estrutura Completa) ---
conn = sqlite3.connect('meuingles.db', check_same_thread=False)
c = conn.cursor()

c.execute('''CREATE TABLE IF NOT EXISTS usuarios 
             (id INTEGER PRIMARY KEY, nome TEXT, nivel_declarado TEXT, dia_jornada INTEGER)''')
# Tabela para Vocab Tracker (Item solicitado)
c.execute('''CREATE TABLE IF NOT EXISTS vocabulario_diario 
             (id INTEGER PRIMARY KEY, user_id INTEGER, data TEXT, termo_en TEXT, traducao_pt TEXT, exemplo TEXT)''')

try:
    c.execute("ALTER TABLE usuarios ADD COLUMN dia_jornada INTEGER DEFAULT 1")
    conn.commit()
except sqlite3.OperationalError:
    pass

c.execute('''CREATE TABLE IF NOT EXISTS historico_estudos (id INTEGER PRIMARY KEY, user_id INTEGER, data TEXT, frase_usuario TEXT, frase_correta TEXT, nota_pronuncia REAL, feedback_audio TEXT)''')
c.execute('''CREATE TABLE IF NOT EXISTS diario (id INTEGER PRIMARY KEY, user_id INTEGER, data TEXT, conteudo TEXT, correcao TEXT)''')
c.execute('''CREATE TABLE IF NOT EXISTS revisao_espaçada (id INTEGER PRIMARY KEY, user_id INTEGER, frase_id INTEGER, proxima_revisao TEXT, nivel_revisao INTEGER)''')
c.execute('''CREATE TABLE IF NOT EXISTS xp_diario (id INTEGER PRIMARY KEY, user_id INTEGER, data TEXT, xp_ganho INTEGER)''')
c.execute('''CREATE TABLE IF NOT EXISTS missoes_diarias (id INTEGER PRIMARY KEY, user_id INTEGER, data TEXT, desafio_texto TEXT, status TEXT)''')
conn.commit()

# --- FUNÇÕES DE IA ---
def processar_estudo(frase_usuario, audio_part=None, user_id=1):
    modelo = "models/gemini-3.1-flash-lite"
    prompt_gramatica = f"Analyze: '{frase_usuario}'. Return: ❌ [Incorrect], ✅ [Correct], Explanation: [Brief rule in English]"
    resultado = client.models.generate_content(model=modelo, contents=prompt_gramatica).text
    
    if audio_part:
        prompt_pronuncia = "Analyze audio for correctness/rhythm. Return: 1. Score (0-10), 2. Tips in English."
        feedback_audio = client.models.generate_content(model=modelo, contents=[prompt_pronuncia, audio_part]).text
        c.execute("INSERT INTO historico_estudos (user_id, data, frase_usuario, frase_correta, nota_pronuncia, feedback_audio) VALUES (?, ?, ?, ?, ?, ?)",
                  (user_id, datetime.now().strftime("%Y-%m-%d %H:%M"), frase_usuario, "Corrigida via IA", 8.0, feedback_audio))
        conn.commit()
        return resultado, feedback_audio
    return resultado, None

def analisar_performance_professor(user_text, audio_data, scenario):
    modelo = "models/gemini-3.1-flash-lite"
    prompt = f"Teacher Role: Analyze student input '{user_text}' in scenario '{scenario}'. Detail: 1. Grammar, 2. Natural Vocabulary, 3. Pronunciation tips. Keep it professional."
    return client.models.generate_content(model=modelo, contents=[prompt, audio_data]).text

def gerar_relatorio_semanal(user_id):
    uma_semana_atras = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M")
    c.execute("SELECT frase_usuario, nota_pronuncia FROM historico_estudos WHERE user_id = ? AND data >= ?", (user_id, uma_semana_atras))
    dados_semana = c.fetchall()
    c.execute("SELECT termo_en, traducao_pt FROM vocabulario_diario WHERE user_id = ? AND data >= ?", (user_id, uma_semana_atras))
    vocab_semana = c.fetchall()
    modelo = "models/gemini-3.1-flash-lite"
    prompt = f"Professor, analise o histórico semanal: Estudos {dados_semana} e Vocabulário {vocab_semana}. Forneça relatório: 1. Progresso (%), 2. Erros recorrentes, 3. Evolução de vocabulário, 4. Dicas."
    return client.models.generate_content(model=modelo, contents=prompt).text

def sugerir_listening(nivel, foco):
    modelo = "models/gemini-3.1-flash-lite"
    prompt = f"Suggest an English listening resource (link) for a {nivel} level, focusing on {foco}. Also provide 3 comprehension questions."
    return client.models.generate_content(model=modelo, contents=prompt).text

def corrigir_diario(conteudo_diario):
    modelo = "models/gemini-3.1-flash-lite"
    prompt = f"Correct this journal entry for natural English: {conteudo_diario}"
    return client.models.generate_content(model=modelo, contents=prompt).text

def buscar_vocabulario(categoria):
    modelo = "models/gemini-3.1-flash-lite"
    prompt = f"Provide 3 essential words/phrases for '{categoria}' for living in Ireland. Include translation, real sentence, and exercise."
    return client.models.generate_content(model=modelo, contents=prompt).text

def gerar_missao_professor(user_id, dia):
    c.execute("SELECT frase_usuario FROM historico_estudos WHERE user_id = ?", (user_id,))
    historico = str(c.fetchall()[-5:])
    prompt = f"You are an English teacher. The student is on day {dia} of a 90-day challenge. History: {historico}. Propose 4 progressive daily missions."
    missao = client.models.generate_content(model="models/gemini-3.1-flash-lite", contents=prompt).text
    c.execute("INSERT INTO missoes_diarias (user_id, data, desafio_texto, status) VALUES (?, ?, ?, ?)", 
              (user_id, datetime.now().strftime("%Y-%m-%d"), missao, 'Pendente'))
    conn.commit()
    return missao

def adicionar_xp(user_id, pontos):
    c.execute("INSERT INTO xp_diario (user_id, data, xp_ganho) VALUES (?, ?, ?)", 
              (user_id, datetime.now().strftime("%Y-%m-%d"), pontos))
    conn.commit()

# --- DICIONÁRIO COMPLETO DE CENÁRIOS ---
cenarios_completos = {
    "🟢 Sobrevivência (A2-B1)": {
        "Transporte": ["Pedir informações na rua", "Comprar passagem de ônibus", "Conversar com motorista", "Solicitar táxi", "Problema com transporte público", "Alugar bicicleta", "Comprar cartão de transporte", "Perdeu o ônibus", "Perguntar horários", "Solicitar reembolso"],
        "Supermercado e compras": ["Fazer compras no mercado", "Procurar um produto", "Conversar com caixa", "Solicitar troca de produto", "Reclamar de cobrança errada", "Comprar roupas", "Experimentar roupas", "Perguntar sobre promoções", "Comprar eletrônicos", "Solicitar garantia"],
        "Restaurantes e pubs": ["Pedir comida", "Reservar mesa", "Conversar com garçom", "Reclamar de pedido errado", "Dividir conta", "Conhecer pessoas no pub", "Pedir recomendações", "Conversa casual no bar", "Fazer amizade com locais", "Participar de um quiz night"]
    },
    "🟡 Independência (B1-B2)": {
        "Moradia": ["Procurar apartamento", "Conversar com landlord", "Visita ao imóvel", "Negociar aluguel", "Relatar problema na casa", "Solicitar reparo", "Renovar contrato", "Dividir apartamento com roommates", "Receber convidados em casa", "Fazer mudança"],
        "Banco e finanças": ["Abrir conta bancária", "Solicitar cartão", "Problema com pagamento", "Fazer transferência bancária", "Conversar sobre empréstimo", "Alterar dados da conta", "Entender taxas bancárias", "Perdeu o cartão", "Solicitar extrato", "Conversar com atendimento do banco"],
        "Saúde": ["Marcar consulta médica", "Conversar com médico", "Comprar remédio na farmácia", "Explicar sintomas", "Emergência médica", "Fazer exame de sangue", "Conversar com recepcionista", "Consultar dentista", "Marcar vacinação", "Solicitar atestado médico"]
    },
    "🔵 Fluência (B2-C1)": {
        "Trabalho e carreira": ["Conversa com colega de trabalho", "Primeiro dia no emprego", "Pedir ajuda ao supervisor", "Explicar um erro cometido", "Solicitar férias", "Avisar que está doente", "Participar de uma reunião", "Fazer uma apresentação rápida", "Receber feedback do gerente", "Entrevista de emprego"],
        "Entregas (Food Delivery)": ["Buscar pedido no restaurante", "Confirmar endereço do cliente", "Cliente não atende o telefone", "Pedido atrasado", "Problema no aplicativo", "Conversa com outro entregador", "Solicitar suporte da empresa", "Explicar atraso ao cliente", "Encontrar o endereço correto", "Conversa com gerente do restaurante"],
        "Imigração e documentos": ["Conversar com oficial de imigração", "Explicar propósito da viagem", "Renovar visto", "Solicitar documentos", "Atualizar endereço", "Fazer cadastro governamental", "Solicitar PPS Number", "Conversar com funcionário público", "Agendar atendimento", "Resolver pendências documentais"],
        "Vida social": ["Apresentar-se para alguém", "Fazer novos amigos", "Conversa em festa", "Convidar alguém para sair", "Aceitar convite", "Recusar convite educadamente", "Conversar sobre hobbies", "Conversar sobre esportes", "Conversar sobre viagens", "Manter uma conversa de 15 minutos sem interrupções"]
    },
    "🟣 Profissional (C1+)": {
        "Cenários avançados": ["Debater política sem conflito", "Discutir economia", "Defender uma opinião", "Resolver um conflito no trabalho", "Negociar salário", "Liderar uma reunião", "Contar uma história longa", "Explicar um problema técnico", "Participar de networking profissional", "Entrevista de emprego avançada"]
    }
}

# --- INTERFACE ---
st.title("🇮🇪 Ireland Fluency Coach")

c.execute("SELECT id, nome FROM usuarios")
perfis = c.fetchall()
opcoes = ["Novo Usuário"] + [p[1] for p in perfis]
user_choice = st.selectbox("Select Profile", opcoes)

if user_choice == "Novo Usuário":
    nome = st.text_input("Name:")
    nivel = st.selectbox("Level:", ["Básico", "Pré-Intermediário", "Intermediário", "Intermediário Avançado", "Avançado"])
    if st.button("Create Profile"):
        c.execute("INSERT INTO usuarios (nome, nivel_declarado, dia_jornada) VALUES (?, ?, ?)", (nome, nivel, 1))
        conn.commit()
        st.rerun()
else:
    else:
    c.execute("SELECT id, dia_jornada FROM usuarios WHERE nome = ?", (user_choice,))
    dados_user = c.fetchone()
    if dados_user:
        user_id, dia = dados_user
        # MENU MOBILE OTIMIZADO
        with st.expander("📍 Navigation Menu"):
            menu = st.radio("Selecione:", ["Daily Missions", "Core Lab", "Speaking Lab", "Vocab Tracker", "Daily Journal", "Listening Lab", "Review System", "Vocab Lab", "Dashboard"])
        if menu == "Daily Missions":
            st.header(f"🎯 Today's Missions (Day {dia})")
            if st.button("Generate Personalized Mission"):
                st.markdown(gerar_missao_professor(user_id, dia))
            if st.button("Complete Missions (+100 XP)"):
                adicionar_xp(user_id, 100)
                c.execute("UPDATE usuarios SET dia_jornada = dia_jornada + 1 WHERE id = ?", (user_id,))
                conn.commit()
                st.success("Progresso salvo!")

        elif menu == "Core Lab":
            frase = st.text_input("Enter your English sentence:")
            if st.button("Grammar Check") and frase:
                st.markdown(processar_estudo(frase)[0])

        elif menu == "Speaking Lab":
            st.header("🗣️ Real-time Roleplay Mode")
            nivel_s = st.selectbox("Difficulty:", list(cenarios_completos.keys()))
            cat_s = st.selectbox("Category:", list(cenarios_completos[nivel_s].keys()))
            sit_s = st.selectbox("Scenario:", cenarios_completos[nivel_s][cat_s])
            
            if 'chat_hist' not in st.session_state: st.session_state.chat_hist = []
            if st.button("Start New Conversation"): st.session_state.chat_hist = [f"System: Start scenario: {sit_s}"]
            
            user_input = st.text_input("You:")
            audio = st.audio_input("Record voice reply:")
            
            if st.button("Send & Get Teacher Feedback"):
                feedback_professor = "Record and send audio for expert analysis."
                if audio:
                    audio_bytes = types.Part.from_bytes(data=audio.getvalue(), mime_type="audio/wav")
                    feedback_professor = analisar_performance_professor(user_input, audio_bytes, sit_s)
                
                context = "\n".join(st.session_state.chat_hist)
                resp = client.models.generate_content(model="models/gemini-3.1-flash-lite", contents=f"Scenario: {sit_s}. History: {context}. User says: {user_input}").text
                
                st.session_state.chat_hist.append(f"User: {user_input}")
                st.session_state.chat_hist.append(f"IA: {resp}")
                st.info(feedback_professor)
            for msg in st.session_state.chat_hist: st.write(msg)

        elif menu == "Vocab Tracker":
            st.header("📝 Vocab Tracker (New Words)")
            with st.form("add_vocab"):
                en = st.text_input("Term (English):")
                pt = st.text_input("Translation (Português):")
                ex = st.text_area("Example Sentence:")
                if st.form_submit_button("Save Vocabulary"):
                    c.execute("INSERT INTO vocabulario_diario (user_id, data, termo_en, traducao_pt, exemplo) VALUES (?, ?, ?, ?, ?)", 
                              (user_id, datetime.now().strftime("%Y-%m-%d"), en, pt, ex))
                    conn.commit()
                    st.success("Vocabulário registrado!")
            st.subheader("Your Progress")
            c.execute("SELECT termo_en, traducao_pt, exemplo FROM vocabulario_diario WHERE user_id = ? ORDER BY id DESC LIMIT 5", (user_id,))
            for v in c.fetchall(): st.markdown(f"**{v[0]}** (*{v[1]}*) - *{v[2]}*")

        elif menu == "Daily Journal":
            st.header("✍️ Daily Journal")
            q1 = st.text_area("Write about your day:")
            if st.button("Save & Correct"): st.markdown(corrigir_diario(q1))

        elif menu == "Listening Lab":
            st.header("🎧 Listening Lab")
            if st.button("Generate Mission"): st.markdown(sugerir_listening("Intermediário", "Daily Life"))

        elif menu == "Review System":
            st.header("🧠 Review System")
            c.execute("SELECT frase_usuario FROM historico_estudos WHERE user_id = ?", (user_id,))
            for item in c.fetchall(): st.info(f"Review: {item[0]}")

        elif menu == "Vocab Lab":
            st.header("🗂️ Vocab Lab")
            cat_v = st.selectbox("Category:", ["Housing", "Work", "Banking", "Healthcare"])
            if st.button("Generate Vocab"): st.markdown(buscar_vocabulario(cat_v))

        elif menu == "Dashboard":
            st.header("📈 Dashboard")
            xp = c.execute("SELECT SUM(xp_ganho) FROM xp_diario WHERE user_id = ?", (user_id,)).fetchone()[0] or 0
            st.metric("Total XP Earned", xp)
            st.write(f"Day: {dia}/90")
            st.subheader("📊 Avaliação Semanal do Professor")
            if st.button("Gerar Relatório Semanal"):
                with st.spinner("Analisando..."): st.info(gerar_relatorio_semanal(user_id))