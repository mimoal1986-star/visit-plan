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
    
    # Вкладка 2: Факт посещений (пустая)
    visits_data = {
        'ID_Точки': [],
        'Дата_визита': []
    }
    
    visits_df = pd.DataFrame(visits_data)
    
    # Создаем Excel файл с двумя вкладками
    with pd.ExcelWriter('шаблон_данных.xlsx', engine='openpyxl') as writer:
        points_df.to_excel(writer, sheet_name='Точки', index=False)
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
    **Содержит 2 вкладки:**
    1. **Точки** - информация о торговых точках (план)
    2. **Факт_посещений** - фактическое посещение точек (по 1 строке на каждый визит)
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
    
    **Вкладка 'Факт_посещений':**
    - `ID_Точки` - идентификатор точки
    - `Дата_визита` - дата фактического посещения (одна строка = один визит)
    """)

st.markdown("---")

# Загрузка файла
st.header("📤 Загрузка файла")

uploaded_file = st.file_uploader("Загрузите файл с данными", type=['xlsx', 'xls'])

# Функции для обработки данных
def load_excel_file(uploaded_file):
    """Загружает данные из Excel файла с двумя вкладками"""
    try:
        # Читаем все вкладки
        points_df = pd.read_excel(uploaded_file, sheet_name='Точки')
        visits_df = pd.read_excel(uploaded_file, sheet_name='Факт_посещений')
        
        return points_df, visits_df
    except Exception as e:
        st.error(f"Ошибка при чтении файла: {str(e)}")
        st.error("Убедитесь, что файл содержит вкладки: 'Точки', 'Факт_посещений'")
        return None, None

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

def process_visits_data(df):
    """Обрабатывает данные фактических посещений"""
    if df is None or df.empty:
        return pd.DataFrame(columns=['ID_Точки', 'Дата_визита'])
    
    df = df.copy()
    
    # Проверяем и переименовываем колонки
    column_mapping = {
        'ID точки': 'ID_Точки',
        'Дата визита': 'Дата_визита',
        'Дата': 'Дата_визита',
        'Date': 'Дата_визита',
        'Visit Date': 'Дата_визита'
    }
    
    for old_col, new_col in column_mapping.items():
        if old_col in df.columns and new_col not in df.columns:
            df = df.rename(columns={old_col: new_col})
    
    # Проверяем наличие необходимых колонок
    required_cols = ['ID_Точки', 'Дата_визита']
    
    for col in required_cols:
        if col not in df.columns:
            st.warning(f"⚠️ В данных посещений отсутствует колонка: {col}")
            return pd.DataFrame(columns=required_cols)
    
    # Преобразуем даты
    df['Дата_визита'] = pd.to_datetime(df['Дата_визита'], errors='coerce')
    
    # Оставляем только строки с валидными датами
    df = df.dropna(subset=['Дата_визита'])
    
    return df

# Функция для получения ISO номера недели
def get_iso_week(date_obj):
    """Возвращает ISO номер недели для даты"""
    if isinstance(date_obj, pd.Timestamp):
        return date_obj.isocalendar()[1]
    elif isinstance(date_obj, datetime):
        return date_obj.isocalendar()[1]
    else:
        try:
            return datetime.strptime(str(date_obj), '%Y-%m-%d').isocalendar()[1]
        except:
            return 0

# Основная кнопка расчета
if st.button("🚀 Рассчитать план", type="primary", use_container_width=True):
    
    if not uploaded_file:
        st.error("⚠️ Пожалуйста, загрузите файл с данными!")
        st.stop()
    
    try:
        # Загружаем данные из файла
        points_df_raw, visits_df_raw = load_excel_file(uploaded_file)
        
        if points_df_raw is None:
            st.stop()
        
        # Обрабатываем данные
        points_df = process_points_data(points_df_raw)
        visits_df = process_visits_data(visits_df_raw)
        
        if points_df is None:
            st.stop()
        
        # Показываем предпросмотр данных
        st.success("✅ Данные успешно загружены!")
        
        with st.expander("📋 Предпросмотр загруженных данных"):
            tab1, tab2 = st.tabs(["Точки", "Факт посещений"])
            
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
                if not visits_df.empty:
                    st.write(f"Загружено записей о посещениях: {len(visits_df)}")
                    st.dataframe(visits_df.head(10), use_container_width=True)
                    
                    # Статистика по факту
                    earliest_date = visits_df['Дата_визита'].min().strftime('%d.%m.%Y')
                    latest_date = visits_df['Дата_визита'].max().strftime('%d.%m.%Y')
                    st.info(f"Период факта: {earliest_date} - {latest_date}")
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
                    'iso_week_number': iso_week,  # ISO номер недели
                    'start_date': week_start,
                    'end_date': week_end,
                    'work_days_in_quarter': work_days,
                    'is_full_week': work_days == 5
                })
                
                current_date = week_end + timedelta(days=1)
            
            return weeks
        
        # Обрабатываем фактические посещения и связываем с точками
        def process_actual_visits(visits_df, year, quarter, points_df):
            """Обрабатывает фактические посещения и связывает их с точками и неделями"""
            if visits_df.empty:
                return pd.DataFrame(), pd.DataFrame()
            
            # Получаем границы квартала
            quarter_start, quarter_end = get_quarter_dates(year, quarter)
            
            # Фильтруем посещения по кварталу
            visits_in_quarter = visits_df[
                (visits_df['Дата_визита'] >= pd.Timestamp(quarter_start)) &
                (visits_df['Дата_визита'] <= pd.Timestamp(quarter_end))
            ].copy()
            
            if visits_in_quarter.empty:
                return pd.DataFrame(), pd.DataFrame()
            
            # Добавляем ISO номер недели
            visits_in_quarter['iso_week'] = visits_in_quarter['Дата_визита'].apply(get_iso_week)
            
            # Группируем по точкам и неделям (считаем каждую запись как 1 посещение)
            visits_summary_by_week = visits_in_quarter.groupby(['ID_Точки', 'iso_week']).size().reset_index(name='факт_посещений')
            
            # Группируем по точкам (общий факт за квартал)
            visits_summary_total = visits_in_quarter.groupby('ID_Точки').size().reset_index(name='факт_посещений')
            
            return visits_summary_by_week, visits_summary_total
        
        # Обрабатываем фактические посещения
        actual_visits_by_week, actual_visits_total = process_actual_visits(visits_df, year, quarter, points_df)
        
        if not actual_visits_total.empty:
            st.success(f"✅ Загружено {len(actual_visits_total)} уникальных точек с фактическими посещениями за квартал")
        else:
            st.info("ℹ️ Фактические посещения за квартал не найдены или файл пустой")
        
        # Создаем фиктивных аудиторов для демонстрации
        # В реальном приложении это должно загружаться из отдельного файла
        st.info("ℹ️ Созданы фиктивные аудиторы для демонстрации расчета")
        
        # Определяем города из точек
        cities = []
        if not points_df['Город'].isnull().all() and not (points_df['Город'] == '').all():
            cities = points_df['Город'].dropna().unique().tolist()
        
        # Создаем фиктивных аудиторов (по 1 на город)
        fake_auditors = []
        for i, city in enumerate(cities[:5]):  # Ограничим 5 городами для демонстрации
            fake_auditors.append({
                'ID_Сотрудника': f'SOVIAUD{i+10}',
                'Город': city
            })
        
        # Если нет городов, создаем одного аудитора
        if not fake_auditors:
            fake_auditors.append({
                'ID_Сотрудника': 'SOVIAUD10',
                'Город': 'Москва'
            })
        
        auditors_df = pd.DataFrame(fake_auditors)
        
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
            else:
                # Если город не указан, создаем одну запись
                city_statistics.append({
                    'Город': 'Не указан',
                    'Всего_точек': len(points_df),
                    'План_посещений': points_df['Кол-во_посещений'].sum()
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
                if auditor in city_auditors:
                    auditor_index = city_auditors.index(auditor)
                else:
                    continue
                
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
                    if weeks_count > 0:
                        stage_idx = min(3, (weeks.index(week)) // (weeks_count // 4))
                    else:
                        stage_idx = 0
                    
                    # Базовое количество посещений для недели
                    if weeks_count > 0:
                        base_visits = total_visits_actual / weeks_count
                    else:
                        base_visits = 0
                    
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
                            'Аудитор': auditor,
                            'Город': city,
                            'ISO_Неделя': iso_week,
                            'Начало_недели': week['start_date'].strftime('%d.%m.%Y'),
                            'Конец_недели': week['end_date'].strftime('%d.%m.%Y'),
                            'Рабочих_дней': work_days,
                            'План_посещений': week_visits_count
                        })
                        
                        # Детализация по посещениям
                        for visit in week_visits_list:
                            detailed_results.append({
                                'Аудитор': auditor,
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
                    elif work_days > 0 and week_visits_count == 0:
                        # Записываем неделю без посещений
                        results.append({
                            'Аудитор': auditor,
                            'Город': city,
                            'ISO_Неделя': iso_week,
                            'Начало_недели': week['start_date'].strftime('%d.%m.%Y'),
                            'Конец_недели': week['end_date'].strftime('%d.%m.%Y'),
                            'Рабочих_дней': work_days,
                            'План_посещений': 0
                        })
            
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
        
        st.success(f"✅ План рассчитан! Охвачено {len(summary_df['Аудитор'].unique())} сотрудников")
        
        # Объединяем план с фактом
        def merge_plan_with_fact(summary_df, details_df, actual_visits_total):
            """Объединяет плановые данные с фактическими"""
            
            # Для сводной таблицы
            if not summary_df.empty:
                summary_with_fact = summary_df.copy()
                
                # Добавляем факт (пока 0, будет заполняться в след. частях)
                summary_with_fact['Факт_посещений'] = 0
                summary_with_fact['%_выполнения'] = 0
            
            # Для детальной таблицы
            details_with_fact = details_df.copy() if not details_df.empty else pd.DataFrame()
            
            return summary_with_fact, details_with_fact
        
        # Объединяем план с фактом
        summary_with_fact, details_with_fact = merge_plan_with_fact(summary_df, details_df, actual_visits_total)
        
        # Сохраняем данные в session state для использования в других частях
        st.session_state['points_df'] = points_df
        st.session_state['auditors_df'] = auditors_df
        st.session_state['summary_df'] = summary_with_fact
        st.session_state['details_df'] = details_with_fact
        st.session_state['city_stats_df'] = city_stats_df
        st.session_state['weekly_assignments'] = weekly_assignments
        st.session_state['actual_visits_total'] = actual_visits_total
        st.session_state['actual_visits_by_week'] = actual_visits_by_week
        st.session_state['year'] = year
        st.session_state['quarter'] = quarter
        st.session_state['coefficients'] = coefficients
        
        # Показываем первую вкладку результатов
        st.markdown("---")
        st.header("📊 Результаты расчета")
        
        # Вкладка 1: Статистика городов (ОБНОВЛЕНА)
        st.subheader("📊 Статистика по городам")
        
        if not city_stats_df.empty:
            # Общая статистика
            total_points = len(points_df)
            total_plan_visits = points_df['Кол-во_посещений'].sum()
            total_auditors = len(auditors_df)
            
            # Рассчитываем факт из actual_visits_total
            if not actual_visits_total.empty:
                total_fact_visits = actual_visits_total['факт_посещений'].sum()
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
            
            # Считаем факт посещений по городам
            if not actual_visits_total.empty and not points_df.empty:
                # Объединяем точки с фактом посещений
                points_with_fact = points_df.merge(
                    actual_visits_total, 
                    on='ID_Точки', 
                    how='left'
                )
                points_with_fact['факт_посещений'] = points_with_fact['факт_посещений'].fillna(0)
                
                # Группируем по городам
                fact_by_city = points_with_fact.groupby('Город')['факт_посещений'].sum().reset_index()
                
                # Объединяем с city_stats_display
                city_stats_display = city_stats_display.merge(
                    fact_by_city,
                    on='Город',
                    how='left'
                )
                city_stats_display['факт_посещений'] = city_stats_display['факт_посещений'].fillna(0).astype(int)
            else:
                city_stats_display['факт_посещений'] = 0
            
            # Рассчитываем процент выполнения для каждого города
            city_stats_display['%_выполнения'] = city_stats_display.apply(
                lambda row: round((row['факт_посещений'] / row['План_посещений'] * 100) if row['План_посещений'] > 0 else 0, 1),
                axis=1
            )
            
            # Переименовываем колонки
            city_stats_display = city_stats_display.rename(columns={
                'Всего_точек': 'Всего точек',
                'План_посещений': 'План посещений',
                'факт_посещений': 'Факт посещений',
                '%_выполнения': '% выполнения'
            })
            
            # Порядок колонок (согласно требованиям)
            city_stats_display = city_stats_display[['Город', 'Всего точек', 'План посещений', 'Факт посещений', '% выполнения']]
            
            st.dataframe(
                city_stats_display,
                use_container_width=True,
                hide_index=True
            )
            
        # Создаем CSV для скачивания статистики по городам
            csv = city_stats_display.to_csv(index=False, encoding='utf-8-sig')
            b64 = base64.b64encode(csv.encode()).decode()
            href = f'<a href="data:file/csv;base64,{b64}" download="статистика_городов.csv">📥 Скачать CSV</a>'
            st.markdown(href, unsafe_allow_html=True)
            
        else:
            st.info("Нет данных по городам для отображения статистики")
        
        # Показываем остальные вкладки (будут в Части 2, 3, 4)
        st.info("""
        **В следующих частях будут реализованы:**
        
        1. 📅 Сводный план с фильтрами
        2. 📊 Диаграммы с Plotly
        3. 📍 Распределение точек по неделям
        4. 🗺️ Карта с полигонами
        5. 📥 Выгрузка KML и отчетов
        
        *Для продолжения разработки сообщите, что Часть 1 работает корректно.*
        """)
        
    except Exception as e:
        st.error(f"❌ Произошла ошибка при обработке данных: {str(e)}")
        import traceback
        st.error(f"Детали ошибки:\n{traceback.format_exc()}")

# Информация в подвале
st.markdown("---")
st.caption("""
**Версия:** Часть 1/4  
**Статус:** Базовая структура, загрузка данных, расчет плана, статистика по городам  
**Следующая часть:** Сводный план, фильтры, диаграммы

**Примечания:**
1. Для продолжения расчетов загрузите файл и нажмите "Рассчитать"
2. В следующих частях будут реализованы остальные функции
""")

            
