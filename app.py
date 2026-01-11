import streamlit as st
import pandas as pd
import plotly.express as px
from groq import Groq
import io
import xlsxwriter
from datetime import datetime
import calendar

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

# --- 2. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

def calculate_forecast(df_branch):
    """
    Рассчитывает прогноз на конец месяца: (Факт / Дней работы) * Дней в месяце
    """
    if df_branch.empty:
        return 0
        
    try:
        # Находим уникальные даты, когда были продажи
        dates = pd.to_datetime(df_branch['Дата'], errors='coerce').dropna().dt.date.unique()
        days_worked = len(dates)
        
        if days_worked == 0:
            return 0
            
        current_fact = df_branch['Продажи'].sum()
        avg_daily_sales = current_fact / days_worked
        
        # Берем дату из первой записи, чтобы понять какой сейчас месяц
        first_date_val = df_branch['Дата'].iloc[0]
        if pd.isna(first_date_val):
            return current_fact 
            
        first_date = pd.to_datetime(first_date_val)
        # Получаем количество дней в этом месяце (28, 30 или 31)
        days_in_month = calendar.monthrange(first_date.year, first_date.month)[1]
        
        forecast = avg_daily_sales * days_in_month
        return forecast
    except Exception as e:
        return df_branch['Продажи'].sum()

def generate_template():
    """Создает Excel файл-образец с инструкцией"""
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        
        # ЛИСТ 1: ИНСТРУКЦИЯ
        workbook = writer.book
        worksheet = workbook.add_worksheet('Инструкция')
        
        bold_head = workbook.add_format({'bold': True, 'font_size': 14, 'color': '#2c3e50'})
        text_norm = workbook.add_format({'font_size': 12, 'text_wrap': True, 'valign': 'top'})
        text_red = workbook.add_format({'bold': True, 'color': 'red', 'font_size': 12})
        
        worksheet.write('A1', 'Как заполнить шаблон под свой бизнес:', bold_head)
        
        rules = [
            "",
            "1. В верхней строке (в листах 'Факт' и 'План') пишите названия ваших точек.",
            "   (Например: Магазины, Склады, Офисы, Филиалы).",
            "",
            "2. Под каждым названием точки есть колонки категорий.",
            "   Вы можете переименовать их как хотите.",
            "   (Например: Товары, Услуги, Доставка или Опт, Розница, Интернет).",
            "",
            "3. Вы можете добавлять новые колонки или удалять лишние.",
            ""
        ]
        
        row = 1
        for line in rules:
            worksheet.write(row, 0, line, text_norm)
            row += 1
            
        worksheet.write(row, 0, 'Важно: Не удаляйте колонку "ИТОГО", она нужна для проверки планов.', text_red)
        worksheet.set_column('A:A', 70)

        # ЛИСТ 2: ФАКТ
        df_fact = pd.DataFrame([
            ["Дата", "Магазин Центр", "", "", "Магазин Склад", "", ""],
            ["", "Кирпич", "Цемент", "Краска", "Кирпич", "Цемент", "Краска"],
            ["2025-05-01", 5000, 3000, 1000, 4000, 2000, 500],
            ["2025-05-02", 5200, 3100, 1100, 4100, 2100, 550]
        ])
        df_fact.to_excel(writer, sheet_name='Факт', index=False, header=False)
        
        # ЛИСТ 3: ПЛАН
        df_plan = pd.DataFrame([
            ["Месяц", "Год", "Магазин Центр", "", "", "", "Магазин Склад", "", "", ""],
            ["", "", "Кирпич", "Цемент", "Краска", "ИТОГО", "Кирпич", "Цемент", "Краска", "ИТОГО"],
            ["Май", 2025, 150000, 100000, 50000, 300000, 100000, 80000, 20000, 200000]
        ])
        df_plan.to_excel(writer, sheet_name='План', index=False, header=False)
        
    buffer.seek(0)
    return buffer

# --- 3. ЗАГРУЗКА ДАННЫХ ---
@st.cache_data
def load_data_and_plan(file):
    try:
        xl = pd.ExcelFile(file)
        sheet_names = xl.sheet_names
        
        # Ищем лист ФАКТ
        fact_sheet = None
        for s in sheet_names:
            if 'факт' in s.lower() or 'fact' in s.lower():
                fact_sheet = s
                break
        if not fact_sheet:
            for s in sheet_names:
                name_lower = s.lower()
                if "инструкция" not in name_lower and "instruction" not in name_lower and "план" not in name_lower and "plan" not in name_lower:
                    fact_sheet = s
                    break
        if not fact_sheet and len(sheet_names) > 1:
            fact_sheet = sheet_names[1]
            
        if not fact_sheet:
            return None, {}

        # Читаем ФАКТ
        df_fact_raw = pd.read_excel(file, sheet_name=fact_sheet, header=None)
        
        row0 = df_fact_raw.iloc[0].tolist()
        row1 = df_fact_raw.iloc[1].tolist()
        
        branches = []
        curr = "Unknown"
        for item in row0:
            if pd.notna(item) and str(item).strip() != "":
                if "дата" not in str(item).lower():
                    curr = str(item).strip()
            branches.append(curr)
            
        fact_data = []
        for idx, row in df_fact_raw.iloc[2:].iterrows():
            date_val = row[0]
            if pd.isna(date_val): continue
            
            start_col = 1
            for col_idx in range(start_col, len(row)):
                if col_idx >= len(branches): break
                branch = branches[col_idx]
                if col_idx >= len(row1): break
                channel = row1[col_idx]
                val = row[col_idx]
                
                invalid_words = ['итого', 'total', 'сумма', 'nan', 'none', 'дата', 'день']
                channel_str = str(channel).strip()
                
                if (branch != "Unknown" 
                    and channel_str 
                    and channel_str.lower() not in invalid_words 
                    and pd.notna(channel)):
                    
                    fact_data.append({
                        'Дата': date_val,
                        'Филиал': branch,
                        'Канал': channel_str.capitalize(),
                        'Продажи': val if pd.notna(val) else 0
                    })
        df_sales = pd.DataFrame(fact_data)

        # Читаем ПЛАН
        plans_map = {}
        plan_sheet_name = next((s for s in sheet_names if 'план' in s.lower() or 'plan' in s.lower()), None)
        
        if plan_sheet_name:
            df_plan_raw = pd.read_excel(file, sheet_name=plan_sheet_name, header=None)
            p_row0 = df_plan_raw.iloc[0].tolist()
            p_row1 = df_plan_raw.iloc[1].tolist()
            p_values = df_plan_raw.iloc[2].tolist()
            
            p_branches = []
            p_curr = "Unknown"
            for i in range(len(p_row0)):
                item = p_row0[i]
                if pd.notna(item) and str(item).strip() != "":
                     if "месяц" not in str(item).lower() and "год" not in str(item).lower():
                        p_curr = str(item).strip()
                p_branches.append(p_curr)

            for i, val in enumerate(p_values):
                if i >= len(p_branches) or i >= len(p_row1): break
                branch = p_branches[i]
                channel = p_row1[i]
                
                if (pd.notna(val) 
                    and branch != "Unknown"
                    and str(channel).lower().strip() in ['итого', 'total', 'сумма']):
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
    
    # Новый точный прогноз для AI
    forecast_val = calculate_forecast(fact_df)
    
    # Конвертируем структуру в строку отдельно, чтобы не ломать f-string
    structure_dict = fact_df.groupby('Канал')['Продажи'].sum().to_dict()
    structure_str = str(structure_dict)
    
    prompt = f"""
    Роль: Старший бизнес-аналитик. Объект анализа: {branch}.
    ВХОДНЫЕ ДАННЫЕ:
    - План на месяц: {plan}
    - Факт продаж: {total_fact} (Выполнение: {percent:.1f}%)
    - Прогноз на конец месяца (расчетный): {forecast_val}
    - Структура продаж: {structure_str}
    
    ТВОЯ ЗАДАЧА:
    Напиши отчет (Markdown).
    1. Оценка ситуации (Сравните прогноз с планом).
    2. Проблемная зона.
    3. 3 конкретных совета.
    """
    
    try:
        client = Groq(api_key=api_key)
        chat = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile"
        )
        return chat.choices[0].message.content
    except Exception as e:
        return f"Ошибка AI сервиса: {e}"

# --- 4. ГЛАВНЫЙ ЭКРАН ---
st.title("📊 SalesPro Analytics Dashboard")

with st.sidebar:
    st.header("Управление")
    template_file = generate_template()
    st.download_button(
        label="📥 Скачать шаблон с инструкцией",
        data=template_file,
        file_name="sales_template_universal.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    st.divider()
    uploaded_file = st.file_uploader("Загрузить отчет (.xlsx)", type="xlsx")

if uploaded_file:
    df, plans_map = load_data_and_plan(uploaded_file)
    
    if df is not None and not df.empty:
        all_branches = sorted(df['Филиал'].unique())
        selected_branch = st.sidebar.selectbox("Выберите объект/филиал", all_branches)
        
        df_branch = df[df['Филиал'] == selected_branch]
        auto_plan = plans_map.get(selected_branch, 0)
        
        if auto_plan == 0:
            st.warning(f"План не найден в файле. Введите вручную.")
            target_plan = st.sidebar.number_input("План продаж", value=200000)
        else:
            st.sidebar.success(f"План подгружен: {auto_plan:,.0f}")
            target_plan = auto_plan
            
        fact = df_branch['Продажи'].sum()
        delta = fact - target_plan
        percent = (fact / target_plan) * 100 if target_plan > 0 else 0
        
        # ИСПРАВЛЕННЫЙ РАСЧЕТ ПРОГНОЗА
        forecast_val = calculate_forecast(df_branch)
        forecast_delta = forecast_val - target_plan
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("🎯 План", f"{target_plan:,.0f}")
        col2.metric("💰 Факт", f"{fact:,.0f}", f"{percent:.1f}%")
        col3.metric("📉 Отклонение", f"{delta:,.0f}", delta_color="normal")
        
        col4.metric(
            "🔮 Прогноз (конец мес.)", 
            f"{forecast_val:,.0f}", 
            f"{forecast_delta:,.0f}", 
            delta_color="normal"
        )

        st.divider()
        c1, c2 = st.columns([2, 1])
        with c1:
            st.subheader("📆 Динамика")
            df_trend = df_branch.groupby('Дата')['Продажи'].sum().reset_index()
            fig_trend = px.area(df_trend, x='Дата', y='Продажи', color_discrete_sequence=['#00CC96'])
            st.plotly_chart(fig_trend, use_container_width=True)
        with c2:
            st.subheader("📊 Категории")
            df_pie = df_branch.groupby('Канал')['Продажи'].sum().reset_index()
            fig_pie = px.pie(df_pie, values='Продажи', names='Канал', hole=0.5)
            st.plotly_chart(fig_pie, use_container_width=True)

        st.divider()
        if st.button("🧠 AI Бизнес-Ассистент", type="primary", use_container_width=True):
            with st.spinner("Анализ данных..."):
                report = get_ai_advice(selected_branch, target_plan, df_branch)
                st.markdown(report)
    else:
        st.error("Ошибка формата. Скачайте шаблон слева.")
else:
    st.info("👈 Начните работу с загрузки файла.")
