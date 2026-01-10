import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from groq import Groq
from io import BytesIO

# --- НАСТРОЙКИ СТРАНИЦЫ (Широкий режим, Темная тема) ---
st.set_page_config(page_title="Audit PRO", page_icon="⚡", layout="wide")

# --- CSS СТИЛИ (ДЕЛАЕМ КРАСИВО) ---
st.markdown("""
<style>
    /* Основной фон */
    .stApp {
        background-color: #0E1117;
        color: #FAFAFA;
    }
    /* Карточки метрик */
    div[data-testid="stMetric"] {
        background-color: #262730;
        border-radius: 10px;
        padding: 15px;
        border: 1px solid #41444C;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.3);
    }
    /* Заголовки */
    h1, h2, h3 {
        font-family: 'Helvetica Neue', sans-serif;
        font-weight: 700;
        color: #FFFFFF;
    }
    /* Кнопки */
    .stButton>button {
        width: 100%;
        border-radius: 8px;
        font-weight: bold;
    }
    /* Сайдбар */
    section[data-testid="stSidebar"] {
        background-color: #161920;
    }
</style>
""", unsafe_allow_html=True)

# --- АВТОРИЗАЦИЯ ---
def check_password():
    if st.session_state.get("password_correct", False): return True
    
    # Красивая форма входа
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.markdown("<h1 style='text-align: center; color: #00CC96;'>🔐 SKLAD AUDIT PRO</h1>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color: gray;'>Введите ключ доступа для начала работы</p>", unsafe_allow_html=True)
        password = st.text_input("License Key", type="password", label_visibility="collapsed")
        
        if st.button("🚀 ВОЙТИ В СИСТЕМУ", type="primary"):
            if password == "START-500": 
                st.session_state["password_correct"] = True
                st.rerun()
            else:
                st.error("❌ Неверный ключ")
    return False

if not check_password(): st.stop()

# --- ПОДКЛЮЧЕНИЕ AI ---
try:
    GROQ_API_KEY = st.secrets["GROQ_API_KEY"]
    client = Groq(api_key=GROQ_API_KEY)
except:
    st.warning("⚠️ AI-ключ не найден. Работает базовый режим.")
    client = None

# --- ГЛАВНОЕ МЕНЮ ---
st.markdown("## ⚡ SKLAD AUDIT PRO <span style='font-size:16px; color:gray;'>v2.0</span>", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### 📥 ПАНЕЛЬ УПРАВЛЕНИЯ")
    uploaded_file = st.file_uploader("Загрузить отчет (.xlsx)", type=["xlsx"])
    
    # Генератор шаблона
    def get_template():
        df = pd.DataFrame({
            'Товарная Группа': ['Овощи', 'Пельмени', 'Молочка', 'Мясо', 'Рыба'],
            'Начало_Кг': [10000, 5000, 2000, 8000, 1500],
            'Приход_Кг': [15000, 2000, 3000, 8500, 1000],
            'Продажи_Кг': [8000, 2100, 2900, 8000, 1200],
            'Конец_Кг': [17000, 4900, 2100, 8500, 1300],
            'Цена_Руб': [270, 350, 80, 450, 600]
        })
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        return output.getvalue()
        
    st.download_button("📄 Скачать шаблон Excel", get_template(), "template.xlsx")
    st.divider()
    if st.button("🚪 Выход из системы"):
        st.session_state["password_correct"] = False
        st.rerun()

# --- ЛОГИКА ---
if uploaded_file:
    try:
        df = pd.read_excel(uploaded_file)
        
        # Поиск цены
        price_col = None
        for col in df.columns:
            if "цена" in str(col).lower() or "price" in str(col).lower():
                price_col = col; break
        if not price_col and len(df.columns) >= 6: price_col = df.columns[5]
            
        df_clean = df.iloc[:, [0, 1, 2, 3, 4]].copy()
        df_clean['Цена_Руб'] = df[price_col]
        df_clean.columns = ['Группа', 'Начало_Кг', 'Приход_Кг', 'Продажи_Кг', 'Конец_Кг', 'Цена_Руб']
        df = df_clean

        # Расчеты
        df['Остаток_Руб'] = df['Конец_Кг'] * df['Цена_Руб']
        df['Индекс'] = df.apply(lambda x: x['Приход_Кг'] / x['Продажи_Кг'] if x['Продажи_Кг'] > 0 else 0, axis=1)
        df['Запас_Дней'] = df.apply(lambda x: (x['Конец_Кг'] / x['Продажи_Кг'] * 30) if x['Продажи_Кг'] > 0 else 999, axis=1)
        df['Движение'] = (df['Конец_Кг'] - df['Начало_Кг']) * df['Цена_Руб']

        def get_status(row):
            i, d = row['Индекс'], row['Запас_Дней']
            if i > 1.2 and d > 45: return "🔴 СЛИВ"
            if i < 0.8 and d < 10: return "🔴 ДЕФИЦИТ"
            if i < 0.9 and d > 30: return "🟢 ВЫВОД"
            return "🟢 БАЛАНС"
        df['Статус'] = df.apply(get_status, axis=1)

        # --- KPI ПАНЕЛЬ ---
        st.divider()
        c1, c2, c3, c4 = st.columns(4)
        
        total_money = df['Остаток_Руб'].sum()
        frozen = df[df['Статус'].str.contains('🔴')]['Остаток_Руб'].sum()
        cash_flow = df['Движение'].sum() * -1
        
        c1.metric("💰 Капитал склада", f"{total_money/1000000:.1f} млн ₽", f"{len(df)} групп")
        c2.metric("🔥 Рисковые активы", f"{frozen/1000000:.1f} млн ₽", "Требуют внимания", delta_color="inverse")
        c3.metric("💸 Денежный поток", f"{cash_flow/1000000:.1f} млн ₽", "За месяц")
        
        # Индикатор здоровья
        health = 100 - (frozen / total_money * 100) if total_money > 0 else 0
        c4.metric("❤️ Здоровье склада", f"{health:.0f}%", "Индекс эффективности")

        # --- ГРАФИКИ ---
        st.subheader("📊 Аналитика Эффективности")
        
        tab1, tab2 = st.tabs(["Карта Денег", "Матрица Рисков"])
        
        with tab1:
            fig = px.bar(
                df, x='Группа', y='Остаток_Руб', color='Статус',
                color_discrete_map={'🔴 СЛИВ': '#FF4B4B', '🔴 ДЕФИЦИТ': '#FF8C00', '🟢 ВЫВОД': '#00CC96', '🟢 БАЛАНС': '#2E8B57'},
                text_auto='.2s', title="Где лежат ваши деньги?"
            )
            fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="white", height=500)
            st.plotly_chart(fig, use_container_width=True)
            
        with tab2:
            fig2 = px.scatter(
                df, x='Запас_Дней', y='Индекс', size='Остаток_Руб', color='Статус',
                hover_name='Группа', size_max=60,
                color_discrete_map={'🔴 СЛИВ': '#FF4B4B', '🔴 ДЕФИЦИТ': '#FF8C00', '🟢 ВЫВОД': '#00CC96', '🟢 БАЛАНС': '#2E8B57'}
            )
            fig2.add_hline(y=1, line_dash="dash", line_color="gray")
            fig2.add_vline(x=30, line_dash="dash", line_color="gray")
            fig2.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="white", height=500)
            st.plotly_chart(fig2, use_container_width=True)

        # --- AI АУДИТ ---
        st.subheader("🤖 AI-Аудитор")
        
        if st.button("🚀 Запустить полный анализ (AI)", type="primary"):
            if client:
                with st.spinner("Нейросеть анализирует данные..."):
                    # Подготовка данных для AI
                    report_data = df.to_csv(index=False)
                    prompt = f"""
                    Ты финансовый директор. Проанализируй этот складской отчет:
                    {report_data}
                    
                    1. Найди 3 главные проблемы (где заморожены деньги).
                    2. Посчитай, сколько денег можно высвободить.
                    3. Дай жесткие рекомендации закупщикам.
                    Пиши кратко, по делу, используй эмодзи.
                    """
                    
                    completion = client.chat.completions.create(
                        model="llama-3.3-70b-versatile",
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.5
                    )
                    st.success("Анализ готов!")
                    st.markdown(f"<div style='background-color: #262730; padding: 20px; border-radius: 10px;'>{completion.choices[0].message.content}</div>", unsafe_allow_html=True)
            else:
                st.error("AI не подключен. Проверьте ключ.")

        # Таблица
        with st.expander("📂 Исходные данные"):
            st.dataframe(df, use_container_width=True)

    except Exception as e: st.error(f"Ошибка: {e}")
else: 
    st.info("👈 Загрузите ваш файл Excel в меню слева")
