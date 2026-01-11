import streamlit as st
import pandas as pd
import plotly.express as px
from groq import Groq
import io

# --- КОНФИГУРАЦИЯ ---
st.set_page_config(page_title="SalesPro Analytics", layout="wide")

# --- 1. АВТОРИЗАЦИЯ ---
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

# --- 2. ГЕНЕРАЦИЯ ШАБЛОНА ---
def generate_template():
    """Создает Excel файл-образец в памяти"""
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        # Лист ФАКТ
        df_fact = pd.DataFrame([
            ["Дата", "Филиал №1", "", "", "Филиал №2", "", ""],
            ["", "Город", "Область", "HoReCa", "Город", "Область", "HoReCa"],
            ["2025-05-01", 5000, 3000, 1000, 4000, 2000, 500],
            ["2025-05-02", 5200, 3100, 1100, 4100, 2100, 550]
        ])
        df_fact.to_excel(writer, sheet_name='Факт', index=False, header=False)
        
        # Лист ПЛАН
        df_plan = pd.DataFrame([
            ["Месяц", "Год", "Филиал №1", "", "", "", "Филиал №2", "", "", ""],
            ["", "", "Город", "Область", "HoReCa", "ИТОГО", "Город", "Область", "HoReCa", "ИТОГО"],
            ["Май", 2025, 150000, 100000, 50000, 300000, 100000, 80000, 20000, 200000]
        ])
        df_plan.to_excel(writer, sheet_name='План', index=False, header=False)
        
    buffer.seek(0)
    return buffer

# --- 3. ОБРАБОТКА ДАННЫХ ---
@st.cache_data
def load_data_and_plan(file):
    try:
        xl = pd.ExcelFile(file)
        
        # --- ФАКТ ---
        fact_sheet = xl.sheet_names[0]
        df_fact_raw = pd.read_excel(file, sheet_name=fact_sheet, header=None)
        
        row0 = df_fact_raw.iloc[0].tolist()
        row1 = df_fact_raw.iloc[1].tolist()
        
        branches = []
        curr = "Unknown"
        for item in row0:
            if pd.notna(item) and "Филиал" in str(item):
                curr = str(item).strip()
            branches.append(curr)
            
        fact_data = []
        for idx, row in df_fact_raw.iloc[2:].iterrows():
            date_val = row[0]
            if pd.isna(date_val): continue
            
            for col_idx in range(1, len(row)): # Исправлен индекс чтения
                if col_idx >= len(branches): break
                branch = branches[col_idx]
                if col_idx >= len(row1): break
                channel = row1[col_idx]
                val = row[col_idx]
                
                if branch and channel and str(channel).lower().strip() in ['город', 'область', 'хорека']:
                    fact_data.append({
                        'Дата': date_val,
                        'Филиал': branch,
                        'Канал': str(channel).strip().capitalize(),
                        'Продажи': val if pd.notna(val) else 0
                    })
        df_sales = pd.DataFrame(fact_data)

        # --- ПЛАН ---
        plans_map = {}
        plan_sheet_name = next((s for s in xl.sheet_names if 'план' in s.lower() or 'plan' in s.lower()), None)
        
        if plan_sheet_name:
            df_plan_raw = pd.read_excel(file, sheet_name=plan_sheet_name, header=None)
            p_row0 = df_plan_raw.iloc[0].tolist()
            p_row1 = df_plan_raw.iloc[1].tolist()
            p_values = df_plan_raw.iloc[2].tolist()
            
            p_branches = []
            p_curr = "Unknown"
            for i in range(len(p_row0)):
                item = p_row0[i]
                if pd.notna(item) and "Филиал" in str(item):
                    p_curr = str(item).strip()
                p_branches.append(p_curr)

            for i, val in enumerate(p_values):
                if i >= len(p_branches) or i >= len(p_row1): break
                branch = p_branches[i]
                channel = p_row1[i]
                
                if pd.notna(val) and str(channel).lower().strip() == 'итого':
                     plans_map[branch] = val

        return df_sales, plans_map

    except Exception as e:
        return None, {}

def get_ai_advice(branch, plan, fact_df):
    try:
        api_key = st.secrets["GROQ_API_KEY"]
    except:
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
            model="llama-3.3-70b-versatile"  # <--- ОБНОВЛЕННАЯ МОДЕЛЬ
        )
        return chat.choices[0].message.content
    except Exception as e:
        return f"Ошибка AI сервиса: {e}"

# --- 4. ГЛАВНЫЙ ЭКРАН ---
st.title("📊 SalesPro Analytics Dashboard")

with st.sidebar:
    st.header("Управление")
    
    # Кнопка скачивания шаблона
    template_file = generate_template()
    st.download_button(
        label="📥 Скачать образец Excel",
        data=template_file,
        file_name="sales_template.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    
    st.divider()
    uploaded_file = st.file_uploader("Загрузить отчет (.xlsx)", type="xlsx")

if uploaded_file:
    df, plans_map = load_data_and_plan(uploaded_file)
    
    if df is not None and not df.empty:
        all_branches = sorted(df['Филиал'].unique())
        selected_branch = st.sidebar.selectbox("Выберите филиал", all_branches)
        
        df_branch = df[df['Филиал'] == selected_branch]
        auto_plan = plans_map.get(selected_branch, 0)
        
        if auto_plan == 0:
            st.warning(f"План не найден. Введите вручную.")
            target_plan = st.sidebar.number_input("План продаж", value=200000)
        else:
            st.sidebar.success(f"План подгружен: {auto_plan:,.0f}")
            target_plan = auto_plan
            
        fact = df_branch['Продажи'].sum()
        delta = fact - target_plan
        percent = (fact / target_plan) * 100 if target_plan > 0 else 0
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("План на месяц", f"{target_plan:,.0f} кг")
        col2.metric("Факт продаж", f"{fact:,.0f} кг", f"{percent:.1f}%")
        col3.metric("Отклонение", f"{delta:,.0f} кг", delta_color="normal")
        col4.metric("Прогноз", f"{fact * 1.25:,.0f} кг")

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

        st.divider()
        st.subheader("🧠 Интеллектуальный помощник")
        if st.button("Запросить анализ AI", type="primary", use_container_width=True):
            with st.spinner("Генерация стратегии..."):
                report = get_ai_advice(selected_branch, target_plan, df_branch)
                st.markdown(report)
    else:
        st.error("Ошибка формата данных. Скачайте образец слева.")
else:
    st.info("👈 Загрузите файл Excel для начала работы.")
