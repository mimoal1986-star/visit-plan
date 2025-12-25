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
try:
    import simplekml
    SIMPLEKML_AVAILABLE = True
except ImportError:
    SIMPLEKML_AVAILABLE = False
    st.warning("⚠️ Библиотека simplekml не установлена. Установите: pip install simplekml")

# ВИЗУАЛИЗАЦИЯ
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import folium
from streamlit_folium import folium_static
import random
from math import radians, cos, sin, asin, sqrt

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
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("#### Шаблон Точки")
        points_template = create_template_points()
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            points_template.to_excel(writer, sheet_name='Точки', index=False)
        excel_data = excel_buffer.getvalue()
        st.markdown(get_download_link(excel_data, "шаблон_точки.xlsx", "📥 Скачать шаблон"), unsafe_allow_html=True)
    
    with col2:
        st.markdown("#### Шаблон Аудиторы")
        auditors_template = create_template_auditors()
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            auditors_template.to_excel(writer, sheet_name='Аудиторы', index=False)
        excel_data = excel_buffer.getvalue()
        st.markdown(get_download_link(excel_data, "шаблон_аудиторы.xlsx", "📥 Скачать шаблон"), unsafe_allow_html=True)
    
    with col3:
        st.markdown("#### Шаблон Факт посещений")
        visits_template = create_template_visits()
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            visits_template.to_excel(writer, sheet_name='Факт_посещений', index=False)
        excel_data = excel_buffer.getvalue()
        st.markdown(get_download_link(excel_data, "шаблон_посещений.xlsx", "📥 Скачать шаблон"), unsafe_allow_html=True)
    
    st.markdown("---")
    st.info("""
    **Как использовать шаблоны:**
    1. Скачайте все три шаблона
    2. Заполните данные в каждом файле
    3. Загрузите заполненные файлы в сервис
    4. Нажмите кнопку "Рассчитать план"
    """)

with upload_tab3:
    st.subheader("Описание полей")
    
    col1, col2 = st.columns(2)
    
    with col1:
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
        """)
    
    with col2:
        st.markdown("""
        ### Файл 'Аудиторы'
        
        **Обязательные поля:**
        - `ID_Сотрудника` - уникальный ID
        - `Город` - город работы
        
        ### Файл 'Факт_посещений'
        
        **Обязательные поля:**
        - `ID_Точки` - должен совпадать с ID в файле Точки
        - `Дата_визита` - дата посещения (дд.мм.гггг)
        - `ID_Сотрудника` - кто совершил визит
        
        **Формат:**
        - Одна строка = один визит
        - Можно оставить пустым, если данных нет
        """)

st.markdown("---")

# ==============================================
# ФУНКЦИИ ДЛЯ ОБРАБОТКИ ДАННЫХ
# ==============================================

def load_and_process_points(file):
    """Загружает и обрабатывает файл Точки"""
    try:
        df = pd.read_excel(file)
        
        # Проверяем обязательные колонки
        required_cols = ['ID_Точки', 'Широта', 'Долгота', 'Город', 'Тип']
        missing_cols = [col for col in required_cols if col not in df.columns]
        
        if missing_cols:
            # Попробуем найти альтернативные названия
            column_mapping = {
                'ID_Точки': ['ID точки', 'ID_точки', 'Point_ID'],
                'Широта': ['Latitude', 'Lat', 'широта'],
                'Долгота': ['Longitude', 'Lon', 'долгота'],
                'Город': ['City', 'city', 'Город работы'],
                'Тип': ['Type', 'Category', 'Тип точки']
            }
            
            for required_col in missing_cols:
                if required_col in column_mapping:
                    for alt_name in column_mapping[required_col]:
                        if alt_name in df.columns and required_col not in df.columns:
                            df = df.rename(columns={alt_name: required_col})
                            break
        
        # Проверяем еще раз
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            st.error(f"❌ В файле Точки отсутствуют обязательные колонки: {', '.join(missing_cols)}")
            return None
        
        # Конвертируем типы точек
        type_mapping = {
            'Convenience': 'Мини',
            'convenience': 'Мини',
            'Convenience Store': 'Мини',
            'Convenience store': 'Мини',
            'Hypermarket': 'Гипер',
            'hypermarket': 'Гипер',
            'Supermarket': 'Супер',
            'supermarket': 'Супер',
            'Мини': 'Мини',
            'Гипер': 'Гипер',
            'Супер': 'Супер'
        }
        
        if 'Тип' in df.columns:
            df['Тип'] = df['Тип'].map(type_mapping).fillna('Мини')
        
        # Обрабатываем количество посещений
        if 'Кол-во_посещений' in df.columns:
            df['Кол-во_посещений'] = pd.to_numeric(df['Кол-во_посещений'], errors='coerce').fillna(1).astype(int)
        else:
            df['Кол-во_посещений'] = 1
        
        # Добавляем недостающие колонки
        if 'Название_Точки' not in df.columns:
            df['Название_Точки'] = df['ID_Точки']
        if 'Адрес' not in df.columns:
            df['Адрес'] = ''
        
        # Валидация координат
        valid_coords = df[
            (df['Широта'] >= 41) & (df['Широта'] <= 82) &
            (df['Долгота'] >= 19) & (df['Долгота'] <= 180)
        ]
        
        invalid_coords = df[~df.index.isin(valid_coords.index)]
        if len(invalid_coords) > 0:
            st.warning(f"⚠️ Пропущено {len(invalid_coords)} точек с некорректными координатами (только Россия: широта 41-82, долгота 19-180)")
        
        if len(valid_coords) == 0:
            st.error("❌ Нет точек с корректными координатами")
            return None
        
        return valid_coords.reset_index(drop=True)
        
    except Exception as e:
        st.error(f"❌ Ошибка при обработке файла Точки: {str(e)}")
        return None

def load_and_process_auditors(file):
    """Загружает и обрабатывает файл Аудиторы"""
    try:
        df = pd.read_excel(file)
        
        # Стандартизируем названия колонок
        column_mapping = {
            'ID_Сотрудника': ['ID Сотрудника', 'ID_сотрудника', 'Employee_ID', 'employee_id', 'Сотрудник'],
            'Город': ['City', 'city', 'Город работы']
        }
        
        for target_col, alt_names in column_mapping.items():
            if target_col not in df.columns:
                for alt_name in alt_names:
                    if alt_name in df.columns:
                        df = df.rename(columns={alt_name: target_col})
                        break
        
        # Проверяем обязательные колонки
        required_cols = ['ID_Сотрудника', 'Город']
        missing_cols = [col for col in required_cols if col not in df.columns]
        
        if missing_cols:
            st.error(f"❌ В файле Аудиторы отсутствуют обязательные колонки: {', '.join(missing_cols)}")
            return None
        
        return df
        
    except Exception as e:
        st.error(f"❌ Ошибка при обработке файла Аудиторы: {str(e)}")
        return None

def load_and_process_visits(file):
    """Загружает и обрабатывает файл Факт_посещений"""
    try:
        if file is None:
            return pd.DataFrame(columns=['ID_Точки', 'Дата_визита', 'ID_Сотрудника'])
        
        df = pd.read_excel(file)
        
        # Стандартизируем названия колонок
        column_mapping = {
            'ID_Точки': ['ID точки', 'ID_точки', 'Point_ID'],
            'Дата_визита': ['Дата визита', 'Дата', 'Date', 'Visit Date', 'Дата посещения'],
            'ID_Сотрудника': ['ID Сотрудника', 'ID_сотрудника', 'Employee_ID', 'Сотрудник']
        }
        
        for target_col, alt_names in column_mapping.items():
            if target_col not in df.columns:
                for alt_name in alt_names:
                    if alt_name in df.columns:
                        df = df.rename(columns={alt_name: target_col})
                        break
        
        # Проверяем обязательные колонки
        required_cols = ['ID_Точки', 'Дата_визита', 'ID_Сотрудника']
        missing_cols = [col for col in required_cols if col not in df.columns]
        
        if missing_cols:
            st.warning(f"⚠️ В файле Факт_посещений отсутствуют колонки: {', '.join(missing_cols)}")
            return pd.DataFrame(columns=required_cols)
        
        # Преобразуем даты (пробуем разные форматы)
        date_formats = ['%d.%m.%Y', '%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d', '%Y/%m/%d']
        
        for date_format in date_formats:
            try:
                df['Дата_визита'] = pd.to_datetime(df['Дата_визита'], format=date_format, errors='raise')
                break
            except:
                continue
        else:
            # Если ни один формат не подошел, пробуем автоопределение
            df['Дата_визита'] = pd.to_datetime(df['Дата_визита'], errors='coerce')
        
        # Удаляем строки с невалидными датами
        invalid_dates = df['Дата_визита'].isna().sum()
        if invalid_dates > 0:
            st.warning(f"⚠️ Пропущено {invalid_dates} записей с невалидными датами")
        
        df = df.dropna(subset=['Дата_визита'])
        
        return df.reset_index(drop=True)
        
    except Exception as e:
        st.error(f"❌ Ошибка при обработке файла Факт_посещений: {str(e)}")
        return pd.DataFrame(columns=['ID_Точки', 'Дата_визита', 'ID_Сотрудника'])

# ==============================================
# ФУНКЦИИ ДЛЯ РАБОТЫ С ДАТАМИ И НЕДЕЛЯМИ
# ==============================================

def get_quarter_dates(year, quarter):
    """Возвращает даты начала и конца квартала"""
    quarter_starts = [date(year, 1, 1), date(year, 4, 1), date(year, 7, 1), date(year, 10, 1)]
    quarter_start = quarter_starts[quarter - 1]
    
    if quarter == 4:
        quarter_end = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        quarter_end = quarter_starts[quarter] - timedelta(days=1)
    
    return quarter_start, quarter_end

def get_iso_week(date_obj):
    """Возвращает ISO номер недели для даты"""
    return date_obj.isocalendar()[1]

def get_weeks_in_quarter(year, quarter):
    """Возвращает список недель в квартале с ISO номерами"""
    quarter_start, quarter_end = get_quarter_dates(year, quarter)
    
    weeks = []
    current_date = quarter_start
    
    while current_date <= quarter_end:
        week_start = current_date
        week_end = min(current_date + timedelta(days=6), quarter_end)
        
        iso_week = get_iso_week(week_start)
        
        weeks.append({
            'iso_week_number': iso_week,
            'start_date': week_start,
            'end_date': week_end,
            'week_display': f"Неделя {iso_week} ({week_start.strftime('%d.%m')}-{week_end.strftime('%d.%m')})"
        })
        
        current_date = week_end + timedelta(days=1)
    
    return weeks

# ==============================================
# АЛГОРИТМ РАСПРЕДЕЛЕНИЯ ТОЧЕК ПО АУДИТОРАМ
# ==============================================

def distribute_points_to_auditors(points_df, auditors_df):
    """
    Распределяет точки по аудиторам внутри каждого города
    Простой алгоритм: сортировка по долготе и деление на равные части
    """
    
    results = []
    polygons_info = {}
    
    # Группируем по городам
    for city in points_df['Город'].unique():
        city_points = points_df[points_df['Город'] == city].copy()
        city_auditors = auditors_df[auditors_df['Город'] == city]['ID_Сотрудника'].tolist()
        
        if len(city_auditors) == 0:
            st.warning(f"⚠️ В городе {city} нет аудиторов")
            continue
        
        if len(city_auditors) == 1:
            # Один аудитор - все точки ему
            auditor = city_auditors[0]
            for _, point in city_points.iterrows():
                results.append({
                    'ID_Точки': point['ID_Точки'],
                    'Аудитор': auditor,
                    'Город': city,
                    'Полигон': city
                })
            
            # Создаем полигон для одного аудитора
            polygons_info[f"{city}"] = {
                'auditor': auditor,
                'points': city_points[['ID_Точки', 'Широта', 'Долгота']].values.tolist()
            }
            
        else:
            # Несколько аудиторов - делим точки
            # Сортируем точки по долготе (запад → восток)
            city_points = city_points.sort_values('Долгота').reset_index(drop=True)
            
            # Определяем названия полигонов в зависимости от количества аудиторов
            directions = ['Запад', 'Центр', 'Восток', 'Север', 'Юг', 
                         'Северо-Запад', 'Северо-Восток', 'Юго-Запад', 'Юго-Восток']
            
            # Вычисляем индексы для деления
            n = len(city_auditors)
            chunk_size = len(city_points) // n
            
            for i, auditor in enumerate(city_auditors):
                # Определяем диапазон точек для этого аудитора
                start_idx = i * chunk_size
                if i == n - 1:  # Последний аудитор получает остаток
                    end_idx = len(city_points)
                else:
                    end_idx = (i + 1) * chunk_size
                
                auditor_points = city_points.iloc[start_idx:end_idx]
                
                if len(auditor_points) == 0:
                    st.warning(f"⚠️ Аудитор {auditor} в городе {city} не получил точек")
                    continue
                
                # Добавляем точки в результаты
                for _, point in auditor_points.iterrows():
                    polygon_name = f"{city}-{directions[i % len(directions)]}"
                    results.append({
                        'ID_Точки': point['ID_Точки'],
                        'Аудитор': auditor,
                        'Город': city,
                        'Полигон': polygon_name
                    })
                
                # Сохраняем информацию для полигона
                polygon_name = f"{city}-{directions[i % len(directions)]}"
                polygons_info[polygon_name] = {
                    'auditor': auditor,
                    'points': auditor_points[['ID_Точки', 'Широта', 'Долгота']].values.tolist()
                }
    
    if not results:
        st.error("❌ Не удалось распределить точки по аудиторам")
        return None, None
    
    return pd.DataFrame(results), polygons_info

# ==============================================
# ГЕНЕРАЦИЯ ПОЛИГОНОВ (ВЫПУКЛАЯ ОБОЛОЧКА)
# ==============================================

def generate_convex_hull(points_coords):
    """Генерирует выпуклую оболочку для набора точек"""
    global SCIPY_AVAILABLE
    
    if len(points_coords) < 3:
        # Для 1-2 точек создаем искусственный полигон вокруг них
        if len(points_coords) == 0:
            return []
        elif len(points_coords) == 1:
            # Извлекаем координаты
            point = points_coords[0]
            if isinstance(point, (list, tuple)) and len(point) >= 2:
                lat, lon = float(point[0]), float(point[1])
            else:
                # Если структура непонятная
                try:
                    lat, lon = float(point[0]), float(point[1])
                except:
                    lat, lon = 55.7558, 37.6173  # Координаты Москвы по умолчанию
            
            return [
                [lat - 0.001, lon - 0.001],
                [lat - 0.001, lon + 0.001],
                [lat + 0.001, lon + 0.001],
                [lat + 0.001, lon - 0.001],
                [lat - 0.001, lon - 0.001]
            ]
        elif len(points_coords) == 2:
            # Извлекаем координаты
            point1 = points_coords[0]
            point2 = points_coords[1]
            
            if isinstance(point1, (list, tuple)) and len(point1) >= 2:
                lat1, lon1 = float(point1[0]), float(point1[1])
            else:
                lat1, lon1 = 55.7558, 37.6173
                
            if isinstance(point2, (list, tuple)) and len(point2) >= 2:
                lat2, lon2 = float(point2[0]), float(point2[1])
            else:
                lat2, lon2 = 55.7658, 37.6273
            
            # Создаем прямоугольник между двумя точками
            return [
                [min(lat1, lat2) - 0.001, min(lon1, lon2) - 0.001],
                [min(lat1, lat2) - 0.001, max(lon1, lon2) + 0.001],
                [max(lat1, lat2) + 0.001, max(lon1, lon2) + 0.001],
                [max(lat1, lat2) + 0.001, min(lon1, lon2) - 0.001],
                [min(lat1, lat2) - 0.001, min(lon1, lon2) - 0.001]
            ]
    
    try:
        if SCIPY_AVAILABLE:
            # Преобразуем координаты в массив numpy
            # Фильтруем некорректные координаты
            valid_coords = []
            for p in points_coords:
                try:
                    lat, lon = float(p[0]), float(p[1])
                    if not (41 <= lat <= 82 and 19 <= lon <= 180):
                        continue
                    valid_coords.append([lat, lon])
                except:
                    continue
            
            if len(valid_coords) < 3:
                # Если после фильтрации осталось мало точек
                return generate_convex_hull(valid_coords)  # Рекурсивно обработаем
            
            coords_array = np.array(valid_coords)
            
            # Вычисляем выпуклую оболочку
            hull = ConvexHull(coords_array)
            
            # Получаем вершины полигона
            hull_points = coords_array[hull.vertices]
            
            # Сортируем по углу от центра для ровного полигона
            center = np.mean(hull_points, axis=0)
            angles = np.arctan2(hull_points[:, 1] - center[1], hull_points[:, 0] - center[0])
            hull_points = hull_points[np.argsort(angles)]
            
            # Замыкаем полигон
            hull_points = np.vstack([hull_points, hull_points[0]])
            
            return hull_points.tolist()
        else:
            # Без scipy используем bounding box
            valid_lats = []
            valid_lons = []
            for p in points_coords:
                try:
                    lat, lon = float(p[0]), float(p[1])
                    if 41 <= lat <= 82 and 19 <= lon <= 180:
                        valid_lats.append(lat)
                        valid_lons.append(lon)
                except:
                    continue
            
            if not valid_lats or not valid_lons:
                return []
            
            return [
                [min(valid_lats) - 0.001, min(valid_lons) - 0.001],
                [min(valid_lats) - 0.001, max(valid_lons) + 0.001],
                [max(valid_lats) + 0.001, max(valid_lons) + 0.001],
                [max(valid_lats) + 0.001, min(valid_lons) - 0.001],
                [min(valid_lats) - 0.001, min(valid_lons) - 0.001]
            ]
        
    except Exception as e:
        # В случае ошибки возвращаем bounding box
        valid_lats = []
        valid_lons = []
        for p in points_coords:
            try:
                lat, lon = float(p[0]), float(p[1])
                if 41 <= lat <= 82 and 19 <= lon <= 180:
                    valid_lats.append(lat)
                    valid_lons.append(lon)
            except:
                continue
        
        if not valid_lats or not valid_lons:
            return []
        
        return [
            [min(valid_lats) - 0.001, min(valid_lons) - 0.001],
            [min(valid_lats) - 0.001, max(valid_lons) + 0.001],
            [max(valid_lats) + 0.001, max(valid_lons) + 0.001],
            [max(valid_lats) + 0.001, min(valid_lons) - 0.001],
            [min(valid_lats) - 0.001, min(valid_lons) - 0.001]
        ]
    
    try:
        if SCIPY_AVAILABLE:
            # Преобразуем координаты в массив numpy
            coords_array = np.array([[p[0], p[1]] for p in points_coords])  # [[lat, lon], ...]
            
            # Вычисляем выпуклую оболочку
            hull = ConvexHull(coords_array)
            
            # Получаем вершины полигона
            hull_points = coords_array[hull.vertices]
            
            # Сортируем по углу от центра для ровного полигона
            center = np.mean(hull_points, axis=0)
            angles = np.arctan2(hull_points[:, 1] - center[1], hull_points[:, 0] - center[0])
            hull_points = hull_points[np.argsort(angles)]
            
            # Замыкаем полигон
            hull_points = np.vstack([hull_points, hull_points[0]])
            
            return hull_points.tolist()
        else:
            # Без scipy используем bounding box
            lats = [p[0] for p in points_coords]
            lons = [p[1] for p in points_coords]
            
            return [
                [min(lats) - 0.001, min(lons) - 0.001],
                [min(lats) - 0.001, max(lons) + 0.001],
                [max(lats) + 0.001, max(lons) + 0.001],
                [max(lats) + 0.001, min(lons) - 0.001],
                [min(lats) - 0.001, min(lons) - 0.001]
            ]
        
    except Exception as e:
        # В случае ошибки возвращаем bounding box
        lats = [p[0] for p in points_coords]
        lons = [p[1] for p in points_coords]
        
        return [
            [min(lats) - 0.001, min(lons) - 0.001],
            [min(lats) - 0.001, max(lons) + 0.001],
            [max(lats) + 0.001, max(lons) + 0.001],
            [max(lats) + 0.001, min(lons) - 0.001],
            [min(lats) - 0.001, min(lons) - 0.001]
        ]

def generate_polygons(polygons_info):
    """Генерирует полигоны для всех аудиторов"""
    polygons = {}
    
    for polygon_name, info in polygons_info.items():
        points_coords = [(p[1], p[2]) for p in info['points']]  # (lat, lon)
        
        # Генерируем выпуклую оболочку
        hull_coords = generate_convex_hull(points_coords)
        
        if not hull_coords:
            continue
        
        polygons[polygon_name] = {
            'auditor': info['auditor'],
            'city': polygon_name.split('-')[0],
            'coordinates': hull_coords,
            'points': info['points']
        }
    
    return polygons

# ==============================================
# РАСПРЕДЕЛЕНИЕ ПОСЕЩЕНИЙ ПО НЕДЕЛЯМ
# ==============================================

def distribute_visits_by_weeks(points_assignment_df, points_df, year, quarter, coefficients):
    """
    Распределяет посещения точек по неделям квартала
    с учетом коэффициентов этапов
    """
    
    # Получаем недели квартала
    weeks = get_weeks_in_quarter(year, quarter)
    
    # Определяем этапы
    total_weeks = len(weeks)
    weeks_per_stage = total_weeks // 4
    stage_assignments = []
    
    for i, week in enumerate(weeks):
        stage_idx = min(3, i // weeks_per_stage)
        stage_assignments.append({
            'iso_week': week['iso_week_number'],
            'stage': stage_idx,
            'coefficient': coefficients[stage_idx],
            'start_date': week['start_date'],
            'end_date': week['end_date']
        })
    
    # Создаем структуры для результатов
    detailed_results = []
    
    # Для каждой точки
    for _, assignment in points_assignment_df.iterrows():
        point_id = assignment['ID_Точки']
        auditor = assignment['Аудитор']
        city = assignment['Город']
        polygon = assignment['Полигон']
        
        # Находим информацию о точке
        point_info = points_df[points_df['ID_Точки'] == point_id].iloc[0]
        visits_needed = point_info['Кол-во_посещений']
        
        # Распределяем посещения по этапам
        total_coefficient = sum([coefficients[i] * (weeks_per_stage if i < 3 else total_weeks - 3*weeks_per_stage) 
                               for i in range(4)])
        
        if total_coefficient == 0:
            total_coefficient = 1  # Защита от деления на ноль
        
        # Вычисляем посещения на каждый этап (округляем вниз)
        stage_visits = []
        remaining_visits = visits_needed
        
        for i in range(3):  # Первые 3 этапа
            stage_weight = coefficients[i] * weeks_per_stage
            visits = int(np.floor(visits_needed * stage_weight / total_coefficient))
            stage_visits.append(max(0, min(visits, remaining_visits)))
            remaining_visits -= stage_visits[-1]
        
        # Четвертый этап получает остаток
        stage_visits.append(max(0, remaining_visits))
        
        # Распределяем посещения по неделям внутри этапов
        week_idx = 0

        for stage_idx in range(4):
            weeks_this_stage = weeks_per_stage if stage_idx < 3 else total_weeks - 3*weeks_per_stage
            visits_this_stage = stage_visits[stage_idx]
            remaining_visits_this_stage = visits_this_stage
            
            if visits_this_stage > 0 and weeks_this_stage > 0:
                # Распределяем посещения равномерно по неделям этапа
                # Вычисляем шаг для равномерного распределения
                if visits_this_stage > 0:
                    step = max(1, weeks_this_stage // visits_this_stage)
                else:
                    step = weeks_this_stage  # Большой шаг, чтобы не распределять
                    
                for week_in_stage in range(weeks_this_stage):
                    if week_idx >= len(weeks):
                        break
                    
                    week_info = stage_assignments[week_idx]
                    
                    # Определяем, нужно ли посещение на этой неделе
                    has_visit = False
                    if remaining_visits_this_stage > 0:
                        # Распределяем равномерно
                        if week_in_stage % step == 0:
                            has_visit = True
                            remaining_visits_this_stage -= 1
                        # Последняя неделя этапа - добавляем оставшиеся посещения
                        elif week_in_stage == weeks_this_stage - 1 and remaining_visits_this_stage > 0:
                            has_visit = True
                            remaining_visits_this_stage -= 1
                    
                    detailed_results.append({
                        'Город': city,
                        'Полигон': polygon,
                        'Аудитор': auditor,
                        'ISO_Неделя': week_info['iso_week'],
                        'Дата_начала': week_info['start_date'],
                        'Дата_окончания': week_info['end_date'],
                        'ID_Точки': point_id,
                        'Название_Точки': point_info['Название_Точки'],
                        'Адрес': point_info['Адрес'],
                        'Тип': point_info['Тип'],
                        'План_посещений': 1 if has_visit else 0
                    })
                    
                    week_idx += 1
            else:
                # Этап без посещений, все равно добавляем недели
                for _ in range(weeks_this_stage):
                    if week_idx >= len(weeks):
                        break
                    
                    week_info = stage_assignments[week_idx]
                    
                    detailed_results.append({
                        'Город': city,
                        'Полигон': polygon,
                        'Аудитор': auditor,
                        'ISO_Неделя': week_info['iso_week'],
                        'Дата_начала': week_info['start_date'],
                        'Дата_окончания': week_info['end_date'],
                        'ID_Точки': point_id,
                        'Название_Точки': point_info['Название_Точки'],
                        'Адрес': point_info['Адрес'],
                        'Тип': point_info['Тип'],
                        'План_посещений': 0
                    })
                    
                    week_idx += 1
    
    if not detailed_results:
        return pd.DataFrame()
    
    return pd.DataFrame(detailed_results)
    

# ==============================================
# ОБРАБОТКА ФАКТИЧЕСКИХ ПОСЕЩЕНИЙ
# ==============================================

def process_actual_visits(visits_df, points_df, year, quarter):
    """Обрабатывает фактические посещения"""
    if visits_df.empty:
        return pd.DataFrame(columns=['ID_Точки', 'Дата_визита', 'ID_Сотрудника', 'ISO_Неделя'])
    
    quarter_start, quarter_end = get_quarter_dates(year, quarter)

    # ИСПРАВЛЕНИЕ: Преобразуем date в datetime для сравнения с pd.Timestamp
    from datetime import datetime as dt_datetime  # Импортируем с другим именем чтобы избежать конфликта
    
    quarter_start_dt = pd.Timestamp(dt_datetime.combine(quarter_start, dt_datetime.min.time()))
    quarter_end_dt = pd.Timestamp(dt_datetime.combine(quarter_end, dt_datetime.max.time()))
    
    # Фильтруем посещения по кварталу
    visits_in_quarter = visits_df[
        (visits_df['Дата_визита'] >= quarter_start_dt) &
        (visits_df['Дата_визита'] <= quarter_end_dt)
    ].copy()
    
    if visits_in_quarter.empty:
        return pd.DataFrame(columns=['ID_Точки', 'Дата_визита', 'ID_Сотрудника', 'ISO_Неделя'])
    
    # Добавляем ISO неделю
    visits_in_quarter['ISO_Неделя'] = visits_in_quarter['Дата_визита'].apply(get_iso_week)
    
    # Проверяем соответствие точек
    valid_point_ids = set(points_df['ID_Точки'].unique())
    invalid_visits = visits_in_quarter[~visits_in_quarter['ID_Точки'].isin(valid_point_ids)]
    
    if len(invalid_visits) > 0:
        st.warning(f"⚠️ Найдено {len(invalid_visits)} посещений несуществующих точек")
    
    visits_in_quarter = visits_in_quarter[visits_in_quarter['ID_Точки'].isin(valid_point_ids)]
    
    return visits_in_quarter.reset_index(drop=True)

# ==============================================
# РАСЧЕТ СТАТИСТИКИ
# ==============================================

def calculate_statistics(points_df, visits_df, detailed_plan_df, year, quarter):
    """Рассчитывает статистику по городам и типам точек"""
    
    # Обрабатываем фактические посещения
    actual_visits = process_actual_visits(visits_df, points_df, year, quarter)
    
    # Статистика по городам
    city_stats = []
    
    for city in points_df['Город'].unique():
        city_points = points_df[points_df['Город'] == city]
        
        # План
        plan_visits = city_points['Кол-во_посещений'].sum()
        
        # Факт
        city_point_ids = set(city_points['ID_Точки'].tolist())
        if not actual_visits.empty:
            fact_visits = len(actual_visits[actual_visits['ID_Точки'].isin(city_point_ids)])
        else:
            fact_visits = 0
        
        # Процент выполнения
        completion = round((fact_visits / plan_visits * 100) if plan_visits > 0 else 0, 1)
        
        city_stats.append({
            'Город': city,
            'Всего_точек': len(city_points),
            'План_посещений': plan_visits,
            'Факт_посещений': fact_visits,
            '%_выполнения': completion
        })
    
    city_stats_df = pd.DataFrame(city_stats)
    
    # Статистика по типам точек
    type_stats = []
    
    for point_type in points_df['Тип'].unique():
        type_points = points_df[points_df['Тип'] == point_type]
        
        # План
        plan_visits = type_points['Кол-во_посещений'].sum()
        
        # Факт
        type_point_ids = set(type_points['ID_Точки'].tolist())
        if not actual_visits.empty:
            fact_visits = len(actual_visits[actual_visits['ID_Точки'].isin(type_point_ids)])
        else:
            fact_visits = 0
        
        # Процент выполнения
        completion = round((fact_visits / plan_visits * 100) if plan_visits > 0 else 0, 1)
        
        type_stats.append({
            'Тип': point_type,
            'План_посещений': plan_visits,
            'Факт_посещений': fact_visits,
            '%_выполнения': completion
        })
    
    type_stats_df = pd.DataFrame(type_stats)
    
    # Сводный план
    summary_df = detailed_plan_df.groupby([
        'Город', 'Полигон', 'Аудитор', 'ISO_Неделя', 'Дата_начала', 'Дата_окончания'
    ]).agg({
        'План_посещений': 'sum'
    }).reset_index()
    
    # Добавляем факт в сводный план
    if not actual_visits.empty:
        # Группируем факт по аудиторам и неделям
        fact_by_auditor_week = actual_visits.groupby(['ID_Сотрудника', 'ISO_Неделя']).size().reset_index(name='Факт_посещений')
        
        # Объединяем с планом
        summary_df = summary_df.merge(
            fact_by_auditor_week,
            left_on=['Аудитор', 'ISO_Неделя'],
            right_on=['ID_Сотрудника', 'ISO_Неделя'],
            how='left'
        )
        
        # Удаляем вспомогательную колонку
        if 'ID_Сотрудника' in summary_df.columns:
            summary_df = summary_df.drop(columns=['ID_Сотрудника'])
        
        summary_df['Факт_посещений'] = summary_df['Факт_посещений'].fillna(0).astype(int)
        
        # Рассчитываем процент выполнения
        summary_df['%_выполнения'] = summary_df.apply(
            lambda row: round((row['Факт_посещений'] / row['План_посещений'] * 100) if row['План_посещений'] > 0 else 0, 1),
            axis=1
        )
    else:
        summary_df['Факт_посещений'] = 0
        summary_df['%_выполнения'] = 0.0
    
    # Добавляем факт в детальный план
    detailed_with_fact = detailed_plan_df.copy()
    
    if not actual_visits.empty:
        # Считаем факт по точкам и неделям
        fact_by_point_week = actual_visits.groupby(['ID_Точки', 'ISO_Неделя']).size().reset_index(name='Факт_посещений')
        
        detailed_with_fact = detailed_with_fact.merge(
            fact_by_point_week,
            on=['ID_Точки', 'ISO_Неделя'],
            how='left'
        )
        detailed_with_fact['Факт_посещений'] = detailed_with_fact['Факт_посещений'].fillna(0).astype(int)
        
        # Проверяем выполнение плана (общее за квартал)
        # Сначала группируем по точкам общий факт
        total_fact_by_point = actual_visits.groupby('ID_Точки').size().reset_index(name='Общий_факт')
        
        # И общий план из points_df
        total_plan_by_point = points_df[['ID_Точки', 'Кол-во_посещений']].rename(columns={'Кол-во_посещений': 'Общий_план'})
        
        # Объединяем
        point_completion = total_plan_by_point.merge(total_fact_by_point, on='ID_Точки', how='left')
        point_completion['Общий_факт'] = point_completion['Общий_факт'].fillna(0).astype(int)
        point_completion['План_выполнен'] = point_completion['Общий_факт'] >= point_completion['Общий_план']
        
        # Добавляем в детальный план
        detailed_with_fact = detailed_with_fact.merge(
            point_completion[['ID_Точки', 'План_выполнен']],
            on='ID_Точки',
            how='left'
        )
        detailed_with_fact['План_выполнен'] = detailed_with_fact['План_выполнен'].fillna(False)
    else:
        detailed_with_fact['Факт_посещений'] = 0
        detailed_with_fact['План_выполнен'] = False
    
    return city_stats_df, type_stats_df, summary_df, detailed_with_fact

# ==============================================
# КНОПКА РАСЧЕТА ПЛАНА
# ==============================================

if st.button("🚀 Рассчитать план", type="primary", use_container_width=True):
    
    if not points_file or not auditors_file:
        st.error("⚠️ Пожалуйста, загрузите как минимум файлы 'Точки' и 'Аудиторы'!")
        st.stop()
    
    try:
        with st.spinner("🔄 Загрузка и обработка данных..."):
            # Загружаем данные
            points_df = load_and_process_points(points_file)
            auditors_df = load_and_process_auditors(auditors_file)
            visits_df = load_and_process_visits(visits_file)
            
            if points_df is None or auditors_df is None:
                st.stop()
            
            # Сохраняем в session state
            st.session_state.points_df = points_df
            st.session_state.auditors_df = auditors_df
            st.session_state.visits_df = visits_df
            
            # Проверяем соответствие городов
            cities_points = set(points_df['Город'].unique())
            cities_auditors = set(auditors_df['Город'].unique())
            
            cities_without_auditors = cities_points - cities_auditors
            cities_without_points = cities_auditors - cities_points
            
            if cities_without_auditors:
                st.warning(f"⚠️ В городах {', '.join(cities_without_auditors)} нет аудиторов")
            
            if cities_without_points:
                st.warning(f"⚠️ Аудиторы в городах {', '.join(cities_without_points)} не имеют точек")
        
        # Показываем предпросмотр данных
        st.success("✅ Данные успешно загружены!")
        
        with st.expander("📋 Предпросмотр загруженных данных", expanded=False):
            tab1, tab2, tab3 = st.tabs(["Точки", "Аудиторы", "Факт посещений"])
            
            with tab1:
                st.write(f"Загружено точек: {len(points_df)}")
                st.dataframe(points_df.head(10), use_container_width=True)
            
            with tab2:
                st.write(f"Загружено аудиторов: {len(auditors_df)}")
                st.dataframe(auditors_df.head(10), use_container_width=True)
            
            with tab3:
                if not visits_df.empty:
                    st.write(f"Загружено записей о посещениях: {len(visits_df)}")
                    st.dataframe(visits_df.head(10), use_container_width=True)
                else:
                    st.info("Данные о посещениях отсутствуют")
        
        st.markdown("---")
        st.header("📅 Расчет плана визитов")
        
        with st.spinner("🔄 Распределение точек по аудиторам..."):
            # Распределяем точки по аудиторам
            points_assignment_df, polygons_info = distribute_points_to_auditors(points_df, auditors_df)
            
            if points_assignment_df is None:
                st.error("❌ Не удалось распределить точки по аудиторам")
                st.stop()
            
            # Генерируем полигоны если нужно
            if st.session_state.generate_polygons_flag or True:  # Всегда генерируем полигоны
                polygons = generate_polygons(polygons_info)
                st.session_state.polygons = polygons
                st.session_state.generate_polygons_flag = False
                if polygons:
                    st.success(f"✅ Сгенерировано {len(polygons)} полигонов")
        
        with st.spinner("🔄 Распределение посещений по неделям..."):
            # Распределяем посещения по неделям
            detailed_plan_df = distribute_visits_by_weeks(
                points_assignment_df, points_df, year, quarter, coefficients
            )
            
            if detailed_plan_df.empty:
                st.error("❌ Не удалось распределить посещения по неделям")
                st.stop()
            
            st.success(f"✅ Распределено {len(detailed_plan_df)} записей по неделям")
        
        with st.spinner("🔄 Расчет статистики..."):
            # Рассчитываем статистику
            city_stats_df, type_stats_df, summary_df, detailed_with_fact = calculate_statistics(
                points_df, visits_df, detailed_plan_df, year, quarter
            )
            
            # Сохраняем результаты в session state
            st.session_state.city_stats_df = city_stats_df
            st.session_state.type_stats_df = type_stats_df
            st.session_state.summary_df = summary_df
            st.session_state.details_df = detailed_with_fact
            st.session_state.plan_calculated = True
        
        st.success("✅ План успешно рассчитан!")
        
        # Показываем краткую статистику
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Городов", len(city_stats_df))
        with col2:
            total_plan = points_df['Кол-во_посещений'].sum()
            st.metric("План посещений", total_plan)
        with col3:
            total_fact = city_stats_df['Факт_посещений'].sum()
            st.metric("Факт посещений", total_fact)
        with col4:
            total_completion = round((total_fact / total_plan * 100) if total_plan > 0 else 0, 1)
            st.metric("% выполнения", f"{total_completion}%")
        
        st.balloons()
        
    except Exception as e:
        st.error(f"❌ Произошла ошибка: {str(e)}")
        import traceback
        st.error(f"Детали ошибки:\n{traceback.format_exc()}")

# ==============================================
# ВКЛАДКИ С РЕЗУЛЬТАТАМИ
# ==============================================

if st.session_state.plan_calculated:
    st.markdown("---")
    st.header("📊 Результаты расчета")
    
    # Создаем вкладки
    results_tabs = st.tabs([
        "📊 Статистика по городам",
        "📋 Сводный план",
        "📍 Детализация",
        "📈 Диаграммы",
        "🗺️ Карта полигонов",
        "⚙️ Управление данными"
    ])
    
    # ВКЛАДКА 1: Статистика по городам
    with results_tabs[0]:
        st.subheader("📊 Статистика по городам")
        
        if st.session_state.city_stats_df is not None:
            city_stats = st.session_state.city_stats_df.copy()
            
            # Переименовываем колонки для отображения
            display_cols = ['Город', 'Всего_точек', 'План_посещений', 'Факт_посещений', '%_выполнения']
            display_df = city_stats[display_cols].copy()
            display_df = display_df.rename(columns={
                'Всего_точек': 'Всего точек',
                'План_посещений': 'План посещений',
                'Факт_посещений': 'Факт посещений',
                '%_выполнения': '% выполнения'
            })
            
            st.dataframe(display_df, use_container_width=True, hide_index=True)
            
            # Выгрузка в Excel
            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                display_df.to_excel(writer, sheet_name='Статистика по городам', index=False)
            
            excel_data = excel_buffer.getvalue()
            b64 = base64.b64encode(excel_data).decode()
            href = f'<a href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64}" download="статистика_городов.xlsx">📥 Скачать Excel</a>'
            st.markdown(href, unsafe_allow_html=True)
    
    # ВКЛАДКА 2: Сводный план
    with results_tabs[1]:
        st.subheader("📋 Сводный план посещений")
        
        if st.session_state.summary_df is not None:
            summary_df = st.session_state.summary_df.copy()
            
            # Фильтры
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                cities = ['Все'] + sorted(summary_df['Город'].dropna().unique().tolist())
                selected_city = st.selectbox("Город", cities, key="summary_city_filter")
            
            with col2:
                if selected_city != 'Все':
                    city_polygons = ['Все'] + sorted(summary_df[summary_df['Город'] == selected_city]['Полигон'].unique().tolist())
                else:
                    city_polygons = ['Все'] + sorted(summary_df['Полигон'].unique().tolist())
                selected_polygon = st.selectbox("Полигон", city_polygons, key="summary_polygon_filter")
            
            with col3:
                if selected_city != 'Все' and selected_polygon != 'Все':
                    city_auditors = ['Все'] + sorted(summary_df[
                        (summary_df['Город'] == selected_city) & 
                        (summary_df['Полигон'] == selected_polygon)
                    ]['Аудитор'].unique().tolist())
                elif selected_city != 'Все':
                    city_auditors = ['Все'] + sorted(summary_df[summary_df['Город'] == selected_city]['Аудитор'].unique().tolist())
                else:
                    city_auditors = ['Все'] + sorted(summary_df['Аудитор'].unique().tolist())
                selected_auditor = st.selectbox("Аудитор", city_auditors, key="summary_auditor_filter")
            
            with col4:
                weeks = ['Все'] + sorted(summary_df['ISO_Неделя'].unique().tolist())
                selected_week = st.selectbox("Неделя (ISO)", weeks, key="summary_week_filter")
            
            # Применяем фильтры
            filtered_df = summary_df.copy()
            
            if selected_city != 'Все':
                filtered_df = filtered_df[filtered_df['Город'] == selected_city]
            
            if selected_polygon != 'Все':
                filtered_df = filtered_df[filtered_df['Полигон'] == selected_polygon]
            
            if selected_auditor != 'Все':
                filtered_df = filtered_df[filtered_df['Аудитор'] == selected_auditor]
            
            if selected_week != 'Все':
                filtered_df = filtered_df[filtered_df['ISO_Неделя'] == selected_week]
            
            # Отображаем результаты
            if not filtered_df.empty:
                # Выбираем колонки для отображения
                display_cols = ['Город', 'Полигон', 'Аудитор', 'ISO_Неделя', 
                              'Дата_начала', 'Дата_окончания', 'План_посещений']
                
                if 'Факт_посещений' in filtered_df.columns:
                    display_cols.extend(['Факт_посещений', '%_выполнения'])
                
                display_df = filtered_df[display_cols].copy()
                
                # Форматируем даты
                display_df['Дата_начала'] = pd.to_datetime(display_df['Дата_начала']).dt.strftime('%d.%m.%Y')
                display_df['Дата_окончания'] = pd.to_datetime(display_df['Дата_окончания']).dt.strftime('%d.%m.%Y')
                
                # Переименовываем колонки
                display_df = display_df.rename(columns={
                    'ISO_Неделя': 'Неделя',
                    'Дата_начала': 'Начало недели',
                    'Дата_окончания': 'Конец недели',
                    'План_посещений': 'План',
                    'Факт_посещений': 'Факт',
                    '%_выполнения': '% выполнения'
                })
                
                # Сортируем
                display_df = display_df.sort_values(['Город', 'Полигон', 'Аудитор', 'Неделя'])
                
                st.dataframe(display_df, use_container_width=True, height=400)
                
                # Статистика
                col_stat1, col_stat2, col_stat3 = st.columns(3)
                with col_stat1:
                    st.metric("План", display_df['План'].sum())
                with col_stat2:
                    fact_sum = display_df['Факт'].sum() if 'Факт' in display_df.columns else 0
                    st.metric("Факт", fact_sum)
                with col_stat3:
                    plan_sum = display_df['План'].sum()
                    if plan_sum > 0 and 'Факт' in display_df.columns:
                        percent = round((fact_sum / plan_sum) * 100, 1)
                        st.metric("% выполнения", f"{percent}%")
                    else:
                        st.metric("% выполнения", "0%")
            else:
                st.info("Нет данных по выбранным фильтрам")
    
    # ВКЛАДКА 3: Детализация
    with results_tabs[2]:
        st.subheader("📍 Детализация посещений")
        
        if st.session_state.details_df is not None:
            details_df = st.session_state.details_df.copy()
            
            # Фильтры
            col1, col2, col3 = st.columns(3)
            
            with col1:
                cities = ['Все'] + sorted(details_df['Город'].dropna().unique().tolist())
                selected_city_detail = st.selectbox("Город", cities, key="detail_city_filter")
            
            with col2:
                if selected_city_detail != 'Все':
                    city_polygons = ['Все'] + sorted(details_df[details_df['Город'] == selected_city_detail]['Полигон'].unique().tolist())
                else:
                    city_polygons = ['Все'] + sorted(details_df['Полигон'].unique().tolist())
                selected_polygon_detail = st.selectbox("Полигон", city_polygons, key="detail_polygon_filter")
            
            with col3:
                weeks = ['Все'] + sorted(details_df['ISO_Неделя'].unique().tolist())
                selected_week_detail = st.selectbox("Неделя (ISO)", weeks, key="detail_week_filter")
            
            # Применяем фильтры
            filtered_details = details_df.copy()
            
            if selected_city_detail != 'Все':
                filtered_details = filtered_details[filtered_details['Город'] == selected_city_detail]
            
            if selected_polygon_detail != 'Все':
                filtered_details = filtered_details[filtered_details['Полигон'] == selected_polygon_detail]
            
            if selected_week_detail != 'Все':
                filtered_details = filtered_details[filtered_details['ISO_Неделя'] == selected_week_detail]
            
            if not filtered_details.empty:
                # Создаем форму для отметок
                with st.form(key="visits_marking_form"):
                    # Группируем по аудиторам
                    auditors = sorted(filtered_details['Аудитор'].unique())
                    
                    for auditor in auditors:
                        auditor_data = filtered_details[filtered_details['Аудитор'] == auditor]
                        
                        with st.expander(f"👤 Аудитор: {auditor} | 🏙️ Город: {auditor_data['Город'].iloc[0]} | 📍 Полигон: {auditor_data['Полигон'].iloc[0]}", expanded=False):
                            
                            # Отображаем точки
                            for _, row in auditor_data.iterrows():
                                if row['План_посещений'] > 0:  # Показываем только точки с планом посещений
                                    col1, col2, col3, col4, col5 = st.columns([2, 3, 3, 2, 1])
                                    
                                    with col1:
                                        st.text(f"**{row['ID_Точки']}**")
                                    with col2:
                                        st.text(row['Название_Точки'])
                                    with col3:
                                        address = row['Адрес'] if pd.notna(row['Адрес']) and row['Адрес'] != '' else "Адрес не указан"
                                        st.text(address)
                                    with col4:
                                        st.text(f"План: {row['План_посещений']} | Факт: {row['Факт_посещений']}")
                                    with col5:
                                        # Checkbox для отметки посещения
                                        checkbox_key = f"visited_{row['ID_Точки']}_{row['ISO_Неделя']}_{auditor}"
                                        
                                        # Значение по умолчанию - из данных
                                        default_value = row['План_выполнен']
                                        
                                        visited = st.checkbox(
                                            "✓", 
                                            key=checkbox_key,
                                            value=default_value,
                                            help="Отметить как выполненное"
                                        )
                    
                    submit_button = st.form_submit_button(label="💾 Сохранить все отметки")
                    if submit_button:
                        st.success("Отметки сохранены в session state!")
                        
                        # Собираем статистику по отметкам
                        visit_keys = [key for key in st.session_state.keys() if key.startswith('visited_') and st.session_state[key]]
                        if visit_keys:
                            st.info(f"✅ Отмечено {len(visit_keys)} посещений")
            
            else:
                st.info("Нет данных по выбранным фильтрам")
    
    # ВКЛАДКА 4: Диаграммы
    with results_tabs[3]:
        st.subheader("📈 Диаграммы и статистика")
        
        # 1. Диаграмма посещений по неделям
        st.markdown("### 📅 Посещения по неделям")
        
        if st.session_state.summary_df is not None:
            summary_df = st.session_state.summary_df
            
            weekly_data = summary_df.groupby('ISO_Неделя').agg({
                'План_посещений': 'sum',
                'Факт_посещений': 'sum'
            }).reset_index()
            
            fig1 = go.Figure()
            
            # План
            fig1.add_trace(go.Bar(
                x=weekly_data['ISO_Неделя'],
                y=weekly_data['План_посещений'],
                name='План',
                marker_color='#1f77b4',
                opacity=0.7
            ))
            
            # Факт
            fig1.add_trace(go.Bar(
                x=weekly_data['ISO_Неделя'],
                y=weekly_data['Факт_посещений'],
                name='Факт',
                marker_color='#2ca02c',
                opacity=0.8
            ))
            
            fig1.update_layout(
                title='План и факт посещений по неделям',
                xaxis_title='Неделя (ISO номер)',
                yaxis_title='Количество посещений',
                barmode='group',
                height=400,
                template='plotly_white'
            )
            
            st.plotly_chart(fig1, use_container_width=True)
        
        # 2. Статистика по типам точек
        st.markdown("### 🏪 Статистика по типам точек")
        
        if st.session_state.type_stats_df is not None:
            type_stats = st.session_state.type_stats_df.copy()
            
            # Отображаем таблицу
            st.dataframe(type_stats, use_container_width=True, hide_index=True)
            
            # Диаграмма
            fig2 = go.Figure()
            
            fig2.add_trace(go.Bar(
                x=type_stats['Тип'],
                y=type_stats['План_посещений'],
                name='План',
                marker_color='#1f77b4',
                opacity=0.7
            ))
            
            fig2.add_trace(go.Bar(
                x=type_stats['Тип'],
                y=type_stats['Факт_посещений'],
                name='Факт',
                marker_color='#2ca02c',
                opacity=0.8
            ))
            
            fig2.update_layout(
                title='План и факт посещений по типам точек',
                xaxis_title='Тип точки',
                yaxis_title='Количество посещений',
                barmode='group',
                height=300,
                template='plotly_white'
            )
            
            st.plotly_chart(fig2, use_container_width=True)
    
    # ВКЛАДКА 5: Карта полигонов
    with results_tabs[4]:
        st.subheader("🗺️ Карта полигонов аудиторов")
        
        if st.session_state.polygons is not None and len(st.session_state.polygons) > 0:
            polygons = st.session_state.polygons
            
            # Создаем карту
            if st.session_state.points_df is not None:
                points_df = st.session_state.points_df
                
                # Находим центр карты
                center_lat = points_df['Широта'].mean()
                center_lon = points_df['Долгота'].mean()
                
                m = folium.Map(location=[center_lat, center_lon], zoom_start=10)
                
                # Цвета для полигонов
                colors = px.colors.qualitative.Set3
                
                # Легенда
                from branca.element import Template, MacroElement
                
                template = """
                {% macro html(this, kwargs) %}
                <div style="
                    position: fixed; 
                    bottom: 50px;
                    left: 50px;
                    width: 250px;
                    height: auto;
                    background-color: white;
                    border: 2px solid grey;
                    z-index: 9999;
                    font-size: 14px;
                    padding: 10px;
                    border-radius: 5px;
                    ">
                    <p style="font-weight: bold; margin-bottom: 5px;">Легенда:</p>
                """
                
                # Добавляем полигоны и точки
                for i, (polygon_name, polygon_data) in enumerate(polygons.items()):
                    color = colors[i % len(colors)]
                    
                    # Добавляем в легенду
                    template += f"""
                    <p style="margin: 2px;">
                        <span style="background-color: {color}; width: 15px; height: 15px; display: inline-block; margin-right: 5px; border-radius: 3px;"></span>
                        {polygon_name} ({polygon_data['auditor']})
                    </p>
                    """
                    
                    # Полигон
                    folium.Polygon(
                        locations=polygon_data['coordinates'],
                        popup=f"""
                        <div style="font-family: Arial, sans-serif;">
                            <h4>📍 {polygon_name}</h4>
                            <p><b>👤 Аудитор:</b> {polygon_data['auditor']}</p>
                            <p><b>🏙️ Город:</b> {polygon_data['city']}</p>
                            <p><b>🔢 Количество точек:</b> {len(polygon_data['points'])}</p>
                        </div>
                        """,
                        tooltip=f"📍 {polygon_name}",
                        color=color,
                        fill=True,
                        fill_opacity=0.3,
                        weight=2
                    ).add_to(m)
                    
                    # Точки
                    for point in polygon_data['points']:
                        point_id, lat, lon = point
                        
                        # Находим информацию о точке
                        point_info = points_df[points_df['ID_Точки'] == point_id]
                        if not point_info.empty:
                            point_name = point_info['Название_Точки'].iloc[0]
                            point_address = point_info['Адрес'].iloc[0] if pd.notna(point_info['Адрес'].iloc[0]) and point_info['Адрес'].iloc[0] != '' else "Адрес не указан"
                            point_type = point_info['Тип'].iloc[0]
                        else:
                            point_name = point_id
                            point_address = "Информация не найдена"
                            point_type = "Неизвестно"
                        
                        folium.CircleMarker(
                            location=[lat, lon],
                            radius=5,
                            popup=f"""
                            <div style="font-family: Arial, sans-serif;">
                                <h4>🏪 {point_name}</h4>
                                <p><b>🆔 ID:</b> {point_id}</p>
                                <p><b>📍 Адрес:</b> {point_address}</p>
                                <p><b>🏷️ Тип:</b> {point_type}</p>
                                <p><b>👤 Аудитор:</b> {polygon_data['auditor']}</p>
                                <p><b>📍 Полигон:</b> {polygon_name}</p>
                            </div>
                            """,
                            tooltip=f"🏪 {point_name}",
                            color=color,
                            fill=True,
                            fill_opacity=0.7
                        ).add_to(m)
                
                # Завершаем легенду
                template += """
                </div>
                {% endmacro %}
                """
                
                macro = MacroElement()
                macro._template = Template(template)
                m.get_root().add_child(macro)
                
                # Отображаем карту
                folium_static(m, width=900, height=600)
                
  # Кнопка выгрузки KML
st.markdown("---")
st.subheader("📤 Выгрузка полигонов")

col1, col2 = st.columns(2)

with col1:
    if st.button("🗺️ Выгрузить KML файл", type="primary", use_container_width=True):
        try:
            import simplekml  # Добавьте импорт сюда
            # Создаем KML файл
            kml = simplekml.Kml()
            
            for polygon_name, polygon_data in polygons.items():
                # Полигон
                pol = kml.newpolygon(name=polygon_name)
                pol.outerboundaryis = polygon_data['coordinates']
                
                # Цвет из палитры
                color_idx = list(polygons.keys()).index(polygon_name) % len(colors)
                color_hex = colors[color_idx].lstrip('#')
                
                # Конвертируем цвет для KML (формат aabbggrr)
                if len(color_hex) == 6:
                    # Из RRGGBB в AABBGGRR
                    r = int(color_hex[0:2], 16)
                    g = int(color_hex[2:4], 16)
                    b = int(color_hex[4:6], 16)
                    kml_color = simplekml.Color.rgb(b, g, r, alpha=128)  # KML использует ABGR
                else:
                    kml_color = simplekml.Color.red
                
                pol.style.polystyle.color = kml_color
                
                # Описание
                pol.description = f"""
                <![CDATA[
                <h3>{polygon_name}</h3>
                <p><b>Аудитор:</b> {polygon_data['auditor']}</p>
                <p><b>Город:</b> {polygon_data['city']}</p>
                <p><b>Количество точек:</b> {len(polygon_data['points'])}</p>
                ]]>
                """
                
                # Добавляем точки в полигон
                folder = kml.newfolder(name=f"Точки полигона {polygon_name}")
                for point in polygon_data['points']:
                    point_id, lat, lon = point
                    
                    # Находим информацию о точке
                    point_info = points_df[points_df['ID_Точки'] == point_id]
                    if not point_info.empty:
                        point_name = point_info['Название_Точки'].iloc[0]
                        point_address = point_info['Адрес'].iloc[0] if pd.notna(point_info['Адрес'].iloc[0]) and point_info['Адрес'].iloc[0] != '' else "Адрес не указан"
                        point_type = point_info['Тип'].iloc[0]
                    else:
                        point_name = point_id
                        point_address = "Информация не найдена"
                        point_type = "Неизвестно"
                    
                    pnt = folder.newpoint(name=point_name)
                    pnt.coords = [(lon, lat)]
                    pnt.description = f"""
                    <![CDATA[
                    <h4>{point_name}</h4>
                    <p><b>ID:</b> {point_id}</p>
                    <p><b>Адрес:</b> {point_address}</p>
                    <p><b>Тип:</b> {point_type}</p>
                    <p><b>Аудитор:</b> {polygon_data['auditor']}</p>
                    ]]>
                    """
                    pnt.style.iconstyle.color = kml_color
            
            # Сохраняем KML
            # ИСПРАВЛЕНИЕ: Сохраняем KML в буфер памяти вместо файла
            import tempfile
            import os
            
            with tempfile.NamedTemporaryFile(mode='wb', suffix='.kml', delete=False) as tmp_file:
                kml.save(tmp_file.name)
                tmp_file_path = tmp_file.name

            # Читаем из временного файла
            with open(tmp_file_path, "rb") as f:
                kml_data = f.read()

            # Удаляем временный файл
            try:
                os.unlink(tmp_file_path)
            except:
                pass
            
            b64 = base64.b64encode(kml_data).decode()
            href = f'<a href="data:application/vnd.google-earth.kml+xml;base64,{b64}" download="полигоны_аудиторов.kml">📥 Скачать KML файл</a>'
            st.markdown(href, unsafe_allow_html=True)
            st.success("✅ KML файл успешно сгенерирован!")
            
        except Exception as e:
            st.error(f"❌ Ошибка при генерации KML: {str(e)}")

with col2:
    if st.button("🔄 Обновить полигоны", type="secondary", use_container_width=True):
        st.session_state.generate_polygons_flag = True
        st.rerun()
    else:
        st.info("Нет данных о точках для отображения на карте")
    else:
        st.info("Полигоны не сгенерированы. Нажмите кнопку 'Рассчитать план' для генерации полигонов.")
    
    # ВКЛАДКА 6: Управление данными
    with results_tabs[5]:
        st.subheader("⚙️ Управление данными и экспорт")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("### 📊 Экспорт данных")
            
            # Экспорт всех данных
            if st.button("📥 Экспорт всех данных в Excel", type="primary", use_container_width=True):
                if all(key in st.session_state for key in ['points_df', 'summary_df', 'details_df', 'city_stats_df', 'type_stats_df']):
                    
                    excel_buffer = io.BytesIO()
                    
                    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                        st.session_state.points_df.to_excel(writer, sheet_name='Точки', index=False)
                        st.session_state.summary_df.to_excel(writer, sheet_name='Сводный план', index=False)
                        st.session_state.details_df.to_excel(writer, sheet_name='Детализация', index=False)
                        st.session_state.city_stats_df.to_excel(writer, sheet_name='Статистика по городам', index=False)
                        st.session_state.type_stats_df.to_excel(writer, sheet_name='Статистика по типам', index=False)
                    
                    excel_data = excel_buffer.getvalue()
                    
                    b64 = base64.b64encode(excel_data).decode()
                    href = f'<a href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64}" download="все_данные.xlsx">📥 Скачать все данные (Excel)</a>'
                    st.markdown(href, unsafe_allow_html=True)
                    st.success("✅ Файл готов к скачиванию!")
                else:
                    st.warning("⚠️ Не все данные доступны для экспорта")
            
            # Экспорт отметок о посещениях
            st.markdown("---")
            st.markdown("### ✅ Экспорт отметок о посещениях")
            
            visit_keys = [key for key in st.session_state.keys() if key.startswith('visited_')]
            
            if visit_keys:
                visits_data = []
                for key in visit_keys:
                    if st.session_state[key]:
                        parts = key.split('_')
                        if len(parts) >= 4:
                            point_id = parts[1]
                            week = parts[2]
                            auditor = parts[3]
                            
                            visits_data.append({
                                'ID_Точки': point_id,
                                'Неделя': week,
                                'Аудитор': auditor,
                                'Отметка': 'Выполнено'
                            })
                
                if visits_data:
                    visits_df = pd.DataFrame(visits_data)
                    
                    csv = visits_df.to_csv(index=False, encoding='utf-8-sig')
                    st.download_button(
                        label="📥 Скачать отметки о посещениях (CSV)",
                        data=csv,
                        file_name="отметки_посещений.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
                else:
                    st.info("ℹ️ Нет сохраненных отметок о посещениях")
        
        with col2:
            st.markdown("### 🗑️ Очистка данных")
            
            st.warning("""
            ⚠️ **Внимание:** Очистка удалит все текущие расчеты
            и сбросит состояние приложения.
            """)
            
            if st.button("🧹 Очистить все данные", type="secondary", use_container_width=True):
                # Список ключей для очистки
                keys_to_clear = [
                    'points_df', 'auditors_df', 'visits_df',
                    'summary_df', 'details_df', 'city_stats_df',
                    'type_stats_df', 'polygons', 'plan_calculated',
                    'generate_polygons_flag'
                ]
                
                for key in keys_to_clear:
                    if key in st.session_state:
                        del st.session_state[key]
                
                # Очищаем отметки о посещениях
                visit_keys = [key for key in st.session_state.keys() if key.startswith('visited_')]
                for key in visit_keys:
                    del st.session_state[key]
                
                st.success("✅ Данные очищены! Обновите страницу.")
                st.rerun()

# ==============================================
# ИНФОРМАЦИЯ В ПОДВАЛЕ
# ==============================================

st.markdown("---")
st.caption(
    """
    **📋 Версия:** Полная реализация | **🔄 Статус:** Все функции реализованы  
    **✅ Включено:** Загрузка 3 файлов, расчет плана, фильтры, диаграммы, карты, полигоны, KML выгрузка  
    
    **🔧 Установите зависимости:**  
    ```bash
    pip install streamlit pandas numpy plotly folium streamlit-folium simplekml scipy openpyxl
    ```
    
    **📝 Примечания:**  
    1. Используйте шаблоны для заполнения данных  
    2. После расчета перейдите во вкладки для просмотра результатов  
    3. Полигоны генерируются автоматически при расчете плана  
    4. Для работы с полигонами требуется библиотека scipy  
    
    **👨‍💻 Разработано с учетом всех требований:**  
    - Распределение точек по аудиторам  
    - Генерация полигонов (выпуклая оболочка)  
    - Распределение посещений по неделям с коэффициентами  
    - Статистика план/факт/выполнение  
    - Выгрузка в Excel и KML форматы
    """

)








