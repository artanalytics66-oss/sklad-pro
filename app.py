import streamlit as st
import pandas as pd
import plotly.express as px
from groq import Groq

# --- КОНФИГУРАЦИЯ ---
st.set_page_config(page_title="SalesPro Analytics", layout="wide")

# --- 1. АВТОРИЗАЦИЯ (Ключ продукта) ---
def check_auth():
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False

    if st.session_state["authenticated"]:
        return True

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.title("🔐 SalesPro Analytics Enterprise")
        st.write("Введите лицензионный ключ для доступа к системе.")
        password = st.text_input("License Key", type="password")
        if st.button("Войти в систему", type="primary", use_container_width=True):
            if password == "START-500":
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("⛔ Неверный ключ активации")
    return False

if not check_auth():
    st.stop()

# --- 2. ОБРАБОТКА ДАННЫХ (ФАКТ + ПЛАН) ---
@st.cache_data
def load_data_and_plan(file):
    """
    Читает сложную горизонтальную структуру файла.
    Возвращает DataFrame с фактом и словарь с планами.
    """
    try:
        xl = pd.ExcelFile(file)
        
        # ------------------ ЧТЕНИЕ ФАКТА ------------------
        # Ищем лист с фактом (обычно первый или с названием Лист1/Sheet1)
        fact_sheet_name = xl.sheet_names[0] 
        df_fact_raw = pd.read_excel(file, sheet_name=fact_sheet_name, header=None)
        
        # Парсинг факта (как делали раньше)
        row0 = df_fact_raw.iloc[0].tolist() # Филиалы
        row1 = df_fact_raw.iloc[1].tolist() # Каналы
        
        branches = []
        curr = "Unknown"
        for item in row0:
            if pd.notna(item) and "Филиал" in str(item):
                curr = str(item).strip()
            branches.append(curr)
            
        fact_data = []
        # Данные начинаются со строки 2 (индекс 2)
        for idx, row in df_fact_raw.iloc[2:].iterrows():
            date_val = row[0]
            if pd.isna(date_val): continue
            
            # Проходим по колонкам начиная с 3-й (индекс 2)
            for col_idx in range(2, len(row)):
                branch = branches[col_idx]
                channel = row1[col_idx]
                val = row[col_idx]
                
                if branch and channel in ['город', 'область', 'хорека']:
                    fact_data.append({
                        'Дата': date_val,
                        'Филиал': branch,
                        'Канал': str(channel).strip().capitalize(),
                        'Продажи': val if pd.notna(val) else 0
                    })
        df_sales = pd.DataFrame(fact_data)

        # ------------------ ЧТЕНИЕ ПЛАНА ------------------
        plans_map = {}
        # Ищем лист с названием "план" (регистронезависимо)
        plan_sheet_name = next((s for s in xl.sheet_names if 'план' in s.lower() or 'plan' in s.lower()), None)
        
        if plan_sheet_name:
            df_plan_raw = pd.read_excel(file, sheet_name=plan_sheet_name, header=None)
            
            # Структура такая же: стр 0 - Филиалы, стр 1 - Каналы, стр 2 - Значения
            p_row0 = df_plan_raw.iloc[0].tolist()
            p_row1 = df_plan_raw.iloc[1].tolist()
            p_values = df_plan_raw.iloc[2].tolist() # Сами цифры плана
            
            p_branches = []
            p_curr = "Unknown"
            # Пропускаем первые 2 колонки (Месяц, Год)
            for i in range(2, len(p_row0)):
                item = p_row0[i]
                if pd.notna(item) and "Филиал" in str(item):
                    p_curr = str(item).strip()
                p_branches.append(p_curr)
                
            # Собираем словарь планов
            # Нам нужны индексы в p_values, которые соответствуют индексам в p_branches + смещение 2
            # p_values уже полный список строки, так что индексы совпадают с p_branches + 2
            
            for i, branch in enumerate(p_branches):
                real_idx = i + 2 # смещение из-за колонок Месяц/Год
                if real_idx >= len(p_values): break
                
                val = p_values[real_idx]
                channel = p_row1[real_idx]
                
                if pd.notna(val) and str(channel).lower().strip() == 'итого':
                     plans_map[branch] = val

        return df_sales, plans_map

    except Exception as e:
        st.error(f"Ошибка обработки файла: {e}")
        return None, {}

def get_ai_advice(branch, plan, fact_df):
    """Запрос к AI с использованием секретного ключа"""
    try:
        # Пытаемся взять ключ из Streamlit Cloud Secrets
        api_key = st.secrets["GROQ_API_KEY"]
    except:
        # Для локального теста, если секретов нет
        return "⚠️ ОШИБКА: Не настроен GROQ_API_KEY в Streamlit Secrets."

    total_fact = fact_df['Продажи'].sum()
    percent = (total_fact / plan * 100) if plan > 0 else 0
    structure = fact_df.groupby('Канал')['Продажи'].sum().to_dict()
    
    prompt = f"""
    Роль: Старший бизнес-аналитик. Объект: {branch}.
    ВХОДНЫЕ ДАННЫЕ:
    - План на месяц: {plan:,.0f}
    - Факт продаж: {total_fact:,.0f} (Выполнение: {percent:.1f}%)
    - Структура по каналам: {structure}
    
    ТВОЯ ЗАДАЧА:
    Напиши стратегический отчет в формате Markdown.
    1. 🎯 Статус выполнения (Опасно/Норма/Отлично).
    2. 📉 Проблемная зона (какой канал тянет вниз).
    3. 🚀 3 конкретных действия для менеджера, чтобы закрыть план.
    Будь краток и конкретен.
    """
    
    try:
        client = Groq(api_key=api_key)
        chat = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama3-70b-8192"
        )
        return chat.choices[0].message.content
    except Exception as e:
        return f"Ошибка AI сервиса: {e}"

# --- 3. ГЛАВНЫЙ ЭКРАН ---
st.title("📊 SalesPro Analytics Dashboard")
st.markdown("Система мониторинга и прогнозирования продаж")

with st.sidebar:
    st.header("Управление")
    uploaded_file = st.file_uploader("Загрузить отчет (.xlsx)", type="xlsx")
    st.info("Файл должен содержать листы с фактом и планом.")

if uploaded_file:
    df, plans_map = load_data_and_plan(uploaded_file)
    
    if df is not None and not df.empty:
        # Выбор филиала
        all_branches = sorted(df['Филиал'].unique())
        selected_branch = st.sidebar.selectbox("Выберите филиал", all_branches)
        
        # Получение данных филиала
        df_branch = df[df['Филиал'] == selected_branch]
        
        # Автоматическое получение плана
        auto_plan = plans_map.get(selected_branch, 0)
        
        if auto_plan == 0:
            st.warning(f"План для {selected_branch} не найден в файле. Введите вручную.")
            target_plan = st.sidebar.number_input("План продаж", value=200000)
        else:
            st.sidebar.success(f"План подгружен: {auto_plan:,.0f}")
            target_plan = auto_plan
            
        # KPI МЕТРИКИ
        fact = df_branch['Продажи'].sum()
        delta = fact - target_plan
        percent = (fact / target_plan) * 100 if target_plan > 0 else 0
        
        # Стильные карточки
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("План на месяц", f"{target_plan:,.0f} кг")
        col2.metric("Факт продаж", f"{fact:,.0f} кг", f"{percent:.1f}%")
        col3.metric("Отклонение", f"{delta:,.0f} кг", delta_color="normal")
        col4.metric("Прогноз (Линейный)", f"{fact * 1.25:,.0f} кг") # Простая экстраполяция

        # ГРАФИКИ
        st.divider()
        c1, c2 = st.columns([2, 1])
        
        with c1:
            st.subheader("📆 Динамика продаж")
            df_trend = df_branch.groupby('Дата')['Продажи'].sum().reset_index()
            fig_trend = px.area(df_trend, x='Дата', y='Продажи', color_discrete_sequence=['#00CC96'])
            st.plotly_chart(fig_trend, use_container_width=True)
            
        with c2:
            st.subheader("📊 Структура каналов")
            df_pie = df_branch.groupby('Канал')['Продажи'].sum().reset_index()
            fig_pie = px.pie(df_pie, values='Продажи', names='Канал', hole=0.5)
            st.plotly_chart(fig_pie, use_container_width=True)

        # AI БЛОК
        st.divider()
        st.subheader("🧠 Интеллектуальный помощник")
        
        col_ai_btn, col_ai_res = st.columns([1, 3])
        with col_ai_btn:
            if st.button("Запросить анализ AI", type="primary", use_container_width=True):
                with st.spinner("Генерация стратегии..."):
                    report = get_ai_advice(selected_branch, target_plan, df_branch)
                    st.session_state['ai_report'] = report
        
        with col_ai_res:
            if 'ai_report' in st.session_state:
                st.markdown(st.session_state['ai_report'])
                
    else:
        st.error("Не удалось прочитать данные. Проверьте формат файла.")
else:
    st.info("👈 Загрузите файл Excel в меню слева.")
