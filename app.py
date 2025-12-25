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
    
    # Кнопка генерации полигонов - ДОБАВЬТЕ key
    if st.button("🗺️ Сгенерировать полигоны", type="secondary", use_container_width=True, key="generate_polygons_btn"):
        if st.session_state.plan_calculated:
            st.session_state.generate_polygons_flag = True
            st.rerun()
        else:
            st.warning("Сначала рассчитайте план!")
    
    st.info("""
    **Инструкция:**
    1. Загрузите файл с данными (1 файл, 3 вкладки)
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
# РАЗДЕЛ ЗАГРРУЗКИ ФАЙЛОВ
# ==============================================

st.header("📤 Загрузка файла")

upload_tab1, upload_tab2, upload_tab3 = st.tabs([
    "📁 Загрузка файла", 
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
    
    # Один загрузчик для всего файла - ДОБАВЬТЕ key
    data_file = st.file_uploader(
        "Файл с данными (Excel)", 
        type=['xlsx', 'xls'], 
        key="data_uploader_main",
        help="Excel файл с тремя вкладками: Точки, Аудиторы, Факт_посещений"
    )
    
    if data_file:
        st.success(f"✅ Загружен файл: {data_file.name}")
        
        # Сохраняем файл в session state
        st.session_state.data_file = data_file
        
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
        """)
    
    with desc_tabs[1]:
        st.markdown("""
        ### Вкладка 'Аудиторы'
        
        **Обязательные поля:**
        - `ID_Сотрудника` - уникальный ID
        - `Город` - город работы
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
        """)

st.markdown("---")

# ==============================================
# ФУНКЦИИ ДЛЯ ГЕНЕРАЦИИ ПОЛИГОНОВ
# ==============================================

def generate_convex_hull(points_coords):
    """Генерирует выпуклую оболочку для набора точек"""
    global SCIPY_AVAILABLE
    
    if len(points_coords) < 3:
        # Для 1-2 точек создаем искусственный полигон вокруг них
        if len(points_coords) == 0:
            return []
        elif len(points_coords) == 1:
            point = points_coords[0]
            if isinstance(point, (list, tuple)) and len(point) >= 2:
                lat, lon = point[0], point[1]
            else:
                lat, lon = 55.7558, 37.6173  # Координаты Москвы по умолчанию
            
            return [
                [lat - 0.001, lon - 0.001],
                [lat - 0.001, lon + 0.001],
                [lat + 0.001, lon + 0.001],
                [lat + 0.001, lon - 0.001],
                [lat - 0.001, lon - 0.001]
            ]
        elif len(points_coords) == 2:
            point1 = points_coords[0]
            point2 = points_coords[1]
            
            if isinstance(point1, (list, tuple)) and len(point1) >= 2:
                lat1, lon1 = point1[0], point1[1]
            else:
                lat1, lon1 = 55.7558, 37.6173
                
            if isinstance(point2, (list, tuple)) and len(point2) >= 2:
                lat2, lon2 = point2[0], point2[1]
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
            coords_array = np.array([[p[0], p[1]] for p in points_coords])
            
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

    # Преобразуем date в datetime для сравнения с pd.Timestamp
    from datetime import datetime as dt_datetime
    
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
# КНОПКА РАСЧЕТА ПЛАНА (полная реализация)
# ==============================================

if st.button("🚀 Рассчитать план", type="primary", use_container_width=True):
    
    if 'data_file' not in st.session_state or st.session_state.data_file is None:
        st.error("⚠️ Пожалуйста, сначала загрузите файл с данными!")
        st.stop()
    
    data_file = st.session_state.data_file
    
    try:
        with st.spinner("🔄 Загрузка и обработка данных..."):
            # Загружаем данные из одного файла
            points_raw, auditors_raw, visits_raw = load_and_process_data(data_file)
            
            if points_raw is None or auditors_raw is None:
                st.stop()
            
            # Обрабатываем каждую таблицу
            points_df = load_and_process_points(points_raw)
            auditors_df = load_and_process_auditors(auditors_raw)
            visits_df = load_and_process_visits(visits_raw)
            
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
            
            # Генерируем полигоны
            polygons = generate_polygons(polygons_info)
            st.session_state.polygons = polygons
            
            st.success(f"✅ Точки распределены по {len(polygons_info)} полигонам")
        
        with st.spinner("🔄 Распределение посещений по неделям..."):
            # Распределяем посещения по неделям
            detailed_plan_df = distribute_visits_by_weeks(
                points_assignment_df, points_df, year, quarter, coefficients
            )
            
            if detailed_plan_df.empty:
                st.error("❌ Не удалось распределить посещения по неделям")
                st.stop()
            
            st.success(f"✅ Распределено {len(detailed_plan_df)} записей по неделям")
        
        # Показываем краткую статистику распределения
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Всего точек", len(points_df))
        with col2:
            st.metric("Всего аудиторов", len(auditors_df))
        with col3:
            st.metric("Полигонов", len(polygons))
        with col4:
            total_visits = points_df['Кол-во_посещений'].sum()
            st.metric("Всего посещений", total_visits)
        
        # Сохраняем предварительные результаты
        st.session_state.polygons_info = polygons_info
        st.session_state.points_assignment_df = points_assignment_df
        st.session_state.detailed_plan_df = detailed_plan_df
        st.session_state.data_loaded = True
        st.session_state.plan_partial = True  # Отметка, что план частично рассчитан
        
        st.success("✅ План частично рассчитан! Готово для полного расчета со статистикой.")
        
    except Exception as e:
        st.error(f"❌ Произошла ошибка: {str(e)}")
        import traceback
        st.error(f"Детали ошибки:\n{traceback.format_exc()}")

# ==============================================
# ИНФОРМАЦИЯ О ПРОГРЕССЕ
# ==============================================

if st.session_state.get('plan_partial', False):
    st.markdown("---")
    st.success("📊 **Этап 2/3 завершен:** План частично рассчитан")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.info("""
        **✅ Что сделано:**
        1. Данные загружены и обработаны
        2. Точки распределены по аудиторам
        3. Сгенерированы полигоны
        4. Посещения распределены по неделям
        """)
    
    with col2:
        st.info("""
        **⏭️ Следующие шаги (Часть 3):**
        1. Расчет полной статистики
        2. Создание сводных отчетов
        3. Визуализация данных
        4. Экспорт результатов
        """)
    
    # Показываем предпросмотр распределения
    if st.session_state.get('points_assignment_df') is not None:
        with st.expander("👥 Предпросмотр распределения точек по аудиторам", expanded=False):
            assignment_df = st.session_state.points_assignment_df
            summary = assignment_df.groupby(['Город', 'Аудитор', 'Полигон']).size().reset_index(name='Количество точек')
            st.dataframe(summary, use_container_width=True)

st.markdown("---")
st.caption("📋 **Часть 2/5:** Функции обработки данных, генерация полигонов, распределение посещений по неделям")

# ==============================================
# ФУНКЦИИ ДЛЯ ОБРАБОТКИ ДАННЫХ
# ==============================================

def load_and_process_data(file):
    """Загружает и обрабатывает файл с тремя вкладками"""
    try:
        # Читаем все три вкладки
        points_df = pd.read_excel(file, sheet_name='Точки')
        auditors_df = pd.read_excel(file, sheet_name='Аудиторы')
        
        # Для факта посещений может быть пустая вкладка
        try:
            visits_df = pd.read_excel(file, sheet_name='Факт_посещений')
        except:
            visits_df = pd.DataFrame(columns=['ID_Точки', 'Дата_визита', 'ID_Сотрудника'])
        
        return points_df, auditors_df, visits_df
        
    except Exception as e:
        st.error(f"❌ Ошибка при загрузке файла: {str(e)}")
        return None, None, None

def load_and_process_points(df):
    """Обрабатывает данные из вкладки Точки"""
    try:
        # Копируем DataFrame чтобы не изменять оригинал
        points_df = df.copy()
        
        # Проверяем обязательные колонки
        required_cols = ['ID_Точки', 'Широта', 'Долгота', 'Город', 'Тип']
        missing_cols = [col for col in required_cols if col not in points_df.columns]
        
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
                        if alt_name in points_df.columns and required_col not in points_df.columns:
                            points_df = points_df.rename(columns={alt_name: required_col})
                            break
        
        # Проверяем еще раз
        missing_cols = [col for col in required_cols if col not in points_df.columns]
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
        
        if 'Тип' in points_df.columns:
            points_df['Тип'] = points_df['Тип'].map(type_mapping).fillna('Мини')
        
        # Обрабатываем количество посещений
        if 'Кол-во_посещений' in points_df.columns:
            points_df['Кол-во_посещений'] = pd.to_numeric(points_df['Кол-во_посещений'], errors='coerce').fillna(1).astype(int)
        else:
            points_df['Кол-во_посещений'] = 1
        
        # Добавляем недостающие колонки
        if 'Название_Точки' not in points_df.columns:
            points_df['Название_Точки'] = points_df['ID_Точки']
        if 'Адрес' not in points_df.columns:
            points_df['Адрес'] = ''
        
        # Валидация координат
        valid_coords = points_df[
            (points_df['Широта'] >= 41) & (points_df['Широта'] <= 82) &
            (points_df['Долгота'] >= 19) & (points_df['Долгота'] <= 180)
        ]
        
        invalid_coords = points_df[~points_df.index.isin(valid_coords.index)]
        if len(invalid_coords) > 0:
            st.warning(f"⚠️ Пропущено {len(invalid_coords)} точек с некорректными координатами (только Россия: широта 41-82, долгота 19-180)")
        
        if len(valid_coords) == 0:
            st.error("❌ Нет точек с корректными координатами")
            return None
        
        return valid_coords.reset_index(drop=True)
        
    except Exception as e:
        st.error(f"❌ Ошибка при обработке данных Точки: {str(e)}")
        return None

def load_and_process_auditors(df):
    """Обрабатывает данные из вкладки Аудиторы"""
    try:
        # Копируем DataFrame
        auditors_df = df.copy()
        
        # Стандартизируем названия колонок
        column_mapping = {
            'ID_Сотрудника': ['ID Сотрудника', 'ID_сотрудника', 'Employee_ID', 'employee_id', 'Сотрудник'],
            'Город': ['City', 'city', 'Город работы']
        }
        
        for target_col, alt_names in column_mapping.items():
            if target_col not in auditors_df.columns:
                for alt_name in alt_names:
                    if alt_name in auditors_df.columns:
                        auditors_df = auditors_df.rename(columns={alt_name: target_col})
                        break
        
        # Проверяем обязательные колонки
        required_cols = ['ID_Сотрудника', 'Город']
        missing_cols = [col for col in required_cols if col not in auditors_df.columns]
        
        if missing_cols:
            st.error(f"❌ В файле Аудиторы отсутствуют обязательные колонки: {', '.join(missing_cols)}")
            return None
        
        return auditors_df
        
    except Exception as e:
        st.error(f"❌ Ошибка при обработке данных Аудиторы: {str(e)}")
        return None

def load_and_process_visits(df):
    """Обрабатывает данные из вкладки Факт_посещений"""
    try:
        if df.empty:
            return pd.DataFrame(columns=['ID_Точки', 'Дата_визита', 'ID_Сотрудника'])
        
        # Копируем DataFrame
        visits_df = df.copy()
        
        # Стандартизируем названия колонок
        column_mapping = {
            'ID_Точки': ['ID точки', 'ID_точки', 'Point_ID'],
            'Дата_визита': ['Дата визита', 'Дата', 'Date', 'Visit Date', 'Дата посещения'],
            'ID_Сотрудника': ['ID Сотрудника', 'ID_сотрудника', 'Employee_ID', 'Сотрудник']
        }
        
        for target_col, alt_names in column_mapping.items():
            if target_col not in visits_df.columns:
                for alt_name in alt_names:
                    if alt_name in visits_df.columns:
                        visits_df = visits_df.rename(columns={alt_name: target_col})
                        break
        
        # Проверяем обязательные колонки
        required_cols = ['ID_Точки', 'Дата_визита', 'ID_Сотрудника']
        missing_cols = [col for col in required_cols if col not in visits_df.columns]
        
        if missing_cols:
            st.warning(f"⚠️ В файле Факт_посещений отсутствуют колонки: {', '.join(missing_cols)}")
            return pd.DataFrame(columns=required_cols)
        
        # Преобразуем даты (пробуем разные форматы)
        date_formats = ['%d.%m.%Y', '%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d', '%Y/%m/%d']
        
        for date_format in date_formats:
            try:
                visits_df['Дата_визита'] = pd.to_datetime(visits_df['Дата_визита'], format=date_format, errors='raise')
                break
            except:
                continue
        else:
            # Если ни один формат не подошел, пробуем автоопределение
            visits_df['Дата_визита'] = pd.to_datetime(visits_df['Дата_визита'], errors='coerce')
        
        # Удаляем строки с невалидными датами
        invalid_dates = visits_df['Дата_визита'].isna().sum()
        if invalid_dates > 0:
            st.warning(f"⚠️ Пропущено {invalid_dates} записей с невалидными датами")
        
        visits_df = visits_df.dropna(subset=['Дата_визита'])
        
        return visits_df.reset_index(drop=True)
        
    except Exception as e:
        st.error(f"❌ Ошибка при обработке данных Факт_посещений: {str(e)}")
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
# КНОПКА РАСЧЕТА ПЛАНА (полная реализация)
# ==============================================

if st.button("🚀 Рассчитать план", type="primary", use_container_width=True, key="calculate_plan_main"):
    
    if 'data_file' not in st.session_state or st.session_state.data_file is None:
        st.error("⚠️ Пожалуйста, сначала загрузите файл с данными!")
        st.stop()
    
    data_file = st.session_state.data_file
    
    try:
        with st.spinner("🔄 Загрузка и обработка данных..."):
            # Загружаем данные из одного файла
            points_raw, auditors_raw, visits_raw = load_and_process_data(data_file)
            
            if points_raw is None or auditors_raw is None:
                st.stop()
            
            # Обрабатываем каждую таблицу
            points_df = load_and_process_points(points_raw)
            auditors_df = load_and_process_auditors(auditors_raw)
            visits_df = load_and_process_visits(visits_raw)
            
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
            
            st.success(f"✅ Точки распределены по {len(polygons_info)} полигонам")
        
        # Показываем краткую статистику распределения
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Всего точек", len(points_df))
        with col2:
            st.metric("Всего аудиторов", len(auditors_df))
        with col3:
            st.metric("Полигонов", len(polygons_info))
        with col4:
            avg_points = len(points_df) / len(auditors_df) if len(auditors_df) > 0 else 0
            st.metric("Среднее точек на аудитора", f"{avg_points:.1f}")
        
        # Сохраняем предварительные результаты
        st.session_state.polygons_info = polygons_info
        st.session_state.points_assignment_df = points_assignment_df
        st.session_state.data_loaded = True
        
        st.success("✅ Готово! Данные обработаны и распределены по аудиторам.")
        
    except Exception as e:
        st.error(f"❌ Произошла ошибка: {str(e)}")
        import traceback
        st.error(f"Детали ошибки:\n{traceback.format_exc()}")

# ==============================================
# ИНФОРМАЦИЯ О ПРОГРЕССЕ
# ==============================================

if st.session_state.get('data_loaded', False):
    st.markdown("---")
    st.success("📊 **Этап 1/3 завершен:** Данные загружены и распределены по аудиторам")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.info("""
        **✅ Что сделано:**
        1. Файл загружен и проверен
        2. Данные обработаны
        3. Точки распределены по аудиторам
        4. Созданы полигоны для каждого аудитора
        """)
    
    with col2:
        st.info("""
        **⏭️ Следующие шаги (Часть 3):**
        1. Распределение посещений по неделям
        2. Генерация полигонов на карте
        3. Расчет статистики
        4. Создание отчетов
        """)

st.markdown("---")

st.caption("📋 **Часть 2/5:** Функции обработки данных, работа с датами, распределение точек по аудиторам")

