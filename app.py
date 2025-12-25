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

# Используем st.tabs для создания трех вкладок
upload_tab1, upload_tab2, upload_tab3 = st.tabs([
    "📁 Загрузка файлов", 
    "📥 Скачать шаблоны", 
    "📋 Описание полей"
])

with upload_tab1:
    st.subheader("Загрузите файлы с данными")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("#### Файл Точки")
        points_file = st.file_uploader(
            "Файл с точками (Excel)", 
            type=['xlsx', 'xls'], 
            key="points_uploader",
            help="Файл с информацией о торговых точках"
        )
        if points_file:
            st.success(f"✅ Загружен: {points_file.name}")
    
    with col2:
        st.markdown("#### Файл Аудиторы")
        auditors_file = st.file_uploader(
            "Файл с аудиторами (Excel)", 
            type=['xlsx', 'xls'], 
            key="auditors_uploader",
            help="Файл с информацией об аудиторах"
        )
        if auditors_file:
            st.success(f"✅ Загружен: {auditors_file.name}")
    
    with col3:
        st.markdown("#### Файл Факт посещений")
        visits_file = st.file_uploader(
            "Файл с посещениями (Excel)", 
            type=['xlsx', 'xls'], 
            key="visits_uploader",
            help="Файл с фактическими посещениями"
        )
        if visits_file:
            st.success(f"✅ Загружен: {visits_file.name}")
    
    if points_file and auditors_file:
        st.info("✅ Файлы загружены. Нажмите кнопку 'Рассчитать план'")
    else:
        st.warning("⚠️ Загрузите как минимум файлы 'Точки' и 'Аудиторы'")

with upload_tab2:
    st.subheader("Шаблоны файлов")
    
    # Создаем одну таблицу с тремя вкладками внутри
    template_tabs = st.tabs(["Точки", "Аудиторы", "Факт посещений"])
    
    with template_tabs[0]:
        st.markdown("#### Шаблон Точки")
        points_template = create_template_points()
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            points_template.to_excel(writer, sheet_name='Точки', index=False)
        excel_data = excel_buffer.getvalue()
        st.markdown(get_download_link(excel_data, "шаблон_точки.xlsx", "📥 Скачать шаблон"), unsafe_allow_html=True)
        
        # Показываем предпросмотр данных
        st.markdown("**Предпросмотр данных:**")
        st.dataframe(points_template, use_container_width=True)
    
    with template_tabs[1]:
        st.markdown("#### Шаблон Аудиторы")
        auditors_template = create_template_auditors()
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            auditors_template.to_excel(writer, sheet_name='Аудиторы', index=False)
        excel_data = excel_buffer.getvalue()
        st.markdown(get_download_link(excel_data, "шаблон_аудиторы.xlsx", "📥 Скачать шаблон"), unsafe_allow_html=True)
        
        # Показываем предпросмотр данных
        st.markdown("**Предпросмотр данных:**")
        st.dataframe(auditors_template, use_container_width=True)
    
    with template_tabs[2]:
        st.markdown("#### Шаблон Факт посещений")
        visits_template = create_template_visits()
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            visits_template.to_excel(writer, sheet_name='Факт_посещений', index=False)
        excel_data = excel_buffer.getvalue()
        st.markdown(get_download_link(excel_data, "шаблон_посещений.xlsx", "📥 Скачать шаблон"), unsafe_allow_html=True)
        
        # Показываем предпросмотр данных
        st.markdown("**Предпросмотр данных:**")
        st.dataframe(visits_template, use_container_width=True)
    
    st.markdown("---")
    st.info("""
    **Как использовать шаблоны:**
    1. Скачайте все три шаблоны
    2. Заполните данные в каждом файле
    3. Загрузите заполненные файлы в сервис
    4. Нажмите кнопку "Рассчитать план"
    """)

with upload_tab3:
    st.subheader("Описание полей")
    
    # Используем st.tabs для трех вкладок внутри описания
    desc_tabs = st.tabs(["Файл 'Точки'", "Файл 'Аудиторы'", "Файл 'Факт посещений'"])
    
    with desc_tabs[0]:
        st.markdown("""
        ### Файл 'Точки'
        
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
        ### Файл 'Аудиторы'
        
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
        ### Файл 'Факт_посещений'
        
        **Обязательные поля:**
        - `ID_Точки` - должен совпадать с ID в файле Точки
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
