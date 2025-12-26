# Картография
try:
    import folium
    from streamlit_folium import folium_static
    FOLIUM_AVAILABLE = True
except ImportError:
    FOLIUM_AVAILABLE = False
    # st.sidebar.warning("⚠️ Для карты установите: pip install folium streamlit-folium")
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

# ГЕОМЕТРИЯ - всегда используем упрощенную версию
SCIPY_AVAILABLE = False
try:
    # Пробуем импортировать scipy
    import scipy
    # Проверяем, можем ли мы использовать ConvexHull
    from scipy.spatial import ConvexHull
    SCIPY_AVAILABLE = True
    st.sidebar.success("✅ SciPy доступен")
except:
    SCIPY_AVAILABLE = False
    st.sidebar.info("ℹ️ Используется упрощенная генерация полигонов")

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
if 'data_loaded' not in st.session_state:
    st.session_state.data_loaded = False
if 'plan_partial' not in st.session_state:
    st.session_state.plan_partial = False

# ==============================================
# БОКОВАЯ ПАНЕЛЬ - НАСТРОЙКИ
# ==============================================

with st.sidebar:
    st.header("⚙️ Настройки")
    
    # Выбор квартала и года
    col1, col2 = st.columns(2)
    with col1:
        quarter = st.selectbox("Квартал", [1, 2, 3, 4], index=0, key="sidebar_quarter")
    with col2:
        year = st.selectbox("Год", list(range(2023, 2027)), index=2, key="sidebar_year")
    
    # Коэффициенты этапов
    st.subheader("Коэффициенты нагрузки по этапам")
    st.caption("Квартал делится на 4 этапа")
    
    stage1 = st.number_input("Этап 1 коэффициент", value=0.8, min_value=0.1, max_value=2.0, step=0.1, key="sidebar_stage1")
    stage2 = st.number_input("Этап 2 коэффициент", value=1.0, min_value=0.1, max_value=2.0, step=0.1, key="sidebar_stage2")
    stage3 = st.number_input("Этап 3 коэффициент", value=1.2, min_value=0.1, max_value=2.0, step=0.1, key="sidebar_stage3")
    stage4 = st.number_input("Этап 4 коэффициент", value=0.9, min_value=0.1, max_value=2.0, step=0.1, key="sidebar_stage4")
    
    coefficients = [stage1, stage2, stage3, stage4]
    
    st.markdown("---")
    
    st.info("""
    **Инструкция:**
    1. Загрузите файл с данными (1 файл, 3 вкладки)
    2. Настройте квартал и коэффициенты
    3. Нажмите кнопку "Рассчитать план"
    4. Используйте вкладки для анализа
    
    *Настройки сохраняются автоматически*
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
# ФУНКЦИИ ДЛЯ ГЕНЕРАЦИИ ПОЛИГОНОВ И РАСПРЕДЕЛЕНИЯ
# ==============================================
def create_simple_polygon(points):
    """Создает простой полигон (прямоугольник) без SciPy"""
    if len(points) == 0:
        return []
    
    # ИСПРАВЛЕНИЕ: безопасное извлечение координат из разных форматов
    coords = []
    
    if isinstance(points, np.ndarray):
        # Формат numpy array
        if points.ndim == 2 and points.shape[1] >= 3:
            # Предполагаем формат: [ID, широта, долгота, ...]
            for point in points:
                if len(point) >= 3:
                    try:
                        lat = float(point[1])
                        lon = float(point[2])
                        coords.append([lat, lon])
                    except (ValueError, TypeError, IndexError):
                        continue
    else:
        # Формат списка/кортежа
        for point in points:
            if isinstance(point, (list, tuple, np.ndarray)) and len(point) >= 3:
                try:
                    # Формат: [ID, широта, долгота]
                    lat = float(point[1])
                    lon = float(point[2])
                    coords.append([lat, lon])
                except (ValueError, TypeError, IndexError):
                    continue
    
    # ИСПРАВЛЕНИЕ: если не удалось извлечь координаты
    if not coords:
        return []
    
    if len(coords) == 1:
        # Одна точка - возвращаем пустой список
        return []
    elif len(coords) == 2:
        # Две точки - создаем линию
        return [coords[0], coords[1], coords[0]]
    else:
        # Несколько точек - создаем bounding box
        lats = [c[0] for c in coords]
        lons = [c[1] for c in coords]
        
        min_lat, max_lat = min(lats), max(lats)
        min_lon, max_lon = min(lons), max(lons)
        
        # Создаем прямоугольник
        polygon = [
            [min_lat, min_lon],  # нижний левый
            [min_lat, max_lon],  # нижний правый
            [max_lat, max_lon],  # верхний правый
            [max_lat, min_lon],  # верхний левый
            [min_lat, min_lon]   # замыкаем полигон
        ]

        return polygon
        
def generate_polygons(polygons_info):
    """Генерирует полигоны на основе информации о точках"""
    polygons = {}
    
    # ИСПРАВЛЕНИЕ: проверяем входные данные
    if not polygons_info or not isinstance(polygons_info, dict):
        return {}
    
    try:
        for polygon_name, info in polygons_info.items():
            # ИСПРАВЛЕНИЕ: проверяем структуру info
            if not info or not isinstance(info, dict) or 'points' not in info:
                continue
                
            points = np.array(info['points'])
            
            # ИСПРАВЛЕНИЕ: добавляем проверку на пустые данные
            if len(points) == 0:
                polygons[polygon_name] = {
                    'auditor': info.get('auditor', 'Неизвестно'),
                    'coordinates': [],
                    'points_count': 0
                }
                continue
                
            if len(points) < 2:
                # Если меньше 2 точек, не можем построить полигон
                polygons[polygon_name] = {
                    'auditor': info.get('auditor', 'Неизвестно'),
                    'coordinates': [],
                    'points_count': len(points)
                }
                continue
            
            # Всегда используем упрощенный метод
            polygon_coords = create_simple_polygon(points)
            
            polygons[polygon_name] = {
                'auditor': info['auditor'],
                'coordinates': polygon_coords,
                'points_count': len(points)
            }
        
        return polygons
    except Exception as e:
        st.error(f"❌ Ошибка при генерации полигонов: {str(e)}")
        import traceback
        st.error(f"Детали ошибки:\n{traceback.format_exc()}")
        return {}

def distribute_visits_by_weeks(points_assignment_df, points_df, year, quarter, coefficients):
    """Распределяет посещения по неделям: сначала по этапам, потом по дням, потом по неделям"""
    try:
        # 1. Создаем структуру для хранения плана по аудиторам и неделям
        weekly_plan = []
        
        # 2. Получаем даты квартала
        quarter_start, quarter_end = get_quarter_dates(year, quarter)
        
        # 3. Получаем недели в квартале
        weeks = get_weeks_in_quarter(year, quarter)
        
        # 4. Рассчитываем общий план по городам
        city_plans = {}
        for city in points_df['Город'].unique():
            city_points = points_df[points_df['Город'] == city]
            total_plan = city_points['Кол-во_посещений'].sum()
            city_plans[city] = total_plan
        
        # 5. Делим квартал на 4 равных этапа (по дням, не по неделям)
        total_days = (quarter_end - quarter_start).days + 1
        stage_length = total_days // 4
        
        # Определяем даты начала каждого этапа
        stage_dates = []
        for i in range(4):
            if i == 0:
                start_date = quarter_start
            else:
                start_date = stage_dates[i-1]['end_date'] + timedelta(days=1)
            
            if i == 3:  # Последний этап - все оставшиеся дни
                end_date = quarter_end
            else:
                end_date = start_date + timedelta(days=stage_length - 1)
            
            stage_dates.append({
                'stage_num': i + 1,
                'start_date': start_date,
                'end_date': end_date,
                'coefficient': coefficients[i] if i < len(coefficients) else 1.0
            })
        
        # 6. Для каждого города распределяем план
        for city, total_plan in city_plans.items():
            # Пропускаем города с нулевым планом
            if total_plan <= 0:
                continue
            
            # Получаем аудиторов города
            city_assignments = points_assignment_df[points_assignment_df['Город'] == city]
            if city_assignments.empty:
                continue
                
            city_auditors = city_assignments['Аудитор'].unique()
            
            # 6.1. Распределяем общий план по этапам с учетом коэффициентов
            stage_plans = {}
            total_coeff = sum(stage['coefficient'] for stage in stage_dates)
            
            for stage in stage_dates:
                # План этапа = общий план × (коэф этапа / сумма коэф)
                stage_plan = total_plan * (stage['coefficient'] / total_coeff)
                stage_plans[stage['stage_num']] = {
                    'plan': stage_plan,
                    'start_date': stage['start_date'],
                    'end_date': stage['end_date']
                }
            
            # 6.2. Для каждого этапа распределяем план по дням
            daily_visits = {}  # {дата: количество визитов}
            
            for stage_num, stage_info in stage_plans.items():
                stage_start = stage_info['start_date']
                stage_end = stage_info['end_date']
                stage_total_plan = stage_info['plan']
                
                # Считаем рабочие дни в этапе (пн-пт)
                work_days = []
                current_date = stage_start
                while current_date <= stage_end:
                    # Только понедельник-пятница (0=пн, 4=пт)
                    if current_date.weekday() < 5:
                        work_days.append(current_date)
                    current_date += timedelta(days=1)
                
                if not work_days:
                    continue
                
                # Распределяем план по дням
                daily_plan = stage_total_plan / len(work_days)
                
                # Для каждого дня: округляем вниз, на последний день - остаток
                remaining_plan = stage_total_plan
                
                for i, day in enumerate(work_days):
                    if i < len(work_days) - 1:
                        # Все дни кроме последнего: округляем вниз
                        day_plan = int(daily_plan)
                        remaining_plan -= day_plan
                    else:
                        # Последний день: берем остаток
                        day_plan = int(round(remaining_plan))
                    
                    if day in daily_visits:
                        daily_visits[day] += day_plan
                    else:
                        daily_visits[day] = day_plan
            
            # 6.3. Агрегируем по неделям
            week_visits = {}  # {iso_week: общее_количество_визитов}
            for day, visits in daily_visits.items():
                iso_week = get_iso_week(day)
                if iso_week not in week_visits:
                    week_visits[iso_week] = 0
                week_visits[iso_week] += visits
            
            # 6.4. Распределяем план недели между аудиторами города
            for iso_week, week_total_visits in week_visits.items():
                if week_total_visits <= 0:
                    continue
                
                # Равномерно между аудиторами города
                visits_per_auditor = week_total_visits // len(city_auditors)
                remainder = week_total_visits % len(city_auditors)
                
                for i, auditor in enumerate(city_auditors):
                    auditor_visits = visits_per_auditor
                    if i < remainder:  # Распределяем остаток
                        auditor_visits += 1
                    
                    if auditor_visits <= 0:
                        continue
                    
                    # Находим полигон аудитора
                    auditor_data = city_assignments[city_assignments['Аудитор'] == auditor]
                    if not auditor_data.empty:
                        auditor_polygon = auditor_data['Полигон'].iloc[0]
                    else:
                        auditor_polygon = city
                    
                    # Находим даты недели
                    week_info = next((w for w in weeks if w['iso_week_number'] == iso_week), None)
                    if week_info:
                        weekly_plan.append({
                            'Город': city,
                            'Полигон': auditor_polygon,
                            'Аудитор': auditor,
                            'ISO_Неделя': iso_week,
                            'Дата_начала': week_info['start_date'],
                            'Дата_окончания': week_info['end_date'],
                            'План_посещений': auditor_visits
                        })
        
        # 7. Сортируем результат
        result_df = pd.DataFrame(weekly_plan)
        if not result_df.empty:
            result_df = result_df.sort_values(['Город', 'Аудитор', 'ISO_Неделя'])
        
        return result_df
        
    except Exception as e:
        import traceback
        st.error(f"❌ Ошибка при распределении посещений по неделям: {str(e)}")
        st.error(f"Детали:\n{traceback.format_exc()}")
        return pd.DataFrame()
        
def distribute_points_to_auditors(points_df, auditors_df):
    """
    Распределяет точки по аудиторам внутри каждого города
    Простой алгоритм: сортировка по долготе и деление на равные части
    """
    
    # ПРОВЕРКА: если нет данных - возвращаем None
    if points_df is None or points_df.empty:
        st.error("❌ Нет данных о точках для распределения")
        return None, None  # ВАЖНО: возвращаем None для согласованности с обработчиком
    
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
    
    # ВАЖНОЕ ИСПРАВЛЕНИЕ: если нет результатов, возвращаем None
    if not results:
        st.warning("⚠️ Не удалось распределить точки по аудиторам (нет подходящих городов)")
        return None, None  # Возвращаем None для согласованности с обработчиком
    
    return pd.DataFrame(results), polygons_info
# ==============================================
# ФУНКЦИИ ДЛЯ ОБРАБОТКИ ФАКТИЧЕСКИХ ПОСЕЩЕНИЙ И СТАТИСТИКИ
# ==============================================

def process_actual_visits(visits_df, points_df, year, quarter):
    """Обрабатывает фактические посещения за квартал"""
    
    if visits_df.empty:
        return pd.DataFrame(columns=['ID_Точки', 'Дата_визита', 'ID_Сотрудника', 'ISO_Неделя'])
    
    # Получаем даты квартала
    quarter_start, quarter_end = get_quarter_dates(year, quarter)
    
    # Преобразуем даты для сравнения
    # ИСПРАВЛЕНИЕ: используем уже импортированный datetime
    quarter_start_dt = pd.Timestamp(datetime.combine(quarter_start, datetime.min.time()))
    quarter_end_dt = pd.Timestamp(datetime.combine(quarter_end, datetime.max.time()))
    
    # Фильтруем посещения по кварталу
    visits_in_quarter = visits_df[
        (visits_df['Дата_визита'] >= quarter_start_dt) &
        (visits_df['Дата_визита'] <= quarter_end_dt)
    ].copy()
    
    if visits_in_quarter.empty:
        return pd.DataFrame(columns=['ID_Точки', 'Дата_визита', 'ID_Сотрудника', 'ISO_Неделя'])
    
    # Добавляем ISO неделю
    visits_in_quarter['ISO_Неделя'] = visits_in_quarter['Дата_визита'].apply(get_iso_week)
    
    # Проверяем соответствие точек (только те, что есть в файле Точки)
    valid_point_ids = set(points_df['ID_Точки'].unique())
    invalid_visits = visits_in_quarter[~visits_in_quarter['ID_Точки'].isin(valid_point_ids)]
    
    if len(invalid_visits) > 0:
        st.warning(f"⚠️ Найдено {len(invalid_visits)} посещений несуществующих точек")
    
    # Оставляем только валидные посещения
    visits_in_quarter = visits_in_quarter[visits_in_quarter['ID_Точки'].isin(valid_point_ids)]
    
    return visits_in_quarter.reset_index(drop=True)

def calculate_statistics(points_df, visits_df, detailed_plan_df, year, quarter):
    """Рассчитывает полную статистику по городам и типам точек"""
    
    # Обрабатываем фактические посещения
    actual_visits = process_actual_visits(visits_df, points_df, year, quarter)
    
    # 1. Статистика по городам
    city_stats = []
    
    for city in points_df['Город'].unique():
        city_points = points_df[points_df['Город'] == city]
        
        # План посещений
        plan_visits = city_points['Кол-во_посещений'].sum()
        
        # Факт посещений
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
    
    # 2. Статистика по типам точек
    type_stats = []
    
    for point_type in points_df['Тип'].unique():
        type_points = points_df[points_df['Тип'] == point_type]
        
        # План посещений
        plan_visits = type_points['Кол-во_посещений'].sum()
        
        # Факт посещений
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
    
    # 3. Сводный план (группировка по аудиторам и неделям)
    # Проверяем, какие колонки есть в данных
    if 'ISO_Неделя' in detailed_plan_df.columns:
        week_col = 'ISO_Неделя'
    elif 'Неделя_ISO' in detailed_plan_df.columns:
        week_col = 'Неделя_ISO'
    else:
        # Если нет колонки с неделями, создаем её
        detailed_plan_df['ISO_Неделя'] = 1
        week_col = 'ISO_Неделя'
    
    # Проверяем колонки дат
    date_cols = []
    for date_col in ['Дата_начала', 'Дата_начала_недели']:
        if date_col in detailed_plan_df.columns:
            start_col = date_col
            break
    else:
        start_col = 'Дата_начала_недели'
        detailed_plan_df[start_col] = date.today()
    
    for date_col in ['Дата_окончания', 'Дата_окончания_недели']:
        if date_col in detailed_plan_df.columns:
            end_col = date_col
            break
    else:
        end_col = 'Дата_окончания_недели'
        detailed_plan_df[end_col] = date.today()
    
    # Группируем данные
    summary_df = detailed_plan_df.groupby([
        'Город', 'Полигон', 'Аудитор', week_col, start_col, end_col
    ]).agg({
        'План_посещений': 'sum'
    }).reset_index()
    
    # Переименовываем для единообразия
    summary_df = summary_df.rename(columns={
        week_col: 'ISO_Неделя',
        start_col: 'Дата_начала',
        end_col: 'Дата_окончания'
    })
    
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
    
    # 4. Детальный план с фактом
    detailed_with_fact = detailed_plan_df.copy()
    
    if not actual_visits.empty:
        # Считаем факт по точкам и неделям
        fact_by_point_week = actual_visits.groupby(['ID_Точки', 'ISO_Неделя']).size().reset_index(name='Факт_посещений')
        
        # Определяем, какая колонка с неделями есть в детальных данных
        week_column = 'ISO_Неделя' if 'ISO_Неделя' in detailed_with_fact.columns else 'Неделя_ISO'
        
        # Переименовываем для слияния
        detailed_with_fact = detailed_with_fact.rename(columns={week_column: 'ISO_Неделя'})
        
        detailed_with_fact = detailed_with_fact.merge(
            fact_by_point_week,
            on=['ID_Точки', 'ISO_Неделя'],
            how='left'
        )
        detailed_with_fact['Факт_посещений'] = detailed_with_fact['Факт_посещений'].fillna(0).astype(int)
        
        # Проверяем выполнение плана (общее за квартал)
        total_fact_by_point = actual_visits.groupby('ID_Точки').size().reset_index(name='Общий_факт')
        
        # Общий план из points_df
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
        
        # Возвращаем оригинальное название колонки недели
        if week_column != 'ISO_Неделя':
            detailed_with_fact = detailed_with_fact.rename(columns={'ISO_Неделя': week_column})
    else:
        detailed_with_fact['Факт_посещений'] = 0
        detailed_with_fact['План_выполнен'] = False
    
    return city_stats_df, type_stats_df, summary_df, detailed_with_fact
    
# ==============================================
# РАЗДЕЛ ЗАГРУЗКИ ФАЙЛОВ
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
    
    # Один загрузчик для всего файла
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
# КНОПКА РАСЧЕТА ПЛАНА
# ==============================================

# ТОЛЬКО ОДНА КНОПКА ВСЕМ КОДЕ!
calculate_button = st.button("🚀 Рассчитать план", type="primary", use_container_width=True, key="calculate_plan_btn")

if calculate_button:
    
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
            
            # ИСПРАВЛЕНИЕ: проверяем оба возвращаемых значения
            if points_assignment_df is None or polygons_info is None:
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
        
        # ==============================================
        # ПОЛНЫЙ РАСЧЕТ СО СТАТИСТИКОЙ
        # ==============================================
        
        with st.spinner("📊 Расчет полной статистики..."):
            try:
                # Рассчитываем полную статистику
                city_stats_df, type_stats_df, summary_df, detailed_with_fact = calculate_statistics(
                    points_df, visits_df, detailed_plan_df, year, quarter
                )
                
                # Сохраняем результаты в session state
                st.session_state.city_stats_df = city_stats_df
                st.session_state.type_stats_df = type_stats_df
                st.session_state.summary_df = summary_df
                st.session_state.details_df = detailed_with_fact
                st.session_state.plan_calculated = True  # ← ВОТ ТУТ, ВНУТРИ БЛОКА!
                
                st.success("✅ Полный расчет завершен! Статистика готова.")
                
                # Показываем итоговую статистику
                st.markdown("---")
                st.header("📊 Итоговая статистика")
                
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
                
                # Запускаем анимацию
                st.balloons()
                
            except Exception as e:
                st.error(f"❌ Ошибка при расчете статистики: {str(e)}")
                st.info("Будет показан частичный расчет без статистики")
                
                # Сохраняем хотя бы частичные результаты
                st.session_state.polygons_info = polygons_info
                st.session_state.points_assignment_df = points_assignment_df
                st.session_state.detailed_plan_df = detailed_plan_df
                st.session_state.plan_calculated = True  # ← И ЗДЕСЬ ТОЖЕ!
                
                st.success("✅ План частично рассчитан! Некоторые функции могут быть недоступны.")
    
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

elif st.session_state.get('data_loaded', False):
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
st.caption("📋 **Часть 2/5:** Функции обработки данных, генерация полигонов, распределение посещений по неделям")

# ==============================================
# ВКЛАДКИ С РЕЗУЛЬТАТАМИ
# ==============================================

if st.session_state.plan_calculated:
    st.markdown("---")
    st.header("📊 Результаты расчета")
    
    # Проверка доступности folium
    try:
        import folium
        from streamlit_folium import folium_static
        FOLIUM_AVAILABLE = True
    except ImportError:
        FOLIUM_AVAILABLE = False
    
    # Создаем вкладки
    results_tabs = st.tabs([
        "📊 Статистика по городам",
        "📋 Сводный план",
        "📍 Детализация",
        "📈 Диаграммы",
        "🗺️ Карта полигонов"
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
            
            # Выгрузка в Excel - ДОБАВИМ ПРОВЕРКУ
            if not city_stats.empty:
                try:
                    excel_buffer = io.BytesIO()
                    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                        city_stats.to_excel(writer, sheet_name='Статистика_городов', index=False)
                    
                    excel_data = excel_buffer.getvalue()
                    b64 = base64.b64encode(excel_data).decode()
                    href = f'<a href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64}" download="статистика_городов.xlsx">📥 Скачать Excel</a>'
                    st.markdown(href, unsafe_allow_html=True)
                except Exception as e:
                    st.error(f"❌ Ошибка при создании Excel файла: {str(e)}")
            else:
                st.warning("Нет данных для выгрузки в Excel")
            
    
    # ВКЛАДКА 2: Сводный план
    with results_tabs[1]:
        st.subheader("📋 Сводный план посещений")
        
        if st.session_state.summary_df is not None:
            summary_df = st.session_state.summary_df.copy()
            
            # Простая таблица без фильтров для начала
            if not summary_df.empty:
                display_df = summary_df.copy()
                
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
                
                st.dataframe(display_df, use_container_width=True, height=400)
                
                # Выгрузка в Excel - С ПРОВЕРКОЙ
                if not summary_df.empty:
                    try:
                        excel_buffer = io.BytesIO()
                        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                            summary_df.to_excel(writer, sheet_name='Сводный_план', index=False)
                        
                        excel_data = excel_buffer.getvalue()
                        b64 = base64.b64encode(excel_data).decode()
                        href = f'<a href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64}" download="сводный_план_{year}_Q{quarter}.xlsx">📥 Скачать Excel</a>'
                        st.markdown(href, unsafe_allow_html=True)
                    except Exception as e:
                        st.error(f"❌ Ошибка при создании Excel файла: {str(e)}")
                else:
                    st.warning("Нет данных для выгрузки в Excel")
            else:
                st.info("Нет данных для отображения")

    # ВКЛАДКА 3: Детализация
    with results_tabs[2]:
        st.subheader("📍 Детализация посещений")
        
        if st.session_state.details_df is not None:
            details_df = st.session_state.details_df.copy()
            
            # Простая таблица
            if not details_df.empty:
                # Проверяем, какие колонки реально есть в данных
                available_columns = []
                expected_columns = ['Город', 'Полигон', 'Аудитор', 'ISO_Неделя', 
                                   'ID_Точки', 'Название_Точки', 'Тип', 
                                   'План_посещений', 'Факт_посещений', 'План_выполнен']
                
                for col in expected_columns:
                    if col in details_df.columns:
                        available_columns.append(col)
                
                if available_columns:
                    display_df = details_df[available_columns].copy()
                    st.dataframe(display_df, use_container_width=True, height=400)
                    
                    # Показываем информацию о недостающих колонках
                    missing_columns = set(expected_columns) - set(available_columns)
                    if missing_columns:
                        st.warning(f"⚠️ Отсутствуют колонки: {', '.join(missing_columns)}")
                    
                    # Выгрузка в Excel - С ПРОВЕРКОЙ
                    if not details_df.empty:
                        try:
                            excel_buffer = io.BytesIO()
                            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                                details_df.to_excel(writer, sheet_name='Детализация', index=False)
                            
                            excel_data = excel_buffer.getvalue()
                            b64 = base64.b64encode(excel_data).decode()
                            href = f'<a href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64}" download="детализация_{year}_Q{quarter}.xlsx">📥 Скачать Excel</a>'
                            st.markdown(href, unsafe_allow_html=True)
                        except Exception as e:
                            st.error(f"❌ Ошибка при создании Excel файла: {str(e)}")
                    else:
                        st.warning("Нет данных для выгрузки в Excel")
                else:
                    st.warning("Нет доступных колонок для отображения")
                    st.write("Доступные колонки:", list(details_df.columns))
            else:
                st.info("Нет данных для отображения")
        else:
            st.info("Детальные данные еще не рассчитаны")
    
    # ВКЛАДКА 4: Диаграммы
    with results_tabs[3]:
        st.subheader("📈 Диаграммы и статистика")
        
        # 1. Диаграмма выполнения плана по городам
        if st.session_state.city_stats_df is not None:
            city_stats = st.session_state.city_stats_df.copy()
            
            # Проверяем, есть ли нужные колонки
            if 'Город' in city_stats.columns and '%_выполнения' in city_stats.columns:
                # Создаем график
                fig = px.bar(city_stats, 
                            x='Город', 
                            y='%_выполнения',
                            title='% выполнения плана по городам',
                            color='%_выполнения',
                            color_continuous_scale='RdYlGn')
                
                fig.update_layout(height=400)
                st.plotly_chart(fig, use_container_width=True)
                
                # Выгрузка статистики по городам в Excel
                if not city_stats.empty:
                    try:
                        excel_buffer = io.BytesIO()
                        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                            city_stats.to_excel(writer, sheet_name='Статистика_городов', index=False)
                        
                        excel_data = excel_buffer.getvalue()
                        b64 = base64.b64encode(excel_data).decode()
                        href = f'<a href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64}" download="статистика_городов.xlsx">📥 Скачать статистику по городам</a>'
                        st.markdown(href, unsafe_allow_html=True)
                    except Exception as e:
                        st.error(f"❌ Ошибка при создании Excel файла: {str(e)}")
            else:
                st.warning("Недостаточно данных для построения диаграммы по городам")
        
        # 2. Статистика по типам точек (из исходника)
        if st.session_state.type_stats_df is not None:
            st.markdown("### 🏪 Статистика по типам точек")
            type_stats = st.session_state.type_stats_df.copy()
            
            # Отображаем таблицу
            if not type_stats.empty:
                st.dataframe(type_stats, use_container_width=True, hide_index=True)
                
                # Простая диаграмма по типам точек
                if 'Тип' in type_stats.columns and 'План_посещений' in type_stats.columns:
                    fig2 = px.bar(type_stats,
                                 x='Тип',
                                 y='План_посещений',
                                 title='План посещений по типам точек',
                                 color='Тип')
                    fig2.update_layout(height=300, showlegend=False)
                    st.plotly_chart(fig2, use_container_width=True)
                
                # Выгрузка статистики по типам в Excel
                try:
                    excel_buffer = io.BytesIO()
                    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                        type_stats.to_excel(writer, sheet_name='Статистика_типов', index=False)
                    
                    excel_data = excel_buffer.getvalue()
                    b64 = base64.b64encode(excel_data).decode()
                    href = f'<a href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64}" download="статистика_типов_точек.xlsx">📥 Скачать статистику по типам точек</a>'
                    st.markdown(href, unsafe_allow_html=True)
                except Exception as e:
                    st.error(f"❌ Ошибка при создании Excel файла: {str(e)}")
        
        # 3. Общая статистика
        st.markdown("### 📊 Общая статистика")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.session_state.points_df is not None:
                total_points = len(st.session_state.points_df)
                st.metric("Всего точек", total_points)
        
        with col2:
            if st.session_state.auditors_df is not None:
                total_auditors = len(st.session_state.auditors_df)
                st.metric("Всего аудиторов", total_auditors)
        
        with col3:
            if st.session_state.polygons is not None:
                total_polygons = len(st.session_state.polygons)
                st.metric("Полигонов", total_polygons)
    
    # ВКЛАДКА 5: Карта полигонов
    with results_tabs[4]:
        st.subheader("🗺️ Карта полигонов аудиторов")
        
        if st.session_state.polygons is not None and len(st.session_state.polygons) > 0:
            polygons = st.session_state.polygons
            
            # Проверяем, установлен ли folium
            try:
                import folium
                from streamlit_folium import folium_static
                FOLIUM_AVAILABLE = True
            except ImportError:
                FOLIUM_AVAILABLE = False
            
            if not FOLIUM_AVAILABLE:
                st.error("""
                ## ⚠️ Библиотека картографии не установлена
                
                Для отображения интерактивной карты установите:
                ```bash
                pip install folium streamlit-folium
                ```
                
                **А пока показываем информацию в таблице:**
                """)
                
                # Таблица с полигонами
                poly_data = []
                for poly_name, poly_info in polygons.items():
                    poly_data.append({
                        'Полигон': poly_name,
                        'Аудитор': poly_info.get('auditor', 'Неизвестно'),
                        'Количество точек': len(poly_info.get('points', [])),
                        'Город': poly_info.get('city', 'Неизвестно')
                    })
                
                if poly_data:
                    poly_df = pd.DataFrame(poly_data)
                    st.dataframe(poly_df, use_container_width=True)
                    
                    # Выгрузка информации о полигонах в Excel
                    try:
                        excel_buffer = io.BytesIO()
                        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                            poly_df.to_excel(writer, sheet_name='Полигоны', index=False)
                        
                        excel_data = excel_buffer.getvalue()
                        b64 = base64.b64encode(excel_data).decode()
                        href = f'<a href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64}" download="информация_о_полигонах.xlsx">📥 Скачать информацию о полигонах</a>'
                        st.markdown(href, unsafe_allow_html=True)
                    except Exception as e:
                        st.error(f"❌ Ошибка при создании Excel файла: {str(e)}")
                    
                    st.markdown("---")
                    st.info("""
                    **После установки folium и streamlit-folium:**
                    1. Закройте приложение
                    2. Установите: `pip install folium streamlit-folium`
                    3. Перезапустите приложение
                    4. Карта появится автоматически
                    """)
            else:
                # Код для карты с folium (упрощенная версия)
                if st.session_state.points_df is not None:
                    points_df = st.session_state.points_df
                    
                    # Находим центр карты
                    center_lat = points_df['Широта'].mean()
                    center_lon = points_df['Долгота'].mean()
                    
                    m = folium.Map(location=[center_lat, center_lon], zoom_start=10)
                    
                    # Простой код для отображения точек
                    colors = ['red', 'blue', 'green', 'purple', 'orange', 'darkred']
                    
                    # Группируем точки по аудиторам для разных цветов
                    if st.session_state.details_df is not None:
                        details_df = st.session_state.details_df
                        auditor_colors = {}
                        auditors = details_df['Аудитор'].unique() if 'Аудитор' in details_df.columns else []
                        
                        for i, auditor in enumerate(auditors):
                            auditor_colors[auditor] = colors[i % len(colors)]
                    
                    for _, point in points_df.iterrows():
                        # Определяем цвет по аудитору
                        color = 'blue'  # цвет по умолчанию
                        
                        folium.CircleMarker(
                            location=[point['Широта'], point['Долгота']],
                            radius=5,
                            popup=f"""
                            <div style="font-family: Arial, sans-serif;">
                                <h4>🏪 {point['Название_Точки']}</h4>
                                <p><b>🆔 ID:</b> {point['ID_Точки']}</p>
                                <p><b>📍 Адрес:</b> {point.get('Адрес', 'Не указан')}</p>
                                <p><b>🏷️ Тип:</b> {point['Тип']}</p>
                                <p><b>🏙️ Город:</b> {point['Город']}</p>
                            </div>
                            """,
                            tooltip=f"🏪 {point['Название_Точки']}",
                            color=color,
                            fill=True,
                            fill_opacity=0.8
                        ).add_to(m)
                    
                    folium_static(m, width=1200, height=600)
                    
                    st.success("✅ Карта загружена с использованием Folium")
                    
                    # Выгрузка информации о точках в Excel
                    try:
                        excel_buffer = io.BytesIO()
                        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                            points_df.to_excel(writer, sheet_name='Точки_на_карте', index=False)
                        
                        excel_data = excel_buffer.getvalue()
                        b64 = base64.b64encode(excel_data).decode()
                        href = f'<a href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64}" download="точки_на_карте.xlsx">📥 Скачать точки с карты</a>'
                        st.markdown(href, unsafe_allow_html=True)
                    except Exception as e:
                        st.error(f"❌ Ошибка при создании Excel файла: {str(e)}")
        else:
            st.info("Полигоны еще не сгенерированы. Нажмите кнопку 'Рассчитать план'")
    st.markdown("---")
    st.subheader("💾 Скачать ВСЕ отчеты одним файлом")
    
    if st.button("📦 Скачать ПОЛНЫЙ ОТЧЕТ (все данные в одном Excel)", use_container_width=True, type="primary"):
        try:
            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                # Добавляем все доступные данные
                if st.session_state.city_stats_df is not None and not st.session_state.city_stats_df.empty:
                    st.session_state.city_stats_df.to_excel(writer, sheet_name='01_Статистика_городов', index=False)
                
                if st.session_state.type_stats_df is not None and not st.session_state.type_stats_df.empty:
                    st.session_state.type_stats_df.to_excel(writer, sheet_name='02_Статистика_типов', index=False)
                
                if st.session_state.summary_df is not None and not st.session_state.summary_df.empty:
                    st.session_state.summary_df.to_excel(writer, sheet_name='03_Сводный_план', index=False)
                
                if st.session_state.details_df is not None and not st.session_state.details_df.empty:
                    st.session_state.details_df.to_excel(writer, sheet_name='04_Детализация', index=False)
                
                if st.session_state.points_df is not None and not st.session_state.points_df.empty:
                    st.session_state.points_df.to_excel(writer, sheet_name='05_Точки', index=False)
                
                if st.session_state.auditors_df is not None and not st.session_state.auditors_df.empty:
                    st.session_state.auditors_df.to_excel(writer, sheet_name='06_Аудиторы', index=False)
                
                # Добавляем информацию о полигонах если есть
                if st.session_state.polygons is not None:
                    poly_data = []
                    for poly_name, poly_info in st.session_state.polygons.items():
                        poly_data.append({
                            'Полигон': poly_name,
                            'Аудитор': poly_info.get('auditor', 'Неизвестно'),
                            'Точек': len(poly_info.get('points', [])),
                            'Город': poly_info.get('city', 'Неизвестно')
                        })
                    if poly_data:
                        pd.DataFrame(poly_data).to_excel(writer, sheet_name='07_Полигоны', index=False)
            
            excel_data = excel_buffer.getvalue()
            st.download_button(
                label="⬇️ Нажмите чтобы скачать",
                data=excel_data,
                file_name=f"ПОЛНЫЙ_ОТЧЕТ_{year}_Q{quarter}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
            
        except Exception as e:
            st.error(f"❌ Ошибка при создании полного отчета: {str(e)}")






























