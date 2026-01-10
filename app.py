import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from groq import Groq
from io import BytesIO

# --- НАСТРОЙКИ СТРАНИЦЫ ---
st.set_page_config(page_title="Audit PRO", page_icon="⚡", layout="wide")

# --- CSS СТИЛИ ---
st.markdown("""
<style>
    .stApp { background-color: #0E1117; color: #FAFAFA; }
    div[data-testid="stMetric"] {
        background-color: #262730; border-radius: 10px; padding: 15px;
        border: 1px solid #41444C; box-shadow: 2px 2px 5px rgba(0,0,0,0.3);
    }
    h1, h2, h3 { font-family: 'Helvetica Neue', sans-serif; font-weight: 700; color: #FFFFFF; }
    section[data-testid="stSidebar"] { background-color: #161920; }
</style>
""", unsafe_allow_html=True)

# --- АВТОРИЗАЦИЯ ---
def check_password():
    if st.session_state.get("password_correct", False): return True
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.markdown("<h1 style='text-align: center; color: #00CC96;'>🔐 SKLAD AUDIT PRO</h1>", unsafe_allow_html=True)
        password = st.text_input("License Key", type="password", label_visibility="collapsed")
        if st.button("🚀 ВОЙТИ", type="primary"):
            if password == "START-500": 
                st.session_state["password_correct"] = True
                st.rerun()
            else: st.error("❌ Неверный ключ")
    return False

if not check_password(): st.stop()

# --- ПОДКЛЮЧЕНИЕ AI ---
try:
    GROQ_API_KEY = st.secrets["GROQ_API_KEY"]
    client = Groq(api_key=GROQ_API_KEY)
except:
    client = None

# --- МЕНЮ ---
st.markdown("## ⚡ SKLAD AUDIT PRO <span style='font-size:16px; color:gray;'>v2.1</span>", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### 📥 УПРАВЛЕНИЕ")
    uploaded_file = st.file_uploader("Загрузить отчет (.xlsx)", type=["xlsx"])
    
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
        with pd.ExcelWriter(output, engine='openpyxl') as writer: df.to_excel(writer, index=False)
        return output.getvalue()
        
    st.download_button("📄 Скачать шаблон", get_template(), "template.xlsx")
    st.divider()
    if st.button("🚪 Выход"):
        st.session_state["password_correct"] = False
        st.rerun()

# --- ЛОГИКА ---
if uploaded_file:
    try:
        df = pd.read_excel(uploaded_file)
        
        # 1. Поиск цены
        price_col = None
        for col in df.columns:
            if "цена" in str(col).lower() or "price" in str(col).lower():
                price_col = col; break
        if not price_col and len(df.columns) >= 6: price_col = df.columns[5]
            
        # 2. Выбор колонок
        df_clean = df.iloc[:, [0, 1, 2, 3, 4]].copy()
        df_clean['Цена_Руб'] = df[price_col]
        df_clean.columns = ['Группа', 'Начало_Кг', 'Приход_Кг', 'Продажи_Кг', 'Конец_Кг', 'Цена_Руб']
        
        # 3. ЧИСТКА ЦИФР (Важное исправление)
        cols_num = ['Начало_Кг', 'Приход_Кг', 'Продажи_Кг', 'Конец_Кг', 'Цена_Руб']
        for col in cols_num:
            df_clean[col] = pd.to_numeric(df_clean[col], errors='coerce').fillna(0)
            
        df = df_clean

        # 4. Расчеты
        df['Остаток_Руб'] = df['Конец_Кг'] * df['Цена_Руб']
        df['Индекс'] = df.apply(lambda x: x['Приход_Кг'] / x['Продажи_Кг'] if x['Продажи_Кг'] > 0 else 0, axis=1)
        df['Запас_Дней'] = df.apply(lambda x: (x['Конец_Кг'] / x['Продажи_Кг'] * 30) if x['Продажи_Кг'] > 0 else 999, axis=1)
        df['Движение'] = (df['Конец_Кг'] - df['Начало_Кг']) * df['Цена_Руб']

        # 5. СТАТУС (Восстановлено!)
        def get_status(row):
            i, d = row['Индекс'], row['Запас_Дней']
            if i > 1.2 and d > 45: return "🔴 СЛИВ"
            if i < 0.8 and d < 10: return "🔴 ДЕФИЦИТ"
            if i < 0.9 and d > 30: return "🟢 ВЫВОД"
            return "🟢 БАЛАНС"
        df['Статус'] = df.apply(get_status, axis=1)

        # --- KPI ---
        st.divider()
        c1, c2, c3, c4 = st.columns(4)
        total = df['Остаток_Руб'].sum()
        frozen = df[df['Статус'].str.contains('🔴')]['Остаток_Руб'].sum()
        cash = df['Движение'].sum() * -1
        
        c1.metric("💰 Капитал", f"{total/1000000:.1f} млн ₽")
        c2.metric("🔥 Риск", f"{frozen/1000000:.1f} млн ₽", "Заморожено", delta_color="inverse")
        c3.metric("💸 Поток", f"{cash/1000000:.1f} млн ₽", "Cashflow")
        c4.metric("❤️ Здоровье", f"{100 - (frozen/total*100) if total>0 else 0:.0f}%")

        # --- ГРАФИКИ ---
        st.subheader("📊 Аналитика")
        tab1, tab2 = st.tabs(["Деньги", "Риски"])
        
        with tab1:
            fig = px.bar(df, x='Группа', y='Остаток_Руб', color='Статус',
                color_discrete_map={'🔴 СЛИВ': '#FF4B4B', '🔴 ДЕФИЦИТ': '#FF8C00', '🟢 ВЫВОД': '#00CC96', '🟢 БАЛАНС': '#2E8B57'},
                title="Где лежат деньги?")
            fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="white", height=400)
            st.plotly_chart(fig, use_container_width=True)
            
        with tab2:
            fig2 = px.scatter(df, x='Запас_Дней', y='Индекс', size='Остаток_Руб', color='Статус',
                color_discrete_map={'🔴 СЛИВ': '#FF4B4B', '🔴 ДЕФИЦИТ': '#FF8C00', '🟢 ВЫВОД': '#00CC96', '🟢 БАЛАНС': '#2E8B57'})
            fig2.add_hline(y=1, line_dash="dash", line_color="gray")
            fig2.add_vline(x=30, line_dash="dash", line_color="gray")
            fig2.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="white", height=400)
            st.plotly_chart(fig2, use_container_width=True)

        # --- AI ---
        st.subheader("🤖 AI-Аудитор")
        if st.button("🚀 Анализ AI", type="primary"):
            if client:
                with st.spinner("Думаю..."):
                    csv = df.to_csv(index=False)
                    prompt = f"Ты финдир. Анализ склада:\n{csv}\nНайди 3 проблемы. Кратко. Жестко."
                    res = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role":"user","content":prompt}])
                    st.success("Готово!")
                    st.markdown(f"<div style='background-color:#262730;padding:20px;border-radius:10px;'>{res.choices[0].message.content}</div>", unsafe_allow_html=True)
            else: st.error("AI не подключен")

        with st.expander("Исходные данные"): st.dataframe(df, use_container_width=True)

    except Exception as e: st.error(f"Ошибка: {e}")
else: st.info("👈 Загрузите файл")
