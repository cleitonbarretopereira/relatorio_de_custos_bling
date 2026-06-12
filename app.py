import streamlit as st
import sqlite3
import pandas as pd
import time
import requests
import json
import io
import os
from dotenv import load_dotenv

load_dotenv()  # Carrega as variáveis de ambiente do arquivo .env

def configurar_banco():
    conexao = sqlite3.connect("custos_fabrica.db")
    cursor = conexao.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS produtos (
            id_produto INTEGER PRIMARY KEY,
            sku TEXT,
            nome TEXT,
            custo REAL
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS estruturas (
            id_pai INTEGER,
            id_insumo INTEGER,
            qtde_unidade REAL
        )
    """)
    conexao.commit()
    conexao.close()

CREDENCIAIS = "tokens.json"

# --- NOVA FUNÇÃO DE CARREGAR TOKENS DA NUVEM ---
def carregar_tokens():
    bin_id = os.getenv("JSONBIN_BIN_ID")
    master_key = os.getenv("JSONBIN_MASTER_KEY")
    
    if not bin_id or not master_key:
        return None
        
    url = f"https://api.jsonbin.io/v3/b/{bin_id}"
    headers = {
        "X-Master-Key": master_key
    }
    
    try:
        # Pede para o JSONBin o arquivo
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            # O JSONBin guarda o nosso arquivo dentro de uma chave chamada "record"
            return res.json().get("record") 
    except Exception as e:
        st.sidebar.error(f"Erro ao ler o cofre: {e}")
        
    return None

def renovar_token_automatico():
    global HEADERS
    
    # Busca as credenciais direto do seu arquivo .env externo
    client_id = os.getenv("BLING_CLIENT_ID")
    client_secret = os.getenv("BLING_CLIENT_SECRET")
    
    # Garante que o processo pare caso o arquivo .env esteja desconfigurado
    if not client_id or not client_secret:
        st.sidebar.error("❌ Credenciais BLING_CLIENT_ID ou BLING_CLIENT_SECRET não encontradas no arquivo .env")
        return False
        
    tokens_atuais = carregar_tokens()
    if not tokens_atuais:
        return False
        
    # --- A PARTE QUE ESTAVA FALTANDO COMEÇA AQUI ---
    refresh_token = tokens_atuais.get("refresh_token")
    url_token = "https://api.bling.com.br/Api/v3/oauth/token"
    
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
    }
    
    try:
        # Faz o pedido de renovação pro Bling
        res = requests.post(url_token, auth=(client_id, client_secret), data=data)
        
        if res.status_code == 200:
            novos_tokens = res.json()
            
            # --- SALVA O NOVO TOKEN NO COFRE DA NUVEM (JSONBIN) ---
            bin_id = os.getenv("JSONBIN_BIN_ID")
            master_key = os.getenv("JSONBIN_MASTER_KEY")
            
            if bin_id and master_key:
                url_bin = f"https://api.jsonbin.io/v3/b/{bin_id}"
                headers_bin = {
                    "Content-Type": "application/json",
                    "X-Master-Key": master_key
                }
                # Envia o token novo atualizando o arquivo lá no site
                requests.put(url_bin, json=novos_tokens, headers=headers_bin)
            
            # Atualiza a memória do sistema para continuar trabalhando
            novo_access = novos_tokens.get("access_token")
            HEADERS = {"Authorization": f"Bearer {novo_access}", "Content-Type": "application/json"}
            return True
            
    except Exception as e:
        st.sidebar.error(f"Erro crítico na renovação: {e}")
        
    return False
    
    # Garante que o processo pare caso o arquivo .env esteja desconfigurado
    if not client_id or not client_secret:
        st.sidebar.error("❌ Credenciais BLING_CLIENT_ID ou BLING_CLIENT_SECRET não encontradas no arquivo .env")
        return False
        
    tokens_atuais = carregar_tokens()
    if not tokens_atuais:
        return False

tokens = carregar_tokens()
ACCESS_TOKEN = tokens["access_token"] if tokens else None
BASE_URL = "https://api.bling.com.br/Api/v3"
HEADERS = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}

def request_bling(url):
    time.sleep(0.35) 
    res = requests.get(url, headers=HEADERS) 
    
    if res.status_code == 200:
        return res.json() 
    else:
        st.sidebar.error(f"⚠️ Erro de API (Status {res.status_code}) na URL: {url}")
        return None 

def buscar_itens_pedido(numero_pedido):
    url_busca = f"{BASE_URL}/pedidos/vendas?numero={numero_pedido}"
    resposta_busca = request_bling(url_busca)
    
    if resposta_busca and "data" in resposta_busca and len(resposta_busca["data"]) > 0:
        id_pedido = resposta_busca["data"][0]["id"]
        
        url_detalhes = f"{BASE_URL}/pedidos/vendas/{id_pedido}"
        resposta_detalhes = request_bling(url_detalhes)
        
        if resposta_detalhes and "data" in resposta_detalhes:
            return resposta_detalhes["data"]
            
    return None

def buscar_estrutura(id_produto):
    conexao = sqlite3.connect("custos_fabrica.db")
    cursor = conexao.cursor()
    cursor.execute("SELECT id_insumo, qtde_unidade FROM estruturas WHERE id_pai = ?", (id_produto,))
    resultados = cursor.fetchall()
    
    if resultados:
        conexao.close()
        return [{"produto": {"id": linha[0]}, "quantidade": linha[1]} for linha in resultados]

    url = f"{BASE_URL}/produtos/{id_produto}"
    resposta = request_bling(url)
    
    if resposta and "data" in resposta:
        componentes = resposta["data"].get("estrutura", {}).get("componentes", [])
        for comp in componentes:
            id_insumo = comp.get("produto", {}).get("id")
            qtde = float(comp.get("quantidade", 0))
            cursor.execute("INSERT INTO estruturas (id_pai, id_insumo, qtde_unidade) VALUES (?, ?, ?)", (id_produto, id_insumo, qtde))
        conexao.commit()
        conexao.close()
        return componentes
        
    conexao.close()
    return []

def buscar_custo_e_nome(id_insumo):
    conexao = sqlite3.connect("custos_fabrica.db")
    cursor = conexao.cursor()

    cursor.execute("SELECT nome, custo FROM produtos WHERE id_produto = ?", (id_insumo,))
    resultado = cursor.fetchone()
    
    if resultado:
        conexao.close()
        return resultado[0], resultado[1]

    url = f"{BASE_URL}/produtos/{id_insumo}"
    resposta = request_bling(url)
    
    if resposta and "data" in resposta:
        nome = resposta["data"].get("nome", "Desconhecido")
        custo = float(resposta["data"].get("fornecedor", {}).get("precoCusto", 0))
        cursor.execute("INSERT OR REPLACE INTO produtos (id_produto, sku, nome, custo) VALUES (?, ?, ?, ?)", (id_insumo, "", nome, custo))
        conexao.commit()
        conexao.close()
        return nome, custo
        
    conexao.close()
    return "Erro", 0.0

configurar_banco()

st.set_page_config(page_title="Gerador de Custos", layout="wide")
st.title("🏭Custos de Produção")
# --- INSERIR LOGO ABAIXO DO TITULO DO SISTEMA ---
st.markdown("""
    <style>
    @media print {
        /* Esconde o topo do Streamlit, barra lateral, botões, inputs e avisos */
        #root [data-testid="stHeader"], 
        #root [data-testid="stSidebar"], 
        .stButton, 
        .stTextInput, 
        .stInfo, 
        .stSuccess,
        [data-testid="stElementToolbar"] {
            display: none !important;
        }
        /* Remove a borda cinza das caixas para parecer um documento contínuo */
        .stExpander {
            border: none !important;
            box-shadow: none !important;
        }
        /* Força o expander a ficar aberto na impressão */
        [data-testid="stExpanderDetails"] {
            display: block !important;
        }
    }
    </style>
""", unsafe_allow_html=True)

#st.write("Bem-vindo ao gerador automático de relatórios integrados ao Bling!")
numero_pedido = st.text_input("Digite o **Número do Pedido** de Venda:")

if st.button("**PESQUISAR PEDIDO**"):
    if numero_pedido:
        #st.info(f"Pesquisando...")
        itens_vendidos = buscar_itens_pedido(numero_pedido)
        # Chamamos a função atualizada
        pedido_completo = buscar_itens_pedido(numero_pedido)
        
        if pedido_completo:
            # Extraímos os itens e o nome do cliente de dentro do pedido completo
            itens_vendidos = pedido_completo.get("itens", [])
            nome_cliente = pedido_completo.get("contato", {}).get("nome", "Cliente não identificado")
            
            #st.success(f"Pedido encontrado! Ele possui {len(itens_vendidos)} linha(s) de produto(s).")
            
            # --- NOVIDADE: Exibe o nome do cliente no topo (vai sair no PDF!) ---
            st.markdown(f"## Cliente: **{nome_cliente}**")
            st.write("---")
            
            todas_linhas_excel = []
            linha_atual_excel = 1 # O Excel sempre começa na linha 1
            
            for item in itens_vendidos:
                nome_produto = item.get("descricao", "Produto sem nome")
                qtde_vendida = int(item.get("quantidade", 0))
                id_produto_pai = item.get("produto", {}).get("id")
                sku_produto = item.get("codigo", "S/ SKU") 
                
                with st.expander(f"**📦 {nome_produto}**"):
                    st.write(f"**QTDE:** {qtde_vendida} unidades-------------**SKU:** {sku_produto}") 
                    #st.write(f"**QTDE:** {qtde_vendida} unidades")
                    
                    estrutura = buscar_estrutura(id_produto_pai)
                    dados_tabela = []
                    custo_total_produto = 0.0 
                    
                    # --- MONTAGEM DO CABEÇALHO DO BLOCO PARA O EXCEL ---
                    linha_qtde_pedido = linha_atual_excel # Guarda a linha onde ficará a QTDE mestre
                    
                     #1. Título do Produto
                    todas_linhas_excel.append({"A": nome_produto, "B": "QTDE:", "C": qtde_vendida, "D": "PEDIDDO Nº", "F": numero_pedido})
                    linha_atual_excel += 1
                    
                    todas_linhas_excel.append({"A": "", "B": "", "C": "", "D": "", "E": ""})
                    linha_atual_excel += 1

                    # 2. Subtítulos das Colunas
                    todas_linhas_excel.append({"A": "Componente", "B": "Qtde/Un", "C": "Custo Un", "D": "Qtde Total", "F": "Custo Total"})
                    linha_atual_excel += 1
                    
                    # Linha 4 do bloco: Vazia para dar espaço para as informações abaixo
                    todas_linhas_excel.append({"A": "", "B": "", "C": "", "D": "", "E": ""})
                    linha_atual_excel += 1

                    if estrutura:
                        st.write("**Lista de Componentes:**")
                        
                        for componente in estrutura:
                            id_insumo = componente.get("produto", {}).get("id")
                            qtde_insumo_por_unidade = float(componente.get("quantidade", 0))
                            
                            nome_insumo, custo_unitario = buscar_custo_e_nome(id_insumo)
                            qtde_total_necessaria = qtde_insumo_por_unidade * qtde_vendida
                            custo_total_insumo = custo_unitario * qtde_total_necessaria
                            
                            custo_total_produto += custo_total_insumo
                            
                            # Tabela do Navegador
                            dados_tabela.append({
                                "Componente": nome_insumo,
                                "Qtde Un": qtde_insumo_por_unidade,
                                "Custo Uni": f"R$ {custo_unitario:,.2f}",
                                "Qtde Total": qtde_total_necessaria,
                                "Custo Total": f"R$ {custo_total_insumo:,.2f}"
                            })
                            
                            # --- FÓRMULAS DINÂMICAS PARA O EXCEL ---
                            # D = Multiplica a Qtde Unitária pela Célula de QTDE mestre do bloco (C)
                            formula_total_insumos = f"=B{linha_atual_excel}*C{linha_qtde_pedido}"
                            # E = Multiplica o Total de Insumos (D) pelo Custo Unitário (C)
                            formula_custo_total = f"=D{linha_atual_excel}*C{linha_atual_excel}"
                            
                            todas_linhas_excel.append({
                                "A": nome_insumo, 
                                "B": qtde_insumo_por_unidade, 
                                "C": custo_unitario, 
                                "D": formula_total_insumos, 
                                "F": formula_custo_total
                            })
                            linha_atual_excel += 1
                            
                    else:
                        st.info("ℹ️ Produto sem estrutura cadastrada. Utilizando o custo direto do item.")
                        
                        nome_insumo, custo_unitario = buscar_custo_e_nome(id_produto_pai)
                        qtde_total_necessaria = qtde_vendida
                        custo_total_insumo = custo_unitario * qtde_total_necessaria
                        
                        custo_total_produto += custo_total_insumo
                        
                        dados_tabela.append({
                            "Componente": f"{nome_insumo} (Item Direto)",
                            "Qtde Un": 1.0,
                            "Custo Uni": f"R$ {custo_unitario:,.2f}",
                            "Qtde Total": qtde_total_necessaria,
                            "Custo Total": f"R$ {custo_total_insumo:,.2f}"
                        })
                        
                        formula_total_insumos = f"=B{linha_atual_excel}*C{linha_qtde_pedido}"
                        formula_custo_total = f"=(B{linha_atual_excel}*C{linha_atual_excel})*C${linha_qtde_pedido}"
                        
                        todas_linhas_excel.append({
                            "A": f"{nome_insumo} (Item Direto)", 
                            "B": 1.0, 
                            "C": custo_unitario, 
                            "D": formula_total_insumos, 
                            "F": formula_custo_total
                        })
                        linha_atual_excel += 1
                        
                    st.table(dados_tabela)
                    st.markdown(f"### 💰 Custo Total: **R$ {custo_total_produto:,.2f}**")
                    st.markdown(f"#####   💰    Custo Unitário: **R$ {custo_total_produto / qtde_vendida if qtde_vendida > 0 else 0:,.2f}**")
                    
                    # 3. Adiciona uma linha em branco para separar os blocos de produtos
                    #todas_linhas_excel.append({"A": "", "B": "", "C": "", "D": "", "E": ""})
                    linha_atual_excel += 2 # Pula uma linha extra para espaçamento

           # --- GERADOR DE EXCEL CORRIGIDO (ESTILO CUSTOS.PY) ---
            if todas_linhas_excel:
                st.write("---")
                df_relatorio = pd.DataFrame(todas_linhas_excel)
                buffer_excel = io.BytesIO()
                
                with pd.ExcelWriter(buffer_excel, engine='openpyxl') as writer:
                    # CORREÇÃO 1: header=False impede que o Pandas crie uma linha com "A, B, C, D" no topo
                    df_relatorio.to_excel(writer, index=False, header=False, sheet_name="Custos de Produção")
                    
                    workbook = writer.book
                    worksheet = writer.sheets["Custos de Produção"]
                    
                    # Define larguras ideais para as colunas reais do relatório
                    worksheet.column_dimensions['A'].width = 45  # Componente
                    worksheet.column_dimensions['B'].width = 8.15  # Qtde/Un
                    worksheet.column_dimensions['C'].width = 8.50  # Custo Un
                    worksheet.column_dimensions['D'].width = 9.6  # Qtde Total
                    worksheet.column_dimensions['E'].width = 12  # Custo Total
                    
                    max_row = worksheet.max_row
                    
                    # CORREÇÃO 2: O loop agora apenas varre aplicando máscaras de exibição, sem inventar colunas F e G
                    for row in range(1, max_row + 1):
                        valor_a = worksheet[f"A{row}"].value
                        valor_b = str(worksheet[f"B{row}"].value)
                        
                        # Se for a linha de título do Produto ou a linha de cabeçalho, aplica Negrito
                        if valor_a and ("QTDE" in valor_b or valor_a == "Componente"):
                            for col in ['A', 'B', 'C', 'D', 'E']:
                                worksheet[f"{col}{row}"].font = Font(bold=True)
                        
                        # Se for uma linha comum de insumo, aplica a formatação financeira (igual ao custos.py)
                        elif valor_a and valor_a != "Componente" and valor_b != "None":
                            worksheet[f"C{row}"].number_format = '"R$" #,##0.00'  # Custo Unitário
                            worksheet[f"E{row}"].number_format = '"R$" #,##0.00'  # Custo Total
                            worksheet[f"B{row}"].number_format = '#,##0.000'        # Qtde/Un
                            worksheet[f"D{row}"].number_format = '#,##0.000'        # Qtde Total
                
# --- LINHAS DE TÉRMINO DO RELATÓRIO ---
                    linha_soma = max_row + 2  # Pula uma linha em branco para ficar organizado
                    
                    # 1. Aplica a Soma Total da coluna E
                    worksheet[f"A{linha_soma}"] = "TOTAL"
                    worksheet[f"E{linha_soma}"] = f"=SUM(E5:E{max_row})"  # Soma desde o primeiro insumo (linha 5) até o último
                    
                    # 2. Aplica a divisão para achar o Custo Unitário mestre
                    linha_custo_uni = linha_soma + 1
                    worksheet[f"A{linha_custo_uni}"] = "CUSTO UNITÁRIO"
                    worksheet[f"E{linha_custo_uni}"] = f"=E{linha_soma}/C1"  # Divide o valor da soma pela célula C1 (Qtde do Pedido)
                    
                    # Estiliza as duas novas linhas com Negrito e formato de Moeda R$
                    for r in [linha_soma, linha_custo_uni]:
                        worksheet[f"A{r}"].font = Font(bold=True)
                        worksheet[f"E{r}"].font = Font(bold=True)
                        worksheet[f"E{r}"].number_format = '"R$" #,##0.00'

                st.download_button(
                    label="📥 Baixar Planilha",
                    data=buffer_excel.getvalue(),
                    file_name=f"Custos_Pedido_{numero_pedido}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )