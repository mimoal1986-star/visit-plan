# === ИМПОРТЫ (без Streamlit команд!) ===
import pandas as pd
import numpy as np
import math
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

# === ИМПОРТ STREAMLIT (первый!) ===
import streamlit as st

# === ТЕПЕРЬ остальные импорты ===
# Картография
try:
    import folium
    from streamlit_folium import folium_static
    FOLIUM_AVAILABLE = True
except ImportError:
    FOLIUM_AVAILABLE = False

# ГЕОМЕТРИЯ - всегда используем упрощенную версию
SCIPY_AVAILABLE = False
try:
    import scipy
    from scipy.spatial import ConvexHull
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False

# Для расчета рабочих дней с праздниками
try:
    from workalendar.europe import Russia
    WORKALENDAR_AVAILABLE = True
except ImportError:
    WORKALENDAR_AVAILABLE = False

# # === ТЕПЕРЬ МОЖНО ИСПОЛЬЗОВАТЬ Streamlit команды ===
# if SCIPY_AVAILABLE:
# st.sidebar.success("✅ SciPy доступен")
# else:
# st.sidebar.info("ℹ️ Используется упрощенная генерация полигонов")

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

st.title("📊 Калькулятор плана визитов по сотрудникам")
st.markdown("---")

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
    
def calculate_weekly_targets(total_points, year, quarter, coefficients):
    """
    Рассчитывает, сколько точек должно быть в каждую неделю квартала
    с учетом коэффициентов нагрузки. Использует ТУ ЖЕ логику, что и
    оригинальная функция distribute_visits_by_weeks():
    - Коэффициенты применяются циклически по ISO номеру недели
    - week_index = (iso_week - 1) % 4
    """
    weeks_info = get_weeks_in_quarter(year, quarter)
    if not weeks_info:
        return []
    
    n_weeks = len(weeks_info)
    
    # 1. Базовая нагрузка (равномерная)
    base_per_week = total_points / n_weeks
    
    # 2. Применяем коэффициенты (ЦИКЛИЧЕСКИ по ISO неделе)
    weekly_targets = []
    for week_info in weeks_info:
        iso_week = week_info['iso_week_number']
        week_index = (iso_week - 1) % 4  # 0, 1, 2, 3, 0, 1, ...
        coefficient = coefficients[week_index % len(coefficients)]
        
        raw_target = base_per_week * coefficient
        weekly_target = max(1, int(round(raw_target)))  # минимум 1 точка
        weekly_targets.append(weekly_target)
    
    # 3. Корректируем сумму до total_points
    current_sum = sum(weekly_targets)
    difference = total_points - current_sum
    
    if difference != 0:
        # Сортируем недели по "гибкости" (насколько можно изменить)
        # Приоритет у недель с самым высоким коэффициентом (могут взять больше)
        week_flexibility = []
        for i, week_info in enumerate(weeks_info):
            iso_week = week_info['iso_week_number']
            week_index = (iso_week - 1) % 4
            coefficient = coefficients[week_index % len(coefficients)]
            
            # "Гибкость" = коэффициент (высокий коэффициент = может взять больше)
            week_flexibility.append((i, coefficient))
        
        # Сортируем по коэффициенту (убывание)
        week_flexibility.sort(key=lambda x: -x[1])
        
        # Корректируем
        week_idx = 0
        while difference != 0 and week_idx < len(week_flexibility):
            i = week_flexibility[week_idx][0]
            
            if difference > 0:
                # Добавляем точку
                weekly_targets[i] += 1
                difference -= 1
            elif difference < 0 and weekly_targets[i] > 1:
                # Убираем точку (но не ниже 1)
                weekly_targets[i] -= 1
                difference += 1
            
            week_idx += 1
    
    # 4. Финальная гарантия (аварийный клапан)
    if sum(weekly_targets) != total_points:
        # Всю оставшуюся разницу на первую неделю
        weekly_targets[0] += (total_points - sum(weekly_targets))
    
    # 5. Проверка (для отладки)
    final_sum = sum(weekly_targets)
    if final_sum != total_points:
        # Это не должно случиться, но если случилось — логируем
        pass
    
    return weekly_targets

# ==============================================
# КЛАСС ДЛЯ ОПТИМИЗАЦИИ МАРШРУТОВ ПО ДНЯМ
# ==============================================

class WeeklyRouteOptimizer:
    """
    Оптимизатор маршрутов на основе логики из optimizer.py
    Распределяет точки по дням недели и строит оптимальные маршруты
    """
    
    @staticmethod
    def calculate_distance(lat1, lon1, lat2, lon2):
        """Расчет евклидова расстояния между точками"""
        return math.sqrt((lat2 - lat1)**2 + (lon2 - lon1)**2)
    
    @staticmethod
    def greedy_route(points):
        """
        Жадный алгоритм построения маршрута
        Начинает с самой дальней точки от центра
        """
        if len(points) <= 1:
            return points
        
        # Вычисляем центр всех точек
        center_lat = np.mean([p['Широта'] for p in points])
        center_lon = np.mean([p['Долгота'] for p in points])
        
        # Находим самую дальнюю точку от центра
        start_idx = max(range(len(points)),
                       key=lambda i: WeeklyRouteOptimizer.calculate_distance(
                           points[i]['Широта'], points[i]['Долгота'],
                           center_lat, center_lon
                       ))
        
        route = [points[start_idx]]
        unvisited = points[:start_idx] + points[start_idx+1:]
        
        while unvisited:
            last_point = route[-1]
            
            # Находим ближайшую непосещенную точку
            nearest_idx = min(range(len(unvisited)),
                key=lambda i: WeeklyRouteOptimizer.calculate_distance(
                    last_point['Широта'], last_point['Долгота'],
                    unvisited[i]['Широта'], unvisited[i]['Долгота']
                ))
            
            route.append(unvisited[nearest_idx])
            unvisited.pop(nearest_idx)
        
        return route
    
    @staticmethod
    def distribute_points_to_days(points_list, visits_per_point, working_days):
        """
        Распределяет точки по рабочим дням недели
        points_list: список словарей с точками
        visits_per_point: сколько раз нужно посетить каждую точку
        working_days: список дат рабочих дней недели
        """
        if not points_list or not working_days:
            return {}
        
        # Создаем список всех посещений
        all_visits = []
        for point in points_list:
            point_id = point['ID_Точки']
            visits = visits_per_point.get(point_id, 1)
            for _ in range(visits):
                all_visits.append(point.copy())
        
        # Равномерно распределяем по дням
        visits_by_day = {}
        days_count = len(working_days)
        
        for i, visit in enumerate(all_visits):
            day_index = i % days_count
            day_date = working_days[day_index]
            
            if day_date not in visits_by_day:
                visits_by_day[day_date] = []
            
            visits_by_day[day_date].append(visit)
        
        return visits_by_day
    
    @staticmethod
    def optimize_week_for_auditor(auditor_points, visits_needed, week_dates, auditor_id):
        """
        Оптимизирует маршруты для аудитора на неделю
        Возвращает список визитов с указанием дня недели
        """
        results = []
        
        # Определяем рабочие дни (понедельник-пятница)
        working_days = []
        for day_date in week_dates:
            # Проверяем что это datetime/date объект
            if hasattr(day_date, 'weekday'):
                if day_date.weekday() < 5:  # 0-4 = Пн-Пт
                    working_days.append(day_date)
        
        if not working_days:
            return results
        
        # Распределяем точки по дням
        visits_by_day = WeeklyRouteOptimizer.distribute_points_to_days(
            auditor_points, visits_needed, working_days
        )
        
        # Для каждого дня строим оптимальный маршрут
        for day_date, day_points in visits_by_day.items():
            if not day_points:
                continue
            
            # Строим оптимальный маршрут для дня
            optimized_route = WeeklyRouteOptimizer.greedy_route(day_points)
            
            # Добавляем каждую точку в результат с указанием дня
            # Преобразуем в datetime если нужно
            if isinstance(day_date, date):
                day_datetime = datetime.combine(day_date, datetime.min.time())
            else:
                day_datetime = day_date
            
            day_of_week = day_datetime.weekday()  # 0=понедельник, 4=пятница
            
            for point in optimized_route:
                results.append({
                    'ID_Точки': point['ID_Точки'],
                    'Дата': day_datetime,
                    'День_недели': day_of_week,
                    'Аудитор': auditor_id,
                    'Широта': point['Широта'],
                    'Долгота': point['Долгота']
                })
        
        return results

# ==============================================
# ФУНКЦИИ ДЛЯ РАСЧЕТА РАБОЧИХ ДНЕЙ И КЛАСТЕРИЗАЦИИ
# ==============================================

def get_working_days_for_quarter(year, quarter):
    """
    Возвращает список рабочих дней в квартале
    с учетом российских праздников (использует workalendar если доступен)
    """
    quarter_start, quarter_end = get_quarter_dates(year, quarter)
    
    if WORKALENDAR_AVAILABLE:
        # Используем библиотеку workalendar для точного расчета
        cal = Russia()
        working_days = []
        current_date = quarter_start
        
        while current_date <= quarter_end:
            if cal.is_working_day(current_date):
                working_days.append(current_date)
            current_date += timedelta(days=1)
        
        return working_days
    else:
        # Простая версия: только понедельник-пятница
        st.sidebar.warning("⚠️ Для учета праздников установите: pip install workalendar")
        
        working_days = []
        current_date = quarter_start
        
        while current_date <= quarter_end:
            if current_date.weekday() < 5:  # Пн-Пт
                working_days.append(current_date)
            current_date += timedelta(days=1)
        
        return working_days

# def simple_cluster_points(points, n_clusters):
#     """
#     Простая кластеризация без sklearn
#     """
#     if not points or n_clusters <= 0:
#         return [[] for _ in range(n_clusters)] if n_clusters > 0 else []
    
#     if len(points) <= n_clusters:
#         # Каждая точка в своей группе
#         clusters = [[p] for p in points]
#         # Добавляем пустые группы если нужно
#         while len(clusters) < n_clusters:
#             clusters.append([])
#         return clusters
    
#     # Выбираем начальные центры
#     centers = []
    
#     # Первый центр - первая точка
#     if points:
#         centers.append(points[0])
    
#     # Остальные центры - самые удаленные
#     for _ in range(1, min(n_clusters, len(points))):
#         max_min_distance = -1
#         best_point = None
        
#         for point in points:
#             if point in centers:
#                 continue
            
#             # Минимальное расстояние до существующих центров
#             min_dist = float('inf')
#             for center in centers:
#                 dist = WeeklyRouteOptimizer.calculate_distance(
#                     point['Широта'], point['Долгота'],
#                     center['Широта'], center['Долгота']
#                 )
#                 min_dist = min(min_dist, dist)
            
#             if min_dist > max_min_distance:
#                 max_min_distance = min_dist
#                 best_point = point
        
#         if best_point:
#             centers.append(best_point)
#         else:
#             # Если не нашли, берем любую неиспользованную
#             for point in points:
#                 if point not in centers:
#                     centers.append(point)
#                     break
    
#     # Если не набрали достаточно центров
#     while len(centers) < n_clusters:
#         centers.append(points[0])  # дублируем первую точку
    
#     # Назначаем точки ближайшим центрам
#     clusters = [[] for _ in range(n_clusters)]
    
#     for point in points:
#         # Находим ближайший центр
#         min_dist = float('inf')
#         nearest_idx = 0
        
#         for i, center in enumerate(centers):
#             dist = WeeklyRouteOptimizer.calculate_distance(
#                 point['Широта'], point['Долгота'],
#                 center['Широта'], center['Долгота']
#             )
#             if dist < min_dist:
#                 min_dist = dist
#                 nearest_idx = i
        
#         if 0 <= nearest_idx < n_clusters:
#             clusters[nearest_idx].append(point)
    
#     return clusters

def create_daily_routes_for_auditor(auditor_points, working_days, auditor_id):
    """
    УНИВЕРСАЛЬНЫЙ АЛГОРИТМ ДЛЯ ГОРОДОВ-МИЛЛИОННИКОВ РОССИИ
    """
    try:
        if not auditor_points or not working_days:
            return []
        
        N = len(auditor_points)
        K = len(working_days)
        
        if K == 0:
            return []
        
        # === 1. ПРЕПРОЦЕССИНГ КООРДИНАТ ===
        valid_points = []
        for point in auditor_points:
            try:
                lat = float(point['Широта'])
                lon = float(point['Долгота'])
                # Проверка на валидные координаты России
                if 41 <= lat <= 82 and 19 <= lon <= 180:
                    valid_points.append(point)
            except (ValueError, TypeError):
                continue
        
        if not valid_points:
            return []
        
        # === 2. ЕСЛИ ТОЧЕК МАЛО ===
        if len(valid_points) <= K:
            # Просто распределяем по дням
            return simple_distribute_points(valid_points, working_days, auditor_id)
        
        # === 3. АНАЛИЗ ГЕОГРАФИЧЕСКОГО РАСПРЕДЕЛЕНИЯ ===
        lats = [p['Широта'] for p in valid_points]
        lons = [p['Долгота'] for p in valid_points]
        
        lat_min, lat_max = min(lats), max(lats)
        lon_min, lon_max = min(lons), max(lons)
        
        lat_range = lat_max - lat_min
        lon_range = lon_max - lon_min
        
        # Приблизительный перевод в километры
        avg_lat = np.mean(lats)
        lat_km = lat_range * 111
        lon_km = lon_range * 111 * math.cos(math.radians(avg_lat))
        
        # Определяем тип распределения
        city_type = "compact"
        if lat_km > 50 or lon_km > 50:
            city_type = "scattered"
        elif max(lat_km, lon_km) / min(lat_km, lon_km) > 3:
            city_type = "linear"
        
        # # === 4. КЛАСТЕРИЗАЦИЯ ===
        # try:
        #     from sklearn.cluster import KMeans
            
        #     # Подготовка координат
        #     coords = np.array([[p['Широта'], p['Долгота']] for p in valid_points])
            
        #     # Масштабирование для разных типов городов
        #     if city_type == "linear":
        #         # Для вытянутых городов
        #         if lon_range > lat_range * 2:
        #             # Вытянут по долготе
        #             scaled_coords = coords * [1.0, 2.0]
        #         else:
        #             # Вытянут по широте
        #             scaled_coords = coords * [2.0, 1.0]
        #     else:
        #         # Нормализация с учетом широты
        #         lon_scale = math.cos(math.radians(avg_lat))
        #         scaled_coords = coords.copy()
        #         scaled_coords[:, 1] *= lon_scale
            
        #     # Кластеризация KMeans
        #     kmeans = KMeans(
        #         n_clusters=K,
        #         init='k-means++',
        #         n_init=10,
        #         random_state=42
        #     )
        #     labels = kmeans.fit_predict(scaled_coords)
            
        #     # Группировка по кластерам
        #     daily_clusters = [[] for _ in range(K)]
        #     for point, label in zip(valid_points, labels):
        #         if 0 <= label < K:
        #             daily_clusters[label].append(point)
            
        # except ImportError:
        #     # Если нет sklearn, используем простую географическую сортировку
        #     st.warning("⚠️ Установите scikit-learn для лучшей кластеризации")
        #     return simple_geographic_distribution(valid_points, working_days, auditor_id)
        
        # except Exception as e:
        #     st.error(f"❌ Ошибка кластеризации: {str(e)}")
        #     return simple_geographic_distribution(valid_points, working_days, auditor_id)
        
        # # === 5. БАЛАНСИРОВКА КЛАСТЕРОВ ===
        # # Перераспределяем точки если кластеры сильно различаются по размеру
        # balanced_clusters = balance_clusters_simple(daily_clusters, K)
        
        # === 6. ПОСТРОЕНИЕ МАРШРУТОВ ===
        routes = []
        
        for day_idx, (day_date, cluster_points) in enumerate(zip(working_days, balanced_clusters)):
            if not cluster_points:
                continue
            
            # Обработка даты
            if isinstance(day_date, date) and not isinstance(day_date, datetime):
                visit_datetime = datetime.combine(day_date, datetime.min.time())
            else:
                visit_datetime = day_date
            
            # Сортировка точек внутри кластера для лучшего маршрута
            if len(cluster_points) > 1:
                # Сортируем по географическому порядку
                if city_type == "linear" and lon_range > lat_range:
                    cluster_points.sort(key=lambda p: p['Долгота'])  # запад → восток
                else:
                    cluster_points.sort(key=lambda p: (-p['Широта'], p['Долгота']))  # север→юг, запад→восток
            
            # Строим маршрут
            try:
                optimized_route = WeeklyRouteOptimizer.greedy_route(cluster_points)
            except:
                optimized_route = cluster_points
            
            # Добавляем точки
            for point in optimized_route:
                routes.append({
                    'ID_Точки': point['ID_Точки'],
                    'Дата': visit_datetime,
                    'День_недели': visit_datetime.weekday(),
                    'Аудитор': auditor_id,
                    'Широта': point['Широта'],
                    'Долгота': point['Долгота'],
                    'Название_Точки': point.get('Название_Точки', point['ID_Точки']),
                    'Адрес': point.get('Адрес', ''),
                    'Тип': point.get('Тип', 'Неизвестно')
                })
        
        return routes
    
    except Exception as e:
        st.error(f"❌ Критическая ошибка: {str(e)}")
        import traceback
        st.error(f"Детали:\n{traceback.format_exc()}")
        return []


# def simple_distribute_points(points, working_days, auditor_id):
#     """Простое распределение точек по дням"""
#     routes = []
    
#     for i, point in enumerate(points):
#         if i >= len(working_days):
#             break
        
#         day_date = working_days[i]
#         if isinstance(day_date, date) and not isinstance(day_date, datetime):
#             visit_datetime = datetime.combine(day_date, datetime.min.time())
#         else:
#             visit_datetime = day_date
        
#         routes.append({
#             'ID_Точки': point['ID_Точки'],
#             'Дата': visit_datetime,
#             'День_недели': visit_datetime.weekday(),
#             'Аудитор': auditor_id,
#             'Широта': point['Широта'],
#             'Долгота': point['Долгота'],
#             'Название_Точки': point.get('Название_Точки', point['ID_Точки']),
#             'Адрес': point.get('Адрес', ''),
#             'Тип': point.get('Тип', 'Неизвестно')
#         })
    
#     return routes


# def balance_clusters_simple(clusters, target_k):
#     """Простая балансировка кластеров"""
#     # Собираем все точки
#     all_points = []
#     for cluster in clusters:
#         all_points.extend(cluster)
    
#     if len(all_points) == 0:
#         return [[] for _ in range(target_k)]
    
#     # Сортируем по географии
#     sorted_points = sorted(all_points, key=lambda p: (-p['Широта'], p['Долгота']))
    
#     # Распределяем равномерно
#     balanced = [[] for _ in range(target_k)]
#     for i, point in enumerate(sorted_points):
#         balanced[i % target_k].append(point)
    
#     return balanced


# def simple_geographic_distribution(points, working_days, auditor_id):
#     """Простое географическое распределение"""
#     if not points or not working_days:
#         return []
    
#     K = len(working_days)
    
#     # Сортируем точки
#     sorted_points = sorted(points, key=lambda p: (-p['Широта'], p['Долгота']))
    
#     # Делим на части
#     daily_clusters = []
#     base_size = len(sorted_points) // K
#     remainder = len(sorted_points) % K
    
#     start_idx = 0
#     for day_idx in range(K):
#         size = base_size + (1 if day_idx < remainder else 0)
#         end_idx = start_idx + size
        
#         if start_idx < len(sorted_points):
#             daily_clusters.append(sorted_points[start_idx:end_idx])
#             start_idx = end_idx
#         else:
#             daily_clusters.append([])
    
#     # Строим маршруты
#     routes = []
#     for day_idx, (day_date, cluster_points) in enumerate(zip(working_days, daily_clusters)):
#         if not cluster_points:
#             continue
        
#         if isinstance(day_date, date) and not isinstance(day_date, datetime):
#             visit_datetime = datetime.combine(day_date, datetime.min.time())
#         else:
#             visit_datetime = day_date
        
#         for point in cluster_points:
#             routes.append({
#                 'ID_Точки': point['ID_Точки'],
#                 'Дата': visit_datetime,
#                 'День_недели': visit_datetime.weekday(),
#                 'Аудитор': auditor_id,
#                 'Широта': point['Широта'],
#                 'Долгота': point['Долгота'],
#                 'Название_Точки': point.get('Название_Точки', point['ID_Точки']),
#                 'Адрес': point.get('Адрес', ''),
#                 'Тип': point.get('Тип', 'Неизвестно')
#             })
    
#     return routes
    
# ==============================================
# ФУНКЦИИ ДЛЯ СОЗДАНИЯ ВЫХОДНОЙ ТАБЛИЦЫ
# ==============================================
def create_weekly_route_schedule(points_df, points_assignment_df, auditors_df, year, quarter):
    """
    Создает ежедневные маршруты для аудиторов в формате EasyMerch
    """
    
    if points_df is None or points_df.empty:
        return pd.DataFrame()
    
    if points_assignment_df is None or points_assignment_df.empty:
        return pd.DataFrame()
    
    # 1. Получаем рабочие дни квартала
    working_days = get_working_days_for_quarter(year, quarter)
    
    if not working_days:
        st.warning(f"⚠️ В {year} квартале {quarter} нет рабочих дней")
        return pd.DataFrame()
    
    all_visits = []
    
    # 2. Для каждого аудитора создаем ежедневные маршруты
    for auditor in auditors_df['ID_Сотрудника'].unique():
        # Находим точки этого аудитора
        auditor_point_ids = points_assignment_df[
            points_assignment_df['Аудитор'] == auditor
        ]['ID_Точки'].tolist()
        
        if not auditor_point_ids:
            continue
        
        # Получаем данные точек
        auditor_points_data = points_df[
            points_df['ID_Точки'].isin(auditor_point_ids)
        ]
        
        if auditor_points_data.empty:
            continue
        
        # Преобразуем в список словарей с учетом количества посещений
        auditor_points = []
        for _, row in auditor_points_data.iterrows():
            # Учитываем количество посещений за квартал
            visits_needed = int(row.get('Кол-во_посещений', 1))
            
            for visit_num in range(visits_needed):
                auditor_points.append({
                    'ID_Точки': row['ID_Точки'],
                    'Широта': float(row['Широта']),
                    'Долгота': float(row['Долгота']),
                    'Название_Точки': row.get('Название_Точки', str(row['ID_Точки'])),
                    'Адрес': row.get('Адрес', ''),
                    'Тип': row.get('Тип', 'Неизвестно')
                })
        
        # Создаем ежедневные маршруты
        daily_visits = create_daily_routes_for_auditor(
            auditor_points, working_days, auditor
        )
        all_visits.extend(daily_visits)
    
    # 3. Преобразуем в DataFrame
    if not all_visits:
        return pd.DataFrame()
    
    results_df = pd.DataFrame(all_visits)
    
    # 4. Группируем по неделям для формата EasyMerch
    # Добавляем информацию о неделе
    results_df['Неделя'] = results_df['Дата'].apply(get_iso_week)
    results_df['Дата_начала_недели'] = results_df['Дата'].apply(
        lambda d: d - timedelta(days=d.weekday())
    )
    
    # 5. Создаем финальную таблицу в формате EasyMerch
    final_rows = []
    
    # Группируем по точкам и неделям
    grouped = results_df.groupby(['ID_Точки', 'Неделя', 'Аудитор'])
    
    for (point_id, week_num, auditor), group in grouped:
        # Находим информацию о точке
        point_mask = points_df['ID_Точки'] == point_id
        if not point_mask.any():
            continue
            
        point_info = points_df[point_mask].iloc[0]
        
        # Количество визитов на этой неделе
        visits_this_week = len(group)
        
        # Дни недели когда есть визиты
        days_visited = set(group['День_недели'].tolist())
        
        # Дата начала недели (понедельник)
        week_start_date = group['Дата_начала_недели'].iloc[0]
        
        # Преобразуем в строку YYYYMMDD
        if isinstance(week_start_date, (datetime, pd.Timestamp)):
            start_date_str = week_start_date.strftime('%Y%m%d')
        else:
            start_date_str = str(week_start_date).replace('-', '')
        
        # Получаем координаты
        try:
            latitude = float(point_info.get('Широта', 0))
            longitude = float(point_info.get('Долгота', 0))
        except (ValueError, TypeError):
            latitude = 0
            longitude = 0
        
        # Создаем строку
        row = {
            'Address': point_info.get('Адрес', ''),
            'L1 Name': point_info.get('Название_Точки', str(point_id)),
            'ЧИСЛО визитов в НЕДЕЛЮ': visits_this_week,
            'Login пользователя': auditor,
            'Понедельник': 1 if 0 in days_visited else '',
            'Вторник': 1 if 1 in days_visited else '',
            'Среда': 1 if 2 in days_visited else '',
            'Четверг': 1 if 3 in days_visited else '',
            'Пятница': 1 if 4 in days_visited else '',
            'Суббота': 1 if 5 in days_visited else '',
            'Воскресенье': 1 if 6 in days_visited else '',
            'Цикл посещения': week_num,
            'Дата начала цикла посещения': start_date_str,
            'Широта': f"{latitude:.6f}",  # Добавлено: 6 знаков после запятой
            'Долгота': f"{longitude:.6f}"   # Добавлено: 6 знаков после запятой
        }
        
        final_rows.append(row)
    
    if not final_rows:
        return pd.DataFrame()
    
    final_df = pd.DataFrame(final_rows)
    
    # Сортируем
    final_df = final_df.sort_values(['Login пользователя', 'Дата начала цикла посещения', 'L1 Name'])
    
    return final_df

def create_easymerch_excel(routes_df):
    """Создает Excel файл в формате EasyMerch с несколькими листами"""
    import io
    
    if routes_df is None or routes_df.empty:
        return None
    
    excel_buffer = io.BytesIO()
    
    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
        # Лист 1: Основные данные в формате EasyMerch
        routes_df.to_excel(writer, sheet_name='Маршруты', index=False)
        
        # Автонастройка ширины колонок для основного листа
        worksheet = writer.sheets['Маршруты']
        for column in worksheet.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 50)
            worksheet.column_dimensions[column_letter].width = adjusted_width
        
        # Лист 2: Инструкция по использованию
        instructions_data = [
            ["ПОЛЕ", "ОПИСАНИЕ", "ПРИМЕР", "ОБЯЗАТЕЛЬНОСТЬ"],
            ["Address", "Полный адрес точки", "ул. Ленина, д. 1, Москва", "Да"],
            ["L1 Name", "Название торговой точки", 'Магазин "Продукты"', "Да"],
            ["ЧИСЛО визитов в НЕДЕЛЮ", "Количество визитов в неделю (цифра)", "1, 2, 3", "Да"],
            ["Login пользователя", "Уникальный ID аудитора", "SOVIAUD10", "Да"],
            ["Понедельник", "Визит в понедельник (1-да, пусто-нет)", "1", "Нет"],
            ["Вторник", "Визит во вторник (1-да, пусто-нет)", "", "Нет"],
            ["Среда", "Визит в среду (1-да, пусто-нет)", "1", "Нет"],
            ["Четверг", "Визит в четверг (1-да, пусто-нет)", "", "Нет"],
            ["Пятница", "Визит в пятницу (1-да, пусто-нет)", "1", "Нет"],
            ["Суббота", "Визит в субботу (1-да, пусто-нет)", "", "Нет"],
            ["Воскресенье", "Визит в воскресенье (1-да, пусто-нет)", "", "Нет"],
            ["Цикл посещения", "Номер недели (ISO стандарт)", "15", "Да"],
            ["Дата начала цикла посещения", "Дата понедельника в формате ГГГГММДД", "20250407", "Да"],
            ["", "", "", ""],
            ["ИНСТРУКЦИЯ ПО ИСПОЛЬЗОВАНИЮ:", "", "", ""],
            ["1. Файл готов для загрузки в EasyMerch", "", "", ""],
            ["2. Формат даты: YYYYMMDD (например: 20250407)", "", "", ""],
            ["3. Пустые ячейки в днях недели = нет визита", "", "", ""],
            ["4. Ячейки с цифрой 1 = визит запланирован", "", "", ""],
            ["5. Не изменяйте названия колонок", "", "", ""]
        ]
        
        instructions_df = pd.DataFrame(instructions_data[1:], columns=instructions_data[0])
        instructions_df.to_excel(writer, sheet_name='Инструкция', index=False)
        
        # Автонастройка ширины для инструкции
        worksheet = writer.sheets['Инструкция']
        worksheet.column_dimensions['A'].width = 25
        worksheet.column_dimensions['B'].width = 40
        worksheet.column_dimensions['C'].width = 25
        worksheet.column_dimensions['D'].width = 15
        
        # Лист 3: Сводка и статистика
        summary_data = {
            'Статистика': [
                'Всего записей в плане',
                'Уникальных аудиторов',
                'Уникальных торговых точек',
                'Общее количество визитов в неделю',
                'Количество недель в плане',
                'Первая неделя',
                'Последняя неделя',
                'Среднее визитов на аудитора',
                'Дата создания отчета'
            ],
            'Значение': [
                len(routes_df),
                routes_df['Login пользователя'].nunique(),
                routes_df['L1 Name'].nunique(),
                routes_df['ЧИСЛО визитов в НЕДЕЛЮ'].sum(),
                routes_df['Цикл посещения'].nunique(),
                routes_df['Цикл посещения'].min() if not routes_df.empty else '-',
                routes_df['Цикл посещения'].max() if not routes_df.empty else '-',
                round(routes_df['ЧИСЛО визитов в НЕДЕЛЮ'].sum() / routes_df['Login пользователя'].nunique(), 1) 
                if routes_df['Login пользователя'].nunique() > 0 else 0,
                datetime.now().strftime('%d.%m.%Y %H:%M')
            ]
        }
        
        summary_df = pd.DataFrame(summary_data)
        summary_df.to_excel(writer, sheet_name='Сводка', index=False)
        
        # Автонастройка ширины для сводки
        worksheet = writer.sheets['Сводка']
        worksheet.column_dimensions['A'].width = 35
        worksheet.column_dimensions['B'].width = 20
        
        # Лист 4: Распределение по аудиторам (дополнительно)
        if 'Login пользователя' in routes_df.columns:
            auditor_stats = routes_df.groupby('Login пользователя').agg({
                'L1 Name': 'nunique',
                'ЧИСЛО визитов в НЕДЕЛЮ': 'sum',
                'Цикл посещения': 'nunique'
            }).reset_index()
            
            auditor_stats.columns = ['Аудитор', 'Уникальных точек', 'Всего визитов', 'Недель в работе']
            auditor_stats = auditor_stats.sort_values('Всего визитов', ascending=False)
            auditor_stats.to_excel(writer, sheet_name='Аудиторы', index=False)
            
            # Автонастройка ширины
            worksheet = writer.sheets['Аудиторы']
            for i, column in enumerate(['A', 'B', 'C', 'D'], 1):
                worksheet.column_dimensions[column].width = 20
    
    return excel_buffer.getvalue()
                                     
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
    
    if not polygons_info or not isinstance(polygons_info, dict):
        return {}
    
    try:
        for polygon_name, info in polygons_info.items():
            if not info or not isinstance(info, dict) or 'points' not in info:
                continue
                
            points = np.array(info['points'])
            
            if len(points) == 0:
                polygons[polygon_name] = {
                    'auditor': info.get('auditor', 'Неизвестно'),
                    'city': info.get('city', 'Неизвестно'),  # ← ДОБАВЛЕНО
                    'coordinates': [],
                    'points_count': 0,
                    'points': []
                }
                continue
                
            if len(points) < 2:
                polygons[polygon_name] = {
                    'auditor': info.get('auditor', 'Неизвестно'),
                    'city': info.get('city', 'Неизвестно'),  # ← ДОБАВЛЕНО
                    'coordinates': [],
                    'points_count': len(points),
                    'points': points.tolist()  # ← ДОБАВЛЕНО
                }
                continue
            
            polygon_coords = create_simple_polygon(points)
            
            polygons[polygon_name] = {
                'auditor': info['auditor'],
                'city': info.get('city', polygon_name.split('-')[0]),  # ← ДОБАВЛЕНО
                'coordinates': polygon_coords,
                'points_count': len(points),
                'points': points.tolist()  # ← ДОБАВЛЕНО
            }
        
        return polygons
    except Exception as e:
        st.error(f"❌ Ошибка при генерации полигонов: {str(e)}")
        import traceback
        st.error(f"Детали ошибки:\n{traceback.format_exc()}")
        return {}

# ==============================================
# ФУНКЦИИ ДЛЯ РАСПРЕДЕЛЕНИЯ ПО НЕДЕЛЯМ
# ==============================================

def distribute_visits_by_weeks(points_assignment_df, points_df, year, quarter, coefficients):
    """Распределяет посещения по неделям на основе личных планов аудиторов"""
    try:
        # 1. Получаем недели в квартале
        weeks_info = get_weeks_in_quarter(year, quarter)
        if not weeks_info:
            return pd.DataFrame()
        
        # 2. Объединяем точки с их аудиторами и планом посещений
        merged_df = pd.merge(
            points_df[['ID_Точки', 'Кол-во_посещений', 'Город']],
            points_assignment_df[['ID_Точки', 'Аудитор', 'Полигон']],
            on='ID_Точки',
            how='left'
        )
        
        # 3. Рассчитываем личный план каждого аудитора
        auditor_plans = merged_df.groupby(['Город', 'Аудитор', 'Полигон'])['Кол-во_посещений'].sum().reset_index()
        auditor_plans = auditor_plans.rename(columns={'Кол-во_посещений': 'Личный_план'})
        
        # 4. Распределяем каждый личный план по неделям
        weekly_plan = []
        
        for _, auditor_row in auditor_plans.iterrows():
            city = auditor_row['Город']
            auditor = auditor_row['Аудитор']
            polygon = auditor_row['Полигон']
            personal_plan = auditor_row['Личный_план']
            
            if personal_plan <= 0:
                continue
            
            # 5. Распределяем личный план аудитора по неделям с учетом коэффициентов
            weeks_in_quarter = len(weeks_info)
            
            # Базовая нагрузка по неделям (равномерно)
            base_per_week = max(1, personal_plan // weeks_in_quarter)
            
            for week_info in weeks_info:
                iso_week = week_info['iso_week_number']
                week_index = (iso_week - 1) % 4  # Для коэффициентов (0-3)
                
                # Применяем коэффициент
                coefficient = coefficients[week_index % len(coefficients)]
                weekly_visits = int(round(base_per_week * coefficient))
                
                # Минимум 0 посещений
                weekly_visits = max(0, weekly_visits)
                
                if weekly_visits > 0:
                    weekly_plan.append({
                        'Город': city,
                        'Полигон': polygon,
                        'Аудитор': auditor,
                        'ISO_Неделя': iso_week,
                        'Дата_начала': week_info['start_date'],
                        'Дата_окончания': week_info['end_date'],
                        'План_посещений': weekly_visits
                    })
        
        # 6. Создаем DataFrame и корректируем округления
        result_df = pd.DataFrame(weekly_plan)
        
        if not result_df.empty:
            # Группируем по аудиторам и перераспределяем остаток
            for (city, auditor), group in result_df.groupby(['Город', 'Аудитор']):
                # Находим целевой личный план
                target_plan = auditor_plans[
                    (auditor_plans['Город'] == city) & 
                    (auditor_plans['Аудитор'] == auditor)
                ]['Личный_план'].sum()
                
                # Находим текущую сумму в распределении
                current_sum = group['План_посещений'].sum()
                
                # Корректируем разницу
                difference = target_plan - current_sum
                
                if difference != 0:
                    # Добавляем/убираем разницу у первой недели этого аудитора
                    first_week_idx = result_df[
                        (result_df['Город'] == city) & 
                        (result_df['Аудитор'] == auditor)
                    ].index[0]
                    
                    new_value = result_df.at[first_week_idx, 'План_посещений'] + difference
                    result_df.at[first_week_idx, 'План_посещений'] = max(0, new_value)
        
        # 7. Проверяем итоговую сумму
        total_expected = points_df['Кол-во_посещений'].sum()
        total_distributed = result_df['План_посещений'].sum()
        
        if total_expected != total_distributed:
            st.warning(f"⚠️ Небольшое расхождение в распределении: {total_expected} ≠ {total_distributed}")
            # Корректируем у первого аудитора
            if not result_df.empty:
                result_df.iloc[0, result_df.columns.get_loc('План_посещений')] += (total_expected - total_distributed)
        
        return result_df
        
    except Exception as e:
        import traceback
        st.error(f"❌ Ошибка при распределении посещений по неделям: {str(e)}")
        st.error(f"Детали:\n{traceback.format_exc()}")
        return pd.DataFrame()

def recursive_geographic_split_by_sizes(points_df, target_sizes, depth=0):
    """
    Рекурсивно делит точки географически на части заданных размеров.
    """
    
    # БАЗОВЫЕ СЛУЧАИ с защитой от ошибок
    # 1. Если точек нет или sizes нет
    if points_df.empty or not target_sizes:
        # Возвращаем пустые кластеры по количеству target_sizes
        return [pd.DataFrame(columns=points_df.columns) for _ in range(len(target_sizes))]
    
    # 2. Если нужна только одна часть
    if len(target_sizes) == 1:
        return [points_df.copy()]
    
    # 3. Если точек меньше, чем нужно частей
    if len(points_df) <= len(target_sizes):
        clusters = []
        points_as_list = []
        
        # Безопасное преобразование
        try:
            points_as_list = points_df.to_dict('records')
        except:
            # Если ошибка, создаём пустые кластеры
            return [pd.DataFrame(columns=points_df.columns) for _ in range(len(target_sizes))]
        
        # Заполняем кластеры точками
        for i, target_size in enumerate(target_sizes):
            if i < len(points_as_list) and target_size > 0:
                # Создаём DataFrame с одной точкой
                try:
                    clusters.append(pd.DataFrame([points_as_list[i]]))
                except:
                    clusters.append(pd.DataFrame(columns=points_df.columns))
            else:
                clusters.append(pd.DataFrame(columns=points_df.columns))
        
        return clusters
    
    # ОСНОВНАЯ ЛОГИКА
    # Определяем ось деления
    axis = 'latitude' if depth % 2 == 0 else 'longitude'
    
    # Сортируем точки по выбранной оси
    try:
        if axis == 'latitude':
            sorted_df = points_df.sort_values('Широта', ascending=False)
        else:
            sorted_df = points_df.sort_values('Долгота', ascending=True)
    except KeyError:
        # Если нет колонок с координатами
        return [pd.DataFrame(columns=points_df.columns) for _ in range(len(target_sizes))]
    
    # Разделяем target_sizes на две группы
    split_index = len(target_sizes) // 2
    first_sizes = target_sizes[:split_index]
    second_sizes = target_sizes[split_index:]
    
    # Вычисляем, сколько точек должно быть в первой группе
    first_group_target = sum(first_sizes)
    
    # БЕЗОПАСНО находим точку раздела
    if len(sorted_df) == 0:
        split_point_idx = 0
    else:
        split_point_idx = min(first_group_target, len(sorted_df))
        split_point_idx = max(0, split_point_idx)  # гарантируем не отрицательный
    
    # Делим DataFrame (безопасно)
    if split_point_idx >= len(sorted_df):
        first_part = sorted_df.copy()
        second_part = pd.DataFrame(columns=points_df.columns)
    elif split_point_idx <= 0:
        first_part = pd.DataFrame(columns=points_df.columns)
        second_part = sorted_df.copy()
    else:
        first_part = sorted_df.iloc[:split_point_idx].copy()
        second_part = sorted_df.iloc[split_point_idx:].copy()
    
    # Рекурсивно делим только если есть точки
    if len(first_part) > 0 and first_sizes:
        first_clusters = recursive_geographic_split_by_sizes(
            first_part, first_sizes, depth + 1
        )
    else:
        first_clusters = [pd.DataFrame(columns=points_df.columns) for _ in range(len(first_sizes))]
    
    if len(second_part) > 0 and second_sizes:
        second_clusters = recursive_geographic_split_by_sizes(
            second_part, second_sizes, depth + 1
        )
    else:
        second_clusters = [pd.DataFrame(columns=points_df.columns) for _ in range(len(second_sizes))]
    
    # Объединяем результаты
    all_clusters = first_clusters + second_clusters
    
    # ГАРАНТИРУЕМ, что количество кластеров = len(target_sizes)
    if len(all_clusters) != len(target_sizes):
        # Корректируем: добавляем пустые или обрезаем лишние
        if len(all_clusters) < len(target_sizes):
            for _ in range(len(target_sizes) - len(all_clusters)):
                all_clusters.append(pd.DataFrame(columns=points_df.columns))
        else:
            all_clusters = all_clusters[:len(target_sizes)]
    
    # СОРТИРОВКА КЛАСТЕРОВ ПО ГЕОГРАФИИ
    cluster_data = []
    for i, cluster in enumerate(all_clusters):
        if not cluster.empty and len(cluster) > 0:
            try:
                centroid_lat = cluster['Широта'].mean()
                centroid_lon = cluster['Долгота'].mean()
            except (KeyError, TypeError):
                centroid_lat = 0
                centroid_lon = 0
        else:
            # Для пустого кластера используем крайние значения
            if axis == 'latitude':
                centroid_lat = -90 if i % 2 == 0 else 90  # чередуем
                centroid_lon = 0
            else:
                centroid_lat = 0
                centroid_lon = -180 if i % 2 == 0 else 180
        
        cluster_data.append({
            'index': i,
            'cluster': cluster,
            'centroid_lat': centroid_lat,
            'centroid_lon': centroid_lon
        })
    
    # Сортируем по оси
    try:
        if axis == 'latitude':
            cluster_data.sort(key=lambda x: -x['centroid_lat'])
        else:
            cluster_data.sort(key=lambda x: x['centroid_lon'])
    except:
        pass  # Если сортировка не удалась, оставляем как есть
    
    # Возвращаем отсортированные кластеры
    return [item['cluster'] for item in cluster_data]

def create_weekly_geographic_clusters(points_assignment_df, points_df, year, quarter, coefficients):
    """
    Создает недельные географические кластеры для каждого аудитора.
    Использует коэффициенты нагрузки и географическое деление.
    """
    
    results = []
    auditors = points_assignment_df['Аудитор'].unique()
    weeks_info = get_weeks_in_quarter(year, quarter)
    
    if not weeks_info:
        st.warning("⚠️ Не удалось получить недели квартала")
        return pd.DataFrame()
    
    for auditor in auditors:
        # 1. Находим точки аудитора
        auditor_point_ids = points_assignment_df[
            points_assignment_df['Аудитор'] == auditor
        ]['ID_Точки'].tolist()
        
        if not auditor_point_ids:
            continue
        
        auditor_points = points_df[
            points_df['ID_Точки'].isin(auditor_point_ids)
        ].copy()
        
        if auditor_points.empty:
            st.warning(f"⚠️ Аудитор {auditor}: не найдены точки с координатами")
            continue
        
        # 2. Рассчитываем целевые размеры недель
        total_points = len(auditor_points)
        weekly_targets = calculate_weekly_targets(
            total_points, year, quarter, coefficients
        )
        
        # 3. СИНХРОНИЗИРУЕМ: если размеры не совпадают, берем минимум
        n_weeks_to_use = min(len(weekly_targets), len(weeks_info))
        
        if n_weeks_to_use == 0:
            st.warning(f"⚠️ Аудитор {auditor}: нет недель для распределения")
            continue
            
        if len(weekly_targets) != len(weeks_info):
            st.warning(f"⚠️ Аудитор {auditor}: недель расчёта {len(weekly_targets)} != календарных {len(weeks_info)}. "
                      f"Используем {n_weeks_to_use} недель.")
        
        # Берём только первые n_weeks_to_use недель
        weekly_targets = weekly_targets[:n_weeks_to_use]
        weeks_to_use = weeks_info[:n_weeks_to_use]
        
        # 4. Делим точки географически
        clusters = recursive_geographic_split_by_sizes(
            auditor_points, weekly_targets
        )
        
        # 5. ПРОВЕРЯЕМ и выравниваем количество кластеров
        if len(clusters) != len(weekly_targets):
            # Если кластеров больше - обрезаем
            if len(clusters) > len(weekly_targets):
                clusters = clusters[:len(weekly_targets)]
            # Если меньше - добавляем пустые
            else:
                while len(clusters) < len(weekly_targets):
                    clusters.append(pd.DataFrame(columns=auditor_points.columns))
        
        # 6. Назначаем кластеры неделям
        for week_index in range(len(weeks_to_use)):
            cluster = clusters[week_index] if week_index < len(clusters) else pd.DataFrame()
            week_info = weeks_to_use[week_index]
            
            # Даже если кластер пустой - создаём запись (неделя без точек)
            if cluster.empty:
                # Пустая неделя - создаём хотя бы одну "фантомную" запись для структуры
                # или просто пропускаем? Пока пропускаем, но логируем
                continue
            
            # Для каждой точки в кластере
            for _, point in cluster.iterrows():
                results.append({
                    'ID_Точки': point['ID_Точки'],
                    'Аудитор': auditor,
                    'Неделя': week_info['iso_week_number'],
                    'Кластер_номер': week_index,
                    'Дата_начала_недели': week_info['start_date'],
                    'Дата_окончания_недели': week_info['end_date'],
                    'План_посещений': 1
                })
    
    # Создаём DataFrame
    if not results:
        st.warning("⚠️ Не удалось создать ни одного кластера")
        return pd.DataFrame()
    
    result_df = pd.DataFrame(results)
    
    # Проверка распределения
    total_assigned = len(result_df)
    total_expected = len(points_assignment_df)
    
    if total_assigned != total_expected:
        st.warning(f"⚠️ Распределено {total_assigned} из {total_expected} точек "
                  f"(разница: {total_expected - total_assigned})")
        # Можно добавить логику для поиска потерянных точек
    
    return result_df

def convert_clusters_to_weekly_plan(weekly_clusters_df, points_df):
    """
    Преобразует DataFrame с недельными кластерами в формат weekly plan.
    Совместимость с существующей системой.
    
    Возвращает DataFrame в формате detailed_plan_df:
    ['Город', 'Полигон', 'Аудитор', 'ISO_Неделя', 
     'Дата_начала', 'Дата_окончания', 'План_посещений',
     'Факт_посещений', '%_выполнения']
    """
    
    if weekly_clusters_df.empty:
        return pd.DataFrame()
    
    # 1. Группируем по аудитору и неделе
    grouped = weekly_clusters_df.groupby([
        'Аудитор', 
        'Неделя', 
        'Дата_начала_недели', 
        'Дата_окончания_недели'
    ]).agg({
        'ID_Точки': 'count',
        'Кластер_номер': 'first'
    }).reset_index()
    
    # 2. Переименовываем для совместимости
    grouped = grouped.rename(columns={
        'ID_Точки': 'План_посещений',
        'Неделя': 'ISO_Неделя',
        'Дата_начала_недели': 'Дата_начала',
        'Дата_окончания_недели': 'Дата_окончания'
    })
    
    # 3. Добавляем обязательные колонки
    grouped['Город'] = 'Неизвестно'
    grouped['Полигон'] = 'Гео-кластер'
    grouped['Факт_посещений'] = 0
    grouped['%_выполнения'] = 0.0
    
    # 4. Определяем город для каждого аудитора
    # (берем город первой точки аудитора)
    for auditor in grouped['Аудитор'].unique():
        auditor_points = weekly_clusters_df[
            weekly_clusters_df['Аудитор'] == auditor
        ]
        
        if not auditor_points.empty:
            # Берём первую точку аудитора
            first_point_id = auditor_points.iloc[0]['ID_Точки']
            
            # Ищем город этой точки
            city_match = points_df[points_df['ID_Точки'] == first_point_id]
            if not city_match.empty:
                city = city_match.iloc[0]['Город']
                grouped.loc[grouped['Аудитор'] == auditor, 'Город'] = city
    
    # 5. Упорядочиваем колонки как в оригинальном detailed_plan_df
    column_order = [
        'Город', 
        'Полигон', 
        'Аудитор', 
        'ISO_Неделя',
        'Дата_начала', 
        'Дата_окончания',
        'План_посещений', 
        'Факт_посещений', 
        '%_выполнения'
    ]
    
    return grouped[column_order]

def create_geographic_daily_routes(points_df, weekly_clusters_df):
    """
    Создает ежедневные маршруты на основе недельных географических кластеров.
    Каждая неделя делится на 5 географических суб-кластеров (дней).
    """
    
    if weekly_clusters_df.empty:
        return pd.DataFrame()
    
    results = []
    
    # 1. Группируем по аудиторам и неделям
    grouped = weekly_clusters_df.groupby(['Аудитор', 'Неделя'])
    
    for (auditor, week_num), week_points in grouped:
        # 2. Получаем все точки этой недели у этого аудитора
        week_point_ids = week_points['ID_Точки'].tolist()
        week_data = points_df[points_df['ID_Точки'].isin(week_point_ids)].copy()
        
        if week_data.empty or len(week_data) < 1:
            continue
        
        # 3. Делим недельный кластер на 5 дней (географически)
        # Вычисляем размеры для каждого дня
        n_points = len(week_data)
        base_size = n_points // 5
        remainder = n_points % 5
        
        daily_targets = [base_size] * 5
        for i in range(remainder):
            daily_targets[i] += 1
        
        # Делим географически
        daily_clusters = recursive_geographic_split_by_sizes(week_data, daily_targets)
        
        # 4. Назначаем дни недели (понедельник-пятница)
        days_of_week = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница']
        
        for day_idx, (day_cluster, day_name) in enumerate(zip(daily_clusters, days_of_week)):
            if day_cluster.empty or len(day_cluster) == 0:
                continue
            
            # 5. Преобразуем в список словарей для greedy_route
            try:
                day_points_list = day_cluster.to_dict('records')
            except:
                continue
            
            # 6. Строим оптимальный маршрут внутри дня
            try:
                optimized_route = WeeklyRouteOptimizer.greedy_route(day_points_list)
            except:
                # Если оптимизация не сработала, используем исходный порядок
                optimized_route = day_points_list
            
            # 7. Получаем дату начала недели (понедельник)
            try:
                start_date = week_points['Дата_начала_недели'].iloc[0]
                if hasattr(start_date, 'strftime'):
                    date_str = start_date.strftime('%Y%m%d')
                else:
                    date_str = str(start_date).replace('-', '')[:8]
            except:
                date_str = f"2025{week_num:02d}01"  # fallback
            
            # 8. Добавляем в результаты в формате EasyMerch
            for point in optimized_route:
                row = {
                    'ID_Точки': point['ID_Точки'],  # ← НОВАЯ ПЕРВАЯ КОЛОНКА
                    'Address': point.get('Адрес', ''),
                    'L1 Name': point.get('Название_Точки', point['ID_Точки']),
                    'ЧИСЛО визитов в НЕДЕЛЮ': 1,
                    'Login пользователя': auditor,
                    'Понедельник': 1 if day_name == 'Понедельник' else '',
                    'Вторник': 1 if day_name == 'Вторник' else '',
                    'Среда': 1 if day_name == 'Среда' else '',
                    'Четверг': 1 if day_name == 'Четверг' else '',
                    'Пятница': 1 if day_name == 'Пятница' else '',
                    'Суббота': '',  # всегда пусто
                    'Воскресенье': '',  # всегда пусто
                    'Вне графика': '',  # ← НОВАЯ ПУСТАЯ КОЛОНКА
                    'Цикл посещения': week_num,
                    'Дата начала цикла посещения': date_str,
                    'Широта': f"{point.get('Широта', 0):.6f}",
                    'Долгота': f"{point.get('Долгота', 0):.6f}",
                    'Город': point.get('Город', '')  # ← НОВАЯ КОЛОНКА
                }    
                
                # Добавляем отметки для дней недели
                for day_col in ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье']:
                    row[day_col] = 1 if day_col == day_name else ''
                
                results.append(row)
    
    if not results:
        return pd.DataFrame()
    
    # Создаём финальный DataFrame
    routes_df = pd.DataFrame(results)
    
    # Упорядочиваем колонки
    column_order = [
        'ID_Точки',           
        'Address',
        'L1 Name',
        'ЧИСЛО визитов в НЕДЕЛЮ',
        'Login пользователя',
        'Понедельник',
        'Вторник',
        'Среда',
        'Четверг',
        'Пятница',
        'Суббота',
        'Воскресенье',
        'Вне графика',        
        'Цикл посещения',
        'Дата начала цикла посещения',
        'Широта',
        'Долгота',
        'Город'              
    ]
    
    # Оставляем только существующие колонки
    column_order = [col for col in column_order if col in routes_df.columns]
    
    return routes_df[column_order]
    

# ==============================================
# ФУНКЦИИ ДЛЯ РАСПРЕДЕЛЕНИЯ ПО АУДИТОРАМ (ГЕОГРАФИЧЕСКОЕ РАЗДЕЛЕНИЕ)
# ==============================================

def split_into_sectors(points_df, n_sectors):
    """
    Делит точки на угловые сектора от географического центра.
    Используется для круглых городов.
    
    Args:
        points_df: DataFrame с точками (должны быть колонки 'Широта', 'Долгота')
        n_sectors: количество секторов
    
    Returns:
        list of DataFrames — список групп точек по секторам
    """
    if len(points_df) == 0 or n_sectors <= 0:
        return []
    
    # 1. Находим географический центр (среднее по координатам)
    center_lat = points_df['Широта'].mean()
    center_lon = points_df['Долгота'].mean()
    
    # 2. Вычисляем азимут (угол от центра) для каждой точки
    def calculate_bearing(lat, lon):
        """Вычисляет угол от центра (в градусах, 0-360)"""
        delta_lon = lon - center_lon
        delta_lat = lat - center_lat
        
        # Вычисляем угол в радианах
        angle = math.atan2(delta_lon, delta_lat)
        # Переводим в градусы (0-360)
        bearing = math.degrees(angle)
        if bearing < 0:
            bearing += 360
        return bearing
    
    points_df_copy = points_df.copy()
    points_df_copy['азимут'] = points_df_copy.apply(
        lambda row: calculate_bearing(row['Широта'], row['Долгота']), 
        axis=1
    )
    
    # 3. Сортируем по азимуту
    points_df_copy = points_df_copy.sort_values('азимут').reset_index(drop=True)
    
    # 4. Делим на равные сектора (равное количество точек, а не равные углы)
    sector_size = len(points_df_copy) // n_sectors
    remainder = len(points_df_copy) % n_sectors
    
    sectors = []
    start_idx = 0
    
    for i in range(n_sectors):
        size = sector_size + (1 if i < remainder else 0)
        end_idx = start_idx + size
        
        if start_idx < len(points_df_copy):
            sector = points_df_copy.iloc[start_idx:end_idx].copy()
            sector = sector.drop(columns=['азимут'])
            sectors.append(sector)
        else:
            sectors.append(pd.DataFrame(columns=points_df.columns))
        
        start_idx = end_idx
    
    return sectors


def divide_points_by_direction(points_df, n_auditors, city):
    """
    Разделяет точки на географические полигоны с равным распределением
    
    - 1 аудитор: весь город
    - 2 аудитора: Север/Юг
    - 3 аудитора: Север + Юго-Восток + Юго-Запад
    - 4 аудитора: 4 квадранта
    - 5+ аудиторов: 
        * вытянутый город → полосы поперек длинной стороны
        * круглый город → угловые сектора от центра
    """
    
    # ========== 1. Базовые случаи (оставляем как есть) ==========
    if n_auditors == 1:
        return [points_df]
    
    elif n_auditors == 2:
        # Север-Юг: сортируем по широте, делим пополам
        points_sorted = points_df.sort_values('Широта', ascending=False).reset_index(drop=True)
        split_idx = len(points_sorted) // 2
        north = points_sorted.iloc[:split_idx].copy()
        south = points_sorted.iloc[split_idx:].copy()
        return [north, south]
    
    elif n_auditors == 3:
        # Север + Юго-Восток + Юго-Запад
        points_sorted = points_df.sort_values('Широта', ascending=False).reset_index(drop=True)
        north_size = len(points_sorted) // 3
        north = points_sorted.iloc[:north_size].copy()
        south_points = points_sorted.iloc[north_size:].copy()
        
        if not south_points.empty:
            south_sorted = south_points.sort_values('Долгота').reset_index(drop=True)
            median_lon = south_sorted['Долгота'].median()
            
            southeast = south_sorted[south_sorted['Долгота'] >= median_lon].copy()
            southwest = south_sorted[south_sorted['Долгота'] < median_lon].copy()
            
            # Балансировка ЮВ и ЮЗ
            target_south_size = len(south_sorted) // 2
            if len(southeast) > target_south_size + 2:
                excess = len(southeast) - target_south_size
                points_to_move = southeast.nsmallest(excess, 'Долгота')
                southeast = southeast.drop(points_to_move.index)
                southwest = pd.concat([southwest, points_to_move], ignore_index=True)
            elif len(southwest) > target_south_size + 2:
                excess = len(southwest) - target_south_size
                points_to_move = southwest.nlargest(excess, 'Долгота')
                southwest = southwest.drop(points_to_move.index)
                southeast = pd.concat([southeast, points_to_move], ignore_index=True)
            
            return [north, southeast, southwest]
        
        return [north, pd.DataFrame(), pd.DataFrame()]
    
    elif n_auditors == 4:
        # 4 квадранта: Северо-Восток, Северо-Запад, Юго-Восток, Юго-Запад
        median_lat = points_df['Широта'].median()
        median_lon = points_df['Долгота'].median()
        
        ne = points_df[(points_df['Широта'] >= median_lat) & (points_df['Долгота'] >= median_lon)].copy()
        nw = points_df[(points_df['Широта'] >= median_lat) & (points_df['Долгота'] < median_lon)].copy()
        se = points_df[(points_df['Широта'] < median_lat) & (points_df['Долгота'] >= median_lon)].copy()
        sw = points_df[(points_df['Широта'] < median_lat) & (points_df['Долгота'] < median_lon)].copy()
        
        return [ne, se, sw, nw]
    
    # ========== 2. НОВАЯ ЛОГИКА ДЛЯ 5+ АУДИТОРОВ ==========
    else:
        # Защита от пустых данных
        if points_df.empty:
            return [pd.DataFrame(columns=points_df.columns) for _ in range(n_auditors)]
        
        # 2.1. Определяем форму города
        lats = points_df['Широта'].values
        lons = points_df['Долгота'].values
        
        lat_range = lats.max() - lats.min()
        lon_range = lons.max() - lons.min()
        
        # Избегаем деления на ноль
        if min(lat_range, lon_range) < 0.0001:
            # Город почти точка — используем простое деление
            return np.array_split(points_df, n_auditors)
        
        ratio = max(lat_range, lon_range) / min(lat_range, lon_range)
        
        # 2.2. Выбираем стратегию в зависимости от формы города
        if ratio > 1.5:
            # ВЫТЯНУТЫЙ ГОРОД — режем полосами поперек длинной стороны
            if lat_range > lon_range:
                # Вытянут по широте (север-юг) → режем по широте на полосы
                points_sorted = points_df.sort_values('Широта', ascending=False).reset_index(drop=True)
            else:
                # Вытянут по долготе (запад-восток) → режем по долготе на полосы
                points_sorted = points_df.sort_values('Долгота', ascending=True).reset_index(drop=True)
            
            # Делим на N равных частей (по количеству точек)
            return np.array_split(points_sorted, n_auditors)
        
        else:
            # КРУГЛЫЙ ГОРОД — режем на угловые сектора от центра
            sectors = split_into_sectors(points_df, n_auditors)
            
            # Если сектора получились пустыми — fallback к простому делению
            if not sectors or all(s.empty for s in sectors):
                return np.array_split(points_df, n_auditors)
            
            return sectors


def balance_point_groups_final(groups, n_auditors):
    """
    Финальная балансировка групп по количеству точек
    Возвращает примерно равные по размеру группы
    """
    if not groups or n_auditors <= 0:
        return []
    
    # Удаляем пустые группы
    valid_groups = [g for g in groups if g is not None and not g.empty]
    
    if not valid_groups:
        # Если все группы пустые, возвращаем оригинальные
        return groups[:n_auditors] if len(groups) >= n_auditors else groups
    
    # Объединяем все точки
    all_points = pd.concat(valid_groups, ignore_index=True)
    
    # Сортируем для воспроизводимости
    all_points = all_points.sort_values('ID_Точки').reset_index(drop=True)
    
    # Делим на равные части
    chunk_size = len(all_points) // n_auditors
    remainder = len(all_points) % n_auditors
    
    balanced_groups = []
    start_idx = 0
    
    for i in range(n_auditors):
        # Определяем размер этой группы
        size = chunk_size + (1 if i < remainder else 0)
        end_idx = start_idx + size
        
        if start_idx < len(all_points):
            group = all_points.iloc[start_idx:end_idx].copy()
        else:
            # Создаем пустую группу с правильными колонками
            group = pd.DataFrame(columns=all_points.columns)
        
        balanced_groups.append(group)
        start_idx = end_idx
    
    return balanced_groups


def distribute_points_to_auditors(points_df, auditors_df):
    """Распределяет точки по аудиторам с географическим разделением"""
    
    if points_df is None or points_df.empty:
        st.error("❌ Нет данных о точках для распределения")
        return None, None
    
    results = []
    polygons_info = {}
    
    # Группируем по городам
    for city in points_df['Город'].unique():
        city_points = points_df[points_df['Город'] == city].copy()
        city_auditors = auditors_df[auditors_df['Город'] == city]['ID_Сотрудника'].tolist()
        
        if len(city_auditors) == 0:
            st.warning(f"⚠️ В городе {city} нет аудиторов")
            continue
        
        n_auditors = len(city_auditors)
        
        # Разделяем точки по географическим направлениям
        point_groups = divide_points_by_direction(city_points, n_auditors, city)
        
        # Финальная балансировка (если групп больше чем аудиторов)
        if len(point_groups) > n_auditors:
            point_groups = point_groups[:n_auditors]
        elif len(point_groups) < n_auditors:
            # Добавляем пустые группы если нужно
            while len(point_groups) < n_auditors:
                point_groups.append(pd.DataFrame(columns=city_points.columns))
        
        # Направления для названий полигонов
        if n_auditors == 1:
            directions = [f"{city}"]
        elif n_auditors == 2:
            directions = [f"{city}-Север", f"{city}-Юг"]
        elif n_auditors == 3:
            directions = [f"{city}-Север", f"{city}-Юго-Восток", f"{city}-Юго-Запад"]
        elif n_auditors == 4:
            directions = [f"{city}-Север", f"{city}-Восток", f"{city}-Юг", f"{city}-Запад"]
        else:
            directions = [f"{city}-Зона-{i+1}" for i in range(n_auditors)]
        
        # Распределяем группы точек по аудиторам
        for i in range(n_auditors):
            if i >= len(city_auditors) or i >= len(point_groups) or i >= len(directions):
                continue
                
            auditor = city_auditors[i]
            point_group = point_groups[i]
            direction = directions[i]
            
            if point_group.empty:
                st.warning(f"⚠️ Аудитор {auditor} в городе {city} не получил точек")
                continue
            
            polygon_name = direction
            
            for _, point in point_group.iterrows():
                results.append({
                    'ID_Точки': point['ID_Точки'],
                    'Аудитор': auditor,
                    'Город': city,
                    'Полигон': polygon_name
                })
            
            polygons_info[polygon_name] = {
                'auditor': auditor,
                'city': city,
                'points': point_group[['ID_Точки', 'Широта', 'Долгота']].values.tolist()
            }
    
    if not results:
        st.warning("⚠️ Не удалось распределить точки по аудиторам")
        return None, None
    
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
    """Минимальная версия - только самое необходимое"""
    
    # 1. Статистика по городам
    city_stats = []
    for city in points_df['Город'].unique():
        city_points = points_df[points_df['Город'] == city]
        city_stats.append({
            'Город': city,
            'Всего_точек': len(city_points),
            'План_посещений': city_points['Кол-во_посещений'].sum(),
            'Факт_посещений': 0,
            '%_выполнения': 0.0
        })
    
    # 2. Статистика по типам
    type_stats = []
    for point_type in points_df['Тип'].unique():
        type_points = points_df[points_df['Тип'] == point_type]
        type_stats.append({
            'Тип': point_type,
            'План_посещений': type_points['Кол-во_посещений'].sum(),
            'Факт_посещений': 0,
            '%_выполнения': 0.0
        })
    
    # 3. Сводный план = detailed_plan_df (уже распределен по неделям и аудиторам)
    summary_df = detailed_plan_df.copy()
    
    # Добавляем недостающие колонки
    if 'Факт_посещений' not in summary_df.columns:
        summary_df['Факт_посещений'] = 0
    
    if '%_выполнения' not in summary_df.columns:
        summary_df['%_выполнения'] = 0.0
    
    # 4. Детализация = та же detailed_plan_df
    detailed_with_fact = detailed_plan_df.copy()
    
    # Проверка
    total_expected = points_df['Кол-во_посещений'].sum()
    total_in_summary = summary_df['План_посещений'].sum()
    
    if total_expected != total_in_summary:
        st.warning(f"⚠️ Расхождение: {total_expected} ≠ {total_in_summary}")
    
    return (
        pd.DataFrame(city_stats),
        pd.DataFrame(type_stats),
        summary_df,
        detailed_with_fact
    )

def create_google_maps_excel(points_df, polygons, points_assignment_df=None):
    """Создает Excel файл для импорта в Google Maps с разбиением по городам/полигонам"""
    
    excel_buffer = io.BytesIO()
    
    # Создаем словарь для сопоставления точек
    point_to_polygon = {}
    point_to_auditor = {}
    
    # 1. Используем points_assignment_df
    if points_assignment_df is not None and not points_assignment_df.empty:
        for idx, row in points_assignment_df.iterrows():
            try:
                point_id = str(row['ID_Точки']).strip()
                if point_id:
                    point_to_polygon[point_id] = row.get('Полигон', 'Не назначен')
                    point_to_auditor[point_id] = row.get('Аудитор', 'Неизвестно')
            except (KeyError, AttributeError):
                continue
    
    # 2. Если нет assignment_df, используем полигоны
    if not point_to_polygon and polygons:
        for poly_name, poly_info in polygons.items():
            if 'points' in poly_info and poly_info['points']:
                for point_info in poly_info['points']:
                    if point_info and len(point_info) >= 3:
                        try:
                            point_id = str(point_info[0]).strip() if point_info[0] is not None else ''
                            if point_id:
                                point_to_polygon[point_id] = poly_name
                                point_to_auditor[point_id] = poly_info.get('auditor', 'Неизвестно')
                        except (IndexError, AttributeError):
                            continue
    
    # 3. Подготавливаем данные с группировкой
    grouped_data = {}
    
    for idx, point in points_df.iterrows():
        try:
            # ID точки
            point_id_raw = point.get('ID_Точки', '')
            point_id_str = str(point_id_raw).strip() if point_id_raw is not None else ''
            
            if not point_id_str:
                continue
                
            # Полигон и аудитор
            polygon = point_to_polygon.get(point_id_str, 'Не назначен')
            auditor = point_to_auditor.get(point_id_str, 'Неизвестно')
            
            # Город точки
            city = point.get('Город', 'Неизвестно')
            if pd.isna(city):
                city = 'Неизвестно'
            
            # Определяем ключ для группировки
            group_key = city
            
            # Координаты
            lat_raw = point.get('Широта', 0)
            lon_raw = point.get('Долгота', 0)
            
            # Преобразуем координаты с ТОЧКОЙ как десятичным разделителем
            try:
                if isinstance(lat_raw, str):
                    lat_clean = lat_raw.replace(',', '.').strip()
                else:
                    lat_clean = str(lat_raw).replace(',', '.').strip()
                    
                if isinstance(lon_raw, str):
                    lon_clean = lon_raw.replace(',', '.').strip()
                else:
                    lon_clean = str(lon_raw).replace(',', '.').strip()
                
                lat_float = float(lat_clean)
                lon_float = float(lon_clean)
                
                lat = f"{lat_float:.6f}"
                lon = f"{lon_float:.6f}"
                
            except (ValueError, TypeError):
                lat = str(lat_raw).replace(',', '.').strip()
                lon = str(lon_raw).replace(',', '.').strip()
            
            # Название и тип точки
            point_name = point.get('Название_Точки', point_id_str)
            if pd.isna(point_name):
                point_name = point_id_str
            
            point_type = point.get('Тип', 'Неизвестно')
            if pd.isna(point_type):
                point_type = 'Неизвестно'
            
            # Добавляем точку в соответствующую группу
            if group_key not in grouped_data:
                grouped_data[group_key] = []
            
            grouped_data[group_key].append({
                'ID точки': point_id_str,
                'Имя точки': str(point_name),
                'Тип точки': str(point_type),
                'Город': str(city),
                'Полигон': str(polygon),
                'Аудитор': str(auditor),
                'Широта': lat,
                'Долгота': lon
            })
        except Exception as e:
            continue
    
    # 4. Проверяем общее количество строк
    total_rows = sum(len(points) for points in grouped_data.values())
    
    # Храним информацию о вкладках для сводки
    sheet_info = []
    
    # 5. Создаем Excel файл
    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
        sheet_counter = 0
        
        # Если строк меньше 2000 - создаем одну вкладку
        if total_rows <= 2000:
            # Объединяем все данные
            all_data = []
            for city, points in grouped_data.items():
                all_data.extend(points)
            
            if all_data:
                df_all = pd.DataFrame(all_data)
                column_order = ['ID точки', 'Имя точки', 'Тип точки', 'Город', 'Полигон', 'Аудитор', 'Широта', 'Долгота']
                column_order = [col for col in column_order if col in df_all.columns]
                df_all = df_all[column_order]
                
                sheet_name = 'Все точки'
                df_all.to_excel(writer, sheet_name=sheet_name, index=False)
                
                sheet_info.append({
                    'Вкладка': sheet_name,
                    'Количество точек': len(df_all),
                    'Город': 'Все',
                    'Полигон': 'Все',
                    'Аудиторов': df_all['Аудитор'].nunique()
                })
        
        else:
            # Разбиваем на вкладки
            for city, city_points in grouped_data.items():
                if len(city_points) <= 2000:
                    # Весь город помещается на одну вкладку
                    df_city = pd.DataFrame(city_points)
                    column_order = ['ID точки', 'Имя точки', 'Тип точки', 'Город', 'Полигон', 'Аудитор', 'Широта', 'Долгота']
                    column_order = [col for col in column_order if col in df_city.columns]
                    df_city = df_city[column_order]
                    
                    # Формируем имя вкладки
                    sheet_name = city[:31]  # Ограничение Excel
                    
                    # Заменяем запрещенные символы
                    invalid_chars = ['/', '\\', '?', '*', ':', '[', ']']
                    for char in invalid_chars:
                        sheet_name = sheet_name.replace(char, '_')
                    
                    # Проверяем уникальность имени
                    original_name = sheet_name
                    counter = 1
                    while sheet_name in writer.sheets:
                        sheet_name = f"{original_name[:28]}_{counter}"
                        counter += 1
                    
                    df_city.to_excel(writer, sheet_name=sheet_name, index=False)
                    
                    sheet_info.append({
                        'Вкладка': sheet_name,
                        'Количество точек': len(df_city),
                        'Город': city,
                        'Полигон': 'Весь город',
                        'Аудиторов': df_city['Аудитор'].nunique()
                    })
                    
                    sheet_counter += 1
                else:
                    # Город нужно разбить по полигонам
                    city_points_df = pd.DataFrame(city_points)
                    
                    # Группируем по полигонам внутри города
                    for polygon in sorted(city_points_df['Полигон'].unique()):
                        polygon_points = city_points_df[city_points_df['Полигон'] == polygon].copy()
                        
                        if len(polygon_points) > 0:
                            # Готовим данные для полигона
                            column_order = ['ID точки', 'Имя точки', 'Тип точки', 'Город', 'Полигон', 'Аудитор', 'Широта', 'Долгота']
                            column_order = [col for col in column_order if col in polygon_points.columns]
                            polygon_points = polygon_points[column_order]
                            
                            # Формируем имя вкладки
                            if polygon != 'Не назначен':
                                sheet_name = f"{city[:15]}_{polygon[:15]}"
                            else:
                                sheet_name = f"{city[:20]}_Без полигона"
                            
                            # Очищаем имя вкладки
                            sheet_name = sheet_name[:31]
                            invalid_chars = ['/', '\\', '?', '*', ':', '[', ']']
                            for char in invalid_chars:
                                sheet_name = sheet_name.replace(char, '_')
                            
                            # Проверяем уникальность
                            original_name = sheet_name
                            counter = 1
                            while sheet_name in writer.sheets:
                                sheet_name = f"{original_name[:28]}_{counter}"
                                counter += 1
                            
                            polygon_points.to_excel(writer, sheet_name=sheet_name, index=False)
                            
                            sheet_info.append({
                                'Вкладка': sheet_name,
                                'Количество точек': len(polygon_points),
                                'Город': city,
                                'Полигон': polygon,
                                'Аудиторов': polygon_points['Аудитор'].nunique()
                            })
                            
                            sheet_counter += 1
        
        # 6. Добавляем сводную вкладку
        if sheet_info:
            df_summary = pd.DataFrame(sheet_info)
            df_summary = df_summary.sort_values('Количество точек', ascending=False)
            df_summary.to_excel(writer, sheet_name='Сводка', index=False)
        
        # 7. Добавляем итоговую статистику
        total_summary = pd.DataFrame([{
            'Всего точек': total_rows,
            'Количество вкладок': len(sheet_info),
            'Количество городов': len(grouped_data),
            'Дата выгрузки': datetime.now().strftime('%d.%m.%Y %H:%M'),
            'Статус': '✅ Успешно создано' if total_rows > 0 else '⚠️ Нет данных'
        }])
        total_summary.to_excel(writer, sheet_name='Итог', index=False)
    
    return excel_buffer.getvalue()

def create_kml_file(points_df, polygons):
    """Создает KML файл для Google Earth"""
    kml_header = '''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
<Document>
<name>Полигоны и точки аудиторов</name>
'''
    
    kml_content = kml_header
    
    # Добавляем полигоны
    for poly_name, poly_info in polygons.items():
        if 'coordinates' in poly_info and len(poly_info['coordinates']) > 0:
            coords = poly_info['coordinates']
            coord_string = " ".join([f"{lon},{lat},0" for lat, lon in coords if len([lat, lon]) >= 2])
            
            if coord_string:
                kml_content += f'''
<Placemark>
<name>🗺️ {poly_name}</name>
<description>Аудитор: {poly_info.get('auditor', 'Неизвестно')}
Город: {poly_info.get('city', 'Неизвестно')}
Количество точек: {len(poly_info.get('points', []))}</description>
<styleUrl>#polygonStyle</styleUrl>
<Polygon>
<outerBoundaryIs>
<LinearRing>
<coordinates>{coord_string}</coordinates>
</LinearRing>
</outerBoundaryIs>
</Polygon>
</Placemark>
'''
    
    # Добавляем точки
    for _, point in points_df.iterrows():
        kml_content += f'''
<Placemark>
<name>🏪 {point['Название_Точки'][:30]}</name>
<description>ID: {point['ID_Точки']}
Тип: {point.get('Тип', 'Неизвестно')}
Адрес: {point.get('Адрес', 'Не указан')}</description>
<Point>
<coordinates>{point['Долгота']},{point['Широта']},0</coordinates>
</Point>
</Placemark>
'''
    
    kml_content += '''
<Style id="polygonStyle">
<LineStyle>
<color>ff0000ff</color>
<width>2</width>
</LineStyle>
<PolyStyle>
<color>400000ff</color>
<fill>1</fill>
<outline>1</outline>
</PolyStyle>
</Style>
</Document>
</kml>
'''
    
    return kml_content

def create_full_excel_report(points_df, auditors_df, city_stats_df, 
                            type_stats_df, summary_df, polygons):
    """Создает полный отчет Excel со всеми данными"""
    import io
    
    excel_buffer = io.BytesIO()
    
    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
        # Лист 1: Точки
        if points_df is not None:
            points_df.to_excel(writer, sheet_name='Точки', index=False)
        
        # Лист 2: Аудиторы
        if auditors_df is not None:
            auditors_df.to_excel(writer, sheet_name='Аудиторы', index=False)
        
        # Лист 3: Статистика по городам
        if city_stats_df is not None:
            city_stats_df.to_excel(writer, sheet_name='Статистика_городов', index=False)
        
        # Лист 4: План посещений
        if summary_df is not None:
            summary_df.to_excel(writer, sheet_name='План_посещений', index=False)
        
        # Лист 5: Полигоны
        if polygons:
            poly_data = []
            for poly_name, poly_info in polygons.items():
                poly_data.append({
                    'Полигон': poly_name,
                    'Аудитор': poly_info.get('auditor', 'Неизвестно'),
                    'Город': poly_info.get('city', 'Неизвестно'),
                    'Количество_точек': len(poly_info.get('points', [])),
                    'Координаты_полигона': str(poly_info.get('coordinates', []))
                })
            
            pd.DataFrame(poly_data).to_excel(writer, sheet_name='Полигоны', index=False)
    
    return excel_buffer.getvalue()

def calculate_polygon_center(poly_info):
    """Вычисляет центроид полигона"""
    try:
        # Из координат полигона
        if 'coordinates' in poly_info and poly_info['coordinates']:
            coords = poly_info['coordinates']
            lats = [c[0] for c in coords if len(c) >= 2]
            lons = [c[1] for c in coords if len(c) >= 2]
            
            if lats and lons:
                return sum(lats) / len(lats), sum(lons) / len(lons)
        
        # Из точек полигона
        if 'points' in poly_info and poly_info['points']:
            points = poly_info['points']
            lats = []
            lons = []
            
            for point in points:
                if len(point) >= 3:
                    lats.append(point[1])  # широта
                    lons.append(point[2])  # долгота
            
            if lats and lons:
                return sum(lats) / len(lats), sum(lons) / len(lons)
    except:
        pass
    
    return None, None

def create_light_map(points_df, polygons, max_points=200):
    """Создает легкую карту (ограниченное количество точек)"""
    import folium
    
    # Центр карты
    center_lat = points_df['Широта'].mean()
    center_lon = points_df['Долгота'].mean()
    
    m = folium.Map(location=[center_lat, center_lon], zoom_start=10)
    
    # Ограничиваем количество точек для производительности
    if len(points_df) > max_points:
        display_points = points_df.sample(max_points)
        folium.Marker(
            location=[center_lat, center_lon],
            popup=f"Показано {max_points} из {len(points_df)} точек",
            icon=folium.Icon(color='red', icon='info-sign')
        ).add_to(m)
    else:
        display_points = points_df
    
    # Простые маркеры для точек
    for _, point in display_points.iterrows():
        folium.CircleMarker(
            location=[point['Широта'], point['Долгота']],
            radius=3,
            popup=point['ID_Точки'],
            color='blue',
            fill=True
        ).add_to(m)
    
    # Полигоны
    for poly_name, poly_info in polygons.items():
        if 'coordinates' in poly_info and len(poly_info['coordinates']) > 2:
            folium.Polygon(
                locations=poly_info['coordinates'],
                popup=f"Полигон: {poly_name}",
                color='red',
                weight=2,
                fill=True,
                fill_opacity=0.1
            ).add_to(m)
    
    return m

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
            
            if points_assignment_df is None or polygons_info is None:
                st.error("❌ Не удалось распределить точки по аудиторам")
                st.stop()
            
            # ✅ СОХРАНЯЕМ ДАННЫЕ ДЛЯ ВЫГРУЗКИ
            st.session_state.points_assignment_df = points_assignment_df
            st.session_state.polygons_info = polygons_info
            
            # Генерируем полигоны
            polygons = generate_polygons(polygons_info)
            st.session_state.polygons = polygons
            
            st.success(f"✅ Точки распределены по {len(polygons_info)} полигонам")
            st.success(f"✅ Сохранено {len(points_assignment_df)} назначений точек")
        
        with st.spinner("🔄 Создание недельных географических кластеров..."):
            # 1. Создаем географические кластеры
            weekly_clusters_df = create_weekly_geographic_clusters(
                points_assignment_df, points_df, year, quarter, coefficients
            )
            
            if weekly_clusters_df.empty:
                st.error("❌ Не удалось создать недельные кластеры. Используем старую логику.")
                # Fallback к старой логике
                detailed_plan_df = distribute_visits_by_weeks(
                    points_assignment_df, points_df, year, quarter, coefficients
                )
            else:
                # Сохраняем новые данные
                st.session_state.weekly_clusters_df = weekly_clusters_df
                
                # 2. Конвертируем в формат weekly plan (для совместимости)
                detailed_plan_df = convert_clusters_to_weekly_plan(
                    weekly_clusters_df, points_df
                )
                
                if detailed_plan_df.empty:
                    st.error("❌ Не удалось преобразовать кластеры. Используем старую логику.")
                    detailed_plan_df = distribute_visits_by_weeps(
                        points_assignment_df, points_df, year, quarter, coefficients
                    )
            
            # Сохраняем результат (в любом случае)
            st.session_state.detailed_plan_df = detailed_plan_df
            
            if not weekly_clusters_df.empty:
                st.success(f"✅ Создано {len(weekly_clusters_df)} распределений точек по неделям")
            else:
                st.success(f"✅ Распределено {len(detailed_plan_df)} записей по неделям (старая логика)")

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
        # ОПТИМИЗАЦИЯ МАРШРУТОВ ПО ДНЯМ
        # ==============================================
        
        with st.spinner("🗺️ Оптимизация маршрутов по дням недели..."):
            try:
                # Используем НОВУЮ географическую логику, если есть кластеры
                if 'weekly_clusters_df' in st.session_state and not st.session_state.weekly_clusters_df.empty:
                    routes_df = create_geographic_daily_routes(
                        points_df, st.session_state.weekly_clusters_df
                    )
                    method_used = "географические кластеры"
                else:
                    # Fallback к старой логике
                    routes_df = create_weekly_route_schedule(
                        points_df, points_assignment_df, auditors_df, year, quarter
                    )
                    method_used = "старая логика"
                
                if not routes_df.empty:
                    st.session_state.routes_df = routes_df
                    st.success(f"✅ Построены маршруты ({method_used}): {len(routes_df)} записей")
                else:
                    st.warning("⚠️ Не удалось построить маршруты")
                    
            except Exception as e:
                st.error(f"❌ Ошибка при оптимизации маршрутов: {str(e)}")
                import traceback
                st.error(f"Детали ошибки:\n{traceback.format_exc()}")
                

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
                st.session_state.plan_calculated = True  
                
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
                st.session_state.plan_calculated = True 
                
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
        st.warning("⚠️ Для отображения карты установите: pip install folium streamlit-folium")
    
    # 1. СОЗДАЕМ СПИСОК ВКЛАДОК
    available_tabs = []
    
    # Проверяем, какие данные есть
    if st.session_state.city_stats_df is not None:
        available_tabs.append("📊 Статистика по городам")
    
    if st.session_state.summary_df is not None:
        available_tabs.append("📋 План посещений")
    
    if (st.session_state.city_stats_df is not None or 
        st.session_state.type_stats_df is not None):
        available_tabs.append("📈 Диаграммы")
    
    available_tabs.append("📤 Выгрузка данных")
    
    # 2. СОЗДАЕМ ВКЛАДКИ ТОЛЬКО ОДИН РАЗ
    if available_tabs:
        results_tabs = st.tabs(available_tabs)
        
        # 3. РАБОТАЕМ С КАЖДОЙ ВКЛАДКОЙ ПО ПОРЯДКУ
        current_tab = 0
        
        # ВКЛАДКА 1: Статистика по городам
        if "📊 Статистика по городам" in available_tabs:
            with results_tabs[current_tab]:
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
            current_tab += 1
        
        # ВКЛАДКА 2: План посещений 
        if "📋 План посещений" in available_tabs:
            with results_tabs[current_tab]:
                st.subheader("📋 План посещений")
                
                if st.session_state.summary_df is not None:
                    summary_df = st.session_state.summary_df.copy()
                    
                    if not summary_df.empty:
                        # Фильтры
                        st.markdown("### 🔍 Фильтры")
                        
                        col1, col2, col3, col4 = st.columns(4)
                        
                        with col1:
                            # Фильтр по городам
                            all_cities = ["Все"] + sorted(summary_df['Город'].unique().tolist())
                            selected_city = st.selectbox("Город", all_cities, key="filter_city")
                        
                        with col2:
                            # Фильтр по аудиторам
                            all_auditors = ["Все"] + sorted(summary_df['Аудитор'].unique().tolist())
                            selected_auditor = st.selectbox("Аудитор", all_auditors, key="filter_auditor")
                        
                        with col3:
                            # Фильтр по неделям
                            all_weeks = ["Все"] + sorted(summary_df['ISO_Неделя'].unique().tolist())
                            selected_week = st.selectbox("Неделя", all_weeks, key="filter_week")
                        
                        with col4:
                            # Фильтр по полигонам
                            all_polygons = ["Все"] + sorted(summary_df['Полигон'].unique().tolist())
                            selected_polygon = st.selectbox("Полигон", all_polygons, key="filter_polygon")
                        
                        # Применяем фильтры
                        filtered_df = summary_df.copy()
                        
                        if selected_city != "Все":
                            filtered_df = filtered_df[filtered_df['Город'] == selected_city]
                        
                        if selected_auditor != "Все":
                            filtered_df = filtered_df[filtered_df['Аудитор'] == selected_auditor]
                        
                        if selected_week != "Все":
                            filtered_df = filtered_df[filtered_df['ISO_Неделя'] == selected_week]
                        
                        if selected_polygon != "Все":
                            filtered_df = filtered_df[filtered_df['Полигон'] == selected_polygon]
                        
                        # Показываем статистику фильтра
                        st.markdown(f"**📊 Найдено записей:** {len(filtered_df)}")
                        
                        if len(filtered_df) > 0:
                            # Суммарная статистика
                            total_plan = filtered_df['План_посещений'].sum()
                            total_fact = filtered_df['Факт_посещений'].sum() if 'Факт_посещений' in filtered_df.columns else 0
                            completion = round((total_fact / total_plan * 100) if total_plan > 0 else 0, 1)
                            
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                st.metric("План посещений", total_plan)
                            with col2:
                                st.metric("Факт посещений", total_fact)
                            with col3:
                                st.metric("% выполнения", f"{completion}%")
                            
                            st.markdown("---")
                            
                            # Подготовка данных для отображения
                            display_df = filtered_df.copy()
                            
                            # Форматируем даты
                            display_df['Дата_начала'] = pd.to_datetime(display_df['Дата_начала']).dt.strftime('%d.%m.%Y')
                            display_df['Дата_окончания'] = pd.to_datetime(display_df['Дата_окончания']).dt.strftime('%d.%m.%Y')
                            
                            # Переименовываем колонки для читаемости
                            display_df = display_df.rename(columns={
                                'ISO_Неделя': 'Неделя',
                                'Дата_начала': 'Начало недели',
                                'Дата_окончания': 'Конец недели',
                                'План_посещений': 'План',
                                'Факт_посещений': 'Факт',
                                '%_выполнения': '% выполнения'
                            })
                            
                            # Выбираем колонки для отображения
                            display_columns = ['Город', 'Полигон', 'Аудитор', 'Неделя', 
                                             'Начало недели', 'Конец недели', 'План', 'Факт', '% выполнения']
                            
                            # Оставляем только существующие колонки
                            display_columns = [col for col in display_columns if col in display_df.columns]
                            
                            st.dataframe(
                                display_df[display_columns], 
                                use_container_width=True, 
                                height=400,
                                hide_index=True
                            )
                           
                            # Показываем краткий предпросмотр маршрутов
                            if 'routes_df' in st.session_state and st.session_state.routes_df is not None:
                                st.markdown("---")
                                st.subheader("🗺️ Маршруты для EasyMerch")
                                
                                routes_df = st.session_state.routes_df
                                
                                if not routes_df.empty:
                                    # Быстрые фильтры
                                    col1, col2 = st.columns(2)
                                    with col1:
                                        # Показываем только первые 20 строк для предпросмотра
                                        preview_df = routes_df.head(20)
                                        st.write(f"**Предпросмотр (первые 20 из {len(routes_df)} строк):**")
                                        st.dataframe(preview_df, use_container_width=True, height=300)
                                    
                                    with col2:
                                        # Статистика
                                        st.write("**📊 Статистика маршрутов:**")
                                        st.write(f"• Всего записей: {len(routes_df)}")
                                        st.write(f"• Аудиторов: {routes_df['Login пользователя'].nunique()}")
                                        st.write(f"• Недель: {routes_df['Цикл посещения'].nunique()}")
                                        st.write(f"• Уникальных точек: {routes_df['L1 Name'].nunique()}")
                                        
                                        # Общее количество визитов
                                        total_visits = routes_df['ЧИСЛО визитов в НЕДЕЛЮ'].sum()
                                        st.write(f"• Всего визитов в неделю: {total_visits}")
                                else:
                                    st.info("Маршруты рассчитаны, но данные пустые")
                            
                            # Выгрузка данных
                            st.markdown("---")
                            st.subheader("💾 Выгрузка данных")

                            
                            # Теперь 3 колонки: фильтр, все данные, EasyMerch Excel
                            col1, col2, col3 = st.columns(3)
                            
                            with col1:
                                # Выгрузка отфильтрованных данных в Excel
                                if filtered_df is not None and not filtered_df.empty:
                                    try:
                                        excel_buffer = io.BytesIO()
                                        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                                            filtered_df.to_excel(writer, sheet_name='План_посещений', index=False)
                                        
                                        excel_data = excel_buffer.getvalue()
                                        st.download_button(
                                            label="📥 Скачать Excel (фильтр)",
                                            data=excel_data,
                                            file_name=f"план_посещений_{year}_Q{quarter}_фильтр.xlsx",
                                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                            use_container_width=True,
                                            help="Только отфильтрованные данные"
                                        )
                                    except Exception as e:
                                        st.error(f"❌ Ошибка Excel: {str(e)}")
                                else:
                                    st.info("Нет данных")
                                    st.download_button(
                                        label="📥 Скачать Excel (фильтр)",
                                        data=b"",
                                        file_name="план_посещений.xlsx",
                                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                        use_container_width=True,
                                        disabled=True
                                    )
                            
                            with col2:
                                # Выгрузка всех данных в Excel
                                if summary_df is not None and not summary_df.empty:
                                    try:
                                        excel_buffer = io.BytesIO()
                                        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                                            summary_df.to_excel(writer, sheet_name='План_посещений', index=False)
                                        
                                        excel_data = excel_buffer.getvalue()
                                        st.download_button(
                                            label="📥 Скачать Excel (все данные)",
                                            data=excel_data,
                                            file_name=f"план_посещений_{year}_Q{quarter}_все.xlsx",
                                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                            use_container_width=True,
                                            help="Все данные плана посещений"
                                        )
                                    except Exception as e:
                                        st.error(f"❌ Ошибка Excel: {str(e)}")
                                else:
                                    st.info("Нет данных")
                                    st.download_button(
                                        label="📥 Скачать Excel (все данные)",
                                        data=b"",
                                        file_name="план_посещений.xlsx",
                                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                        use_container_width=True,
                                        disabled=True
                                    )
                            
                            with col3:
                                # Выгрузка для EasyMerch в Excel
                                if 'routes_df' in st.session_state and st.session_state.routes_df is not None:
                                    routes_df = st.session_state.routes_df
                                    
                                    if routes_df is not None and not routes_df.empty:
                                        with st.spinner("🔄 Подготовка Excel файла..."):
                                            try:
                                                # Создаем Excel файл
                                                excel_data = create_easymerch_excel(routes_df)
                                                
                                                if excel_data:
                                                    st.download_button(
                                                        label="📊 EasyMerch (Excel)",
                                                        data=excel_data,
                                                        file_name=f"easymerch_маршруты_{year}_Q{quarter}.xlsx",
                                                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                                        use_container_width=True,
                                                        help="Полный отчет для EasyMerch с инструкцией и статистикой"
                                                    )
                                                    
                                                    # Информация о файле
                                                    st.caption(f"📁 {len(routes_df)} записей, {routes_df['Login пользователя'].nunique()} аудиторов")
                                                else:
                                                    st.error("❌ Не удалось создать файл")
                                                    
                                            except Exception as e:
                                                st.error(f"❌ Ошибка создания Excel: {str(e)}")
                                    else:
                                        st.info("Маршруты не рассчитаны")
                                        st.download_button(
                                            label="📊 EasyMerch (Excel)",
                                            data=b"",
                                            file_name="маршруты.xlsx",
                                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                            use_container_width=True,
                                            disabled=True,
                                            help="Сначала рассчитайте маршруты"
                                        )
                                else:
                                    st.info("Маршруты не рассчитаны")
                                    st.download_button(
                                        label="📊 EasyMerch (Excel)",
                                        data=b"",
                                        file_name="маршруты.xlsx",
                                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                        use_container_width=True,
                                        disabled=True,
                                        help="Сначала рассчитайте маршруты"
                                    )
                            
                            # Информация о формате EasyMerch Excel
                            st.markdown("---")
                            with st.expander("📋 Формат EasyMerch Excel", expanded=False):
                                st.markdown("""
                                **Excel файл содержит 4 листа:**
                                
                                ### 📄 **1. Маршруты**
                                Основные данные в формате EasyMerch для импорта:
                                - Address | L1 Name | ЧИСЛО визитов в НЕДЕЛЮ | Login пользователя
                                - Пн | Вт | Ср | Чт | Пт | Сб | Вс
                                - Цикл посещения | Дата начала цикла посещения
                                
                                ### 📖 **2. Инструкция**
                                Подробное описание всех полей с примерами заполнения
                                
                                ### 📊 **3. Сводка**
                                Статистика по всему плану визитов
                                
                                ### 👥 **4. Аудиторы**
                                Распределение нагрузки по сотрудникам
                                
                                ---
                                **🔥 Особенности:**
                                - Автоподбор ширины колонок
                                - Готов к печати
                                - Сохраняет форматирование
                                - Поддерживает русские названия колонок
                                """)
        
        # ВКЛАДКА 3: Диаграммы
        if "📈 Диаграммы" in available_tabs:
            with results_tabs[current_tab]:
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
                
                # 2. Статистика по типам точек
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
            current_tab += 1
        
            # ВКЛАДКА 4: Выгрузка данных
            if available_tabs and "📤 Выгрузка данных" in available_tabs:
                with results_tabs[current_tab]:
                    st.subheader("📤 Выгрузка данных для карт и отчетов")
                    
                    st.info("""
                    **Выберите формат выгрузки:**  
                    🔹 **Excel для Google Карт** - данные с координатами для импорта  
                    🔹 **KML для Google Earth** - географические данные с полигонами  
                    🔹 **Полный отчет Excel** - все данные для анализа  
                    """)
                    
                    st.markdown("---")
                    
                    # КОЛОНКА 1: Excel для Google Карт
                    with st.container():
                        st.markdown("### 📊 Excel для Google Карт")
                        st.caption("Формат для импорта в Google Карты / My Maps")
                        
                        col1, col2 = st.columns([2, 1])
                        with col1:
                            st.markdown("""
                            **Что включено:**
                            - Все точки с координатами
                            - Полигоны с центроидами
                            - Описания и метаданные
                            - Готовые столбцы для импорта
                            """)
                        
                        with col2:
                            if st.button("📥 Скачать Excel", key="download_excel_google", use_container_width=True):
                                with st.spinner("🔄 Создание Excel файла для Google Карт..."):
                                    try:
                                        if 'polygons' not in st.session_state or not st.session_state.polygons:
                                            st.error("❌ Нет данных полигонов")
                                        else:
                                            excel_buffer = create_google_maps_excel(
                                                st.session_state.points_df,
                                                st.session_state.polygons,
                                                st.session_state.get('points_assignment_df')  # Передаем assignment_df
                                            )
                                            
                                            # Сразу показываем кнопку скачивания
                                            st.download_button(
                                                label="📊 Нажмите, чтобы скачать Excel для Google Карт",
                                                data=excel_buffer,
                                                file_name=f"google_maps_export_{year}_Q{quarter}.xlsx",
                                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                                use_container_width=True,
                                                key=f"google_excel_{year}_{quarter}_{datetime.now().timestamp()}"
                                            )
                                            st.success("✅ Excel файл создан! Нажмите кнопку выше для скачивания")
                                    except Exception as e:
                                        st.error(f"❌ Ошибка создания Excel: {str(e)}")
                    
                    # КОЛОНКА 2: KML для Google Earth
                    with st.container():
                        st.markdown("### 🗺️ KML для Google Earth")
                        st.caption("Географический формат для GIS-систем")
                        
                        col1, col2 = st.columns([2, 1])
                        with col1:
                            st.markdown("""
                            **Что включено:**
                            - Полигоны как замкнутые контуры
                            - Точки с метками
                            - Иерархия по городам/аудиторам
                            - Поддерживается в Google Earth, QGIS
                            """)
                        
                        with col2:
                            if st.button("📥 Скачать KML", key="download_kml", use_container_width=True):
                                with st.spinner("🔄 Создание KML файла для Google Earth..."):
                                    try:
                                        if 'polygons' not in st.session_state or not st.session_state.polygons:
                                            st.error("❌ Нет данных полигонов")
                                        else:
                                            kml_content = create_kml_file(
                                                st.session_state.points_df,
                                                st.session_state.polygons
                                            )
                                            
                                            # Сразу показываем кнопку скачивания
                                            st.download_button(
                                                label="🗺️ Нажмите, чтобы скачать KML для Google Earth",
                                                data=kml_content.encode('utf-8'),
                                                file_name=f"polygons_{year}_Q{quarter}.kml",
                                                mime="application/vnd.google-earth.kml+xml",
                                                use_container_width=True,
                                                key=f"kml_{year}_{quarter}_{datetime.now().timestamp()}"
                                            )
                                            st.success("✅ KML файл создан! Нажмите кнопку выше для скачивания")
                                    except Exception as e:
                                        st.error(f"❌ Ошибка создания KML: {str(e)}")
                    
                    # КОЛОНКА 3: Полный отчет Excel
                    with st.container():
                        st.markdown("### 📋 Полный отчет Excel")
                        st.caption("Все данные приложения в одном файле")
                        
                        col1, col2 = st.columns([2, 1])
                        with col1:
                            st.markdown("""
                            **Что включено:**
                            - Статистика по городам
                            - План посещений по неделям
                            - Распределение по аудиторам
                            - Данные по точкам
                            - Полигоны и координаты
                            """)
                        
                        with col2:
                            if st.button("📥 Скачать полный отчет", key="download_full_report", use_container_width=True):
                                with st.spinner("🔄 Создание полного отчета Excel..."):
                                    try:
                                        full_excel = create_full_excel_report(
                                            st.session_state.points_df,
                                            st.session_state.auditors_df,
                                            st.session_state.city_stats_df,
                                            st.session_state.type_stats_df,
                                            st.session_state.summary_df,
                                            st.session_state.polygons
                                        )
                                        
                                        # Сразу показываем кнопку скачивания
                                        st.download_button(
                                            label="📋 Нажмите, чтобы скачать полный отчет Excel",
                                            data=full_excel,
                                            file_name=f"full_report_{year}_Q{quarter}.xlsx",
                                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                            use_container_width=True,
                                            key=f"full_report_{year}_{quarter}_{datetime.now().timestamp()}"
                                        )
                                        st.success("✅ Полный отчет создан! Нажмите кнопку выше для скачивания")
                                    except Exception as e:
                                        st.error(f"❌ Ошибка создания отчета: {str(e)}")
                            
                            
        # === ИНСТРУКЦИИ ===
        st.markdown("---")
        with st.expander("📋 Инструкции по импорту", expanded=False):
            tab1, tab2, tab3 = st.tabs(["Google Карты", "Google Earth", "Excel"])
            
            with tab1:
                st.markdown("""
                **Импорт в Google Карты:**
                1. Откройте [Google My Maps](https://www.google.com/maps/d/)
                2. Создайте новую карту → "Импорт"
                3. Выберите скачанный Excel файл
                4. Укажите столбцы:
                   - **Широта** → Latitude
                   - **Долгота** → Longitude  
                   - **Название** → Name
                   - **Описание** → Description
                5. Нажмите "Импортировать"
                """)
            
            with tab2:
                st.markdown("""
                **Импорт в Google Earth:**
                1. Откройте Google Earth Pro
                2. Файл → Открыть
                3. Выберите KML файл
                4. Данные появятся в панели "Мои места"
                5. Щелкните по объектам для просмотра информации
                """)
            
            with tab3:
                st.markdown("""
                **Использование Excel отчета:**
                - **Лист 1:** Точки с координатами
                - **Лист 2:** Статистика по городам
                - **Лист 3:** План посещений
                - **Лист 4:** Полигоны и аудиторы
                - **Лист 5:** Сводная таблица
                """)
        
        # === АЛЬТЕРНАТИВА КАРТЕ ===
        st.markdown("---")
        with st.expander("📍 Быстрый просмотр данных (без карты)", expanded=False):
            if st.session_state.polygons:
                # Показываем таблицу с полигонами
                poly_data = []
                for poly_name, poly_info in st.session_state.polygons.items():
                    poly_data.append({
                        'Полигон': poly_name,
                        'Аудитор': poly_info.get('auditor', 'Неизвестно'),
                        'Город': poly_info.get('city', 'Неизвестно'),
                        'Точек': len(poly_info.get('points', [])),
                        'Центроид': f"{poly_info.get('center_lat', 'N/A'):.4f}, {poly_info.get('center_lon', 'N/A'):.4f}" 
                        if 'center_lat' in poly_info else "N/A"
                    })
                
                if poly_data:
                    df_poly = pd.DataFrame(poly_data)
                    st.dataframe(df_poly, use_container_width=True, hide_index=True)
                    
                    # Кнопка для скачивания этой таблицы
                    csv = df_poly.to_csv(index=False, sep=';').encode('utf-8')
                    st.download_button(
                        label="📋 Скачать список полигонов (CSV)",
                        data=csv,
                        file_name=f"polygons_list_{year}_Q{quarter}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
            else:
                st.info("Нет данных о полигонах")
        
        # Информация о данных
        st.markdown("---")
        st.caption(f"📊 Данные: {len(st.session_state.points_df) if st.session_state.points_df is not None else 0} точек, "
                  f"{len(st.session_state.polygons) if st.session_state.polygons else 0} полигонов, "
                  f"{len(st.session_state.auditors_df) if st.session_state.auditors_df is not None else 0} аудиторов")
    current_tab += 1









