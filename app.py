import streamlit as st
import pandas as pd
import numpy as np
import io
from datetime import datetime, date, timedelta
import calendar
import json
import base64
from typing import Dict, List, Tuple, Optional

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
    1. Скачайте шаблон файла
    2. Заполните данные в двух вкладках
    3. Загрузите заполненный файл
    4. Нажмите кнопку "Рассчитать"
    
    **Внимание:** План визитов рассчитывается автоматически 
    как сумма посещений всех точек по городам.
    """)

# Функции для создания шаблона
def create_template():
    """Создает шаблон Excel файла с двумя вкладками"""
    
    # Вкладка 1: Точки (план)
    points_data = {
        'ID_Точки': ['P001', 'P002', 'P003', 'P004'],
        'Название_Точки': ['Магазин 1', 'Гипермаркет 1', 'Супермаркет 1', 'Минимаркет 2'],
        'Адрес': ['ул. Ленина, 1', 'ул. Мира, 10', 'пр. Победы, 5', 'ул. Центральная, 3'],
        'Широта': [55.7558, 55.7507, 55.7601, 55.7520],
        'Долгота': [37.6173, 37.6177, 37.6254, 37.6200],
        'Город': ['Москва', 'Москва', 'Москва', 'Москва'],
        'Тип': ['Мини', 'Гипер', 'Супер', 'Мини'],
        'Кол-во_посещений': [1, 1, 1, 2]  # По умолчанию 1, если не заполнено
    }
    
    points_df = pd.DataFrame(points_data)
    
    # Вкладка 2: Аудиторы
    auditors_data = {
        'ID_Сотрудника': ['SOVIAUD13', 'SOVIAUD14', 'SOVIAUD15'],
        'Город': ['Москва', 'Москва', 'Москва']
    }
    
    auditors_df = pd.DataFrame(auditors_data)
    
    # Вкладка 3: Факт посещений (пустая)
    visits_data = {
        'ID_Точки': [],
        'Дата_визита': [],
        'ID_Сотрудника': []  # Кто совершил визит
    }
    
    visits_df = pd.DataFrame(visits_data)
    
    # Создаем Excel файл с тремя вкладками
    with pd.ExcelWriter('шаблон_данных.xlsx', engine='openpyxl') as writer:
        points_df.to_excel(writer, sheet_name='Точки', index=False)
        auditors_df.to_excel(writer, sheet_name='Аудиторы', index=False)
        visits_df.to_excel(writer, sheet_name='Факт_посещений', index=False)
    
    # Читаем созданный файл для отдачи
    with open('шаблон_данных.xlsx', 'rb') as f:
        excel_data = f.read()
    
    return excel_data

# Функция для скачивания файлов
def get_download_link(data, filename, text, mime_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'):
    """Генерирует ссылку для скачивания файла"""
    b64 = base64.b64encode(data).decode()
    href = f'<a href="data:{mime_type};base64,{b64}" download="{filename}">{text}</a>'
    return href

# Отображение шаблона для скачивания
st.header("📄 Шаблон файла")

col1, col2 = st.columns(2)

with col1:
    st.subheader("Шаблон данных")
    template_data = create_template()
    st.markdown(get_download_link(template_data, "шаблон_данных.xlsx", "📥 Скачать шаблон"), unsafe_allow_html=True)
    
    st.markdown("""
    **Содержит 3 вкладки:**
    1. **Точки** - информация о торговых точках
    2. **Аудиторы** - привязка сотрудников к городам  
    3. **Факт_посещений** - фактическое посещение точек
    """)

with col2:
    st.subheader("Поля в шаблоне")
    st.markdown("""
    **Вкладка 'Точки':**
    - `ID_Точки` - уникальный идентификатор точки
    - `Название_Точки` - название торговой точки
    - `Адрес` - необязательно (можно определить по координатам)
    - `Широта`, `Долгота` - координаты точки
    - `Город` - необязательно (можно определить по координатам)
    - `Тип` - Мини/Гипер/Супер
    - `Кол-во_посещений` - план посещений (по умолчанию 1)
    
    **Вкладка 'Аудиторы':**
    - `ID_Сотрудника` - идентификатор сотрудника
    - `Город` - город работы
    
    **Вкладка 'Факт_посещений':**
    - `ID_Точки` - идентификатор точки
    - `Дата_визита` - дата фактического посещения
    - `ID_Сотрудника` - кто совершил визит
    """)

st.markdown("---")

# Загрузка файла
st.header("📤 Загрузка файла")

uploaded_file = st.file_uploader("Загрузите файл с данными", type=['xlsx', 'xls'])

# Функции для обработки данных
def load_excel_file(uploaded_file):
    """Загружает данные из Excel файла с тремя вкладками"""
    try:
        # Читаем все вкладки
        points_df = pd.read_excel(uploaded_file, sheet_name='Точки')
        auditors_df = pd.read_excel(uploaded_file, sheet_name='Аудиторы')
        visits_df = pd.read_excel(uploaded_file, sheet_name='Факт_посещений')
        
        return points_df, auditors_df, visits_df
    except Exception as e:
        st.error(f"Ошибка при чтении файла: {str(e)}")
        st.error("Убедитесь, что файл содержит вкладки: 'Точки', 'Аудиторы', 'Факт_посещений'")
        return None, None, None

def process_points_data(df):
    """Обрабатывает данные точек"""
    df = df.copy()
    
    # Проверяем и переименовываем колонки
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
    
    # Преобразуем типы точек
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
    required_cols = ['ID_Точки', 'Название_Точки', 'Широта', 'Долгота', 'Тип', 'Кол-во_посещений']
    optional_cols = ['Адрес', 'Город']
    
    # Проверяем обязательные колонки
    for col in required_cols:
        if col not in df.columns:
            st.error(f"❌ Отсутствует обязательная колонка: {col}")
            return None
    
    # Добавляем опциональные колонки, если их нет
    for col in optional_cols:
        if col not in df.columns:
            df[col] = ''
    
    # Упорядочиваем колонки
    final_cols = required_cols + optional_cols
    df = df[final_cols]
    
    return df

def process_auditors_data(df):
    """Обрабатывает данные аудиторов"""
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
                st.error(f"❌ Отсутствует обязательная колонка: {col}")
                return None
    
    return df[required_cols]

def process_visits_data(df):
    """Обрабатывает данные фактических посещений"""
    if df is None or df.empty:
        return pd.DataFrame(columns=['ID_Точки', 'Дата_визита', 'ID_Сотрудника'])
    
    df = df.copy()
    
    # Проверяем и переименовываем колонки
    column_mapping = {
        'ID точки': 'ID_Точки',
        'Дата визита': 'Дата_визита',
        'Дата': 'Дата_визита',
        'Date': 'Дата_визита',
        'ID Сотрудника': 'ID_Сотрудника',
        'Employee ID': 'ID_Сотрудника'
    }
    
    for old_col, new_col in column_mapping.items():
        if old_col in df.columns and new_col not in df.columns:
            df = df.rename(columns={old_col: new_col})
    
    # Проверяем наличие необходимых колонок
    required_cols = ['ID_Точки', 'Дата_визита']
    optional_cols = ['ID_Сотрудника']
    
    for col in required_cols:
        if col not in df.columns:
            st.warning(f"⚠️ В данных посещений отсутствует колонка: {col}")
            return pd.DataFrame(columns=required_cols + optional_cols)
    
    # Добавляем опциональные колонки, если их нет
    for col in optional_cols:
        if col not in df.columns:
            df[col] = ''
    
    # Преобразуем даты
    df['Дата_визита'] = pd.to_datetime(df['Дата_визита'], errors='coerce')
    
    return df

# Функция для получения ISO номера недели
def get_iso_week(date_obj):
    """Возвращает ISO номер недели для даты"""
    return date_obj.isocalendar()[1]

# Основная кнопка расчета
if st.button("🚀 Рассчитать план", type="primary", use_container_width=True):
    
    if not uploaded_file:
        st.error("⚠️ Пожалуйста, загрузите файл с данными!")
        st.stop()
    
    try:
        # Загружаем данные из файла
        points_df_raw, auditors_df_raw, visits_df_raw = load_excel_file(uploaded_file)
        
        if points_df_raw is None:
            st.stop()
        
        # Обрабатываем данные
        points_df = process_points_data(points_df_raw)
        auditors_df = process_auditors_data(auditors_df_raw)
        visits_df = process_visits_data(visits_df_raw)
        
        if points_df is None or auditors_df is None:
            st.stop()
        
        # Показываем предпросмотр данных
        st.success("✅ Данные успешно загружены!")
        
        with st.expander("📋 Предпросмотр загруженных данных"):
            tab1, tab2, tab3 = st.tabs(["Точки", "Аудиторы", "Факт посещений"])
            
            with tab1:
                st.write(f"Загружено точек: {len(points_df)}")
                st.dataframe(points_df.head(10), use_container_width=True)
                
                # Статистика по точкам
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Всего посещений (план)", points_df['Кол-во_посещений'].sum())
                with col2:
                    st.metric("Типы точек", ", ".join(points_df['Тип'].unique()))
                with col3:
                    cities = points_df['Город'].unique()
                    if len(cities) > 0 and cities[0] != '':
                        st.metric("Города", ", ".join(cities[:3]) + ("..." if len(cities) > 3 else ""))
                    else:
                        st.metric("Города", "Не указаны")
            
            with tab2:
                st.write(f"Загружено аудиторов: {len(auditors_df)}")
                st.dataframe(auditors_df.head(10), use_container_width=True)
            
            with tab3:
                if not visits_df.empty:
                    st.write(f"Загружено записей о посещениях: {len(visits_df)}")
                    st.dataframe(visits_df.head(10), use_container_width=True)
                else:
                    st.info("Данные о посещениях отсутствуют")
        
               # Продолжение расчета...
        st.markdown("---")
        st.header("📅 Расчет плана визитов")
        
        # Функции для работы с датами
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
            """Возвращает список недель в квартале с ISO номерами"""
            quarter_start, quarter_end = get_quarter_dates(year, quarter)
            
            weeks = []
            current_date = quarter_start
            week_num = 1
            
            while current_date <= quarter_end:
                week_start = current_date
                week_end = min(current_date + timedelta(days=6), quarter_end)
                
                # Получаем ISO номер недели для начала недели
                iso_week = get_iso_week(week_start)
                
                # Считаем рабочие дни в этой неделе для квартала
                work_days = 0
                temp_date = week_start
                while temp_date <= week_end:
                    if temp_date.weekday() < 5:  # Пн-Пт
                        work_days += 1
                    temp_date += timedelta(days=1)
                
                weeks.append({
                    'week_number': week_num,  # Порядковый номер в квартале
                    'iso_week_number': iso_week,  # ISO номер недели
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
            # Если города не указаны в точках, пропускаем проверку
            if points_df['Город'].isnull().all() or (points_df['Город'] == '').all():
                return [], set(auditors_df['Город'].unique())
            
            auditors_cities = set(auditors_df['Город'].dropna().unique())
            points_cities = set(points_df['Город'].dropna().unique())
            
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
        
        # Проверяем соответствие городов
        warnings, common_cities = check_city_compatibility(auditors_df, points_df)
        
        for warning in warnings:
            if warning.startswith("⚠️"):
                st.warning(warning)
            else:
                st.success(warning)
        
        # Если нет общих городов и города указаны в точках, предупреждаем
        if not common_cities and not points_df['Город'].isnull().all() and not (points_df['Город'] == '').all():
            st.warning("⚠️ Нет общих городов между аудиторами и точками. Проверка будет пропущена.")
        
        # Обрабатываем фактические посещения
        def process_actual_visits(visits_df, year, quarter):
            """Обрабатывает фактические посещения и связывает их с неделями"""
            if visits_df.empty:
                return pd.DataFrame()
            
            # Оставляем только валидные даты
            visits_df = visits_df.dropna(subset=['Дата_визита'])
            
            if visits_df.empty:
                return pd.DataFrame()
            
            # Получаем границы квартала
            quarter_start, quarter_end = get_quarter_dates(year, quarter)
            
            # Фильтруем посещения по кварталу
            visits_in_quarter = visits_df[
                (visits_df['Дата_визита'] >= pd.Timestamp(quarter_start)) &
                (visits_df['Дата_визита'] <= pd.Timestamp(quarter_end))
            ].copy()
            
            if visits_in_quarter.empty:
                return pd.DataFrame()
            
            # Добавляем ISO номер недели
            visits_in_quarter['iso_week'] = visits_in_quarter['Дата_визита'].apply(get_iso_week)
            
            # Группируем по точкам и неделям (считаем каждую запись как 1 посещение)
            visits_summary = visits_in_quarter.groupby(['ID_Точки', 'iso_week']).size().reset_index(name='факт_посещений')
            
            return visits_summary
        
        # Обрабатываем фактические посещения
        actual_visits_df = process_actual_visits(visits_df, year, quarter)
        
        if not actual_visits_df.empty:
            st.success(f"✅ Загружено {len(actual_visits_df)} записей о фактических посещениях за квартал")
        else:
            st.info("ℹ️ Фактические посещения за квартал не найдены или файл пустой")
        
        # Функция для расчета плана посещений
        def calculate_visits_plan(points_df, auditors_df, year, quarter, coefficients, max_visits_per_week):
            """Основная функция расчета плана посещений"""
            
            # Получаем недели квартала
            weeks = get_weeks_in_quarter(year, quarter)
            
            # Создаем структуры для хранения результатов
            results = []
            detailed_results = []
            weekly_assignments = {}
            city_statistics = []
            
            # Собираем статистику по городам
            if not points_df['Город'].isnull().all() and not (points_df['Город'] == '').all():
                city_stats = points_df.groupby('Город').agg({
                    'ID_Точки': 'count',
                    'Кол-во_посещений': 'sum'
                }).reset_index()
                
                for _, row in city_stats.iterrows():
                    city_statistics.append({
                        'Город': row['Город'],
                        'Всего_точек': row['ID_Точки'],
                        'План_посещений': row['Кол-во_посещений']
                    })
            
            # Для каждого сотрудника
            for auditor in auditors_df['ID_Сотрудника'].unique():
                city = auditors_df[auditors_df['ID_Сотрудника'] == auditor]['Город'].iloc[0]
                
                # Получаем точки города сотрудника
                if not points_df['Город'].isnull().all() and not (points_df['Город'] == '').all():
                    city_points = points_df[points_df['Город'] == city].copy()
                else:
                    # Если город не указан, берем все точки
                    city_points = points_df.copy()
                
                if len(city_points) == 0:
                    continue
                
                # Распределяем точки между аудиторами города
                city_auditors = auditors_df[auditors_df['Город'] == city]['ID_Сотрудника'].tolist()
                auditor_index = city_auditors.index(auditor)
                
                # Простое распределение по порядку
                points_per_auditor = len(city_points) // len(city_auditors)
                remainder = len(city_points) % len(city_auditors)
                
                start_idx = sum([points_per_auditor + (1 if i < remainder else 0) 
                                for i in range(auditor_index)])
                end_idx = start_idx + points_per_auditor + (1 if auditor_index < remainder else 0)
                
                auditor_points = city_points.iloc[start_idx:end_idx].copy()
                
                if len(auditor_points) == 0:
                    continue
                
                # Создаем список всех посещений для аудитора
                all_visits_list = []
                for _, point in auditor_points.iterrows():
                    visits_count = point.get('Кол-во_посещений', 1)
                    for _ in range(visits_count):
                        all_visits_list.append(point.to_dict())
                
                total_visits_actual = len(all_visits_list)
                weeks_count = len(weeks)
                
                # Распределяем посещения по неделям
                visit_idx = 0
                
                for week in weeks:
                    week_visits_count = 0
                    week_visits_list = []
                    
                    # Определяем коэффициент для недели
                    iso_week = week['iso_week_number']
                    work_days = week['work_days_in_quarter']
                    
                    # Определяем этап (1-4)
                    stage_idx = min(3, (week['week_number'] - 1) // (weeks_count // 4))
                    
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
                            'ISO_Неделя': iso_week,
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
                                'ISO_Неделя': iso_week,
                                'ID_Точки': visit.get('ID_Точки', ''),
                                'Название_Точки': visit.get('Название_Точки', ''),
                                'Адрес': visit.get('Адрес', ''),
                                'Тип_точки': visit.get('Тип', ''),
                                'Широта': visit.get('Широта', ''),
                                'Долгота': visit.get('Долгота', ''),
                                'Кол-во_посещений_план': visit.get('Кол-во_посещений', 1)
                            })
                        
                        # Сохраняем для группировки
                        if auditor not in weekly_assignments:
                            weekly_assignments[auditor] = {}
                        
                        weekly_assignments[auditor][iso_week] = week_visits_list
            
            # Создаем DataFrame результатов
            summary_df = pd.DataFrame(results) if results else pd.DataFrame()
            details_df = pd.DataFrame(detailed_results) if detailed_results else pd.DataFrame()
            city_stats_df = pd.DataFrame(city_statistics) if city_statistics else pd.DataFrame()
            
            return summary_df, details_df, weekly_assignments, city_stats_df
        
        # Выполняем расчет плана
        with st.spinner("🔄 Идет расчет плана..."):
            summary_df, details_df, weekly_assignments, city_stats_df = calculate_visits_plan(
                points_df, auditors_df, year, quarter, coefficients, max_visits_per_week
            )
        
        if summary_df.empty:
            st.error("❌ Не удалось рассчитать план. Проверьте данные.")
            st.stop()
        
        st.success(f"✅ План рассчитан! Охвачено {len(summary_df['Сотрудник'].unique())} сотрудников")
        
        # Объединяем план с фактом
        def merge_plan_with_fact(summary_df, details_df, actual_visits_df):
            """Объединяет плановые данные с фактическими"""
            
            # Для сводной таблицы
            if not summary_df.empty:
                summary_with_fact = summary_df.copy()
                
                # Если есть фактические данные, добавляем
                if not actual_visits_df.empty:
                    # Для каждой строки плана ищем факт по сотруднику и неделе
                    summary_with_fact['Факт_посещений'] = 0
                    # Здесь будет логика сопоставления
                else:
                    summary_with_fact['Факт_посещений'] = 0
                
                summary_with_fact['%_выполнения'] = summary_with_fact.apply(
                    lambda x: round((x['Факт_посещений'] / x['План_посещений'] * 100) if x['План_посещений'] > 0 else 0, 1),
                    axis=1
                )
            
            # Для детальной таблицы
            if not details_df.empty and not actual_visits_df.empty:
                details_with_fact = details_df.copy()
                # Здесь будет логика сопоставления
            else:
                details_with_fact = details_df.copy() if not details_df.empty else pd.DataFrame()
            
            return summary_with_fact, details_with_fact
        
        # Объединяем план с фактом
        summary_with_fact, details_with_fact = merge_plan_with_fact(summary_df, details_df, actual_visits_df)
        
        # Сохраняем данные в session state для использования в других частях
        st.session_state['points_df'] = points_df
        st.session_state['auditors_df'] = auditors_df
        st.session_state['summary_df'] = summary_with_fact
        st.session_state['details_df'] = details_with_fact
        st.session_state['city_stats_df'] = city_stats_df
        st.session_state['weekly_assignments'] = weekly_assignments
        st.session_state['actual_visits_df'] = actual_visits_df
        st.session_state['year'] = year
        st.session_state['quarter'] = quarter
        st.session_state['coefficients'] = coefficients
        
        # Показываем первую вкладку результатов
        st.markdown("---")
        st.header("📊 Результаты расчета")
        
        # Вкладка 1: Статистика городов
        st.subheader("📊 Статистика по городам")
        
        if not city_stats_df.empty:
            # Общая статистика
            total_points = len(points_df)
            total_plan_visits = points_df['Кол-во_посещений'].sum()
            total_auditors = len(auditors_df)
            
            # Рассчитываем факт из actual_visits_df
            if not actual_visits_df.empty:
                total_fact_visits = actual_visits_df['факт_посещений'].sum()
                completion_percent = round((total_fact_visits / total_plan_visits * 100) if total_plan_visits > 0 else 0, 1)
            else:
                total_fact_visits = 0
                completion_percent = 0
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Всего городов", len(city_stats_df))
            with col2:
                st.metric("План посещений", total_plan_visits)
            with col3:
                st.metric("Факт посещений", total_fact_visits)
            with col4:
                st.metric("% выполнения", f"{completion_percent}%")
            
            # Добавляем факт в таблицу статистики городов
            city_stats_display = city_stats_df.copy()
            city_stats_display['Факт_посещений'] = 0  # Заглушка - будет рассчитано в след. части
            city_stats_display['%_выполнения'] = 0
            
            # Переименовываем колонки
            city_stats_display = city_stats_display.rename(columns={
                'Всего_точек': 'Всего точек',
                'План_посещений': 'План посещений'
            })
            
            # Порядок колонок
            city_stats_display = city_stats_display[['Город', 'Всего точек', 'План посещений', 'Факт_посещений', '%_выполнения']]
            
            st.dataframe(
                city_stats_display,
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("Нет данных по городам для отображения статистики")
        
    except Exception as e:
        st.error(f"❌ Произошла ошибка при обработке данных: {str(e)}")
        import traceback
        st.error(f"Детали ошибки:\n{traceback.format_exc()}")
        # Создаем вкладки для разных видов отчетов
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "📅 Сводный план", 
            "📍 Распределение посещений", 
            "📈 Статистика по типам",
            "🗺️ Карта полигонов",
            "📥 Выгрузка"
        ])
        
        with tab1:
            st.subheader("📅 Сводный план по неделям")
            
            if not summary_with_fact.empty:
                # Фильтры
                col1, col2, col3 = st.columns(3)
                with col1:
                    # Фильтр по ISO неделям
                    available_weeks = sorted(summary_with_fact['ISO_Неделя'].unique())
                    selected_week = st.selectbox(
                        "Выберите неделю (ISO)",
                        available_weeks,
                        key="week_filter_main"
                    )
                
                with col2:
                    # Фильтр по городу
                    available_cities = ['Все'] + sorted(summary_with_fact['Город'].dropna().unique().tolist())
                    selected_city = st.selectbox(
                        "Выберите город",
                        available_cities,
                        key="city_filter_main"
                    )
                
                with col3:
                    # Фильтр по полигону (пока заглушка - будет в след. части)
                    available_polygons = ['Все']
                    selected_polygon = st.selectbox(
                        "Выберите полигон",
                        available_polygons,
                        key="polygon_filter_main",
                        disabled=True  # Пока не реализовано
                    )
                
                # Применяем фильтры
                filtered_data = summary_with_fact.copy()
                
                if selected_week:
                    filtered_data = filtered_data[filtered_data['ISO_Неделя'] == selected_week]
                
                if selected_city != 'Все':
                    filtered_data = filtered_data[filtered_data['Город'] == selected_city]
                
                # Формируем таблицу для отображения
                display_df = filtered_data[['Сотрудник', 'Город', 'План_посещений', 'Факт_посещений', '%_выполнения']].copy()
                display_df.columns = ['Сотрудник', 'Город', 'План посещений', 'Факт посещений', '% выполнения']
                
                # Сортируем по сотруднику
                display_df = display_df.sort_values('Сотрудник')
                
                if not display_df.empty:
                    st.dataframe(
                        display_df,
                        use_container_width=True,
                        hide_index=True
                    )
                    
                    # Итоги по неделе
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Всего сотрудников", len(display_df))
                    with col2:
                        total_plan = display_df['План посещений'].sum()
                        total_fact = display_df['Факт посещений'].sum()
                        st.metric("План посещений", total_plan)
                    with col3:
                        st.metric("Факт посещений", total_fact)
                    
                    # Диаграмма выполнения плана
                    try:
                        import plotly.graph_objects as go
                        
                        # Готовим данные для диаграммы
                        employees = display_df['Сотрудник'].tolist()
                        plan_values = display_df['План посещений'].tolist()
                        fact_values = display_df['Факт посещений'].tolist()
                        completion = display_df['% выполнения'].tolist()
                        
                        # Создаем диаграмму
                        fig = go.Figure()
                        
                        # Столбцы плана
                        fig.add_trace(go.Bar(
                            name='План',
                            x=employees,
                            y=plan_values,
                            marker_color='lightblue',
                            text=plan_values,
                            textposition='outside'
                        ))
                        
                        # Столбцы факта (накладываем на план)
                        fig.add_trace(go.Bar(
                            name='Факт',
                            x=employees,
                            y=fact_values,
                            marker_color='orange',
                            text=fact_values,
                            textposition='outside'
                        ))
                        
                        # Настройки диаграммы
                        fig.update_layout(
                            title=f'Выполнение плана на неделю {selected_week}',
                            barmode='overlay',
                            xaxis_title='Сотрудник',
                            yaxis_title='Количество посещений',
                            showlegend=True,
                            height=400
                        )
                        
                        st.plotly_chart(fig, use_container_width=True)
                        
                    except ImportError:
                        st.warning("Для отображения диаграмм установите библиотеку plotly")
                        st.info("Запустите: pip install plotly")
                else:
                    st.info(f"Нет данных для недели {selected_week} с выбранными фильтрами")
            else:
                st.info("Нет данных для отображения сводного плана")
        
        with tab2:
            st.subheader("📍 Распределение посещений по неделям и сотрудникам")
            
            if not details_with_fact.empty:
                # Фильтры
                col1, col2 = st.columns(2)
                with col1:
                    # Выбор сотрудника
                    employees = sorted(details_with_fact['Сотрудник'].unique())
                    selected_employee = st.selectbox(
                        "Выберите сотрудника",
                        employees,
                        key="employee_filter_detail"
                    )
                
                with col2:
                    # Фильтр по городу
                    available_cities = ['Все'] + sorted(details_with_fact['Город'].dropna().unique().tolist())
                    selected_city_detail = st.selectbox(
                        "Выберите город",
                        available_cities,
                        key="city_filter_detail"
                    )
                
                # Применяем фильтры
                employee_data = details_with_fact[details_with_fact['Сотрудник'] == selected_employee].copy()
                
                if selected_city_detail != 'Все':
                    employee_data = employee_data[employee_data['Город'] == selected_city_detail]
                
                if not employee_data.empty:
                    # Сводная по неделям для выбранного сотрудника
                    weeks_summary = employee_data.groupby('ISO_Неделя').agg({
                        'ID_Точки': 'count',
                        'Тип_точки': lambda x: ', '.join([f"{val}:{list(x).count(val)}" for val in x.unique()])
                    }).reset_index()
                    
                    weeks_summary.columns = ['ISO Неделя', 'План посещений', 'Распределение по типам']
                    
                    st.dataframe(
                        weeks_summary,
                        use_container_width=True,
                        hide_index=True
                    )
                    
                    # Детализация для выбранной недели
                    st.subheader(f"Детализация посещений для {selected_employee}")
                    
                    available_weeks_detail = sorted(employee_data['ISO_Неделя'].unique())
                    selected_week_detail = st.selectbox(
                        "Выберите неделю для детализации",
                        available_weeks_detail,
                        key="week_detail_filter"
                    )
                    
                    week_details = employee_data[employee_data['ISO_Неделя'] == selected_week_detail]
                    
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
                        display_details = week_details[['ID_Точки', 'Название_Точки', 'Адрес', 'Тип_точки']].copy()
                        
                        # Добавляем чекбоксы для отметки посещений
                        if 'checkboxes' not in st.session_state:
                            st.session_state.checkboxes = {}
                        
                        # Создаем колонку с чекбоксами
                        display_details['Визит совершен'] = False
                        
                        # Отображаем таблицу с возможностью редактирования
                        edited_df = st.data_editor(
                            display_details,
                            column_config={
                                "Визит совершен": st.column_config.CheckboxColumn(
                                    "Визит совершен",
                                    help="Отметьте, если визит был совершен",
                                    default=False,
                                )
                            },
                            disabled=["ID_Точки", "Название_Точки", "Адрес", "Тип_точки"],
                            hide_index=True,
                            use_container_width=True
                        )
                        
                        # Кнопка для сохранения изменений
                        if st.button("💾 Сохранить отметки о посещениях", key="save_visits"):
                            # Здесь будет логика сохранения в файл
                            st.success("Отметки сохранены (функция будет реализована в след. части)")
                    else:
                        st.info(f"На неделю {selected_week_detail} нет запланированных посещений")
                else:
                    st.info(f"Нет данных для сотрудника {selected_employee}")
            else:
                st.info("Нет данных для отображения распределения посещений")
        
        with tab3:
            st.subheader("📈 Статистика по типам точек")
            
            if not points_df.empty:
                # Группируем данные по типам точек
                type_stats = points_df.groupby('Тип').agg({
                    'ID_Точки': 'count',
                    'Кол-во_посещений': 'sum'
                }).reset_index()
                
                type_stats.columns = ['Тип точки', 'Количество точек', 'План посещений']
                
                # Добавляем фактические данные (если есть)
                if not actual_visits_df.empty and not details_with_fact.empty:
                    # Сопоставляем фактические посещения по типам точек
                    # Это упрощенная логика - в реальности нужно сопоставлять ID точек
                    type_stats['Факт посещений'] = 0  # Заглушка
                else:
                    type_stats['Факт посещений'] = 0
                
                # Рассчитываем процент выполнения
                type_stats['% выполнения'] = type_stats.apply(
                    lambda x: round((x['Факт посещений'] / x['План посещений'] * 100) if x['План посещений'] > 0 else 0, 1),
                    axis=1
                )
                
                # Упорядочиваем колонки
                type_stats = type_stats[['Тип точки', 'Количество точек', 'План посещений', 'Факт посещений', '% выполнения']]
                
                st.dataframe(
                    type_stats,
                    use_container_width=True,
                    hide_index=True
                )
                
                # Диаграмма плана посещений по типам точек
                try:
                    import plotly.graph_objects as go
                    
                    fig = go.Figure()
                    
                    # Гистограмма плана
                    fig.add_trace(go.Bar(
                        name='План посещений',
                        x=type_stats['Тип точки'],
                        y=type_stats['План посещений'],
                        marker_color='lightblue',
                        text=type_stats['План посещений'],
                        textposition='outside'
                    ))
                    
                    # Если есть факт, добавляем вторую гистограмму
                    if type_stats['Факт посещений'].sum() > 0:
                        fig.add_trace(go.Bar(
                            name='Факт посещений',
                            x=type_stats['Тип точки'],
                            y=type_stats['Факт посещений'],
                            marker_color='orange',
                            text=type_stats['Факт посещений'],
                            textposition='outside'
                        ))
                    
                    fig.update_layout(
                        title='Распределение посещений по типам точек',
                        barmode='group',
                        xaxis_title='Тип точки',
                        yaxis_title='Количество посещений',
                        showlegend=True,
                        height=400
                    )
                    
                    st.plotly_chart(fig, use_container_width=True)
                    
                except ImportError:
                    st.warning("Для отображения диаграмм установите библиотеку plotly")
            
            else:
                st.info("Нет данных для статистики по типам точек")
        
        with tab4:
            st.subheader("🗺️ Карта полигонов")
            
            st.info("🚧 Функционал карты будет реализован в следующей части")
            st.info("""
            **Планируется:**
            1. Отображение полигонов на карте
            2. Точки внутри полигонов
            3. Цветовая синхронизация
            4. Кнопка выгрузки KML
            """)
            
            # Заглушка для будущей карты
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🔄 Обновить карту", disabled=True):
                    st.info("Функция в разработке")
            
            with col2:
                if st.button("🗺️ Выгрузить KML", disabled=True):
                    st.info("Функция в разработке")
        
        with tab5:
            st.subheader("📥 Выгрузка результатов")
            
            st.info("🚧 Функционал выгрузки будет реализован в следующей части")
            st.info("""
            **Будут доступны для выгрузки:**
            1. Полный отчет в Excel
            2. KML файл с полигонами и точками
            3. Отчет по выполнению плана
            """)
            
            # Заглушки для кнопок выгрузки
            col1, col2, col3 = st.columns(3)
            
            with col1:
                if st.button("📊 Выгрузить Excel отчет", disabled=True):
                    st.info("Функция в разработке")
            
            with col2:
                if st.button("🗺️ Выгрузить KML", disabled=True):
                    st.info("Функция в разработке")
            
            with col3:
                if st.button("📈 Выгрузить статистику", disabled=True):
                    st.info("Функция в разработке")
        
        # Информация о квартале
        st.markdown("---")
        st.subheader("📅 Информация о квартале")
        
        quarter_start, quarter_end = get_quarter_dates(year, quarter)
        total_weeks = len(get_weeks_in_quarter(year, quarter))
        
        st.info(f"""
        **Выбранный квартал:** {quarter} квартал {year} года  
        **Период:** {quarter_start.strftime('%d.%m.%Y')} - {quarter_end.strftime('%d.%m.%Y')}  
        **Всего недель в квартале:** {total_weeks}  
        **Коэффициенты по этапам:** {', '.join([str(c) for c in coefficients])}
        **Максимум посещений в неделю:** {max_visits_per_week}
        """)

# Информация в подвале
st.markdown("---")
st.caption("""


**Примечания:**
1. Для продолжения расчетов загрузите файл и нажмите "Рассчитать"
2. В следующей части кода будут реализованы: расчет плана, полигоны, KML выгрузка
3. Для определения города/адреса по координатам будет добавлен геокодер
""")