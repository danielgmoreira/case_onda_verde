import streamlit as st
import pandas as pd
import plotly.express as px

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Monitoramento Onda Verde - Stone",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Cores da Identidade Visual
COLOR_GREEN = "#00A868"  # Verde Stone
COLOR_RED = "#E04F5F"    # Vermelho Risco
COLOR_BARS = ["#00A868", "#E04F5F"]

# --- 1. CARREGAMENTO E ETL ---
@st.cache_data
def load_data():
    try:
        df = pd.read_excel("tabela.xlsx")
    except FileNotFoundError:
        st.error("❌ Arquivo 'tabela.xlsx' não encontrado. Adicione-o à pasta do projeto.")
        st.stop()

    # Ordenação Temporal
    df = df.sort_values(by=['safra', 'mob'])

    df_plantio = df.groupby(['nr_plantio', 'tipo_semente', 'tipo_solo', 'tipo_plantio', 'safra', 'score_inicial']).agg({
        'dias_contaminados': 'max',       # Se teve contaminação em algum momento
        'qtd_sementes': 'mean'            # Média para corrigir a variação apontada no PDF
    }).reset_index()

    # Flag de Contaminação (1 = Contaminado, 0 = Saudável)
    df_plantio['status'] = df_plantio['dias_contaminados'].apply(lambda x: 'Contaminado' if x > 0 else 'Saudável')
    df_plantio['is_bad'] = df_plantio['dias_contaminados'].apply(lambda x: 1 if x > 0 else 0)

    # Binagem de Score 
    df_plantio['faixa_score'] = pd.cut(
        df_plantio['score_inicial'], 
        bins=[0, 35, 50, 75, 100],
        labels=['Baixo (0-35)', 'Médio (36-50)', 'Alto (51-75)', 'Excelência (>75)']
    )

    return df, df_plantio

# Carregar dados
df_mob, df_plantio = load_data()

# --- 2. SIDEBAR E FILTROS ---
st.sidebar.title("Filtros de Visão")

# Filtro de Safra
all_safras = sorted(df_plantio['safra'].unique())
sel_safra = st.sidebar.multiselect("Safras", all_safras, default=all_safras)

# Filtro de Score
min_s, max_s = int(df_plantio['score_inicial'].min()), int(df_plantio['score_inicial'].max())
range_score = st.sidebar.slider("Score Inicial", min_s, max_s, (min_s, max_s))

# Aplicação dos Filtros
df_filtered = df_plantio[
    (df_plantio['safra'].isin(sel_safra)) & 
    (df_plantio['score_inicial'] >= range_score[0]) &
    (df_plantio['score_inicial'] <= range_score[1])
]

df_filtered['safra'] = df_filtered['safra'].astype(str)

# Filtrar base Mob também (para gráficos temporais)
plantios_selecionados = df_filtered['nr_plantio'].unique()
df_mob_filtered = df_mob[df_mob['nr_plantio'].isin(plantios_selecionados)]

# --- 3. CONTEÚDO PRINCIPAL ---
st.title("🌱 Estudo de Caso: O que está acontecendo com a Onda Verde?")
st.markdown("---")

tab1, tab2, tab3 = st.tabs(["📊 O Negócio & Expansão", "🎯 Problema de Scoragem", "🧬 Análise de Sementes"])


with tab1:
    st.header("Visão Geral da Expansão")

    c1, c2, c3, c4 = st.columns(4)

    vol_total = df_filtered['qtd_sementes'].sum() / 1_000_000
    taxa_contaminacao = df_filtered['is_bad'].mean()

    c1.metric("Volume Total (Mi)", f"{vol_total:.1f} mi")
    c2.metric("Taxa de Contaminação", f"{taxa_contaminacao:.1%}", delta_color="inverse")
    c3.metric("Plantios Analisados", df_filtered.shape[0])
    c4.metric("Safra Mais Recente", str(df_filtered['safra'].max()))

    st.subheader("1. Evolução do Volume (Nossos Números)")

    vol_safra = (
        df_filtered
        .groupby('safra')['qtd_sementes']
        .sum()
        .reset_index()
    )

    fig_vol = px.bar(
        vol_safra,
        x='safra',
        y='qtd_sementes',
        title="Sementes Plantadas por Safra",
        color_discrete_sequence=[COLOR_GREEN],
        text_auto='.2s'
    )

    # Blindagem extra
    fig_vol.update_xaxes(type='category')

    st.plotly_chart(fig_vol, use_container_width=True)


# --- ABA 2: PROBLEMA DE SCORAGEM ---
with tab2:
    st.header("Diagnóstico do Modelo")
    st.markdown("##### *'Alta concentração de plantas contaminadas em scores mais altos.'*")

    # Linha 1: O Paradoxo do Score
    c1, c2 = st.columns([1, 2])

    # Gráfico de Barras Empilhadas: Score x Status
    fig_score = px.histogram(df_filtered, x="faixa_score", color="status", 
                                title="Distribuição de Contaminação por Faixa de Score",
                                color_discrete_map={'Saudável': COLOR_GREEN, 'Contaminado': COLOR_RED},
                                barnorm='percent', text_auto='.0f')
    st.plotly_chart(fig_score, use_container_width=True)

    st.divider()
    st.subheader("Onde o modelo está errando?")
    
    # Linha 2: Quebras por Solo e Tipo de Plantio
    col_solo, col_plantio = st.columns(2)
    
    df_score_alto = df_filtered[df_filtered['score_inicial'] > 75]

    # ===== Tipo de Solo =====
    solo_dist = (
        df_score_alto
        .groupby(['tipo_solo', 'status'])
        .size()
        .reset_index(name='qtd')
    )

    solo_dist['percentual'] = (
        solo_dist['qtd']
        / solo_dist.groupby('tipo_solo')['qtd'].transform('sum')
    )

    fig_solo = px.bar(
        solo_dist,
        x='tipo_solo',
        y='percentual',
        color='status',
        title="% Plantas Saudáveis vs Contaminadas por Tipo de Solo (Score > 75)",
        text=solo_dist['percentual'].apply(lambda x: f"{x:.0%}"),
        color_discrete_map={
            'Saudável': COLOR_GREEN,
            'Contaminado': COLOR_RED
        }
    )

    fig_solo.update_layout(
        barmode='stack',
        yaxis_tickformat='.0%',
        yaxis_title=''
    )

    st.plotly_chart(fig_solo, use_container_width=True)

    # ===== Tipo de Plantio =====
    plantio_dist = (
        df_score_alto
        .groupby(['tipo_plantio', 'status'])
        .size()
        .reset_index(name='qtd')
    )

    plantio_dist['percentual'] = (
        plantio_dist['qtd']
        / plantio_dist.groupby('tipo_plantio')['qtd'].transform('sum')
    )

    fig_plantio = px.bar(
        plantio_dist,
        x='tipo_plantio',
        y='percentual',
        color='status',
        title="% Plantas Saudáveis vs Contaminadas por Tipo de Plantio (Score > 75)",
        text=plantio_dist['percentual'].apply(lambda x: f"{x:.0%}"),
        color_discrete_map={
            'Saudável': COLOR_GREEN,
            'Contaminado': COLOR_RED
        }
    )

    fig_plantio.update_layout(
        barmode='stack',
        yaxis_tickformat='.0%',
        yaxis_title=''
    )

    st.plotly_chart(fig_plantio, use_container_width=True)

# --- ABA 3: ANÁLISE DE SEMENTES ---
with tab3:
    st.header("Examinando as Sementes")
    st.markdown("##### *'Existem alguns tipos com uma porcentagem muito alta de contaminação.'*")

    # Cálculo da Taxa de Contaminação por Semente
    seed_metrics = df_filtered.groupby('tipo_semente').agg(
        volume=('qtd_sementes', 'sum'),
        taxa_erro=('is_bad', 'mean')
    ).reset_index()

    # Classificação conforme Slide 4 (>50% é Tóxica)
    seed_metrics['grupo'] = seed_metrics['taxa_erro'].apply(lambda x: '> 50% Contaminação (Cortar)' if x > 0.5 else '< 50% Contaminação (Manter)')
    
    # Gráfico de Barras: Taxa de Erro por Semente
    fig_seeds = px.bar(seed_metrics.sort_values(by='taxa_erro', ascending=False), 
                       x='tipo_semente', y='taxa_erro', color='taxa_erro',
                       title="Taxa de Contaminação por Tipo de Semente",
                       color_continuous_scale='RdYlGn_r') # Vermelho para alto erro
    st.plotly_chart(fig_seeds, use_container_width=True)

    # Impacto no Volume
    c1, c2 = st.columns(2)

    # Tabela de Detalhe das Sementes Tóxicas
    st.write("Lista de Sementes Críticas (>50% de erro):")
    st.dataframe(
        seed_metrics[seed_metrics['taxa_erro'] > 0.5]
        .sort_values(by='taxa_erro', ascending=False)
        .style.format({'volume': '{:,.0f}', 'taxa_erro': '{:.1%}'}),
        use_container_width=True
    )