import streamlit as st
import pandas as pd
import numpy as np
import io
from datetime import datetime, date, timedelta
import calendar
import json
from typing import Dict, List, Tuple, Optional
import base64

# Настройка страницы
st.set_page_config(
    page_title="Калькулятор плана визитов",
    page_icon="📊",
    layout="wide"
)

st.title("📊 Калькулятор плана визитов по сотрудникам")
st.markdown("---")

# Создаем боковую панель для настроек
with st.sidebar:
    st.header("⚙️ Настройки")
    
    # Выбор квартала и года
    col1, col2 = st.columns(2)
    with col1:
        quarter = st.selectbox("Квартал", [1, 2, 3, 4], index=0)
    with col2:
        year = st.selectbox("Год", list(range(2023, 2027)), index=2)
    
    # Настройки коэффициентов по этапам
    st.subheader("Коэффициенты нагрузки по этапам")
    st.caption("Весь квартал делится на 4 равных этапа")
    
    stage1 = st.number_input("Этап 1 коэффициент", value=0.8, min_value=0.1, max_value=2.0, step=0.1)
    stage2 = st.number_input("Этап 2 коэффициент", value=1.0, min_value=0.1, max_value=2.0, step=0.1)
    stage3 = st.number_input("Этап 3 коэффициент", value=1.2, min_value=0.1, max_value=2.0, step=0.1)
    stage4 = st.number_input("Этап 4 коэффициент", value=0.9, min_value=0.1, max_value=2.0, step=0.1)
    
    coefficients = [stage1, stage2, stage3, stage4]
    
    # Настройка максимального количества посещений на неделю
    max_visits_per_week = st.number_input(
        "Максимум посещений в неделю на сотрудника", 
        value=50, 
        min_value=1, 
        max_value=200, 
        step=1
    )
    
    st.markdown("---")
    st.info("""
    **Инструкция:**
    1. Скачайте шаблоны файлов
    2. Заполните их данными
    3. Загрузите заполненные файлы
    4. Нажмите кнопку "Рассчитать"
    
    **Важно:** План визитов рассчитывается автоматически 
    как сумма посещений всех точек по городам.
    """)

# Функции для создания шаблонов
def create_auditors_template():
    """Создает шаблон для аудиторов"""
    template = pd.DataFrame(columns=['ID_Сотрудника', 'Город'])
    
    example_data = {
        'ID_Сотрудника': ['SOVIAUD13', 'SOVIAUD14', 'SOVIAUD15'],
        'Город': ['Москва', 'Москва', 'Москва']
    }
    
    template = pd.DataFrame(example_data)
    return template

def create_points_template():
    """Создает шаблон для точек с колонкой количества посещений"""
    template = pd.DataFrame(columns=[
        'ID_Точки', 
        'Название_Точки', 
        'Адрес', 
        'Широта', 
        'Долгота',
        'Город',
        'Тип',
        'Кол-во_посещений'  # Новая колонка
    ])
    
    example_data = {
        'ID_Точки': ['P001', 'P002', 'P003', 'P004'],
        'Название_Точки': ['Магазин 1', 'Гипермаркет 1', 'Супермаркет 1', 'Минимаркет 2'],
        'Адрес': ['ул. Ленина, 1', 'ул. Мира, 10', 'пр. Победы, 5', 'ул. Центральная, 3'],
        'Широта': [55.7558, 55.7507, 55.7601, 55.7520],
        'Долгота': [37.6173, 37.6177, 37.6254, 37.6200],
        'Город': ['Москва', 'Москва', 'Москва', 'Москва'],
        'Тип': ['Мини', 'Гипер', 'Супер', 'Мини'],  # Convenience->Мини, Hypermarket->Гипер, Supermarket->Супер
        'Кол-во_посещений': [1, 1, 1, 2]  # Может быть больше 1
    }
    
    template = pd.DataFrame(example_data)
    return template

# Функция для скачивания файлов
def get_download_link(df, filename, text):
    """Генерирует ссылку для скачивания DataFrame"""
    towrite = io.BytesIO()
    if filename.endswith('.xlsx'):
        df.to_excel(towrite, index=False)
        mime_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    elif filename.endswith('.json'):
        towrite.write(json.dumps(df, ensure_ascii=False, indent=2).encode('utf-8'))
        mime_type = 'application/json'
    else:
        df.to_csv(towrite, index=False, encoding='utf-8')
        mime_type = 'text/csv'
    
    towrite.seek(0)
    b64 = base64.b64encode(towrite.read()).decode()
    href = f'<a href="data:{mime_type};base64,{b64}" download="{filename}">{text}</a>'
    return href

# Функции для обработки загруженных данных
def process_uploaded_points(df):
    """Обрабатывает загруженный файл точек"""
    df = df.copy()
    
    # Проверяем и переименовываем колонки, если нужно
    column_mapping = {
        'ID точки': 'ID_Точки',
        'Название точки': 'Название_Точки',
        'Latitude': 'Широта',
        'Longitude': 'Долгота',
        'City': 'Город',
        'Type': 'Тип',
        'Category': 'Тип',
        'Кол-во посещений': 'Кол-во_посещений',
        'Visits': 'Кол-во_посещений',
        'Количество посещений': 'Кол-во_посещений'
    }
    
    for old_col, new_col in column_mapping.items():
        if old_col in df.columns and new_col not in df.columns:
            df = df.rename(columns={old_col: new_col})
    
    # Преобразуем типы точек из английских в русские
    if 'Тип' in df.columns:
        type_mapping = {
            'Convenience': 'Мини',
            'convenience': 'Мини',
            'Convenience Store': 'Мини',
            'Hypermarket': 'Гипер',
            'hypermarket': 'Гипер',
            'Supermarket': 'Супер',
            'supermarket': 'Супер',
            'Мини': 'Мини',
            'Гипер': 'Гипер',
            'Супер': 'Супер'
        }
        
        df['Тип'] = df['Тип'].map(type_mapping).fillna('Мини')
    
    # Убедимся, что количество посещений - целое число
    if 'Кол-во_посещений' in df.columns:
        df['Кол-во_посещений'] = pd.to_numeric(df['Кол-во_посещений'], errors='coerce').fillna(1).astype(int)
    else:
        df['Кол-во_посещений'] = 1  # По умолчанию 1 посещение
    
    # Проверяем наличие всех необходимых колонок
    required_cols = ['ID_Точки', 'Название_Точки', 'Адрес', 'Широта', 'Долгота', 'Город', 'Тип', 'Кол-во_посещений']
    
    # Создаем недостающие колонки, если нужно
    for col in required_cols:
        if col not in df.columns:
            if col == 'Адрес' and 'Address' in df.columns:
                df['Адрес'] = df['Address']
            elif col == 'Широта' and 'Lat' in df.columns:
                df['Широта'] = df['Lat']
            elif col == 'Долгота' and 'Lon' in df.columns:
                df['Долгота'] = df['Lon']
            elif col == 'Название_Точки' and 'Название' in df.columns:
                df['Название_Точки'] = df['Название']
            elif col == 'Кол-во_посещений':
                df['Кол-во_посещений'] = 1
            else:
                df[col] = ''
    
    return df[required_cols]

def process_uploaded_auditors(df):
    """Обрабатывает загруженный файл аудиторов"""
    df = df.copy()
    
    # Проверяем и переименовываем колонки
    column_mapping = {
        'ID Сотрудника': 'ID_Сотрудника',
        'Employee ID': 'ID_Сотрудника',
        'City': 'Город'
    }
    
    for old_col, new_col in column_mapping.items():
        if old_col in df.columns and new_col not in df.columns:
            df = df.rename(columns={old_col: new_col})
    
    # Проверяем наличие необходимых колонок
    required_cols = ['ID_Сотрудника', 'Город']
    
    for col in required_cols:
        if col not in df.columns:
            if col == 'Город' and 'City' in df.columns:
                df['Город'] = df['City']
            else:
                df[col] = ''
    
    return df[required_cols]

# Функция для получения дат квартала
def get_quarter_dates(year, quarter):
    """Возвращает даты начала и конца квартала"""
    quarter_starts = [date(year, 1, 1), date(year, 4, 1), date(year, 7, 1), date(year, 10, 1)]
    quarter_start = quarter_starts[quarter - 1]
    
    if quarter == 4:
        quarter_end = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        quarter_end = quarter_starts[quarter] - timedelta(days=1)
    
    return quarter_start, quarter_end

def get_weeks_in_quarter(year, quarter):
    """Возвращает список недель в квартале с датами"""
    quarter_start, quarter_end = get_quarter_dates(year, quarter)
    
    weeks = []
    current_date = quarter_start
    week_num = 1
    
    while current_date <= quarter_end:
        week_start = current_date
        week_end = min(current_date + timedelta(days=6), quarter_end)
        
        # Считаем рабочие дни в этой неделе для квартала
        work_days = 0
        temp_date = week_start
        while temp_date <= week_end:
            if temp_date.weekday() < 5:  # Пн-Пт
                work_days += 1
            temp_date += timedelta(days=1)
        
        weeks.append({
            'week_number': week_num,
            'start_date': week_start,
            'end_date': week_end,
            'work_days_in_quarter': work_days,
            'is_full_week': work_days == 5
        })
        
        current_date = week_end + timedelta(days=1)
        week_num += 1
    
    return weeks

# Функция для проверки соответствия городов
def check_city_compatibility(auditors_df, points_df):
    """Проверяет соответствие городов между файлами аудиторов и точек"""
    auditors_cities = set(auditors_df['Город'].unique())
    points_cities = set(points_df['Город'].unique())
    
    warnings = []
    
    # Города с аудиторами, но без точек
    cities_with_auditors_no_points = auditors_cities - points_cities
    if cities_with_auditors_no_points:
        warnings.append(f"⚠️ Аудиторы городов {', '.join(cities_with_auditors_no_points)} не имеют точек для посещения")
    
    # Города с точками, но без аудиторов
    cities_with_points_no_auditors = points_cities - auditors_cities
    if cities_with_points_no_auditors:
        warnings.append(f"⚠️ В городах {', '.join(cities_with_points_no_auditors)} нет аудиторов для посещения точек")
    
    # Города, которые есть в обоих файлах
    common_cities = auditors_cities & points_cities
    if common_cities:
        warnings.append(f"✅ Общие города с аудиторами и точками: {', '.join(common_cities)}")
    
    return warnings, common_cities

# Функция для генерации полигонов
def generate_polygons(points_df, auditors_df):
    """Генерирует полигоны для каждого аудитора на основе распределения точек"""
    
    polygons_data = []
    polygons_json = {
        "type": "FeatureCollection",
        "features": []
    }
    
    for city in points_df['Город'].unique():
        city_points = points_df[points_df['Город'] == city]
        
        # Получаем аудиторов для города
        city_auditors = auditors_df[auditors_df['Город'] == city]['ID_Сотрудника'].tolist()
        
        if len(city_auditors) == 0:
            continue
        
        # Если один аудитор - весь город его полигон
        if len(city_auditors) == 1:
            auditor = city_auditors[0]
            
            # Создаем прямоугольный полигон вокруг всех точек города
            min_lat = city_points['Широта'].min()
            max_lat = city_points['Широта'].max()
            min_lon = city_points['Долгота'].min()
            max_lon = city_points['Долгота'].max()
            
            # Генерируем 6 точек полигона
            polygon_points = [
                [min_lon, min_lat],
                [min_lon + (max_lon - min_lon) * 0.3, min_lat],
                [max_lon, min_lat],
                [max_lon, max_lat],
                [min_lon + (max_lon - min_lon) * 0.7, max_lat],
                [min_lon, max_lat]
            ]
            
            polygon_name = f"{city}"
            
            polygons_data.append({
                'Полигон': polygon_name,
                'Аудитор': auditor,
                'Город': city,
                'Тип': 'Весь город',
                'Координаты': '; '.join([f"{lon:.6f},{lat:.6f}" for lon, lat in polygon_points])
            })
            
            # Добавляем в GeoJSON
            polygons_json["features"].append({
                "type": "Feature",
                "properties": {
                    "name": polygon_name,
                    "auditor": auditor,
                    "city": city,
                    "type": "full_city"
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [polygon_points]
                }
            })
        
        else:
            # Для нескольких аудиторов делим город на сектора
            center_lat = city_points['Широта'].mean()
            center_lon = city_points['Долгота'].mean()
            
            # Радиус полигона
            lat_range = city_points['Широта'].max() - city_points['Широта'].min()
            lon_range = city_points['Долгота'].max() - city_points['Долгота'].min()
            radius = max(lat_range, lon_range) * 0.6
            
            # Создаем сектора для каждого аудитора
            for i, auditor in enumerate(city_auditors):
                # Вычисляем углы для сектора
                angle_start = (i * 360) / len(city_auditors)
                angle_end = ((i + 1) * 360) / len(city_auditors)
                
                # Генерируем точки полигона (6 точек)
                polygon_points = [[center_lon, center_lat]]  # Центральная точка
                
                for j in range(5):
                    angle = angle_start + (angle_end - angle_start) * (j / 4)
                    rad = np.radians(angle)
                    
                    lat = center_lat + radius * np.cos(rad)
                    lon = center_lon + radius * np.sin(rad)
                    
                    polygon_points.append([lon, lat])
                
                # Закрываем полигон
                polygon_points.append(polygon_points[0])
                
                # Определяем направление
                directions = ['Север', 'Северо-Восток', 'Восток', 'Юго-Восток', 
                            'Юг', 'Юго-Запад', 'Запад', 'Северо-Запад']
                direction_idx = int((angle_start + angle_end) / 2 / 45) % 8
                
                polygon_name = f"{city} - {directions[direction_idx]}"
                
                polygons_data.append({
                    'Полигон': polygon_name,
                    'Аудитор': auditor,
                    'Город': city,
                    'Тип': 'Сектор',
                    'Координаты': '; '.join([f"{lon:.6f},{lat:.6f}" for lon, lat in polygon_points])
                })
                
                # Добавляем в GeoJSON
                polygons_json["features"].append({
                    "type": "Feature",
                    "properties": {
                        "name": polygon_name,
                        "auditor": auditor,
                        "city": city,
                        "type": "sector",
                        "direction": directions[direction_idx]
                    },
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [polygon_points]
                    }
                })
    
    return pd.DataFrame(polygons_data), polygons_json

# Функция для распределения точек по полигонам
def distribute_points_by_polygons(points_df, polygons_df):
    """Распределяет точки по полигонам и аудиторам"""
    
    distribution = {}
    points_with_polygon = []
    
    for _, polygon_row in polygons_df.iterrows():
        auditor = polygon_row['Аудитор']
        city = polygon_row['Город']
        polygon_name = polygon_row['Полигон']
        
        # Получаем координаты полигона
        coords_str = polygon_row['Координаты']
        polygon_coords = []
        for coord in coords_str.split(';'):
            if coord.strip():
                lon, lat = map(float, coord.strip().split(','))
                polygon_coords.append([lon, lat])
        
        # Получаем точки города
        city_points = points_df[points_df['Город'] == city].copy()
        
        if len(city_points) == 0:
            continue
        
        # Простая логика распределения: берем каждую n-ю точку для этого аудитора
        city_auditors = polygons_df[polygons_df['Город'] == city]['Аудитор'].unique()
        auditor_index = list(city_auditors).index(auditor)
        
        # Разбиваем точки на группы для каждого аудитора
        points_per_auditor = len(city_points) // len(city_auditors)
        remainder = len(city_points) % len(city_auditors)
        
        start_idx = sum([points_per_auditor + (1 if i < remainder else 0) 
                        for i in range(auditor_index)])
        end_idx = start_idx + points_per_auditor + (1 if auditor_index < remainder else 0)
        
        auditor_points = city_points.iloc[start_idx:end_idx].copy()
        
        # Сортируем по типам (сначала гипер, потом супер, потом мини)
        type_order = {'Гипер': 0, 'Супер': 1, 'Мини': 2}
        auditor_points['type_order'] = auditor_points['Тип'].map(type_order)
        auditor_points = auditor_points.sort_values('type_order').drop('type_order', axis=1)
        
        # Сохраняем распределение
        if auditor not in distribution:
            distribution[auditor] = []
        
        points_list = auditor_points.to_dict('records')
        distribution[auditor].extend(points_list)
        
        # Добавляем информацию о полигоне к каждой точке
        for point in points_list:
            points_with_polygon.append({
                **point,
                'Аудитор': auditor,
                'Полигон': polygon_name
            })
    
    return distribution, pd.DataFrame(points_with_polygon)

# Функция для расчета плана посещений
def calculate_visits_plan(auditors_df, points_df, year, quarter, coefficients, max_visits_per_week):
    """Основная функция расчета плана посещений"""
    
    # Получаем недели квартала
    weeks = get_weeks_in_quarter(year, quarter)
    
    # Генерируем полигоны
    polygons_df, polygons_json = generate_polygons(points_df, auditors_df)
    
    # Распределяем точки по полигонам и аудиторам
    points_distribution, points_with_polygons = distribute_points_by_polygons(points_df, polygons_df)
    
    # Создаем структуры для хранения результатов
    results = []
    detailed_results = []
    weekly_assignments = {}
    city_statistics = []
    
    # Сначала собираем статистику по городам
    for city in points_df['Город'].unique():
        city_points = points_df[points_df['Город'] == city]
        total_visits = city_points['Кол-во_посещений'].sum()
        
        # Статистика по типам точек в городе
        type_stats = city_points.groupby('Тип').agg({
            'ID_Точки': 'count',
            'Кол-во_посещений': 'sum'
        }).reset_index()
        
        city_statistics.append({
            'Город': city,
            'Всего_точек': len(city_points),
            'Всего_посещений': total_visits,
            'Гипер': type_stats[type_stats['Тип'] == 'Гипер']['Кол-во_посещений'].sum() if 'Гипер' in type_stats['Тип'].values else 0,
            'Супер': type_stats[type_stats['Тип'] == 'Супер']['Кол-во_посещений'].sum() if 'Супер' in type_stats['Тип'].values else 0,
            'Мини': type_stats[type_stats['Тип'] == 'Мини']['Кол-во_посещений'].sum() if 'Мини' in type_stats['Тип'].values else 0,
        })
    
    # Для каждого сотрудника
    for auditor in auditors_df['ID_Сотрудника'].unique():
        city = auditors_df[auditors_df['ID_Сотрудника'] == auditor]['Город'].iloc[0]
        
        # Получаем точки сотрудника
        auditor_points = points_distribution.get(auditor, [])
        
        if not auditor_points:
            continue
        
        # Считаем общее количество посещений для этого аудитора
        total_visits = sum(point.get('Кол-во_посещений', 1) for point in auditor_points)
        weeks_count = len(weeks)
        
        # Распределяем посещения по неделям с учетом коэффициентов
        # Сначала создаем список всех посещений (если точка требует 4 посещений, добавляем ее 4 раза)
        all_visits_list = []
        for point in auditor_points:
            visits_count = point.get('Кол-во_посещений', 1)
            for _ in range(visits_count):
                all_visits_list.append(point.copy())
        
        total_visits_actual = len(all_visits_list)
        
        # Распределяем посещения по неделям
        visit_idx = 0
        
        for week in weeks:
            week_visits_count = 0
            week_visits_list = []
            
            # Определяем коэффициент для этой недели
            week_num = week['week_number']
            work_days = week['work_days_in_quarter']
            
            # Определяем этап (1-4)
            stage_idx = min(3, (week_num - 1) // (weeks_count // 4))
            
            # Базовое количество посещений для недели
            base_visits = total_visits_actual / weeks_count
            
            # Применяем коэффициенты
            adjusted_visits = base_visits * coefficients[stage_idx]
            
            # Корректируем на рабочие дни
            if work_days > 0:
                week_target = int(adjusted_visits * (work_days / 5))
            else:
                week_target = 0
            
            # Ограничиваем максимумом
            week_target = min(week_target, max_visits_per_week)
            
            # Убедимся, что week_target хотя бы 1, если есть посещения
            if week_target == 0 and total_visits_actual > 0 and work_days > 0:
                week_target = 1
            
            # Берем посещения для этой недели
            while week_visits_count < week_target and visit_idx < total_visits_actual:
                week_visits_list.append(all_visits_list[visit_idx])
                week_visits_count += 1
                visit_idx += 1
            
            if week_visits_count > 0:
                # Сохраняем результаты
                results.append({
                    'Сотрудник': auditor,
                    'Город': city,
                    'Неделя': week_num,
                    'Начало_недели': week['start_date'].strftime('%d.%m.%Y'),
                    'Конец_недели': week['end_date'].strftime('%d.%m.%Y'),
                    'Рабочих_дней': work_days,
                    'План_посещений': week_visits_count,
                    'Этап': stage_idx + 1,
                    'Коэффициент': coefficients[stage_idx]
                })
                
                # Детализация по посещениям
                for visit in week_visits_list:
                    detailed_results.append({
                        'Сотрудник': auditor,
                        'Город': city,
                        'Неделя': week_num,
                        'ID_Точки': visit.get('ID_Точки', ''),
                        'Название_Точки': visit.get('Название_Точки', ''),
                        'Адрес': visit.get('Адрес', ''),
                        'Тип_точки': visit.get('Тип', ''),
                        'Широта': visit.get('Широта', ''),
                        'Долгота': visit.get('Долгота', ''),
                        'Полигон': visit.get('Полигон', ''),
                        'Номер_посещения': f"{visit_idx - week_visits_count + 1}/{total_visits_actual}"
                    })
                
                # Сохраняем для группировки
                if auditor not in weekly_assignments:
                    weekly_assignments[auditor] = {}
                
                weekly_assignments[auditor][week_num] = week_visits_list
        
        # Если остались непосещенные точки, распределяем их по оставшимся неделям
        remaining_visits = total_visits_actual - visit_idx
        if remaining_visits > 0:
            # Распределяем по оставшимся неделям равномерно
            remaining_weeks = [w for w in weeks if w['week_number'] > week_num]
            if remaining_weeks:
                visits_per_week = max(1, remaining_visits // len(remaining_weeks))
                
                for week in remaining_weeks:
                    week_visits_count = 0
                    week_visits_list = []
                    
                    week_target = min(visits_per_week, max_visits_per_week)
                    
                    while week_visits_count < week_target and visit_idx < total_visits_actual:
                        week_visits_list.append(all_visits_list[visit_idx])
                        week_visits_count += 1
                        visit_idx += 1
                    
                    if week_visits_count > 0:
                        results.append({
                            'Сотрудник': auditor,
                            'Город': city,
                            'Неделя': week['week_number'],
                            'Начало_недели': week['start_date'].strftime('%d.%m.%Y'),
                            'Конец_недели': week['end_date'].strftime('%d.%m.%Y'),
                            'Рабочих_дней': week['work_days_in_quarter'],
                            'План_посещений': week_visits_count,
                            'Этап': min(3, (week['week_number'] - 1) // (weeks_count // 4)) + 1,
                            'Коэффициент': coefficients[min(3, (week['week_number'] - 1) // (weeks_count // 4))]
                        })
    
    return (
        pd.DataFrame(results) if results else pd.DataFrame(columns=['Сотрудник', 'Город', 'Неделя', 'Начало_недели', 'Конец_недели', 'Рабочих_дней', 'План_посещений', 'Этап', 'Коэффициент']),
        pd.DataFrame(detailed_results) if detailed_results else pd.DataFrame(columns=['Сотрудник', 'Город', 'Неделя', 'ID_Точки', 'Название_Точки', 'Адрес', 'Тип_точки', 'Широта', 'Долгота', 'Полигон', 'Номер_посещения']),
        polygons_df,
        polygons_json,
        weekly_assignments,
        pd.DataFrame(city_statistics)
    )

# Отображение шаблонов для скачивания
st.header("📄 Шаблоны файлов")

col1, col2 = st.columns(2)

with col1:
    st.subheader("Аудиторы")
    auditors_template = create_auditors_template()
    st.markdown(get_download_link(auditors_template, "шаблон_аудиторы.xlsx", "📥 Скачать шаблон"), unsafe_allow_html=True)
    st.dataframe(auditors_template.head(3), use_container_width=True)

with col2:
    st.subheader("Точки")
    points_template = create_points_template()
    st.markdown(get_download_link(points_template, "шаблон_точки.xlsx", "📥 Скачать шаблон"), unsafe_allow_html=True)
    st.dataframe(points_template.head(3), use_container_width=True)

st.markdown("---")

# Загрузка файлов
st.header("📤 Загрузка файлов")

uploaded_auditors = st.file_uploader("Загрузите файл аудиторов", type=['xlsx', 'xls'])
uploaded_points = st.file_uploader("Загрузите файл точек", type=['xlsx', 'xls'])

# Кнопка расчета
if st.button("🚀 Рассчитать план", type="primary", use_container_width=True):
    
    if not all([uploaded_auditors, uploaded_points]):
        st.error("⚠️ Пожалуйста, загрузите все необходимые файлы!")
        st.stop()
    
    try:
        # Загружаем данные
        auditors_df_raw = pd.read_excel(uploaded_auditors)
        points_df_raw = pd.read_excel(uploaded_points)
        
        # Обрабатываем данные
        auditors_df = process_uploaded_auditors(auditors_df_raw)
        points_df = process_uploaded_points(points_df_raw)
        
        # Проверяем необходимые колонки после обработки
        required_auditor_cols = ['ID_Сотрудника', 'Город']
        required_point_cols = ['ID_Точки', 'Название_Точки', 'Адрес', 'Широта', 'Долгота', 'Город', 'Тип', 'Кол-во_посещений']
        
        for df_name, df, required_cols in [
            ("Аудиторы", auditors_df, required_auditor_cols),
            ("Точки", points_df, required_point_cols)
        ]:
            missing_cols = [col for col in required_cols if col not in df.columns]
            if missing_cols:
                st.error(f"❌ В файле {df_name} отсутствуют колонки: {', '.join(missing_cols)}")
                st.error(f"Найденные колонки: {', '.join(df.columns)}")
                st.stop()
        
        # Проверяем соответствие городов
        warnings, common_cities = check_city_compatibility(auditors_df, points_df)
        
        for warning in warnings:
            if warning.startswith("⚠️"):
                st.warning(warning)
            else:
                st.success(warning)
        
        # Если нет общих городов, останавливаем расчет
        if not common_cities:
            st.error("❌ Нет общих городов между файлами аудиторов и точек. Расчет невозможен.")
            st.stop()
        
        # Показываем предпросмотр обработанных данных
        with st.expander("Предпросмотр обработанных данных"):
            col1, col2 = st.columns(2)
            with col1:
                st.write("Аудиторы (первые 5 строк):")
                st.dataframe(auditors_df.head(5), use_container_width=True)
                st.write(f"Всего аудиторов: {len(auditors_df)}")
                st.write(f"Города аудиторов: {', '.join(auditors_df['Город'].unique())}")
            with col2:
                st.write("Точки (первые 5 строк):")
                st.dataframe(points_df.head(5), use_container_width=True)
                st.write(f"Всего точек: {len(points_df)}")
                st.write(f"Всего посещений: {points_df['Кол-во_посещений'].sum()}")
                st.write(f"Города точек: {', '.join(points_df['Город'].unique())}")
        
        # Выполняем расчет
        with st.spinner("🔄 Идет расчет плана..."):
            summary_df, details_df, polygons_df, polygons_json, weekly_assignments, city_stats_df = calculate_visits_plan(
                auditors_df, points_df, 
                year, quarter, coefficients, max_visits_per_week
            )
        
        st.success("✅ Расчет завершен!")
        st.markdown("---")
        
        # Проверяем, есть ли результаты
        if summary_df.empty:
            st.warning("⚠️ Нет данных для отображения. Возможно, нет общих городов с точками и аудиторами.")
            st.stop()
        
        # Отображение результатов
        st.header("📈 Результаты расчета")
        
        # Создаем вкладки для разных видов отчетов
        tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
            "📊 Статистика городов", 
            "📅 Сводный план", 
            "📍 Распределение точек", 
            "🗺️ Полигоны", 
            "📈 Статистика по типам",
            "📥 Выгрузка"
        ])
        
        with tab1:
            st.subheader("📊 Статистика по городам")
            
            # Общая статистика
            total_points = len(points_df)
            total_visits = points_df['Кол-во_посещений'].sum()
            total_auditors = len(auditors_df)
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Всего городов", len(city_stats_df))
            with col2:
                st.metric("Всего точек", total_points)
            with col3:
                st.metric("Всего посещений", total_visits)
            with col4:
                st.metric("Всего аудиторов", total_auditors)
            
            # Таблица статистики по городам
            st.dataframe(
                city_stats_df,
                use_container_width=True,
                hide_index=True
            )
            
            # График распределения посещений по городам
            st.subheader("Распределение посещений по городам")
            if not city_stats_df.empty:
                chart_data = city_stats_df[['Город', 'Всего_посещений']].set_index('Город')
                st.bar_chart(chart_data)
        
        with tab2:
            # Фильтр по неделям
            if not summary_df.empty and 'Неделя' in summary_df.columns:
                col1, col2 = st.columns([1, 2])
                with col1:
                    selected_week = st.selectbox(
                        "Выберите неделю для просмотра",
                        sorted(summary_df['Неделя'].unique()),
                        key="week_filter_main"
                    )
                
                # Сводная таблица по сотрудникам
                st.subheader(f"План на неделю {selected_week}")
                week_summary = summary_df[summary_df['Неделя'] == selected_week]
                
                if not week_summary.empty:
                    display_df = week_summary[['Сотрудник', 'Город', 'План_посещений', 'Этап', 'Коэффициент']].copy()
                    display_df.columns = ['Сотрудник', 'Город', 'Кол-во посещений', 'Этап', 'Коэффициент']
                    
                    st.dataframe(
                        display_df,
                        use_container_width=True,
                        hide_index=True
                    )
                    
                    # График распределения
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Всего сотрудников", len(week_summary))
                    with col2:
                        st.metric("Всего посещений", week_summary['План_посещений'].sum())
                    with col3:
                        st.metric("Среднее на сотрудника", round(week_summary['План_посещений'].mean(), 1))
                else:
                    st.info(f"На неделю {selected_week} нет запланированных визитов")
            else:
                st.info("Нет данных для отображения плана")
        
        with tab3:
            if not details_df.empty and 'Сотрудник' in details_df.columns:
                st.subheader("Распределение точек по неделям и сотрудникам")
                
                # Выбор сотрудника
                employees = sorted(details_df['Сотрудник'].unique())
                selected_employee = st.selectbox("Выберите сотрудника", employees, key="employee_filter")
                
                if selected_employee:
                    employee_data = details_df[details_df['Сотрудник'] == selected_employee]
                    
                    # Сводная по неделям
                    weeks_summary = employee_data.groupby('Неделя').agg({
                        'ID_Точки': 'count',
                        'Тип_точки': lambda x: ', '.join([f"{val}:{list(x).count(val)}" for val in x.unique()])
                    }).reset_index()
                    
                    weeks_summary.columns = ['Неделя', 'Количество посещений', 'Распределение по типам']
                    
                    st.dataframe(
                        weeks_summary,
                        use_container_width=True,
                        hide_index=True
                    )
                    
                    # Детализация точек
                    st.subheader(f"Детализация посещений для {selected_employee}")
                    
                    selected_week_detail = st.selectbox(
                        "Выберите неделю для детализации",
                        sorted(employee_data['Неделя'].unique()),
                        key="week_detail_filter"
                    )
                    
                    week_details = employee_data[employee_data['Неделя'] == selected_week_detail]
                    
                    if not week_details.empty:
                        # Статистика по типам
                        type_counts = week_details['Тип_точки'].value_counts()
                        
                        cols = st.columns(len(type_counts) + 1)
                        for idx, (type_name, count) in enumerate(type_counts.items()):
                            with cols[idx]:
                                st.metric(type_name, count)
                        
                        with cols[-1]:
                            st.metric("Всего", len(week_details))
                        
                        # Таблица с точками
                        st.dataframe(
                            week_details[['ID_Точки', 'Название_Точки', 'Адрес', 'Тип_точки']],
                            use_container_width=True,
                            hide_index=True
                        )
                    else:
                        st.info(f"На неделю {selected_week_detail} нет посещений")
            else:
                st.info("Нет данных для отображения распределения")
        
        with tab4:
            st.subheader("🗺️ Полигоны аудиторов")
            
            if not polygons_df.empty:
                # Отображение таблицы с полигонами
                st.dataframe(
                    polygons_df[['Полигон', 'Аудитор', 'Город', 'Тип', 'Координаты']],
                    use_container_width=True,
                    hide_index=True
                )
                
                # Инструкция для загрузки в Google Карты
                st.subheader("Инструкция для Google Карты")
                st.markdown("""
                1. Скачайте файл полигонов в формате GeoJSON
                2. Перейдите на [Google Мои карты](https://www.google.com/maps/d/)
                3. Нажмите "Создать новую карту"
                4. Нажмите "Импорт" и загрузите скачанный GeoJSON файл
                5. Полигоны автоматически отобразятся на карте
                """)
                
                # Превью GeoJSON
                with st.expander("Просмотр GeoJSON структуры"):
                    st.json(polygons_json)
            else:
                st.info("Нет данных для отображения полигонов")
        
        with tab5:
            st.subheader("📈 Статистика по типам точек")
            
            if not points_df.empty:
                # Статистика по типам точек
                type_stats = points_df.groupby('Тип').agg({
                    'ID_Точки': 'count',
                    'Кол-во_посещений': 'sum'
                }).reset_index()
                
                type_stats.columns = ['Тип точки', 'Количество точек', 'Количество посещений']
                
                # Расчет процентов
                total_points_all = type_stats['Количество точек'].sum()
                total_visits_all = type_stats['Количество посещений'].sum()
                
                type_stats['% от всех точек'] = (type_stats['Количество точек'] / total_points_all * 100).round(1)
                type_stats['% от всех посещений'] = (type_stats['Количество посещений'] / total_visits_all * 100).round(1)
                
                st.dataframe(
                    type_stats,
                    use_container_width=True,
                    hide_index=True
                )
                
                # Графики
                col1, col2 = st.columns(2)
                with col1:
                    st.subheader("Распределение точек по типам")
                    chart_data = type_stats[['Тип точки', 'Количество точек']].set_index('Тип точки')
                    st.bar_chart(chart_data)
                
                with col2:
                    st.subheader("Распределение посещений по типам")
                    chart_data = type_stats[['Тип точки', 'Количество посещений']].set_index('Тип точки')
                    st.bar_chart(chart_data)
            else:
                st.info("Нет данных для статистики по типам")
        
        with tab6:
            st.header("📥 Выгрузка результатов")
            
            # Создаем Excel файл с несколькими вкладками
            with pd.ExcelWriter('результаты_плана.xlsx', engine='openpyxl') as writer:
                # Вкладка 1: Статистика городов
                if not city_stats_df.empty:
                    city_stats_df.to_excel(writer, sheet_name='Статистика_городов', index=False)
                
                # Вкладка 2: Сводная информация
                if not summary_df.empty:
                    summary_display = summary_df.copy()
                    summary_display.to_excel(writer, sheet_name='Сводная', index=False)
                
                # Вкладка 3: Детализация точек
                if not details_df.empty:
                    details_display = details_df.copy()
                    details_display.to_excel(writer, sheet_name='Детализация', index=False)
                
                # Вкладка 4: Полигоны
                if not polygons_df.empty:
                    polygons_display = polygons_df.copy()
                    polygons_display.to_excel(writer, sheet_name='Полигоны', index=False)
                
                # Вкладка 5: Статистика по типам
                if not points_df.empty:
                    type_stats_export = points_df.groupby(['Город', 'Тип']).agg({
                        'ID_Точки': 'count',
                        'Кол-во_посещений': 'sum'
                    }).reset_index()
                    type_stats_export.columns = ['Город', 'Тип точки', 'Количество точек', 'Количество посещений']
                    type_stats_export.to_excel(writer, sheet_name='Статистика_по_типам', index=False)
                
                # Вкладка 6: Группировка точек по неделям
                if weekly_assignments:
                    grouped_data = []
                    for auditor, weeks_data in weekly_assignments.items():
                        for week_num, points_list in weeks_data.items():
                            if points_list:
                                points_info = []
                                for point in points_list:
                                    point_str = f"{point.get('Название_Точки', '')} ({point.get('Тип', '')}) - {point.get('Адрес', '')}"
                                    points_info.append(point_str)
                                
                                grouped_data.append({
                                    'Сотрудник': auditor,
                                    'Город': point.get('Город', '') if points_list else '',
                                    'Неделя': week_num,
                                    'Количество посещений': len(points_list),
                                    'Перечень точек': '; '.join(points_info)
                                })
                    
                    if grouped_data:
                        grouped_df = pd.DataFrame(grouped_data)
                        grouped_df.to_excel(writer, sheet_name='Группировка', index=False)
                
                # Вкладка 7: Исходные данные
                auditors_df.to_excel(writer, sheet_name='Аудиторы_исходные', index=False)
                points_df.to_excel(writer, sheet_name='Точки_исходные', index=False)
            
            # Создаем отдельный файл GeoJSON для полигонов
            if polygons_json:
                geojson_filename = f'полигоны_квартал{quarter}_{year}.geojson'
                
                # Предлагаем скачать файлы
                col1, col2 = st.columns(2)
                
                with col1:
                    with open('результаты_плана.xlsx', 'rb') as f:
                        excel_data = f.read()
                    
                    b64_excel = base64.b64encode(excel_data).decode()
                    href_excel = f'<a href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64_excel}" download="план_визитов_квартал{quarter}_{year}.xlsx">📥 Скачать полный отчет (Excel)</a>'
                    st.markdown(href_excel, unsafe_allow_html=True)
                
                with col2:
                    # Скачивание GeoJSON
                    geojson_str = json.dumps(polygons_json, ensure_ascii=False, indent=2)
                    b64_geojson = base64.b64encode(geojson_str.encode()).decode()
                    href_geojson = f'<a href="data:application/json;base64,{b64_geojson}" download="полигоны_квартал{quarter}_{year}.geojson">🗺️ Скачать полигоны (GeoJSON)</a>'
                    st.markdown(href_geojson, unsafe_allow_html=True)
            
            # Информация о квартале
            st.markdown("---")
            st.subheader("📅 Информация о квартале")
            
            quarter_start, quarter_end = get_quarter_dates(year, quarter)
            st.info(f"""
            **Выбранный квартал:** {quarter} квартал {year} года  
            **Период:** {quarter_start.strftime('%d.%m.%Y')} - {quarter_end.strftime('%d.%m.%Y')}  
            **Всего недель в квартале:** {len(get_weeks_in_quarter(year, quarter))}  
            **Коэффициенты по этапам:** {', '.join([str(c) for c in coefficients])}
            **Максимум посещений в неделю:** {max_visits_per_week}
            """)
        
    except Exception as e:
        st.error(f"❌ Произошла ошибка при расчете: {str(e)}")
        import traceback
        st.error(f"Детали ошибки:\n{traceback.format_exc()}")
        st.stop()

# Информация в подвале
st.markdown("---")
st.caption("""
**Примечания:**
1. План визитов рассчитывается как сумма посещений всех точек по городам
2. Каждая точка может требовать от 1 до N посещений за квартал
3. При расчете учитываются только рабочие дни (понедельник-пятница)
4. Коэффициенты применяются к этапам квартала (каждый этап = 1/4 квартала)
5. Посещения распределяются целыми числами с учетом коэффициентов этапов
""")