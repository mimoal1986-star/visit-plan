# Сначала ВСЕ импорты из стандартной библиотеки
from functools import lru_cache 

# Потом сторонние библиотеки
import streamlit as st
import pandas as pd
import numpy as np
import math
import io
from datetime import datetime, date, timedelta
import calendar
import json
import base64
from typing import Dict, List, Tuple, Optional, Any, Callable
import warnings
warnings.filterwarnings('ignore')

# ВИЗУАЛИЗАЦИЯ
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ГЕОМЕТРИЯ - используем SciPy если доступен, иначе упрощенную версию
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

# Для расчета рабочих дней с праздниками
try:
    from workalendar.europe import Russia
    WORKALENDAR_AVAILABLE = True
except ImportError:
    WORKALENDAR_AVAILABLE = False

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
# ГЕОМЕТРИЧЕСКИЕ ФУНКЦИИ ДЛЯ СЕТКИ И ПОЛИГОНОВ (ИСПРАВЛЕННАЯ)
# ==============================================

from functools import lru_cache

@lru_cache(maxsize=10000)
def is_point_in_polygon_cached(point_tuple, polygon_tuple):
    """
    Кэшированная проверка точки внутри полигона.
    """
    if not polygon_tuple or len(polygon_tuple) < 3:
        return False
    
    x, y = point_tuple
    inside = False
    n = len(polygon_tuple)
    
    for i in range(n):
        x1, y1 = polygon_tuple[i]
        x2, y2 = polygon_tuple[(i + 1) % n]
        
        if ((y1 > y) != (y2 > y)) and \
           (x < (x2 - x1) * (y - y1) / (y2 - y1) + x1):
            inside = not inside
    
    return inside

def is_point_in_polygon(point, polygon):
    """
    Обертка для кэшированной функции.
    """
    if not polygon or len(polygon) < 3:
        return False
    
    # Преобразуем в кортежи для кэширования
    try:
        point_tuple = (float(point[0]), float(point[1]))
        # Убедимся что polygon - список кортежей
        polygon_tuple = tuple((float(p[0]), float(p[1])) for p in polygon)
        return is_point_in_polygon_cached(point_tuple, polygon_tuple)
    except (ValueError, TypeError, IndexError):
        return False

def is_cell_in_polygon(cell_lat, cell_lon, grid_size, polygon_coords):
    """
    Проверяет что хотя бы часть ячейки внутри полигона.
    """
    # Проверяем 5 точек: 4 угла + центр
    test_points = [
        (cell_lat, cell_lon),  # левый нижний
        (cell_lat + grid_size, cell_lon),  # левый верхний
        (cell_lat, cell_lon + grid_size),  # правый нижний
        (cell_lat + grid_size, cell_lon + grid_size),  # правый верхний
        (cell_lat + grid_size/2, cell_lon + grid_size/2)  # центр
    ]
    
    for point in test_points:
        if is_point_in_polygon(point, polygon_coords):
            return True
    return False

def create_grid_inside_polygon(polygon_coords, grid_size=0.0009):
    """
    Создает сетку ячеек внутри полигона.
    """
    if not polygon_coords or len(polygon_coords) < 3:
        return None
    
    try:
        # Bounding box полигона
        lats = [float(p[0]) for p in polygon_coords]
        lons = [float(p[1]) for p in polygon_coords]
        
        min_lat, max_lat = min(lats), max(lats)
        min_lon, max_lon = min(lons), max(lons)
        
        # Добавляем небольшой запас
        eps = grid_size * 0.1
        min_lat -= eps
        max_lat += eps
        min_lon -= eps
        max_lon += eps
        
        # Начальные координаты сетки
        start_lat = math.floor(min_lat / grid_size) * grid_size
        start_lon = math.floor(min_lon / grid_size) * grid_size
        
        # Рассчитываем размеры сетки
        width_cells = int(math.ceil((max_lon - start_lon) / grid_size))
        height_cells = int(math.ceil((max_lat - start_lat) / grid_size))
        
        cells = []
        cell_index = {}  # Для быстрого поиска
        
        # Создаем все возможные ячейки в bounding box
        for i in range(height_cells):
            for j in range(width_cells):
                cell_lat = start_lat + i * grid_size
                cell_lon = start_lon + j * grid_size
                
                # Проверяем, что ячейка хотя бы частично внутри полигона
                if is_cell_in_polygon(cell_lat, cell_lon, grid_size, polygon_coords):
                    cell_data = {
                        'grid_x': i,
                        'grid_y': j,
                        'center': (cell_lat + grid_size/2, cell_lon + grid_size/2),
                        'lat': cell_lat,
                        'lon': cell_lon,
                        'lat_end': cell_lat + grid_size,
                        'lon_end': cell_lon + grid_size
                    }
                    cells.append(cell_data)
                    
                    # Добавляем в индекс
                    cell_key = f"{i}_{j}"
                    cell_index[cell_key] = cell_data
        
        if not cells:
            return None
        
        return {
            'bbox': (min_lat, max_lat, min_lon, max_lon),
            'grid_size': grid_size,
            'cells': cells,
            'cell_index': cell_index,  # Быстрый поиск
            'width': width_cells,
            'height': height_cells,
            'start_lat': start_lat,
            'start_lon': start_lon
        }
        
    except Exception as e:
        print(f"Ошибка при создании сетки: {e}")
        return None

def assign_points_to_grid_cells(points_coords, point_ids, grid):
    """
    Распределяет точки по ячейкам сетки.
    """
    if not grid or not points_coords or not point_ids:
        return {}
    
    if len(points_coords) != len(point_ids):
        print(f"Предупреждение: {len(points_coords)} координат != {len(point_ids)} ID")
        return {}
    
    cell_to_points = {}
    grid_size = grid['grid_size']
    start_lat = grid['start_lat']
    start_lon = grid['start_lon']
    cell_index = grid.get('cell_index', {})
    
    for i, (point_coord, point_id) in enumerate(zip(points_coords, point_ids)):
        try:
            lat, lon = float(point_coord[0]), float(point_coord[1])
            
            # Определяем ячейку
            grid_x = int((lat - start_lat) / grid_size)
            grid_y = int((lon - start_lon) / grid_size)
            
            cell_key = f"{grid_x}_{grid_y}"
            
            # Проверяем, что ячейка существует в сетке
            if cell_key in cell_index:
                if cell_key not in cell_to_points:
                    cell_to_points[cell_key] = []
                cell_to_points[cell_key].append(point_id)
            else:
                # Точка вне сетки (на границе или ошибка)
                print(f"Точка {point_id} вне сетки: {lat}, {lon}")
                
        except (ValueError, TypeError, IndexError) as e:
            print(f"Пропущена точка {i}: {e}")
            continue
    
    return cell_to_points

def get_cell_neighbors(cell_key, grid):
    """
    Возвращает 4 соседа ячейки (север, юг, восток, запад).
    Проверяет существование соседей.
    """
    try:
        grid_x, grid_y = map(int, cell_key.split('_'))
        cell_index = grid.get('cell_index', {})
        
        neighbor_keys = [
            f"{grid_x}_{grid_y + 1}",  # север
            f"{grid_x}_{grid_y - 1}",  # юг
            f"{grid_x + 1}_{grid_y}",  # восток
            f"{grid_x - 1}_{grid_y}",  # запад
        ]
        
        # Возвращаем только существующих соседей
        valid_neighbors = []
        for key in neighbor_keys:
            if key in cell_index:
                valid_neighbors.append(key)
        
        return valid_neighbors
        
    except Exception as e:
        print(f"Ошибка при поиске соседей ячейки {cell_key}: {e}")
        return []

# ==============================================
# УПРОЩЕННЫЕ ФУНКЦИИ ДЛЯ АЛГОРИТМА КЛАСТЕРИЗАЦИИ (ЭТАП 2)
# ==============================================

def find_initial_boundary_simple(grid, polygon_coords):
    """
    Упрощенный поиск граничных ячеек.
    Граничная = имеет хотя бы одного соседа, которого нет в сетке.
    """
    if not grid or not polygon_coords:
        return set()
    
    boundary_cells = set()
    cell_index = grid.get('cell_index', {})
    
    for cell_key in cell_index.keys():
        try:
            x, y = map(int, cell_key.split('_'))
            
            # Проверяем 4 соседа
            neighbors = [
                f"{x}_{y+1}",  # север
                f"{x}_{y-1}",  # юг  
                f"{x+1}_{y}",  # восток
                f"{x-1}_{y}",  # запад
            ]
            
            # Если хоть один сосед отсутствует в сетке - ячейка граничная
            for neighbor_key in neighbors:
                if neighbor_key not in cell_index:
                    boundary_cells.add(cell_key)
                    break
                    
        except (ValueError, AttributeError):
            continue
    
    return boundary_cells

def sort_boundary_by_northwest(boundary_cells, grid):
    """
    Сортирует граничные ячейки от северо-запада к юго-востоку.
    """
    if not boundary_cells:
        return []
    
    cells_with_coords = []
    cell_index = grid.get('cell_index', {})
    
    for cell_key in boundary_cells:
        if cell_key in cell_index:
            cell = cell_index[cell_key]
            cells_with_coords.append({
                'key': cell_key,
                'x': cell['grid_x'],
                'y': cell['grid_y'],
                'lat': cell['center'][0],
                'lon': cell['center'][1]
            })
    
    if not cells_with_coords:
        return []
    
    # Сортируем: сначала по широте (север → юг), потом по долготе (запад → восток)
    sorted_cells = sorted(cells_with_coords, 
                         key=lambda c: (-c['lat'], c['lon']))
    
    return [cell['key'] for cell in sorted_cells]

def find_next_start_cell_simple(ordered_boundary, used_cells):
    """
    Упрощенный поиск стартовой ячейки.
    """
    if not ordered_boundary:
        return None
    
    for cell_key in ordered_boundary:
        if cell_key not in used_cells:
            return cell_key
    
    return None

def update_boundary_simple(boundary_cells, cluster_cells, grid):
    """
    Упрощенное обновление границы.
    """
    if not boundary_cells:
        return set()
    
    # Удаляем использованные ячейки
    new_boundary = set(boundary_cells)
    new_boundary.difference_update(cluster_cells)
    
    cell_index = grid.get('cell_index', {})
    
    # Для каждой ячейки кластера проверяем ее соседей
    for cell_key in cluster_cells:
        try:
            x, y = map(int, cell_key.split('_'))
            
            neighbors = [
                f"{x}_{y+1}",  # север
                f"{x}_{y-1}",  # юг
                f"{x+1}_{y}",  # восток  
                f"{x-1}_{y}",  # запад
            ]
            
            for neighbor_key in neighbors:
                # Если сосед в сетке и еще не в границе и не в кластере
                if (neighbor_key in cell_index and 
                    neighbor_key not in new_boundary and
                    neighbor_key not in cluster_cells):
                    new_boundary.add(neighbor_key)
                    
        except (ValueError, AttributeError):
            continue
    
    return new_boundary

def get_cell_neighbors_4(cell_key):
    """
    Возвращает 4 соседа ячейки (север, юг, восток, запад).
    """
    try:
        x, y = map(int, cell_key.split('_'))
        return [
            f"{x}_{y+1}",  # север
            f"{x}_{y-1}",  # юг
            f"{x+1}_{y}",  # восток
            f"{x-1}_{y}",  # запад
        ]
    except (ValueError, AttributeError):
        return []

def find_additional_cells(grid, used_cells, polygon_coords, needed_points):
    """
    Ищет дополнительные ячейки для завершения кластера.
    """
    additional_cells = []
    cell_index = grid.get('cell_index', {})
    
    # Ищем все неиспользованные ячейки
    for cell_key, cell in cell_index.items():
        if cell_key in used_cells:
            continue
        
        # Проверяем что ячейка внутри полигона
        cell_center = cell['center']
        if is_point_in_polygon(cell_center, polygon_coords):
            additional_cells.append(cell_key)
        
        if len(additional_cells) >= needed_points * 2:  # Берем с запасом
            break
    
    return additional_cells

def build_simple_cluster(start_cell_key, target_points, grid, cell_to_points, used_cells, polygon_coords, logger=None):
    """
    Фикс: ограничиваем максимальный размер кластера.
    Вместо 900+ ячеек для 10 точек.
    """
    if start_cell_key in used_cells:
        if logger:
            logger(f"Ячейка {start_cell_key} уже использована")
        return [], []
    
    if start_cell_key not in grid.get('cell_index', {}):
        if logger:
            logger(f"Ячейка {start_cell_key} не существует в сетке")
        return [], []
    
    cluster_cells = []
    cluster_points = []
    queue = [start_cell_key]
    visited = set([start_cell_key])
    
    # ОГРАНИЧЕНИЕ: максимум в 3 раза больше ячеек чем нужно точек
    # Было: 207 ячеек для 10 точек → станет: максимум 30 ячеек
    MAX_CLUSTER_SIZE = max(target_points * 3, 10)  # Минимум 10 ячеек
    
    while queue and len(cluster_cells) < MAX_CLUSTER_SIZE and len(cluster_points) < target_points:
        cell_key = queue.pop(0)
        
        if cell_key in used_cells:
            continue
        
        # Добавляем ячейку в кластер
        cluster_cells.append(cell_key)
        used_cells.add(cell_key)
        
        # Добавляем точки из этой ячейки (если есть)
        if cell_key in cell_to_points:
            cluster_points.extend(cell_to_points[cell_key])
            if logger and cell_to_points[cell_key]:
                logger(f"  Ячейка {cell_key}: {len(cell_to_points[cell_key])} точек")
        
        # Если набрали достаточно точек - можно остановиться раньше
        if len(cluster_points) >= target_points:
            break
        
        # Добавляем соседей (BFS)
        neighbors = get_cell_neighbors_4(cell_key)
        for neighbor_key in neighbors:
            if (neighbor_key in grid['cell_index'] and 
                neighbor_key not in used_cells and
                neighbor_key not in visited):
                
                # Проверяем что ячейка внутри полигона
                neighbor_cell = grid['cell_index'][neighbor_key]
                if is_point_in_polygon(neighbor_cell['center'], polygon_coords):
                    queue.append(neighbor_key)
                    visited.add(neighbor_key)
    
    if logger:
        logger(f"Создан кластер: {len(cluster_cells)} ячеек, {len(cluster_points)} точек")
    
    # Если не набрали достаточно точек, ищем дополнительные ячейки С ТОЧКАМИ
    if len(cluster_points) < target_points:
        needed = target_points - len(cluster_points)
        if logger:
            logger(f"Не хватает {needed} точек, ищем дополнительные ячейки...")
        
        # Ищем ближайшие ячейки с точками
        additional_found = 0
        for cell_key in grid['cell_index']:
            if cell_key in used_cells:
                continue
            
            # Берем только ячейки с точками
            if cell_key in cell_to_points and cell_to_points[cell_key]:
                # Проверяем что ячейка внутри полигона
                cell = grid['cell_index'][cell_key]
                if is_point_in_polygon(cell['center'], polygon_coords):
                    cluster_cells.append(cell_key)
                    cluster_points.extend(cell_to_points[cell_key])
                    used_cells.add(cell_key)
                    additional_found += len(cell_to_points[cell_key])
                    
                    if logger:
                        logger(f"  Добавлена ячейка {cell_key}: {len(cell_to_points[cell_key])} точек")
                    
                    if len(cluster_points) >= target_points:
                        break
        
        if logger and additional_found > 0:
            logger(f"Найдено дополнительно {additional_found} точек")
    
    return cluster_cells, cluster_points[:target_points] if cluster_points else []

def cluster_from_perimeter_to_center_simple(polygon_coords, grid, cell_to_points, weekly_targets, logger=None):
    """
    Упрощенный алгоритм кластеризации "от границы к центру".
    """
    if logger:
        logger(f"Начинаем кластеризацию: {len(weekly_targets)} недель")
    
    # 1. Проверка входных данных
    if not polygon_coords or not grid or not cell_to_points or not weekly_targets:
        if logger:
            logger("❌ Недостаточно данных для кластеризации")
        return {}
    
    total_points = sum(len(pts) for pts in cell_to_points.values())
    total_target = sum(weekly_targets)
    
    if total_points < total_target:
        if logger:
            logger(f"⚠️ Предупреждение: точек ({total_points}) меньше чем цель ({total_target})")
    
    # 2. Инициализация
    week_assignment = {}
    used_cells = set()
    
    # 3. Находим начальную границу
    boundary_cells = find_initial_boundary_simple(grid, polygon_coords)
    
    if not boundary_cells:
        if logger:
            logger("⚠️ Нет граничных ячеек")
        return {}
    
    # 4. Сортируем границу
    ordered_boundary = sort_boundary_by_northwest(boundary_cells, grid)
    
    if logger:
        logger(f"Найдено {len(boundary_cells)} граничных ячеек")
    
    # 5. Создаем кластеры для каждой недели
    for week_idx, target_points in enumerate(weekly_targets):
        if target_points <= 0:
            if logger:
                logger(f"Неделя {week_idx}: цель = 0 точек, пропускаем")
            week_assignment[str(week_idx)] = []
            continue
        
        if logger:
            logger(f"Неделя {week_idx}: цель = {target_points} точек")
        
        # Находим ячейку для старта кластера
        start_cell = find_next_start_cell_simple(ordered_boundary, used_cells)
        
        if not start_cell:
            if logger:
                logger(f"⚠️ Неделя {week_idx}: нет доступных ячеек для старта")
            week_assignment[str(week_idx)] = []
            break
        
        # Создаем кластер
        cluster_cells, cluster_points = build_simple_cluster(
            start_cell, target_points, grid, cell_to_points, 
            used_cells, polygon_coords, logger
        )
        
        # Сохраняем результат (даже если пустой)
        week_assignment[str(week_idx)] = cluster_points
        
        if cluster_cells:
            used_cells.update(cluster_cells)
            
            # Обновляем границу
            ordered_boundary = list(update_boundary_simple(set(ordered_boundary), cluster_cells, grid))
            
            if logger:
                logger(f"✅ Неделя {week_idx}: создан кластер из {len(cluster_points)} точек")
        else:
            if logger:
                logger(f"⚠️ Неделя {week_idx}: не удалось создать кластер")
    
    # 6. Проверяем результат
    total_assigned = sum(len(pts) for pts in week_assignment.values())
    
    if logger:
        logger(f"Итог: распределено {total_assigned} из {total_points} точек")
        
        # Логируем распределение по неделям
        for week_idx, points in week_assignment.items():
            logger(f"  Неделя {week_idx}: {len(points)} точек")
    
    return week_assignment

def fallback_simple_distribution(point_ids, num_weeks):
    """
    Простое распределение точек по неделям (fallback).
    """
    if not point_ids or num_weeks <= 0:
        return {}
    
    week_assignment = {}
    points_per_week = len(point_ids) // num_weeks
    remainder = len(point_ids) % num_weeks
    
    start_idx = 0
    for week in range(num_weeks):
        week_size = points_per_week + (1 if week < remainder else 0)
        end_idx = start_idx + week_size
        
        if start_idx < len(point_ids):
            week_assignment[str(week)] = point_ids[start_idx:end_idx]
            start_idx = end_idx
        else:
            week_assignment[str(week)] = []
    
    return week_assignment


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

    st.markdown("---")
    
    st.subheader("🎯 Алгоритм разбиения")
    use_enhanced_split = st.checkbox(
        "Использовать улучшенное разбиение по неделям", 
        value=False,
        help="Разбивает полигоны аудиторов на компактные недельные области с балансировкой ±3 точки"
    )


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
# КЛАСС ДЛЯ ОПТИМИЗАЦИИ МАРШРУТОВ ПО ДНЯМ
# ==============================================

class WeeklyRouteOptimizer:
    """
    Оптимизатор маршрутов на основе логики из optimizer.py
    Распределяет точки по дням недели и строит оптимальные маршруты
    """
    
    @staticmethod
    def calculate_distance(lat1, lon1, lat2, lon2):
        """Расчет расстояния в КИЛОМЕТРАХ между точками"""
        # 1 градус широты = 111 км
        km_per_lat = 111.0
        
        # Средняя широта для расчета масштаба долготы
        avg_lat = (lat1 + lat2) / 2
        km_per_lon = 111.0 * math.cos(math.radians(avg_lat))
        
        # Разница в километрах
        lat_km = (lat2 - lat1) * km_per_lat
        lon_km = (lon2 - lon1) * km_per_lon
        
        # Прямоугольное расстояние (проще для городов)
        distance_km = abs(lat_km) + abs(lon_km)
        
        return distance_km
    
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

def simple_cluster_points(points, n_clusters):
    """
    Простая кластеризация без sklearn
    """
    if not points or n_clusters <= 0:
        return [[] for _ in range(n_clusters)] if n_clusters > 0 else []
    
    if len(points) <= n_clusters:
        # Каждая точка в своей группе
        clusters = [[p] for p in points]
        # Добавляем пустые группы если нужно
        while len(clusters) < n_clusters:
            clusters.append([])
        return clusters
    
    # Выбираем начальные центры
    centers = []
    
    # Первый центр - первая точка
    if points:
        centers.append(points[0])
    
    # Остальные центры - самые удаленные
    for _ in range(1, min(n_clusters, len(points))):
        max_min_distance = -1
        best_point = None
        
        for point in points:
            if point in centers:
                continue
            
            # Минимальное расстояние до существующих центров
            min_dist = float('inf')
            for center in centers:
                dist = WeeklyRouteOptimizer.calculate_distance(
                    point['Широта'], point['Долгота'],
                    center['Широта'], center['Долгота']
                )
                min_dist = min(min_dist, dist)
            
            if min_dist > max_min_distance:
                max_min_distance = min_dist
                best_point = point
        
        if best_point:
            centers.append(best_point)
        else:
            # Если не нашли, берем любую неиспользованную
            for point in points:
                if point not in centers:
                    centers.append(point)
                    break
    
    # Если не набрали достаточно центров
    while len(centers) < n_clusters:
        centers.append(points[0])  # дублируем первую точку
    
    # Назначаем точки ближайшим центрам
    clusters = [[] for _ in range(n_clusters)]
    
    for point in points:
        # Находим ближайший центр
        min_dist = float('inf')
        nearest_idx = 0
        
        for i, center in enumerate(centers):
            dist = WeeklyRouteOptimizer.calculate_distance(
                point['Широта'], point['Долгота'],
                center['Широта'], center['Долгота']
            )
            if dist < min_dist:
                min_dist = dist
                nearest_idx = i
        
        if 0 <= nearest_idx < n_clusters:
            clusters[nearest_idx].append(point)
    
    return clusters

def create_daily_routes_for_auditor(auditor_points, working_days, auditor_id):

        # ДИАГНОСТИКА
    print(f"=== create_daily_routes_for_auditor ===")
    print(f"Аудитор: {auditor_id}")
    print(f"Получено точек: {len(auditor_points)}")
    print(f"Получено рабочих дней: {len(working_days)}")
    print(f"Дни недели: {[d.strftime('%Y-%m-%d (%a)') for d in working_days]}")
    
    if not auditor_points or not working_days:
        print("❌ Пустые входные данные!")
        return []
    """
    УНИВЕРСАЛЬНЫЙ АЛГОРИТМ ДЛЯ ГОРОДОВ-МИЛЛИОННИКОВ РОССИИ
    С ПРОСТЫМ ГЕОГРАФИЧЕСКИМ РАЙОНИРОВАНИЕМ
    """
    try:
        if not auditor_points or not working_days:
            return []
        
        K = len(working_days)
        if K == 0:
            return []
        
        # 1. Валидация точек
        valid_points = []
        for point in auditor_points:
            try:
                lat = float(point['Широта'])
                lon = float(point['Долгота'])
                if 41 <= lat <= 82 and 19 <= lon <= 180:
                    valid_points.append(point)
            except:
                continue
        
        if not valid_points:
            return []
        
        # 2. Если точек мало
        if len(valid_points) <= K:
            return simple_distribute_points(valid_points, working_days, auditor_id)
        
        # 3. ПРОСТОЙ И ЭФФЕКТИВНЫЙ АЛГОРИТМ
        def spatial_hash(point):
            """Пространственный хеш для группировки близких точек"""
            lat = point['Широта']
            lon = point['Долгота']
            # Квадратные ячейки примерно 1.1x1.1 км
            cell_size = 0.01  # ~1.1 км
            lat_cell = int(lat / cell_size)
            lon_cell = int(lon / cell_size)
            return f"{lat_cell}_{lon_cell}"
        
        # Группируем по пространственным ячейкам
        cells = {}
        for point in valid_points:
            cell = spatial_hash(point)
            if cell not in cells:
                cells[cell] = []
            cells[cell].append(point)
        
        # Сортируем ячейки по географическому положению
        sorted_cells = sorted(cells.items(), 
                            key=lambda x: (-float(x[0].split('_')[0]),  # север→юг
                                           float(x[0].split('_')[1])))  # запад→восток
        
        # 4. Распределяем ячейки по дням
        daily_groups = [[] for _ in range(K)]
        cell_idx = 0
        
        for cell_key, cell_points in sorted_cells:
            # Добавляем всю ячейку в один день
            day_idx = cell_idx % K
            daily_groups[day_idx].extend(cell_points)
            cell_idx += 1
        
        # 5. Создаем маршруты
        routes = []
        
        for day_idx, (day_date, day_points) in enumerate(zip(working_days, daily_groups)):
            if not day_points:
                continue
            
            # Обработка даты
            visit_datetime = day_date
            if isinstance(day_date, date) and not isinstance(day_date, datetime):
                visit_datetime = datetime.combine(day_date, datetime.min.time())
            
            for order, point in enumerate(day_points, 1):
                routes.append({
                    'ID_Точки': point['ID_Точки'],
                    'Дата': visit_datetime,
                    'День_недели': visit_datetime.weekday(),
                    'Аудитор': auditor_id,
                    'Широта': point['Широта'],
                    'Долгота': point['Долгота'],
                    'Название_Точки': point.get('Название_Точки', point['ID_Точки']),
                    'Адрес': point.get('Адрес', ''),
                    'Тип': point.get('Тип', 'Неизвестно'),
                    'Порядок_в_дне': order
                })
        
        return routes
    
    except Exception as e:
        st.error(f"❌ Ошибка в create_daily_routes_for_auditor: {str(e)}")
        return []


def simple_distribute_points(points, working_days, auditor_id):
    """Простое распределение точек по дням"""
    routes = []
    
    for i, point in enumerate(points):
        if i >= len(working_days):
            break
        
        day_date = working_days[i]
        if isinstance(day_date, date) and not isinstance(day_date, datetime):
            visit_datetime = datetime.combine(day_date, datetime.min.time())
        else:
            visit_datetime = day_date
        
        routes.append({
            'ID_Точки': point['ID_Точки'],
            'Дата': visit_datetime,
            'День_недели': visit_datetime.weekday(),
            'Аудитор': auditor_id,
            'Широта': point['Широта'],
            'Долгота': point['Долгота'],
            'Название_Точки': point.get('Название_Точки', point['ID_Точки']),
            'Адрес': point.get('Адрес', ''),
            'Тип': point.get('Тип', 'Неизвестно'),
            'Порядок_в_дне': 1  # ДОБАВЛЕНО
        })
    
    return routes


def balance_clusters_simple(clusters, target_k):
    """Простая балансировка кластеров"""
    # Собираем все точки
    all_points = []
    for cluster in clusters:
        all_points.extend(cluster)
    
    if len(all_points) == 0:
        return [[] for _ in range(target_k)]
    
    # Сортируем по географии
    sorted_points = sort_points_spatially(points)
    
    # Распределяем равномерно
    balanced = [[] for _ in range(target_k)]
    for i, point in enumerate(sorted_points):
        balanced[i % target_k].append(point)
    
    return balanced


def simple_geographic_distribution(points, working_days, auditor_id):
    """Простое географическое распределение"""
    if not points or not working_days:
        return []
    
    K = len(working_days)
    
# УЛУЧШЕННАЯ СОРТИРОВКА ДЛЯ КОМПАКТНЫХ ЗОН
    def spatial_sort_key(point):
        """
        Сортировка создающая КВАДРАТНЫЕ зоны:
        1. Группируем точки в "ряды" по широте (~1.1 км)
        2. Внутри ряда сортируем по долготе
        """
        lat = point['Широта']
        lon = point['Долгота']
        
        # Группируем в полосы по 0.01° (~1.1 км в РФ)
        # Это создаст горизонтальные полосы на карте
        lat_row = int(lat / 0.01)
        
        # Сортируем: сначала по рядам (север→юг), 
        # потом внутри ряда (запад→восток)
        return (-lat_row, lon)
    
    # Используем улучшенную сортировку
    sorted_points = sorted(points, key=spatial_sort_key)
    
    # Делим на части
    daily_clusters = []
    base_size = len(sorted_points) // K
    remainder = len(sorted_points) % K
    
    start_idx = 0
    for day_idx in range(K):
        size = base_size + (1 if day_idx < remainder else 0)
        end_idx = start_idx + size
        
        if start_idx < len(sorted_points):
            daily_clusters.append(sorted_points[start_idx:end_idx])
            start_idx = end_idx
        else:
            daily_clusters.append([])
    
    # Строим маршруты
    routes = []
    for day_idx, (day_date, cluster_points) in enumerate(zip(working_days, daily_clusters)):
        if not cluster_points:
            continue
        
        if isinstance(day_date, date) and not isinstance(day_date, datetime):
            visit_datetime = datetime.combine(day_date, datetime.min.time())
        else:
            visit_datetime = day_date
        
        for point in cluster_points:
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
    
# ==============================================
# ФУНКЦИИ ДЛЯ СОЗДАНИЯ ВЫХОДНОЙ ТАБЛИЦЫ
# ==============================================

# ==============================================
# ИСПРАВЛЕННЫЙ МОДУЛЬ: РАЗБИЕНИЕ ПОЛИГОНА ПО НЕДЕЛЯМ (БЕЗ STREAMLIT)
# ==============================================

# Добавьте эти импорты в НАЧАЛО модуля:
import numpy as np
from typing import Dict, List, Tuple, Optional, Callable
import warnings


def detect_outliers_simple(points: np.ndarray, centroid: np.ndarray, 
                          threshold_multiplier: float = 2.0) -> Tuple[List[int], List[int]]:
    """Простой метод определения выбросов по расстоянию до центроида"""
    if len(points) == 0:
        return [], []
    
    try:
        # Вычисляем расстояния до центроида
        distances = np.sqrt(np.sum((points - centroid) ** 2, axis=1))
        
        # Среднее расстояние + порог
        mean_dist = np.mean(distances)
        std_dist = np.std(distances) if len(distances) > 1 else 0
        
        if std_dist == 0:
            # Все точки на одинаковом расстоянии
            return list(range(len(points))), []
        
        threshold = mean_dist + threshold_multiplier * std_dist
        
        normal_indices = np.where(distances <= threshold)[0].tolist()
        outlier_indices = np.where(distances > threshold)[0].tolist()
        
        return normal_indices, outlier_indices
    except:
        # Если что-то пошло не так, считаем все точки нормальными
        return list(range(len(points))), []


def calculate_weekly_targets_simple(total_points: int, num_weeks: int, 
                                   coefficients: List[float]) -> List[int]:
    """Упрощенный расчет целевого количества точек"""
    if total_points <= 0 or num_weeks <= 0:
        return []
    
    if len(coefficients) < 4:
        coefficients = [1.0] * 4
    
    # Простая логика распределения
    if num_weeks <= 4:
        # Используем коэффициенты напрямую
        normalized = [c / sum(coefficients[:num_weeks]) for c in coefficients[:num_weeks]]
    else:
        # Распределяем коэффициенты циклически
        weekly_coeffs = []
        for i in range(num_weeks):
            weekly_coeffs.append(coefficients[i % 4])
        total_coeff = sum(weekly_coeffs)
        normalized = [c / total_coeff for c in weekly_coeffs]
    
    # Рассчитываем цели
    targets = []
    remaining = total_points
    
    for i in range(num_weeks):
        if i == num_weeks - 1:
            target = remaining  # Последняя неделя получает остаток
        else:
            target = max(1, int(round(total_points * normalized[i])))
            remaining -= target
        
        targets.append(target)
    
    # Корректируем если нужно
    total_assigned = sum(targets)
    if total_assigned != total_points:
        diff = total_points - total_assigned
        if diff != 0 and targets:
            targets[-1] += diff
    
    return targets


def initialize_clusters_simple(polygon: np.ndarray, num_clusters: int, 
                              points: np.ndarray) -> np.ndarray:
    """Простая инициализация центров кластеров"""
    if len(points) == 0:
        return np.array([])
    
    if len(points) <= num_clusters:
        return points.copy()
    
    try:
        # Пробуем использовать вершины полигона если возможно
        if len(polygon) >= num_clusters:
            # Выбираем равномерно распределенные точки полигона
            indices = np.linspace(0, len(polygon) - 1, num_clusters, dtype=int)
            return polygon[indices]
        else:
            # Случайные точки из данных
            np.random.seed(42)  # Для воспроизводимости
            indices = np.random.choice(len(points), num_clusters, replace=False)
            return points[indices]
    except:
        # Fallback: первые num_clusters точек
        return points[:num_clusters]


def simple_balanced_kmeans(points: np.ndarray, point_ids: List[str], 
                          num_clusters: int, initial_centers: np.ndarray,
                          weekly_targets: List[int], logger: Callable) -> Tuple[Dict, Dict]:
    """Упрощенный балансированный k-means"""
    n_points = len(points)
    
    if n_points == 0 or num_clusters <= 0:
        return {}, {}
    
    # Инициализация центров
    centers = initial_centers.copy()
    if len(centers) < num_clusters:
        # Дополняем если нужно
        needed = num_clusters - len(centers)
        if n_points >= needed:
            indices = np.random.choice(n_points, needed, replace=False)
            centers = np.vstack([centers, points[indices]])
    
    # Простой k-means
    for iteration in range(30):  # Максимум 30 итераций
        # Шаг 1: Назначение точек по ближайшему центру
        assignments = np.zeros(n_points, dtype=int)
        for i, point in enumerate(points):
            distances = np.sqrt(np.sum((centers - point) ** 2, axis=1))
            assignments[i] = np.argmin(distances)
        
        # Шаг 2: Балансировка
        assignments = simple_balance_assignments(assignments, weekly_targets, points, centers)
        
        # Шаг 3: Обновление центров
        new_centers = centers.copy()
        for i in range(num_clusters):
            cluster_points = points[assignments == i]
            if len(cluster_points) > 0:
                new_centers[i] = np.mean(cluster_points, axis=0)
            else:
                # Если кластер пуст, перемещаем центр к случайной точке
                idx = np.random.randint(0, n_points)
                new_centers[i] = points[idx]
        
        # Шаг 4: Проверка сходимости
        if np.max(np.sqrt(np.sum((centers - new_centers) ** 2, axis=1))) < 0.001:
            break
        
        centers = new_centers
    
    # Формируем результат
    week_assignments = {}
    week_clusters = {}
    
    for week in range(num_clusters):
        week_mask = assignments == week
        week_point_ids = [point_ids[i] for i in range(n_points) if week_mask[i]]
        
        if week_point_ids:
            week_points = points[week_mask]
            week_assignments[week] = week_point_ids
            
            # Вычисляем центроид
            centroid = np.mean(week_points, axis=0) if len(week_points) > 0 else centers[week]
            
            # Вычисляем компактность (среднее расстояние до центроида)
            if len(week_points) > 0:
                distances = np.sqrt(np.sum((week_points - centroid) ** 2, axis=1))
                compactness = np.mean(distances)
            else:
                compactness = 0
            
            week_clusters[week] = {
                'centroid': centroid.tolist(),
                'size': len(week_points),
                'compactness': float(compactness)
            }
    
    return week_assignments, week_clusters


def simple_balance_assignments(assignments: np.ndarray, targets: List[int],
                              points: np.ndarray, centers: np.ndarray) -> np.ndarray:
    """Простая балансировка назначений"""
    n_clusters = len(targets)
    current_counts = np.bincount(assignments, minlength=n_clusters)
    
    # Создаем копию для модификации
    balanced = assignments.copy()
    
    # Для каждого кластера проверяем баланс
    for cluster in range(n_clusters):
        current = current_counts[cluster]
        target = targets[cluster]
        
        if current > target + 3:  # Слишком много точек
            excess = current - (target + 3)
            cluster_indices = np.where(balanced == cluster)[0]
            
            # Находим самые дальние точки от центра
            if len(cluster_indices) > 0:
                distances = np.sqrt(np.sum((points[cluster_indices] - centers[cluster]) ** 2, axis=1))
                # Сортируем по убыванию расстояния
                far_indices = cluster_indices[np.argsort(distances)[::-1]]
                
                # Перемещаем excess самых дальних точек
                moved = 0
                for idx in far_indices:
                    if moved >= excess:
                        break
                    
                    # Находим ближайший другой кластер с дефицитом
                    point = points[idx]
                    best_new_cluster = -1
                    best_dist = float('inf')
                    
                    for other_cluster in range(n_clusters):
                        if other_cluster == cluster:
                            continue
                        if current_counts[other_cluster] < targets[other_cluster]:
                            dist = np.sqrt(np.sum((point - centers[other_cluster]) ** 2))
                            if dist < best_dist:
                                best_dist = dist
                                best_new_cluster = other_cluster
                    
                    if best_new_cluster != -1:
                        balanced[idx] = best_new_cluster
                        current_counts[cluster] -= 1
                        current_counts[best_new_cluster] += 1
                        moved += 1
    
    return balanced


def attach_outliers_simple(outlier_points: np.ndarray, outlier_ids: List[str],
                          week_clusters: Dict, week_assignments: Dict) -> Dict:
    """Прикрепление выбросов к ближайшим кластерам"""
    if len(outlier_points) == 0:
        return week_assignments
    
    for i, point in enumerate(outlier_points):
        point_id = outlier_ids[i]
        min_dist = float('inf')
        best_week = -1
        
        # Находим ближайший кластер
        for week, cluster_info in week_clusters.items():
            centroid = np.array(cluster_info['centroid'])
            dist = np.sqrt(np.sum((point - centroid) ** 2))
            if dist < min_dist:
                min_dist = dist
                best_week = week
        
        # Добавляем точку к ближайшему кластеру
        if best_week != -1:
            if best_week not in week_assignments:
                week_assignments[best_week] = []
            week_assignments[best_week].append(point_id)
    
    return week_assignments


def fallback_geographic_split(points_coords: List[List[float]], 
                             point_ids: List[str], 
                             num_weeks: int, 
                             coefficients: List[float]) -> Tuple[Dict, Dict]:
    """Фолбэк: простое географическое разбиение"""
    if not points_coords or not point_ids or num_weeks <= 0:
        return {}, {}
    
    try:
        points_np = np.array(points_coords, dtype=float)
    except:
        return {}, {}
    
    # Сортируем по широте (север-юг), затем по долготе (запад-восток)
    if len(points_np) > 0:
        # Используем устойчивую сортировку
        sorted_indices = np.lexsort((points_np[:, 1], points_np[:, 0]))  # lat, lon
    else:
        return {}, {}
    
    week_assignments = {}
    week_clusters = {}
    
    points_per_week = len(points_coords) // num_weeks
    remainder = len(points_coords) % num_weeks
    
    start_idx = 0
    for week in range(num_weeks):
        week_size = points_per_week + (1 if week < remainder else 0)
        end_idx = min(start_idx + week_size, len(points_coords))
        
        if start_idx < len(points_coords):
            week_indices = sorted_indices[start_idx:end_idx]
            week_point_ids = [point_ids[idx] for idx in week_indices]
            
            week_assignments[week] = week_point_ids
            
            # Вычисляем центроид
            if len(week_indices) > 0:
                week_points = points_np[week_indices]
                centroid = np.mean(week_points, axis=0)
                week_clusters[week] = {
                    'centroid': centroid.tolist(),
                    'size': len(week_points),
                    'compactness': 0.0
                }
            
            start_idx = end_idx
    
    return week_assignments, week_clusters
                                 
# ==============================================
# ФУНКЦИЯ ДЛЯ РАЗБИЕНИЯ ПОЛИГОНА ПО НЕДЕЛЯМ
# ==============================================

def split_polygon_by_weeks(polygon_coords, points_coords, point_ids, num_weeks, 
                          coefficients, polygon_name="", auditor_id="", logger=None):
    """
    Разбивает полигон аудитора на N компактных областей по неделям
    Возвращает: (week_assignment, week_clusters)
    """
    
    import numpy as np
    
    # Проверка входных данных
    if not points_coords or not point_ids or num_weeks <= 0:
        if logger:
            logger("❌ Недостаточно данных для разбиения")
        return {}, {}
    
    if len(points_coords) != len(point_ids):
        if logger:
            logger(f"❌ Несоответствие координат ({len(points_coords)}) и ID ({len(point_ids)})")
        return {}, {}
    
    # Создаем logger если не предоставлен
    if logger is None:
        def default_logger(msg):
            print(f"[{auditor_id or 'UNKNOWN'}] {msg}")
        logger = default_logger
    
    try:
        logger(f"Начинаю разбиение: {len(point_ids)} точек на {num_weeks} недель")
        
        week_assignment = {}
        week_clusters = {}
        
        # 1. Если точек меньше чем недель
        if len(point_ids) < num_weeks:
            logger(f"⚠️ Точек ({len(point_ids)}) меньше чем недель ({num_weeks})")
            # Каждой точке своя неделя
            for i, point_id in enumerate(point_ids):
                if i < num_weeks:
                    week_assignment[i] = [point_id]
                    if i < len(points_coords):
                        week_clusters[i] = {
                            'centroid': points_coords[i],
                            'size': 1
                        }
            return week_assignment, week_clusters
        
        # 2. Распределяем точки по неделям
        total_points = len(point_ids)
        points_per_week = total_points // num_weeks
        remainder = total_points % num_weeks
        
        logger(f"Точек в неделю: {points_per_week}, остаток: {remainder}")
        
        start_idx = 0
        for week in range(num_weeks):
            # Определяем размер недели
            week_size = points_per_week + (1 if week < remainder else 0)
            end_idx = start_idx + week_size
            
            if start_idx >= total_points:
                break
                
            # Берем точки для этой недели
            week_point_ids = point_ids[start_idx:end_idx]
            week_assignment[week] = week_point_ids
            
            # Вычисляем центроид
            week_points_coords = []
            for i in range(start_idx, min(end_idx, len(points_coords))):
                week_points_coords.append(points_coords[i])
            
            if week_points_coords:
                try:
                    points_array = np.array(week_points_coords, dtype=float)
                    centroid = points_array.mean(axis=0).tolist()
                    week_clusters[week] = {
                        'centroid': centroid,
                        'size': len(week_points_coords),
                        'points_count': len(week_point_ids)
                    }
                except Exception as e:
                    logger(f"⚠️ Ошибка вычисления центроида недели {week}: {str(e)}")
                    # Используем первую точку как центроид
                    week_clusters[week] = {
                        'centroid': week_points_coords[0] if week_points_coords else [0, 0],
                        'size': len(week_points_coords),
                        'points_count': len(week_point_ids)
                    }
            
            start_idx = end_idx
        
        # 3. Проверяем результат
        total_assigned = sum(len(ids) for ids in week_assignment.values())
        logger(f"✅ Разбиение завершено: {total_assigned} точек распределено по {len(week_assignment)} неделям")
        
        # Логи по неделям
        for week in sorted(week_assignment.keys()):
            week_size = len(week_assignment[week])
            logger(f"  Неделя {week}: {week_size} точек")
        
        return week_assignment, week_clusters
        
    except Exception as e:
        logger(f"🔥 КРИТИЧЕСКАЯ ОШИБКА в split_polygon_by_weeks: {str(e)}")
        import traceback
        logger(f"Детали: {traceback.format_exc()[:200]}")
        return {}, {}

# ==============================================
# ОБНОВЛЕННАЯ ФУНКЦИЯ create_weekly_route_schedule
# ==============================================

def create_weekly_route_schedule(points_df, points_assignment_df, auditors_df, 
                                 year, quarter, use_enhanced_split=True):

    # ========== ДИАГНОСТИКА ==========
    st.info("=== ДИАГНОСТИКА НАЧАТА ===")
    st.info(f"use_enhanced_split = {use_enhanced_split}")
    st.info(f"points_df: {'НЕТ' if points_df is None else f'{len(points_df)} строк'}")
    st.info(f"auditors_df: {'НЕТ' if auditors_df is None else f'{len(auditors_df)} строк'}")
    st.info(f"Есть ли polygons в session_state: {'polygons' in st.session_state}")
    
    if 'polygons' in st.session_state:
        polygons = st.session_state.polygons
        st.info(f"Количество полигонов: {len(polygons)}")
        for i, (name, poly) in enumerate(list(polygons.items())[:3]):
            st.info(f"  Полигон {i+1}: {name}, аудитор: {poly.get('auditor', '?')}")

                                     
    """
    Создает ежедневные маршруты для аудиторов в формате EasyMerch
    """
    
    if points_df is None or points_df.empty:
        return pd.DataFrame()
    
    if points_assignment_df is None or points_assignment_df.empty:
        return pd.DataFrame()
    
    # Получаем недели (общее для всех вариантов)
    try:
        weeks_info = get_weeks_in_quarter(year, quarter)
        if not weeks_info:
            st.warning(f"⚠️ В {year} квартале {quarter} нет недель")
            return pd.DataFrame()
        num_weeks = len(weeks_info)
        weeks_dict = {i: weeks_info[i] for i in range(num_weeks)}
    except Exception as e:
        st.error(f"❌ Ошибка получения недель: {str(e)}")
        return pd.DataFrame()
    
    all_visits = []
    
    # ============================================
    # НОВАЯ ЛОГИКА: разбиение полигона по неделям
    # ============================================
    if use_enhanced_split:
        # Коэффициенты из настроек
        coefficients = [
            st.session_state.get('sidebar_stage1', 0.8),
            st.session_state.get('sidebar_stage2', 1.0),
            st.session_state.get('sidebar_stage3', 1.2),
            st.session_state.get('sidebar_stage4', 0.9)
        ]
        
        # Для каждого аудитора
        for auditor in auditors_df['ID_Сотрудника'].unique():
            try:
                # Находим точки этого аудитора
                auditor_point_ids = points_assignment_df[
                    points_assignment_df['Аудитор'] == auditor
                ]['ID_Точки'].tolist()
                
                if not auditor_point_ids:
                    continue
                
                auditor_points_data = points_df[
                    points_df['ID_Точки'].isin(auditor_point_ids)
                ]
                
                if auditor_points_data.empty:
                    continue
                
                # Находим полигон аудитора
                polygon_info = None
                polygon_name = None
                polygons = st.session_state.get('polygons', {})
                for poly_name, poly_info in polygons.items():
                    if poly_info.get('auditor') == auditor:
                        polygon_info = poly_info
                        polygon_name = poly_name
                        break
                
                if not polygon_info or not polygon_info.get('coordinates'):
                    # Если нет полигона, используем все точки
                    week_points_list = []
                    for _, row in auditor_points_data.iterrows():
                        visits_needed = int(row.get('Кол-во_посещений', 1))
                        for _ in range(visits_needed):
                            week_points_list.append({
                                'ID_Точки': row['ID_Точки'],
                                'Широта': float(row['Широta']),
                                'Долгота': float(row['Долгота']),
                                'Название_Точки': row.get('Название_Точки', str(row['ID_Точки'])),
                                'Адрес': row.get('Адрес', ''),
                                'Тип': row.get('Тип', 'Неизвестно')
                            })
                    
                    
                        # Распределяем по неделям простым способом
                        for week_idx in range(num_weeks):
                            week_info = weeks_dict.get(week_idx)
                            if not week_info:
                                continue
                            
                            week_start = week_info['start_date']
                            week_end = week_info['end_date']
                            
                            # Только рабочие дни (Пн-Пт)
                            working_days_this_week = []
                            current_date = week_start
                            while current_date <= week_end:
                                if current_date.weekday() < 5:  # 0=Пн, 4=Пт
                                    working_days_this_week.append(current_date)
                                current_date += timedelta(days=1)
                            
                            if working_days_this_week:
                                st.info(f"📅 Неделя {week_idx}: {len(working_days_this_week)} рабочих дней")
                                
                                weekly_visits = create_daily_routes_for_auditor(
                                    week_points_list, working_days_this_week, auditor
                                )
                                
                                if weekly_visits:
                                    all_visits.extend(weekly_visits)
                                    st.success(f"✅ Создано {len(weekly_visits)} визитов")
                                else:
                                    st.warning(f"⚠️ Не создано ни одного визита для недели {week_idx}")
                        continue
                
                # Подготавливаем данные для разбиения
                polygon_coords = polygon_info['coordinates']
                points_coords = []
                point_ids_list = []
                
                for _, row in auditor_points_data.iterrows():
                    point_id = str(row['ID_Точки'])
                    try:
                        lat = float(row['Широта'])
                        lon = float(row['Долгота'])
                        visits_needed = int(row.get('Кол-во_посещений', 1))
                        for _ in range(visits_needed):
                            points_coords.append([lat, lon])
                            point_ids_list.append(point_id)
                    except (ValueError, TypeError):
                        continue
                
                if len(points_coords) == 0:
                    continue
                
                # Создаем логгер для этого аудитора
                current_auditor = auditor  # Фиксируем переменную
                log_messages = []
                
                def auditor_logger(msg):
                    log_messages.append(f"{current_auditor}: {msg}")
                
                # Разбиваем полигон по неделям
                week_assignment, week_clusters = split_polygon_by_weeks(
                    polygon_coords=polygon_coords,
                    points_coords=points_coords,
                    point_ids=point_ids_list,
                    num_weeks=num_weeks,
                    coefficients=coefficients,
                    polygon_name=polygon_name,
                    auditor_id=auditor,
                    logger=auditor_logger
                )
                
                # Показываем логи
                for msg in log_messages[-3:]:
                    st.info(msg)
                
                if not week_assignment:
                    st.warning(f"⚠️ {auditor}: не удалось разбить полигон")
                    continue
                               # Создаем маршруты для каждой недели
                for week_key, week_point_ids in week_assignment.items():
                    if not week_point_ids:
                        continue
                    
                    # Преобразуем week_key в индекс (0-based)
                    try:
                        week_idx = int(week_key)
                        if week_idx >= num_weeks:
                            continue
                    except (ValueError, TypeError):
                        continue
                    
                    # Фильтруем точки этой недели
                    week_points_data = auditor_points_data[
                        auditor_points_data['ID_Точки'].isin(week_point_ids)
                    ]
                    
                    if week_points_data.empty:
                        continue
                    
                    # Преобразуем в список словарей
                    week_points_list = []
                    for _, row in week_points_data.iterrows():
                        visits_needed = int(row.get('Кол-во_посещений', 1))
                        for _ in range(visits_needed):
                            week_points_list.append({
                                'ID_Точки': row['ID_Точки'],
                                'Широта': float(row['Широта']),
                                'Долгота': float(row['Долгота']),
                                'Название_Точки': row.get('Название_Точки', str(row['ID_Точки'])),
                                'Адрес': row.get('Адрес', ''),
                                'Тип': row.get('Тип', 'Неизвестно')
                            })
                    
                    # Находим даты этой недели
                    week_info = weeks_dict.get(week_idx)
                    if not week_info:
                        continue
                    
                    week_start = week_info['start_date']
                    week_end = week_info['end_date']
                    
                    # Только рабочие дни (Пн-Пт)
                    working_days_this_week = []
                    current_date = week_start
                    while current_date <= week_end:
                        if current_date.weekday() < 5:  # 0=Пн, 4=Пт
                            working_days_this_week.append(current_date)
                        current_date += timedelta(days=1)
                    
                    if working_days_this_week:
                        st.info(f"📅 Неделя {week_idx}: {len(working_days_this_week)} рабочих дней")
                        
                        weekly_visits = create_daily_routes_for_auditor(
                            week_points_list, working_days_this_week, auditor
                        )
                        
                        if weekly_visits:
                            all_visits.extend(weekly_visits)
                            st.success(f"✅ Создано {len(weekly_visits)} визитов")
                        else:
                            st.warning(f"⚠️ Не создано ни одного визита для недели {week_idx}")
                    
            except Exception as e:
                st.error(f"❌ {auditor}: ошибка: {str(e)[:100]}")
            continue
    
    
    
    # ============================================
    # ОБЩАЯ ЧАСТЬ: формирование финальной таблицы
    # ============================================
    if not all_visits:
        return pd.DataFrame()
    
    # Преобразуем в DataFrame
    results_df = pd.DataFrame(all_visits)
    
    # Группируем по неделям для формата EasyMerch
    results_df['Неделя'] = results_df['Дата'].apply(lambda d: d.isocalendar()[1])
    results_df['Дата_начала_недели'] = results_df['Дата'].apply(
        lambda d: d - timedelta(days=d.weekday())
    )
    
    # Создаем финальную таблицу в формате EasyMerch
    final_rows = []
    
    # Группируем по точкам и неделям
    grouped = results_df.groupby(['ID_Точки', 'Неделя', 'Аудитор'])
    
    for (point_id, week_num, auditor), group in grouped:
        point_mask = points_df['ID_Точки'] == point_id
        if not point_mask.any():
            continue
            
        point_info = points_df[point_mask].iloc[0]
        
        visits_this_week = len(group)
        days_visited = set(group['День_недели'].tolist())
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
            'ID_Точки': point_id,
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
            'Широта': f"{latitude:.6f}",
            'Долгота': f"{longitude:.6f}"
        }
        
        final_rows.append(row)
    
    if not final_rows:
        return pd.DataFrame()
    
    final_df = pd.DataFrame(final_rows)
    final_df = final_df.sort_values(['Login пользователя', 'Дата начала цикла посещения', 'L1 Name'])
    
    return final_df

def create_easymerch_excel(routes_df, points_df):
    """Создает Excel файл в формате EasyMerch с несколькими листами"""
    import io
    
    if routes_df is None or routes_df.empty:
        return None
    
    excel_buffer = io.BytesIO()
    
    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
        # Лист 1: Основные данные в формате EasyMerch
        # Создаем копию для модификации
        easymerch_df = routes_df.copy()
        
        # 1. Добавляем Customer number как первый столбец
        # Используем ID_Точки если есть, иначе L1 Name
        customer_number_col = None
        if 'ID_Точки' in easymerch_df.columns:
            customer_number_col = 'ID_Точки'
        elif 'L1 Name' in easymerch_df.columns:
            customer_number_col = 'L1 Name'
        
        if customer_number_col:
            easymerch_df.insert(0, 'Customer number', easymerch_df[customer_number_col])
        else:
            easymerch_df.insert(0, 'Customer number', '')
        
        # 2. Заполняем столбец Город
        easymerch_df['Город'] = ''
        
        if points_df is not None and not points_df.empty:
            # Создаем словарь для сопоставления Customer number -> Город
            city_mapping = {}
            
            # Вариант 1: по ID_Точки
            if 'ID_Точки' in points_df.columns and 'Город' in points_df.columns:
                for idx, row in points_df.iterrows():
                    point_id = str(row['ID_Точки']).strip()
                    city = str(row['Город']).strip()
                    if point_id and city:
                        city_mapping[point_id] = city
            
            # Вариант 2: по названию точки (если нет ID_Точки в routes_df)
            if 'Название_Точки' in points_df.columns and 'Город' in points_df.columns:
                for idx, row in points_df.iterrows():
                    point_name = str(row['Название_Точки']).strip()
                    city = str(row['Город']).strip()
                    if point_name and city:
                        city_mapping[point_name] = city
            
            # Заполняем города
            if city_mapping:
                # Пробуем сопоставить по Customer number
                easymerch_df['Город'] = easymerch_df['Customer number'].map(city_mapping).fillna('')
        
        # 3. Добавляем столбец Вне графика после Воскресенье
        if 'Воскресенье' in easymerch_df.columns:
            # Находим индекс столбца Воскресенье
            col_list = list(easymerch_df.columns)
            if 'Воскресенье' in col_list:
                sunday_idx = col_list.index('Воскресенье')
                # Вставляем новый столбец после Воскресенье
                easymerch_df.insert(sunday_idx + 1, 'Вне графика', '')
        
        # Сохраняем в Excel
        easymerch_df.to_excel(writer, sheet_name='Маршруты', index=False)
        
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
            ["Customer number", "ID торговой точки", "P001", "Да"],
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
            ["Вне графика", "Визиты вне регулярного графика", "", "Нет"],
            ["Цикл посещения", "Номер недели (ISO стандарт)", "15", "Да"],
            ["Дата начала цикла посещения", "Дата понедельника в формате ГГГГММДД", "20250407", "Да"],
            ["Широта", "Координата широты", "55.755831", "Нет"],
            ["Долгота", "Координата долготы", "37.617673", "Нет"],
            ["Город", "Город расположения точки", "Москва", "Да"],
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
                'Количество городов',
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
                easymerch_df['Город'].nunique() if 'Город' in easymerch_df.columns else 0,
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
# ==============================================
# ФУНКЦИИ ДЛЯ РАСПРЕДЕЛЕНИЯ ПО АУДИТОРАМ (ГЕОГРАФИЧЕСКОЕ РАЗДЕЛЕНИЕ)
# ==============================================

def divide_points_by_direction(points_df, n_auditors, city):
    """
    Разделяет точки на географические полигоны с равным распределением
    """
    if n_auditors == 1:
        return [points_df]
    
    if n_auditors <= 0 or points_df.empty:
        return []
    
    points_df = points_df.copy().reset_index(drop=True)
    
    # Для воспроизводимости сортируем по ID
    points_df = points_df.sort_values('ID_Точки').reset_index(drop=True)
    
    if n_auditors == 2:
        # Север-Юг: сортируем по широте, делим пополам
        points_sorted = points_df.sort_values('Широта', ascending=False).reset_index(drop=True)
        split_idx = len(points_sorted) // 2
        
        north = points_sorted.iloc[:split_idx].copy()  # Север (более высокие широты)
        south = points_sorted.iloc[split_idx:].copy()  # Юг
        
        return [north, south]
    
    elif n_auditors == 3:
        # Север-Юго-Восток-Юго-Запад
        # Сначала находим самые северные точки для "Севера"
        points_sorted = points_df.sort_values('Широта', ascending=False).reset_index(drop=True)
        
        # 1/3 самых северных точек = Север
        north_size = len(points_sorted) // 3
        north = points_sorted.iloc[:north_size].copy()
        
        # Остальные точки = Юг
        south_points = points_sorted.iloc[north_size:].copy()
        
        # Делим южные точки на Восток и Запад по долготе
        if not south_points.empty:
            # Сортируем южные точки по долготе
            south_sorted = south_points.sort_values('Долгота').reset_index(drop=True)
            
            # Медианная долгота для разделения
            median_lon = south_sorted['Долгота'].median()
            
            southeast = south_sorted[south_sorted['Долгота'] >= median_lon].copy()
            southwest = south_sorted[south_sorted['Долгота'] < median_lon].copy()
            
            # Балансируем размеры ЮВ и ЮЗ
            target_south_size = len(south_sorted) // 2
            if len(southeast) > target_south_size + 2:
                # Перемещаем самые западные точки из ЮВ в ЮЗ
                excess = len(southeast) - target_south_size
                points_to_move = southeast.nsmallest(excess, 'Долгота')
                southeast = southeast.drop(points_to_move.index)
                southwest = pd.concat([southwest, points_to_move], ignore_index=True)
            elif len(southwest) > target_south_size + 2:
                # Перемещаем самые восточные точки из ЮЗ в ЮВ
                excess = len(southwest) - target_south_size
                points_to_move = southwest.nlargest(excess, 'Долгота')
                southwest = southwest.drop(points_to_move.index)
                southeast = pd.concat([southeast, points_to_move], ignore_index=True)
            
            return [north, southeast, southwest]
        
        return [north, pd.DataFrame(), pd.DataFrame()]
    
    elif n_auditors == 4:
        # Север-Восток-Юг-Запад через квадранты
        # Вычисляем медианные координаты
        median_lat = points_df['Широта'].median()
        median_lon = points_df['Долгота'].median()
        
        # Создаем квадранты
        ne_mask = (points_df['Широта'] >= median_lat) & (points_df['Долгота'] >= median_lon)
        nw_mask = (points_df['Широта'] >= median_lat) & (points_df['Долгота'] < median_lon)
        se_mask = (points_df['Широта'] < median_lat) & (points_df['Долгота'] >= median_lon)
        sw_mask = (points_df['Широта'] < median_lat) & (points_df['Долгота'] < median_lon)
        
        ne_points = points_df[ne_mask].copy()  # Северо-Восток → Север
        nw_points = points_df[nw_mask].copy()  # Северо-Запад → Запад
        se_points = points_df[se_mask].copy()  # Юго-Восток → Восток
        sw_points = points_df[sw_mask].copy()  # Юго-Запад → Юг
        
        # Возвращаем в порядке: Север, Восток, Юг, Запад
        return [ne_points, se_points, sw_points, nw_points]
    
    else:
        # Для другого количества - простое равное деление
        return np.array_split(points_df, n_auditors)


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
        
        with st.spinner("🔄 Распределение посещений по неделям..."):
            # Распределяем посещения по неделям
            detailed_plan_df = distribute_visits_by_weeks(
                points_assignment_df, points_df, year, quarter, coefficients
            )
            
            if detailed_plan_df.empty:
                st.error("❌ Не удалось распределить посещения по неделям")
                st.stop()
            
            st.session_state.detailed_plan_df = detailed_plan_df
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
        # ОПТИМИЗАЦИЯ МАРШРУТОВ ПО ДНЯМ
        # ==============================================
        
        with st.spinner("🗺️ Оптимизация маршрутов по дням недели..."):
            try:
                # Создаем таблицу с маршрутами
                routes_df = create_weekly_route_schedule(
                    points_df,
                    points_assignment_df,
                    auditors_df,  # ← ТОЛЬКО 5 АРГУМЕНТОВ!
                    year,
                    quarter,
                    use_enhanced_split=use_enhanced_split
                )
                
                if not routes_df.empty:
                    st.session_state.routes_df = routes_df
                    st.success(f"✅ Построены маршруты: {len(routes_df)} записей")
                    st.info("📋 Маршруты доступны во вкладке 'План посещений' для выгрузки в формате EasyMerch")
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
                                                excel_data = create_easymerch_excel(routes_df, st.session_state.points_df)
                                                
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
                    with st.container(border=True):
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
                    with st.container(border=True):
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
                    with st.container(border=True):
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
# ==============================================
# ТЕСТОВАЯ СЕКЦИЯ ДЛЯ ЭТАПА 1 (удалить после реализации)
# ==============================================

if st.sidebar.checkbox("🧪 Тест геометрических функций", False, key="test_geo_functions"):
    st.sidebar.markdown("---")
    st.sidebar.subheader("Тест новых функций")
    
    # Тестовый полигон (квадрат Москва)
    test_polygon = [
        [55.5, 37.3],
        [55.5, 37.8],
        [55.8, 37.8],
        [55.8, 37.3],
        [55.5, 37.3]
    ]
    
    # Тестовые точки
    test_point_inside = (55.65, 37.55)
    test_point_outside = (55.4, 37.55)
    
    col1, col2 = st.sidebar.columns(2)
    
    with col1:
        inside = is_point_in_polygon(test_point_inside, test_polygon)
        st.sidebar.write(f"📍 (55.65, 37.55)")
        st.sidebar.write(f"Внутри: **{'✅ Да' if inside else '❌ Нет'}**")
    
    with col2:
        outside = is_point_in_polygon(test_point_outside, test_polygon)
        st.sidebar.write(f"📍 (55.4, 37.55)")
        st.sidebar.write(f"Внутри: **{'❌ Да' if outside else '✅ Нет'}**")
    
    # Тест сетки
    st.sidebar.markdown("---")
    
    if st.sidebar.button("Создать тестовую сетку", key="test_grid_btn"):
        grid = create_grid_inside_polygon(test_polygon, grid_size=0.05)
        
        if grid:
            st.sidebar.success(f"✅ Создана сетка: {len(grid['cells'])} ячеек")
            st.sidebar.write(f"📐 Размер: {grid['width']}x{grid['height']}")
            
            # Тест распределения точек
            test_points = [
                [55.65, 37.55],
                [55.75, 37.65],
                [55.55, 37.35],
            ]
            test_ids = ["P001", "P002", "P003"]
            
            assignment = assign_points_to_grid_cells(test_points, test_ids, grid)
            
            st.sidebar.write("📊 Распределение точек:")
            for cell_key, points in assignment.items():
                st.sidebar.write(f"Ячейка {cell_key}: {points}")
        else:
            st.sidebar.error("❌ Не удалось создать сетку")



# ==============================================
# ТЕСТОВАЯ СЕКЦИЯ ДЛЯ ЭТАПА 2 (добавить в конец файла)
# ==============================================

if st.sidebar.checkbox("🧪 Тест алгоритма кластеризации", False, key="test_clustering_func"):
    st.sidebar.markdown("---")
    st.sidebar.subheader("Тест кластеризации (Этап 2)")
    
    # Тестовый полигон
    test_polygon = [
        [55.5, 37.3],
        [55.5, 37.8], 
        [55.8, 37.8],
        [55.8, 37.3],
        [55.5, 37.3]
    ]
    
    # Тестовые точки
    test_points = []
    test_ids = []
    
    # Создаем 50 тестовых точек внутри полигона
    for i in range(50):
        lat = 55.5 + (i % 10) * 0.03
        lon = 37.3 + (i // 10) * 0.05
        test_points.append([lat, lon])
        test_ids.append(f"P{i:03d}")
    
    if st.sidebar.button("Запустить тест кластеризации", key="run_clustering_test_btn"):
        with st.sidebar:
            st.info("🔄 Запускаем тест...")
            
            # 1. Создаем сетку
            grid = create_grid_inside_polygon(test_polygon, grid_size=0.01)
            
            if grid:
                st.success(f"✅ Создана сетка: {len(grid['cells'])} ячеек")
                
                # 2. Распределяем точки
                cell_to_points = assign_points_to_grid_cells(test_points, test_ids, grid)
                st.info(f"📊 Распределено {len(test_points)} точек по {len(cell_to_points)} ячейкам")
                
                # 3. Тест граничных ячеек
                boundary = find_initial_boundary_simple(grid, test_polygon)
                st.info(f"📍 Граничных ячеек: {len(boundary)}")
                
                # 4. Тест сортировки
                ordered = sort_boundary_by_northwest(boundary, grid)
                st.info(f"📈 Упорядочено: {len(ordered)} ячеек")
                
                # 5. Тест кластеризации
                weekly_targets = [10, 10, 10, 10, 10]  # 5 недель по 10 точек
                
                def test_logger(msg):
                    st.write(f"📝 {msg}")
                
                clusters = cluster_from_perimeter_to_center_simple(
                    test_polygon, grid, cell_to_points, weekly_targets, test_logger
                )
                
                if clusters:
                    st.success(f"✅ Создано {len(clusters)} кластеров")
                    for week, points in clusters.items():
                        st.write(f"Неделя {week}: {len(points)} точек")
                else:
                    st.error("❌ Не удалось создать кластеры")
            else:
                st.error("❌ Не удалось создать сетку")
# ==============================================
# КОНЕЦ ((удалить после реализации))
# ==============================================

















