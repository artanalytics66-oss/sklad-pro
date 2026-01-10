import streamlit as st
import pandas as pd
import plotly.express as px
from groq import Groq

# --- НАСТРОЙКИ ---
st.set_page_config(page_title="SalesPro Analytics", layout="wide")

# Вставьте сюда ваш ключ API
GROQ_API_KEY = ""  #

# --- ФУНКЦИИ ЗАГРУЗКИ ---
@st.cache_data
def load_data(file):
    """
    Хитрая функция для чтения вашего специфического Excel-файла
    с многоуровневой шапкой (Филиалы в ряд).
    """
    # Читаем без заголовков, чтобы разобрать структуру вручную
    df = pd.read_excel(file, header=None)
    
    # Строка 0 - Филиалы, Строка 1 - Каналы (Город, Область...), Строка 2+ - Данные
    row0 = df.iloc[0].tolist()
    row1 = df.iloc[1].tolist()
    
    branches = []
    current_branch = "Unknown"
    
    # Заполняем пропуски в названиях филиалов (merged cells)
    for item in row0:
        if pd.notna(item) and "Филиал" in str(item):
            current_branch = str(item).strip()
        branches.append(current_branch)
        
    cleaned_data = []
    
    # Проходим по строкам данных
    for idx, row in df.iloc[2:].iterrows():
        date_val = row[0]
        if pd.isna(date_val): continue # Пропускаем пустые строки
        
        # Проходим по колонкам (начиная со 2-й, т.к. 0-Дата, 1-День)
        for col_idx in range(2, len(row)):
            branch = branches[col_idx]
            channel = row1[col_idx]
            val = row[col_idx]
            
            # Собираем только нужные метрики
            if branch and channel in ['город', 'область', 'хорека']:
                cleaned_data.append({
                    'Дата': date_val,
                    'Филиал': branch,
                    'Канал': channel.capitalize(), # Делаем с большой буквы
                    'Продажи': val if pd.notna(val) else 0
                })
                
    return pd.DataFrame(cleaned_data)

def get_ai_advice(branch, plan, fact_df):
    """Генерация промпта и запрос к AI"""
    if not GROQ_API_KEY.startswith("gsk_"):
        return "⚠️ Пожалуйста, укажите корректный API Key в коде."
    
    # Агрегация данных
    total_fact = fact_df['Продажи'].sum()
    structure = fact_df.groupby('Канал')['Продажи'].sum().to_dict()
    
    prompt = f"""
    Роль: Бизнес-аналитик. Объект: {branch}.
    ДАННЫЕ:
    - План: {plan:,.0f}
    - Факт: {total_fact:,.0f} ({total_fact/plan*100:.1f}% выполнения)
    - Структура: {structure}
    
    ЗАДАЧА:
    Краткий отчет в Markdown:
    1. Анализ выполнения (риски/успехи).
    2. Худший канал продаж - почему?
    3. 3 конкретных шага для выполнения плана.
    """
    
    try:
        client = Groq(api_key=GROQ_API_KEY)
        chat = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile"
        )
        return chat.choices[0].message.content
    except Exception as e:
        return f"Ошибка AI: {e}"

# --- ИНТЕРФЕЙС ---
st.title("📊 SalesPro Analytics Dashboard")

# 1. Боковая панель
with st.sidebar:
    st.header("Настройки")
    uploaded_file = st.file_uploader("Загрузить отчет (Excel)", type="xlsx")
    
    # Ручной ввод плана, т.к. в файле его нет
    st.divider()
    st.subheader("Планирование")
    target_plan = st.number_input("План продаж на месяц (кг)", value=230000, step=1000)

if uploaded_file:
    # Загрузка и обработка
    df = load_data(uploaded_file)
    
    # Фильтр по филиалам
    all_branches = df['Филиал'].unique()
    selected_branch = st.sidebar.selectbox("Выберите филиал", all_branches)
    
    # Фильтрация данных
    df_branch = df[df['Филиал'] == selected_branch]
    
    # --- KPI БЛОК ---
    fact_sales = df_branch['Продажи'].sum()
    progress = (fact_sales / target_plan) * 100
    avg_check = df_branch['Продажи'].mean() # Упрощенно
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("План на месяц", f"{target_plan:,.0f} кг")
    col2.metric("Факт продаж", f"{fact_sales:,.0f} кг", f"{progress:.1f}%")
    col3.metric("Прогноз (Линейный)", f"{fact_sales * 1.2:,.0f} кг") # Пример прогноза
    col4.metric("Среднее в день", f"{fact_sales / 30:,.0f} кг") # Пример
    
    # --- ГРАФИКИ ---
    st.divider()
    c1, c2 = st.columns([2, 1])
    
    with c1:
        st.subheader("Динамика продаж")
        # Группировка по датам для графика
        df_trend = df_branch.groupby('Дата')['Продажи'].sum().reset_index()
        fig_trend = px.area(df_trend, x='Дата', y='Продажи', color_discrete_sequence=['#00CC96'])
        fig_trend.update_layout(height=350, margin=dict(l=0,r=0,t=0,b=0))
        st.plotly_chart(fig_trend, use_container_width=True)
        
    with c2:
        st.subheader("Структура каналов")
        df_pie = df_branch.groupby('Канал')['Продажи'].sum().reset_index()
        fig_pie = px.pie(df_pie, values='Продажи', names='Канал', hole=0.4)
        fig_pie.update_layout(height=350, margin=dict(l=0,r=0,t=0,b=0))
        st.plotly_chart(fig_pie, use_container_width=True)

    # --- AI БЛОК ---
    st.divider()
    if st.button("🧠 Запустить интеллектуальный аудит (AI)", type="primary"):
        with st.spinner("Анализирую данные..."):
            advice = get_ai_advice(selected_branch, target_plan, df_branch)
            st.markdown("### Рекомендации AI")
            st.markdown(advice)

    # --- ДЕТАЛЬНАЯ ТАБЛИЦА ---
    with st.expander("Посмотреть исходные данные"):
        st.dataframe(df_branch, use_container_width=True)

else:
    st.info("👆 Пожалуйста, загрузите файл Excel в меню слева для начала работы.")
