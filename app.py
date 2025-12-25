import streamlit as st
import pandas as pd
import numpy as np
import io
from datetime import datetime, date, timedelta
import calendar
import json
import base64
from typing import Dict, List, Tuple, Optional, Any
import warnings
warnings.filterwarnings('ignore')

# ВИЗУАЛИЗАЦИЯ
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ГЕОМЕТРИЯ
try:
    from scipy.spatial import ConvexHull
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False
    st.warning("⚠️ Библиотека scipy не установлена. Установите: pip install scipy")

# НАСТРОЙКА СТРАНИЦЫ
st.set_page_config(
    page_title="Калькулятор плана визитов",
    page_icon="📊",
    layout="wide"
)

st.title("📊 Калькулятор плана визитов по сотрудникам")
st.markdown("---")

# ==============================================
# ИНИЦИАЛИЗАЦИЯ SESSION STATE
# ==============================================

if 'points_df' not in st.session_state:
    st.session_state.points_df = None
if 'auditors_df' not in st.session_state:
    st.session_state.auditors_df = None
if 'visits_df' not in st.session_state:
    st.session_state.visits_df = None
if 'summary_df' not in st.session_state:
    st.session_state.summary_df = None
if 'details_df' not in st.session_state:
    st.session_state.details_df = None
if 'city_stats_df' not in st.session_state:
    st.session_state.city_stats_df = None
if 'type_stats_df' not in st.session_state:
    st.session_state.type_stats_df = None
if 'polygons' not in st.session_state:
    st.session_state.polygons = None
if 'plan_calculated' not in st.session_state:
    st.session_state.plan_calculated = False
if 'generate_polygons_flag' not in st.session_state:
    st.session_state.generate_polygons_flag = False

# ==============================================
# БОКОВАЯ ПАНЕЛЬ - НАСТРОЙКИ
# ==============================================

with st.sidebar:
    st.header("⚙️ Настройки")
    
    # Выбор квартала и года
    col1, col2 = st.columns(2)
    with col1:
        quarter = st.selectbox("Квартал", [1, 2, 3, 4], index=0)
    with col2:
        year = st.selectbox("Год", list(range(2023, 2027)), index=2)
    
    # Коэффициенты этапов
    st.subheader("Коэффициенты нагрузки по этапам")
    st.caption("Квартал делится на 4 этапа")
    
    stage1 = st.number_input("Этап 1 коэффициент", value=0.8, min_value=0.1, max_value=2.0, step=0.1)
    stage2 = st.number_input("Этап 2 коэффициент", value=1.0, min_value=0.1, max_value=2.0, step=0.1)
    stage3 = st.number_input("Этап 3 коэффициент", value=1.2, min_value=0.1, max_value=2.0, step=0.1)
    stage4 = st.number_input("Этап 4 коэффициент", value=0.9, min_value=0.1, max_value=2.0, step=0.1)
    
    coefficients = [stage1, stage2, stage3, stage4]
    
    st.markdown("---")
    
    # Кнопка генерации полигонов
    if st.button("🗺️ Сгенерировать полигоны", type="secondary", use_container_width=True):
        if st.session_state.plan_calculated:
            st.session_state.generate_polygons_flag = True
            st.rerun()
        else:
            st.warning("Сначала рассчитайте план!")
    
    st.info("""
    **Инструкция:**
    1. Загрузите 3 файла с данными
    2. Настройте квартал и коэффициенты
    3. Нажмите кнопку "Рассчитать план"
    4. Используйте вкладки для анализа
    """)

# ==============================================
# ФУНКЦИИ ДЛЯ СОЗДАНИЯ ШАБЛОНОВ
# ==============================================

def create_template_points():
    """Создает шаблон для файла Точки"""
    data = {
        'ID_Точки': ['P001', 'P002', 'P003', 'P004'],
        'Название_Точки': ['Магазин 1', 'Гипермаркет 1', 'Супермаркет 1', 'Минимаркет 2'],
        'Адрес': ['ул. Ленина, 1', 'ул. Мира, 10', 'пр. Победы, 5', 'ул. Центральная, 3'],
        'Широта': [55.7558, 55.7507, 55.7601, 55.7520],
        'Долгота': [37.6173, 37.6177, 37.6254, 37.6200],
        'Город': ['Москва', 'Москва', 'Москва', 'Москва'],
        'Тип': ['Convenience', 'Hypermarket', 'Supermarket', 'Convenience'],
        'Кол-во_посещений': [1, 1, 1, 2]
    }
    return pd.DataFrame(data)

def create_template_auditors():
    """Создает шаблон для файла Аудиторы"""
    data = {
        'ID_Сотрудника': ['SOVIAUD10', 'SOVIAUD11', 'SOVIAUD12'],
        'Город': ['Москва', 'Москва', 'Санкт-Петербург']
    }
    return pd.DataFrame(data)

def create_template_visits():
    """Создает шаблон для файла Факт_посещений"""
    data = {
        'ID_Точки': ['P001', 'P001', 'P002'],
        'Дата_визита': ['15.04.2025', '30.04.2025', '16.04.2025'],
        'ID_Сотрудника': ['SOVIAUD10', 'SOVIAUD10', 'SOVIAUD11']
    }
    return pd.DataFrame(data)

# ==============================================
# ФУНКЦИИ ДЛЯ СКАЧИВАНИЯ ФАЙЛОВ
# ==============================================

def get_download_link(data, filename, text, mime_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'):
    """Генерирует ссылку для скачивания файла"""
    b64 = base64.b64encode(data).decode()
    href = f'<a href="data:{mime_type};base64,{b64}" download="{filename}">{text}</a>'
    return href

# ==============================================
# РАЗДЕЛ ЗАГРУЗКИ ФАЙЛОВ
# ==============================================

st.header("📤 Загрузка файлов")

upload_tab1, upload_tab2, upload_tab3 = st.tabs([
    "📁 Загрузка файлов", 
    "📥 Скачать шаблон", 
    "📋 Описание полей"
])

with upload_tab1:
    st.subheader("Загрузите файл с данными")
    
    st.info("""
    **📝 Формат файла:** 
    - Один файл Excel с тремя вкладками: "Точки", "Аудиторы", "Факт_посещений"
    - Скачайте шаблон справа, заполните данные и загрузите обратно
    """)
    
    # Один загрузчик для всего файла
    data_file = st.file_uploader(
        "Файл с данными (Excel)", 
        type=['xlsx', 'xls'], 
        key="data_uploader",
        help="Excel файл с тремя вкладками: Точки, Аудиторы, Факт_посещений"
    )
    
    if data_file:
        st.success(f"✅ Загружен файл: {data_file.name}")
        
        # Пробуем загрузить и проверить вкладки
        try:
            # Читаем названия всех листов
            xl = pd.ExcelFile(data_file)
            sheets = xl.sheet_names
            
            # Проверяем наличие необходимых листов
            required_sheets = ['Точки', 'Аудиторы', 'Факт_посещений']
            missing_sheets = [sheet for sheet in required_sheets if sheet not in sheets]
            
            if missing_sheets:
                st.warning(f"⚠️ В файле отсутствуют вкладки: {', '.join(missing_sheets)}")
                st.info("Убедитесь, что файл содержит вкладки с названиями: 'Точки', 'Аудиторы', 'Факт_посещений'")
            else:
                st.success("✅ Все необходимые вкладки найдены!")
                
                # Показываем предпросмотр каждой вкладки
                with st.expander("📋 Предпросмотр данных", expanded=False):
                    preview_tabs = st.tabs(["Точки", "Аудиторы", "Факт_посещений"])
                    
                    with preview_tabs[0]:
                        points_preview = pd.read_excel(data_file, sheet_name='Точки', nrows=5)
                        st.write(f"Точки: {len(points_preview)} строк")
                        st.dataframe(points_preview, use_container_width=True)
                    
                    with preview_tabs[1]:
                        auditors_preview = pd.read_excel(data_file, sheet_name='Аудиторы', nrows=5)
                        st.write(f"Аудиторы: {len(auditors_preview)} строк")
                        st.dataframe(auditors_preview, use_container_width=True)
                    
                    with preview_tabs[2]:
                        visits_preview = pd.read_excel(data_file, sheet_name='Факт_посещений', nrows=5)
                        st.write(f"Факт посещений: {len(visits_preview)} строк")
                        st.dataframe(visits_preview, use_container_width=True)
        
        except Exception as e:
            st.error(f"❌ Ошибка при чтении файла: {str(e)}")
    
    else:
        st.warning("⚠️ Загрузите файл с данными для продолжения")

with upload_tab2:
    st.subheader("Шаблон файла")
    
    st.info("""
    **📋 Инструкция:**
    1. Скачайте шаблон
    2. Заполните данные на каждой вкладке
    3. Сохраните файл
    4. Загрузите заполненный файл в приложение
    """)
    
    # Создаем файл с тремя вкладками
    excel_buffer = io.BytesIO()
    
    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
        # Вкладка 1: Точки
        points_template = create_template_points()
        points_template.to_excel(writer, sheet_name='Точки', index=False)
        
        # Вкладка 2: Аудиторы
        auditors_template = create_template_auditors()
        auditors_template.to_excel(writer, sheet_name='Аудиторы', index=False)
        
        # Вкладка 3: Факт_посещений
        visits_template = create_template_visits()
        visits_template.to_excel(writer, sheet_name='Факт_посещений', index=False)
    
    excel_data = excel_buffer.getvalue()
    
    # Кнопка скачивания
    st.download_button(
        label="📥 Скачать шаблон (Excel)",
        data=excel_data,
        file_name="шаблон_данных.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )
    
    # Предпросмотр вкладок шаблона
    st.markdown("---")
    st.markdown("**Предпросмотр шаблона:**")
    
    template_tabs = st.tabs(["Точки", "Аудиторы", "Факт_посещений"])
    
    with template_tabs[0]:
        st.markdown("##### Вкладка 'Точки'")
        st.dataframe(points_template, use_container_width=True)
        st.caption("Обязательные поля: ID_Точки, Широта, Долгота, Город, Тип")
    
    with template_tabs[1]:
        st.markdown("##### Вкладка 'Аудиторы'")
        st.dataframe(auditors_template, use_container_width=True)
        st.caption("Обязательные поля: ID_Сотрудника, Город")
    
    with template_tabs[2]:
        st.markdown("##### Вкладка 'Факт_посещений'")
        st.dataframe(visits_template, use_container_width=True)
        st.caption("Обязательные поля: ID_Точки, Дата_визита, ID_Сотрудника")
    
    st.markdown("---")
    st.success("✅ Шаблон содержит все три вкладки в одном файле Excel")

with upload_tab3:
    st.subheader("Описание полей")
    
    # Используем st.tabs для трех вкладок внутри описания
    desc_tabs = st.tabs(["Вкладка 'Точки'", "Вкладка 'Аудиторы'", "Вкладка 'Факт_посещений'"])
    
    with desc_tabs[0]:
        st.markdown("""
        ### Вкладка 'Точки'
        
        **Обязательные поля:**
        - `ID_Точки` - уникальный идентификатор
        - `Широта`, `Долгота` - координаты
        - `Тип` - Convenience/Hypermarket/Supermarket
        - `Город` - название города
        
        **Необязательные:**
        - `Адрес` - физический адрес
        - `Название_Точки` - название магазина
        - `Кол-во_посещений` - план посещений (по умолчанию 1)
        
        **Типы точек:**
        - `Convenience` → Мини
        - `Hypermarket` → Гипер
        - `Supermarket` → Супер
        
        **Пример данных:**
        ```csv
        ID_Точки,Название_Точки,Адрес,Широта,Долгота,Город,Тип,Кол-во_посещений
        P001,Магазин 1,ул. Ленина, 1,55.7558,37.6173,Москва,Convenience,1
        P002,Гипермаркет 1,ул. Мира, 10,55.7507,37.6177,Москва,Hypermarket,1
        ```
        """)
    
    with desc_tabs[1]:
        st.markdown("""
        ### Вкладка 'Аудиторы'
        
        **Обязательные поля:**
        - `ID_Сотрудника` - уникальный ID
        - `Город` - город работы
        
        **Пример данных:**
        ```csv
        ID_Сотрудника,Город
        SOVIAUD10,Москва
        SOVIAUD11,Москва
        SOVIAUD12,Санкт-Петербург
        ```
        """)
    
    with desc_tabs[2]:
        st.markdown("""
        ### Вкладка 'Факт_посещений'
        
        **Обязательные поля:**
        - `ID_Точки` - должен совпадать с ID во вкладке Точки
        - `Дата_визита` - дата посещения (дд.мм.гггг)
        - `ID_Сотрудника` - кто совершил визит
        
        **Формат:**
        - Одна строка = один визит
        - Можно оставить пустым, если данных нет
        
        **Пример данных:**
        ```csv
        ID_Точки,Дата_визита,ID_Сотрудника
        P001,15.04.2025,SOVIAUD10
        P001,30.04.2025,SOVIAUD10
        P002,16.04.2025,SOVIAUD11
        ```
        """)

st.markdown("---")
