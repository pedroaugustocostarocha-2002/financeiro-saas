import streamlit as st
import pandas as pd
import plotly.express as px
import pdfplumber
import re
import time
from google import genai
from supabase import create_client, Client

# --- 1. CONFIGURAÇÃO DA PÁGINA (Obrigatório ser a primeira linha) ---
st.set_page_config(
    page_title="Financeiro SaaS AI", 
    layout="wide",
    page_icon="💰"
)

# --- 2. SUAS CHAVES (SISTEMA HÍBRIDO: NUVEM + LOCAL) ---
try:
    # Tenta pegar dos segredos da nuvem (Streamlit Cloud)
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
    GEMINI_KEY = st.secrets["GEMINI_KEY"]
except:
    # Se falhar (está rodando no seu PC), usa essas aqui:
    SUPABASE_URL = "https://udusmdtvghwahbnnpsjf.supabase.co"
    SUPABASE_KEY = "sb_secret_NRoaIvgqjcp9lEFQCRBscA_nLRkFfTg"
    GEMINI_KEY = "AIzaSyCS6YvYYxJFw0F6U6ivvuvtQlGGy4pnc8I"

MODELO_ESCOLHIDO = "gemini-2.5-flash"

# --- 3. CONEXÃO COM O BANCO E IA (Cache para otimizar) ---
@st.cache_resource
def init_connections():
    try:
        client_ai = genai.Client(api_key=GEMINI_KEY)
        client_db = create_client(SUPABASE_URL, SUPABASE_KEY)
        return client_ai, client_db
    except Exception as e:
        st.error(f"Erro de conexão: {e}")
        return None, None

genai_client, supabase = init_connections()

# --- 4. FUNÇÃO CÉREBRO (CATEGORIZAÇÃO) ---
def categorizar_com_gemini(descricao, valor):
    prompt = f"""
    Aja como um analista financeiro SaaS. Categorize a transação em UMA palavra.
    Categorias aceitas: Alimentação, Transporte, Lazer, Fornecedores, Serviços, Impostos, Salários, Receita, Investimento, Casa, Educação, Saúde.
    
    Transação: {descricao}
    Valor: R$ {valor}
    
    Responda APENAS a categoria.
    """
    
    tentativas = 0
    while tentativas < 3:
        try:
            response = genai_client.models.generate_content(
                model=MODELO_ESCOLHIDO, 
                contents=prompt
            )
            return response.text.strip()
        except Exception as e:
            # Se der erro 429 (Muitos pedidos), espera um pouco
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                time.sleep(10) 
                tentativas += 1
            else:
                return "Outros"
    return "Outros"

# --- 5. FUNÇÃO DE PROCESSAMENTO (LEITURA DO PDF) ---
def processar_pdf(uploaded_file):
    with open("temp_upload.pdf", "wb") as f:
        f.write(uploaded_file.getbuffer())

    # Limpa dados antigos
    supabase.table('transacoes').delete().neq('id', 0).execute()

    transacoes = []
    mapa_meses = {'JAN': '01', 'FEV': '02', 'MAR': '03', 'ABR': '04', 'MAI': '05', 'JUN': '06',
                  'JUL': '07', 'AGO': '08', 'SET': '09', 'OUT': '10', 'NOV': '11', 'DEZ': '12'}

    st.info("🤖 Iniciando processamento inteligente...")
    status_text = st.empty() 
    barra_progresso = st.progress(0)
    
    with pdfplumber.open("temp_upload.pdf") as pdf:
        total_paginas = len(pdf.pages)
        for i, page in enumerate(pdf.pages):
            texto = page.extract_text()
            if not texto: continue
            linhas = texto.split('\n')
            data_atual = ""
            
            for linha in linhas:
                match_data = re.search(r'(\d{2})\s([A-Z]{3})\s(\d{4})', linha)
                if match_data:
                    dia, mes_nome, ano = match_data.groups()
                    mes_numero = mapa_meses.get(mes_nome, '01')
                    data_atual = f"{ano}-{mes_numero}-{dia}"
                    continue

                match_transacao = re.search(r'^(.+?)\s+([\d\.]*,\d{2})$', linha)
                if match_transacao and data_atual:
                    descricao = match_transacao.group(1).strip()
                    valor_str = match_transacao.group(2)
                    
                    if "Saldo" in descricao or "Total de" in descricao: continue
                    
                    valor_float = float(valor_str.replace('.', '').replace(',', '.'))
                    desc_lower = descricao.lower()
                    if any(x in desc_lower for x in ['compra', 'envio', 'enviada', 'pagamento', 'saída']):
                        valor_float = valor_float * -1
                    elif "resgate" in desc_lower or "recebida" in desc_lower or "depósito" in desc_lower:
                        valor_float = abs(valor_float)

                    # --- FEEDBACK VISUAL ---
                    status_text.markdown(f"🧠 A IA está analisando: **{descricao}** ...")
                    
                    categoria = categorizar_com_gemini(descricao, valor_float)
                    
                    transacoes.append({
                        "data_transacao": data_atual,
                        "descricao": descricao,
                        "valor": valor_float,
                        "banco": "Nubank",
                        "categoria": categoria,
                        "comentarios": "Upload via SaaS Dashboard"
                    })
                    
                    time.sleep(4) 

            barra_progresso.progress((i + 1) / total_paginas)

    if transacoes:
        status_text.text("📤 Salvando dados na nuvem...")
        supabase.table('transacoes').insert(transacoes).execute()
        
        barra_progresso.empty()
        status_text.success("✅ Concluído! Atualizando seus gráficos agora...")
        time.sleep(2)
        st.rerun()

# --- 6. INTERFACE (FRONT-END) ---

# Barra Lateral
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/4206/4206233.png", width=50)
    st.header("Área do Cliente")
    st.write("Faça upload do seu extrato PDF para gerar o relatório.")
    
    arquivo = st.file_uploader("Arraste seu Extrato aqui", type="pdf")
    
    if arquivo is not None:
        if st.button("🚀 Processar Extrato com IA", type="primary"):
            processar_pdf(arquivo)

    st.divider()
    st.caption("Sistema v1.0 • Powered by Gemini 2.5")

# Tela Principal
st.title("📊 Painel Financeiro Inteligente")

try:
    response = supabase.table('transacoes').select("*").execute()
    dados = response.data
except:
    dados = []

if not dados:
    st.info("👋 Bem-vindo! Para começar, arraste seu PDF na barra lateral esquerda.")
else:
    df = pd.DataFrame(dados)
    df['data_transacao'] = pd.to_datetime(df['data_transacao'])

    # KPI Cards
    col1, col2, col3 = st.columns(3)
    
    receitas = df[df['valor'] > 0]['valor'].sum()
    despesas = df[df['valor'] < 0]['valor'].sum()
    saldo = receitas + despesas

    col1.metric("💰 Receitas", f"R$ {receitas:,.2f}", delta="Entradas")
    col2.metric("💸 Despesas", f"R$ {despesas:,.2f}", delta="-Saídas", delta_color="inverse")
    col3.metric("🏦 Saldo Líquido", f"R$ {saldo:,.2f}", delta_color="off")

    st.divider()

    # Gráficos
    col_graf1, col_graf2 = st.columns(2)
    
    with col_graf1:
        st.subheader("Onde foi o dinheiro?")
        df_pizza = df[df['valor'] < 0].copy()
        df_pizza['valor'] = df_pizza['valor'].abs()
        
        if not df_pizza.empty:
            fig_pizza = px.pie(df_pizza, values='valor', names='categoria', hole=0.4, color_discrete_sequence=px.colors.sequential.RdBu)
            st.plotly_chart(fig_pizza, use_container_width=True)
        else:
            st.write("Sem despesas registradas.")

    with col_graf2:
        st.subheader("Evolução Diária")
        df_linha = df.groupby('data_transacao')['valor'].sum().reset_index()
        fig_barras = px.bar(df_linha, x='data_transacao', y='valor', color='valor', color_continuous_scale='Bluered_r')
        st.plotly_chart(fig_barras, use_container_width=True)

    # Tabela
    st.subheader("Extrato Detalhado e Categorizado")
    
    categorias = st.multiselect("Filtrar por Categoria", options=df['categoria'].unique())
    if categorias:
        df = df[df['categoria'].isin(categorias)]
        
    st.dataframe(
        df[['data_transacao', 'descricao', 'categoria', 'valor', 'banco']].sort_values(by="data_transacao", ascending=False),
        use_container_width=True,
        hide_index=True
    )