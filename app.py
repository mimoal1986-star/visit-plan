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
    
    # Настройка максимального количества точек на неделю
    max_points_per_week = st.number_input(
        "Максимум точек в неделю на сотрудника", 
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
    """)

# Функции для создания шаблонов
def create_plan_template():
    """Создает шаблон для плана визитов"""
    template = pd.DataFrame(columns=[
        'Город', 
        'Квота_общая', 
        'Квота_Гипер', 
        'Квота_Супер', 
        'Квота_Мини'
    ])
    
    # Пример заполнения
    example_data = {
        'Город': ['Москва', 'Санкт-Петербург', 'Екатеринбург'],
        'Квота_общая': [3664, 1870, 987],
        'Квота_Гипер': [50, 54, 30],
        'Квота_Супер': [456, 158, 65],
        'Квота_Мини': [3158, 1658, 892]
    }
    
    template = pd.DataFrame(example_data)
    return template

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
    """Создает шаблон для точек"""
    template = pd.DataFrame(columns=[
        'ID_Точки', 
        'Название_Точки', 
        'Адрес', 
        'Широта', 
        'Долгота',
        'Город',
        'Тип'
    ])
    
    example_data = {
        'ID_Точки': ['P001', 'P002', 'P003'],
        'Название_Точки': ['Магазин 1', 'Гипермаркет 1', 'Супермаркет 1'],
        'Адрес': ['ул. Ленина, 1', 'ул. Мира, 10', 'пр. Победы, 5'],
        'Широта': [55.7558, 55.7507, 55.7601],
        'Долгота': [37.6173, 37.6177, 37.6254],
        'Город': ['Москва', 'Москва', 'Москва'],
        'Тип': ['Мини', 'Гипер', 'Супер']
    }
    
    template = pd.DataFrame(example_data)
    return template

# Функция для скачивания файлов
def get_download_link(df, filename, text):
    """Генерирует ссылку для скачивания DataFrame"""
    towrite = io.BytesIO()
    if filename.endswith('.xlsx'):
        df.to_excel(towrite, index=False, encoding='utf-8')
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

# Отображение шаблонов для скачивания
st.header("📄 Шаблоны файлов")

col1, col2, col3 = st.columns(3)

with col1:
    st.subheader("План визитов")
    plan_template = create_plan_template()
    st.markdown(get_download_link(plan_template, "шаблон_план.xlsx", "📥 Скачать шаблон"), unsafe_allow_html=True)
    st.dataframe(plan_template.head(3), use_container_width=True)

with col2:
    st.subheader("Аудиторы")
    auditors_template = create_auditors_template()
    st.markdown(get_download_link(auditors_template, "шаблон_аудиторы.xlsx", "📥 Скачать шаблон"), unsafe_allow_html=True)
    st.dataframe(auditors_template.head(3), use_container_width=True)

with col3:
    st.subheader("Точки")
    points_template = create_points_template()
    st.markdown(get_download_link(points_template, "шаблон_точки.xlsx", "📥 Скачать шаблон"), unsafe_allow_html=True)
    st.dataframe(points_template.head(3), use_container_width=True)

st.markdown("---")

# Загрузка файлов
st.header("📤 Загрузка файлов")

uploaded_plan = st.file_uploader("Загрузите файл плана визитов", type=['xlsx', 'xls'])
uploaded_auditors = st.file_uploader("Загрузите файл аудиторов", type=['xlsx', 'xls'])
uploaded_points = st.file_uploader("Загрузите файл точек", type=['xlsx', 'xls'])

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

# Функция для расчета плана
def calculate_plan(plan_df, auditors_df, points_df, year, quarter, coefficients, max_points_per_week):
    """Основная функция расчета плана"""
    
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
    
    # Для каждого сотрудника
    for auditor in auditors_df['ID_Сотрудника'].unique():
        city = auditors_df[auditors_df['ID_Сотрудника'] == auditor]['Город'].iloc[0]
        
        # Получаем план для города
        if city in plan_df['Город'].values:
            city_plan = plan_df[plan_df['Город'] == city].iloc[0]
        else:
            # Если города нет в плане, используем данные из точек
            city_points = points_df[points_df['Город'] == city]
            city_plan = {
                'Квота_общая': len(city_points),
                'Квота_Гипер': len(city_points[city_points['Тип'] == 'Гипер']),
                'Квота_Супер': len(city_points[city_points['Тип'] == 'Супер']),
                'Квота_Мини': len(city_points[city_points['Тип'] == 'Мини'])
            }
        
        # Получаем точки сотрудника
        auditor_points = points_distribution.get(auditor, [])
        
        if not auditor_points:
            continue
        
        total_points = len(auditor_points)
        weeks_count = len(weeks)
        
        # Распределяем точки по неделям с учетом коэффициентов
        point_idx = 0
        
        for week in weeks:
            week_points_count = 0
            week_points_list = []
            
            # Определяем коэффициент для этой недели
            week_num = week['week_number']
            work_days = week['work_days_in_quarter']
            
            # Определяем этап (1-4)
            stage_idx = min(3, (week_num - 1) // (weeks_count // 4))
            
            # Базовое количество точек для недели
            base_points = total_points / weeks_count
            
            # Применяем коэффициенты
            adjusted_points = base_points * coefficients[stage_idx]
            
            # Корректируем на рабочие дни
            if work_days > 0:
                week_target = int(adjusted_points * (work_days / 5))
            else:
                week_target = 0
            
            # Ограничиваем максимумом
            week_target = min(week_target, max_points_per_week)
            
            # Берем точки для этой недели
            while week_points_count < week_target and point_idx < total_points:
                week_points_list.append(auditor_points[point_idx])
                week_points_count += 1
                point_idx += 1
            
            if week_points_count > 0:
                # Сохраняем результаты
                results.append({
                    'Сотрудник': auditor,
                    'Город': city,
                    'Неделя': week_num,
                    'Начало_недели': week['start_date'].strftime('%d.%m.%Y'),
                    'Конец_недели': week['end_date'].strftime('%d.%m.%Y'),
                    'Рабочих_дней': work_days,
                    'План_точек': week_points_count,
                    'Этап': stage_idx + 1,
                    'Коэффициент': coefficients[stage_idx]
                })
                
                # Детализация по точкам
                for point in week_points_list:
                    detailed_results.append({
                        'Сотрудник': auditor,
                        'Город': city,
                        'Неделя': week_num,
                        'ID_Точки': point.get('ID_Точки', ''),
                        'Название_Точки': point.get('Название_Точки', ''),
                        'Адрес': point.get('Адрес', ''),
                        'Тип_точки': point.get('Тип', ''),
                        'Широта': point.get('Широта', ''),
                        'Долгота': point.get('Долгота', ''),
                        'Полигон': point.get('Полигон', '')
                    })
                
                # Сохраняем для группировки
                if auditor not in weekly_assignments:
                    weekly_assignments[auditor] = {}
                
                weekly_assignments[auditor][week_num] = week_points_list
    
    return (
        pd.DataFrame(results), 
        pd.DataFrame(detailed_results), 
        polygons_df, 
        polygons_json,
        weekly_assignments
    )

# Кнопка расчета
if st.button("🚀 Рассчитать план", type="primary", use_container_width=True):
    
    if not all([uploaded_plan, uploaded_auditors, uploaded_points]):
        st.error("⚠️ Пожалуйста, загрузите все необходимые файлы!")
        st.stop()
    
    try:
        # Загружаем данные
        plan_df = pd.read_excel(uploaded_plan)
        auditors_df = pd.read_excel(uploaded_auditors)
        points_df = pd.read_excel(uploaded_points)
        
        # Проверяем необходимые колонки
        required_plan_cols = ['Город', 'Квота_общая', 'Квота_Гипер', 'Квота_Супер', 'Квота_Мини']
        required_auditor_cols = ['ID_Сотрудника', 'Город']
        required_point_cols = ['ID_Точки', 'Название_Точки', 'Адрес', 'Широта', 'Долгота', 'Город', 'Тип']
        
        for df_name, df, required_cols in [
            ("План", plan_df, required_plan_cols),
            ("Аудиторы", auditors_df, required_auditor_cols),
            ("Точки", points_df, required_point_cols)
        ]:
            missing_cols = [col for col in required_cols if col not in df.columns]
            if missing_cols:
                st.error(f"❌ В файле {df_name} отсутствуют колонки: {', '.join(missing_cols)}")
                st.stop()
        
        # Выполняем расчет
        with st.spinner("🔄 Идет расчет плана..."):
            summary_df, details_df, polygons_df, polygons_json, weekly_assignments = calculate_plan(
                plan_df, auditors_df, points_df, 
                year, quarter, coefficients, max_points_per_week
            )
        
        st.success("✅ Расчет завершен!")
        st.markdown("---")
        
        # Отображение результатов
        st.header("📈 Результаты расчета")
        
        # Создаем вкладки для разных видов отчетов
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "📅 Сводный план", 
            "📍 Распределение точек", 
            "🗺️ Полигоны", 
            "📊 Статистика", 
            "📥 Выгрузка"
        ])
        
        with tab1:
            # Фильтр по неделям
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
                display_df = week_summary[['Сотрудник', 'Город', 'План_точек', 'Этап', 'Коэффициент']].copy()
                display_df.columns = ['Сотрудник', 'Город', 'Кол-во точек', 'Этап', 'Коэффициент']
                
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
                    st.metric("Всего точек", week_summary['План_точек'].sum())
                with col3:
                    st.metric("Среднее на сотрудника", round(week_summary['План_точек'].mean(), 1))
            else:
                st.info(f"На неделю {selected_week} нет запланированных визитов")
        
        with tab2:
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
                
                weeks_summary.columns = ['Неделя', 'Количество точек', 'Распределение по типам']
                
                st.dataframe(
                    weeks_summary,
                    use_container_width=True,
                    hide_index=True
                )
                
                # Детализация точек
                st.subheader(f"Детализация точек для {selected_employee}")
                
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
                    st.info(f"На неделю {selected_week_detail} нет точек")
        
        with tab3:
            st.subheader("🗺️ Полигоны аудиторов")
            
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
        
        with tab4:
            st.subheader("📊 Статистика по кварталу")
            
            # Общая статистика
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Всего сотрудников", len(summary_df['Сотрудник'].unique()))
            with col2:
                st.metric("Всего недель", len(summary_df['Неделя'].unique()))
            with col3:
                st.metric("Всего точек в плане", summary_df['План_точек'].sum())
            with col4:
                avg_per_employee = summary_df.groupby('Сотрудник')['План_точек'].sum().mean()
                st.metric("Среднее на сотрудника", round(avg_per_employee, 1))
            
            # Статистика по типам точек
            st.subheader("Распределение по типам точек")
            if not details_df.empty:
                type_stats = details_df.groupby('Тип_точки').agg({
                    'ID_Точки': 'count',
                    'Сотрудник': 'nunique'
                }).reset_index()
                
                type_stats.columns = ['Тип точки', 'Количество', 'Количество сотрудников']
                st.dataframe(type_stats, use_container_width=True, hide_index=True)
            
            # Статистика по городам
            st.subheader("Распределение по городам")
            city_stats = summary_df.groupby('Город').agg({
                'Сотрудник': 'nunique',
                'План_точек': 'sum'
            }).reset_index()
            
            city_stats.columns = ['Город', 'Количество сотрудников', 'Количество точек']
            st.dataframe(city_stats, use_container_width=True, hide_index=True)
        
        with tab5:
            st.header("📥 Выгрузка результатов")
            
            # Создаем Excel файл с несколькими вкладками
            with pd.ExcelWriter('результаты_плана.xlsx', engine='openpyxl') as writer:
                # Вкладка 1: Сводная информация
                summary_display = summary_df.copy()
                summary_display.to_excel(writer, sheet_name='Сводная', index=False)
                
                # Вкладка 2: Детализация точек
                details_display = details_df.copy()
                details_display.to_excel(writer, sheet_name='Детализация', index=False)
                
                # Вкладка 3: Полигоны
                polygons_display = polygons_df.copy()
                polygons_display.to_excel(writer, sheet_name='Полигоны', index=False)
                
                # Вкладка 4: Группировка точек по неделям
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
                                'Неделя': week_num,
                                'Количество точек': len(points_list),
                                'Перечень точек': '; '.join(points_info)
                            })
                
                if grouped_data:
                    grouped_df = pd.DataFrame(grouped_data)
                    grouped_df.to_excel(writer, sheet_name='Группировка', index=False)
                
                # Вкладка 5: Статистика
                stats_data = []
                for employee in summary_df['Сотрудник'].unique():
                    emp_summary = summary_df[summary_df['Сотрудник'] == employee]
                    emp_details = details_df[details_df['Сотрудник'] == employee]
                    
                    # Получаем город сотрудника
                    city = emp_summary['Город'].iloc[0] if not emp_summary.empty else 'Не определен'
                    
                    stats_data.append({
                        'Сотрудник': employee,
                        'Город': city,
                        'Всего точек на квартал': emp_summary['План_точек'].sum(),
                        'Всего недель с планом': emp_summary['Неделя'].nunique(),
                        'Среднее точек в неделю': round(emp_summary['План_точек'].mean(), 1),
                        'Максимум в неделю': emp_summary['План_точек'].max(),
                        'Минимум в неделю': emp_summary['План_точек'].min(),
                        'Гипермаркеты': len(emp_details[emp_details['Тип_точки'] == 'Гипер']),
                        'Супермаркеты': len(emp_details[emp_details['Тип_точки'] == 'Супер']),
                        'Минимаркеты': len(emp_details[emp_details['Тип_точки'] == 'Мини'])
                    })
                
                stats_df = pd.DataFrame(stats_data)
                stats_df.to_excel(writer, sheet_name='Статистика', index=False)
            
            # Создаем отдельный файл GeoJSON для полигонов
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
1. Точки распределяются между сотрудниками одного города равномерно
2. При расчете учитываются только рабочие дни (понедельник-пятница)
3. Недели, попадающие на границу квартала, рассчитываются пропорционально
4. Коэффициенты применяются к этапам квартала (каждый этап = 1/4 квартала)
""")