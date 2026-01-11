import streamlit as st
import pandas as pd
import plotly.express as px
from groq import Groq

# --- НАСТРОЙКИ СТРАНИЦЫ ---
st.set_page_config(page_title="SalesPro Analytics", layout="wide")

# --- 1. СИСТЕМА ЛИЦЕНЗИРОВАНИЯ (ВХОД ПО КЛЮЧУ) ---
def check_password():
    """Возвращает True, если ключ верный."""
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False

    if st.session_state["authenticated"]:
        return True

    st.title("🔐 SalesPro Analytics Enterprise")
    st.write("Для доступа к системе введите лицензионный ключ.")
    
    password = st.text_input("Ключ активации", type="password")
    
    if st.button("Войти"):
        if password == "START-500":
            st.session_state["authenticated"] = True
            st.rerun()  # Перезагрузка страницы для входа
        else:
            st.error("⛔ Неверный ключ активации")
            
    return False

if not check_password():
    st.stop()  # Останавливаем выполнение, если пароль не введен

# --- ОСНОВНОЕ ПРИЛОЖЕНИЕ (ЗАПУСКАЕТСЯ ПОСЛЕ ВХОДА) ---

# --- ФУНКЦИИ ЗАГРУЗКИ ---
@st.cache_data
def load_data(file):
    """Загрузка факта и плана из Excel"""
    try:
        # 1. Читаем ФАКТ (Лист1)
        df_fact = pd.read_excel(file, sheet_name=0, header=None)
        
        # Парсинг сложной шапки (как в прошлом коде)
        row0 = df_fact.iloc[0].tolist()
        row1 = df_fact.iloc[1].tolist()
        branches = []
        current_branch = "Unknown"
        for item in row0:
            if pd.notna(item) and "Филиал" in str(item):
                current_branch = str(item).strip()
            branches.append(current_branch)
            
        cleaned_fact = []
        for idx, row in df_fact.iloc[2:].iterrows():
            date_val = row[0]
            if pd.isna(date_val): continue
            for col_idx in range(2, len(row)):
                branch = branches[col_idx]
                channel = row1[col_idx]
                val = row[col_idx]
                if branch and channel in ['город', 'область', 'хорека']:
                    cleaned_fact.append({
                        'Дата': date_val,
                        'Филиал': branch,
                        'Канал': channel.capitalize(),
                        'Продажи': val if pd.notna(val) else 0
                    })
        df_sales = pd.DataFrame(cleaned_fact)

        # 2. Читаем ПЛАН (Ищем лист "План" или "Plan")
        try:
            # Пытаемся найти лист с названием 'План' или 'Plan'
            xl_file = pd.ExcelFile(file)
            sheet_names = xl_file.sheet_names
            plan_sheet = next((s for s in sheet_names if 'лан' in s or 'lan' in s), None)
            
            plans_dict = {}
            if plan_sheet:
                # Ожидаем структуру: Колонка А - Филиал, Колонка B - План
                df_plan = pd.read_excel(file, sheet_name=plan_sheet)
                # Ищем колонки, похожие на 'Филиал' и 'План'
                # Для простоты берем 1-ю и 2-ю колонку, если заголовки не совпадают
                plans_dict = dict(zip(df_plan.iloc[:, 0], df_plan.iloc[:, 1]))
            
        except Exception as e:
            st.warning(f"Не удалось прочитать лист с планами: {e}. Используем стандартные.")
            plans_dict = {}

        return df_sales, plans_dict

    except Exception as e:
        st.error(f"Ошибка чтения файла: {e}")
        return None, {}

def get_ai_advice(branch, plan, fact_df):
    """Генерация рекомендаций через Groq API"""
    
    # 2. ПОЛУЧЕНИЕ API KEY ИЗ СЕКРЕТОВ (для защиты)
    try:
        api_key = st.secrets["GROQ_API_KEY"]
    except:
        return "⚠️ Ошибка: Ключ API не найден. Настройте 'GROQ_API_KEY' в настройках Streamlit Cloud."

    # Агрегация данных
    total_fact = fact_df['Продажи'].sum()
    if plan > 0:
        percent = (total_fact / plan) * 100
    else:
        percent = 0
        
    structure = fact_df.groupby('Канал')['Продажи'].sum().to_dict()
    
    prompt = f"""
    Роль: Бизнес-аналитик. Филиал: {branch}.
    ДАННЫЕ:
    - План: {plan:,.0f}
    - Факт: {total_fact:,.0f} ({percent:.1f}%)
    - Структура: {structure}
    
    ЗАДАЧА:
    Краткий отчет (Markdown, русский язык):
    1. Оценка ситуации (кратко).
    2. Слабые места.
    3. 3 шага для выполнения плана.
    """
    
    try:
        client = Groq(api_key=api_key)
        chat = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama3-70b-8192"
        )
        return chat.choices[0].message.content
    except Exception as e:
        return f"Ошибка соединения с AI: {e}"

# --- ИНТЕРФЕЙС ПРИЛОЖЕНИЯ ---
st.title("📊 SalesPro Analytics Dashboard")

with st.sidebar:
    st.header("Данные")
    uploaded_file = st.file_uploader("Загрузить отчет (Excel)", type="xlsx")
    
if uploaded_file:
    df, loaded_plans = load_data(uploaded_file)
    
    if df is not None:
        all_branches = df['Филиал'].unique()
        selected_branch = st.sidebar.selectbox("Выберите филиал", all_branches)
        
        # Получаем план из файла или берем дефолт
        # Ищем точное совпадение названия филиала в загруженных планах
        branch_plan = loaded_plans.get(selected_branch, 230000) 
        
        # Возможность скорректировать план вручную
        target_plan = st.sidebar.number_input("План продаж (кг)", value=int(branch_plan), step=1000)
        
        df_branch = df[df['Филиал'] == selected_branch]
        
        # Метрики
        fact_sales = df_branch['Продажи'].sum()
        progress = (fact_sales / target_plan) * 100 if target_plan > 0 else 0
        
        col1, col2, col3 = st.columns(3)
        col1.metric("🎯 План", f"{target_plan:,.0f}")
        col2.metric("💰 Факт", f"{fact_sales:,.0f}", f"{progress:.1f}%")
        col3.metric("📉 Прогноз", f"{fact_sales * 1.2:,.0f}") # Примерная логика

        # Графики
        c1, c2 = st.columns([2, 1])
        with c1:
            st.subheader("Динамика")
            df_trend = df_branch.groupby('Дата')['Продажи'].sum().reset_index()
            st.plotly_chart(px.area(df_trend, x='Дата', y='Продажи'), use_container_width=True)
            
        with c2:
            st.subheader("Каналы")
            df_pie = df_branch.groupby('Канал')['Продажи'].sum().reset_index()
            st.plotly_chart(px.pie(df_pie, values='Продажи', names='Канал'), use_container_width=True)

        # AI Аналитик
        st.divider()
        if st.button("🧠 AI Рекомендации", type="primary"):
            with st.spinner("Анализирую данные..."):
                advice = get_ai_advice(selected_branch, target_plan, df_branch)
                st.markdown(advice)
else:
    st.info("👋 Добро пожаловать! Загрузите Excel файл для начала работы.")
