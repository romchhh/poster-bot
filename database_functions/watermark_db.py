import os
import base64
import time
from datetime import datetime
from typing import Dict, Tuple


def format_datetime_dd_mm_yyyy_hh_mm_ss() -> str:
    return datetime.now().strftime("%d.%m.%Y %H:%M:%S")


from database_functions.connection import conn, cursor

WATERMARKS_DIR = "database/watermarks"
if not os.path.exists(WATERMARKS_DIR):
    os.makedirs(WATERMARKS_DIR)

temp_watermarks = {}

# Кеш для перевірок наявності вотермарки (TTL 5 хвилин = 300 секунд)
_watermark_cache: Dict[str, Tuple[bool, float]] = {}
WATERMARK_CACHE_TTL = 300  # 5 хвилин

def _get_cache_key(user_id: int, channel_id: str, donor_id: str) -> str:
    """Генерує ключ для кешу"""
    return f"{user_id}_{channel_id}_{donor_id}"

def _is_cache_valid(timestamp: float) -> bool:
    """Перевіряє чи кеш ще валідний"""
    return time.time() - timestamp < WATERMARK_CACHE_TTL

def _clear_expired_cache():
    """Очищає застарілі записи з кешу"""
    current_time = time.time()
    expired_keys = [key for key, (_, timestamp) in _watermark_cache.items() 
                     if current_time - timestamp >= WATERMARK_CACHE_TTL]
    for key in expired_keys:
        del _watermark_cache[key]

def invalidate_watermark_cache(user_id: int, channel_id: str, donor_id: str):
    """Інвалідує кеш для конкретного вотермарки"""
    key = _get_cache_key(user_id, channel_id, donor_id)
    if key in _watermark_cache:
        del _watermark_cache[key]
        print(f"🗑️ Кеш вотермарки інвалідовано для {key}")


def create_watermark_table():
    """Створює таблицю watermarks якщо її немає"""
    if not os.path.exists(WATERMARKS_DIR):
        os.makedirs(WATERMARKS_DIR, exist_ok=True)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS watermarks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            channel_id TEXT NOT NULL,
            donor_id TEXT NOT NULL,
            watermark_file_path TEXT NOT NULL,
            position TEXT DEFAULT 'bottom-right',
            size_percent INTEGER DEFAULT 50,
            opacity INTEGER DEFAULT 100,
            indent INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(user_id, channel_id, donor_id)
        )
    ''')
    conn.commit()


def get_temp_watermark_key(user_id, channel_id, donor_id):
    """Генерує ключ для тимчасового водяного знаку"""
    return f"{user_id}_{channel_id}_{donor_id}"


def save_temp_watermark(user_id, channel_id, donor_id, watermark_data, position='bottom-right', size_percent=50, opacity=100, indent=0):
    """Зберігає тимчасовий водяний знак в пам'яті"""
    key = get_temp_watermark_key(user_id, channel_id, donor_id)
    temp_watermarks[key] = {
        'watermark_data': watermark_data,
        'position': position,
        'size_percent': size_percent,
        'opacity': opacity,
        'indent': indent,
        'created_at': format_datetime_dd_mm_yyyy_hh_mm_ss(),
        'updated_at': format_datetime_dd_mm_yyyy_hh_mm_ss()
    }
    print(f"💾 Водяний знак збережено тимчасово для {key}")


def get_temp_watermark(user_id, channel_id, donor_id):
    """Отримує тимчасовий водяний знак з пам'яті"""
    key = get_temp_watermark_key(user_id, channel_id, donor_id)
    return temp_watermarks.get(key)


def update_temp_watermark_settings(user_id, channel_id, donor_id, **kwargs):
    """Оновлює налаштування тимчасового водяного знаку"""
    key = get_temp_watermark_key(user_id, channel_id, donor_id)
    if key in temp_watermarks:
        temp_watermarks[key].update(kwargs)
        temp_watermarks[key]['updated_at'] = format_datetime_dd_mm_yyyy_hh_mm_ss()
        return True
    return False


def clear_temp_watermark(user_id, channel_id, donor_id):
    """Видаляє тимчасовий водяний знак з пам'яті"""
    key = get_temp_watermark_key(user_id, channel_id, donor_id)
    if key in temp_watermarks:
        del temp_watermarks[key]
        print(f"🗑️ Тимчасовий водяний знак видалено для {key}")


def generate_watermark_filename(user_id, channel_id, donor_id):
    """Генерує унікальне ім'я файлу для водяного знаку"""
    import hashlib
    unique_id = f"{user_id}_{channel_id}_{donor_id}"
    hash_id = hashlib.md5(unique_id.encode()).hexdigest()
    return f"watermark_{hash_id}.png"


def save_watermark_file(image_bytes, filename):
    """Зберігає файл водяного знаку на диск"""
    try:
        file_path = os.path.join(WATERMARKS_DIR, filename)
        with open(file_path, 'wb') as f:
            f.write(image_bytes)
        return file_path
    except Exception as e:
        print(f"❌ Помилка збереження водяного знаку: {e}")
        return None


def load_watermark_file(file_path):
    """Завантажує файл водяного знаку з диска"""
    try:
        if os.path.exists(file_path):
            with open(file_path, 'rb') as f:
                return f.read()
        return None
    except Exception as e:
        print(f"❌ Помилка завантаження водяного знаку: {e}")
        return None


def save_watermark(user_id: int, channel_id: str, donor_id: str, watermark_data: str, 
                  position: str = 'bottom-right', size_percent: int = 50, opacity: int = 100, indent: int = 0):
    """Зберігає водяний знак в БД та на диск"""
    try:
        # Інвалідуємо кеш при збереженні
        invalidate_watermark_cache(user_id, channel_id, donor_id)
        # Генеруємо ім'я файлу та зберігаємо водяний знак локально
        filename = generate_watermark_filename(user_id, channel_id, donor_id)
        
        # Конвертуємо base64 в bytes та зберігаємо як файл
        image_bytes = base64.b64decode(watermark_data)
        file_path = save_watermark_file(image_bytes, filename)
        
        if not file_path:
            return False
        
        created_at = format_datetime_dd_mm_yyyy_hh_mm_ss()
        updated_at = created_at
        
        cursor.execute('''
            INSERT OR REPLACE INTO watermarks 
            (user_id, channel_id, donor_id, watermark_file_path, position, size_percent, opacity, indent, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, channel_id, donor_id, file_path, position, size_percent, opacity, indent, created_at, updated_at))
        
        conn.commit()
        print(f"✅ Водяний знак збережено локально: {file_path}")
        return True
    except Exception as e:
        print(f"❌ Помилка збереження водяного знаку: {e}")
        return False


def get_watermark(user_id: int, channel_id: str, donor_id: str):
    """Отримує водяний знак з БД або тимчасового сховища"""
    try:
        # Спочатку перевіряємо тимчасові водяні знаки
        temp_data = get_temp_watermark(user_id, channel_id, donor_id)
        if temp_data:
            return temp_data
        
        # Якщо тимчасового немає, шукаємо в базі даних
        cursor.execute('''
            SELECT watermark_file_path, position, size_percent, opacity, indent, created_at, updated_at
            FROM watermarks 
            WHERE user_id = ? AND channel_id = ? AND donor_id = ?
        ''', (user_id, channel_id, donor_id))
        
        result = cursor.fetchone()
        if result:
            file_path = result[0]
            
            if file_path:
                watermark_bytes = load_watermark_file(file_path)
                if watermark_bytes:
                    watermark_base64 = base64.b64encode(watermark_bytes).decode()
                    
                    return {
                        'watermark_data': watermark_base64,
                        'position': result[1],
                        'size_percent': result[2],
                        'opacity': result[3],
                        'indent': result[4],
                        'created_at': result[5],
                        'updated_at': result[6],
                        'file_path': file_path
                    }
                else:
                    print(f"⚠️ Не вдалося завантажити водяний знак з файлу: {file_path}")
        return None
    except Exception as e:
        print(f"❌ Помилка отримання водяного знаку: {e}")
        return None


def get_any_watermark_for_channel(user_id: int, channel_id: str):
    """
    Повертає будь-який (останній оновлений) водяний знак для каналу,
    ігноруючи donor_id. Використовується для ручних постів, де донор відсутній.
    """
    try:
        # Спочатку перевіряємо тимчасові водяні знаки для будь-якого donor_id цього каналу
        # (ключ temp_watermarks: user_id_channel_id_donor_id)
        possible_keys = [key for key in temp_watermarks.keys() if key.startswith(f"{user_id}_{channel_id}_")]
        if possible_keys:
            # Беремо перший знайдений тимчасовий вотермарк
            return temp_watermarks[possible_keys[0]]

        # Якщо тимчасових немає — шукаємо останній оновлений запис у БД
        cursor.execute(
            '''
            SELECT watermark_file_path, position, size_percent, opacity, indent, created_at, updated_at
            FROM watermarks
            WHERE user_id = ? AND channel_id = ?
            ORDER BY datetime(updated_at) DESC
            LIMIT 1
            ''',
            (user_id, channel_id),
        )

        result = cursor.fetchone()
        if result:
            file_path = result[0]
            if file_path:
                watermark_bytes = load_watermark_file(file_path)
                if watermark_bytes:
                    watermark_base64 = base64.b64encode(watermark_bytes).decode()
                    return {
                        'watermark_data': watermark_base64,
                        'position': result[1],
                        'size_percent': result[2],
                        'opacity': result[3],
                        'indent': result[4],
                        'created_at': result[5],
                        'updated_at': result[6],
                        'file_path': file_path
                    }
                else:
                    print(f"⚠️ Не вдалося завантажити водяний знак з файлу (channel-only): {file_path}")
        return None
    except Exception as e:
        print(f"❌ Помилка отримання водяного знаку для каналу (без donor_id): {e}")
        return None


def update_watermark_settings(user_id: int, channel_id: str, donor_id: str, 
                            position: str = None, size_percent: int = None, opacity: int = None, indent: int = None):
    """Оновлює налаштування водяного знаку"""
    try:
        temp_data = get_temp_watermark(user_id, channel_id, donor_id)
        if temp_data:
            update_params = {}
            if position is not None:
                update_params['position'] = position
            if size_percent is not None:
                update_params['size_percent'] = size_percent
            if opacity is not None:
                update_params['opacity'] = opacity
            if indent is not None:
                update_params['indent'] = indent
            
            return update_temp_watermark_settings(user_id, channel_id, donor_id, **update_params)
        
        updated_at = format_datetime_dd_mm_yyyy_hh_mm_ss()
        
        current = get_watermark(user_id, channel_id, donor_id)
        if not current:
            return False
        
        new_position = position if position is not None else current['position']
        new_size = size_percent if size_percent is not None else current['size_percent']
        new_opacity = opacity if opacity is not None else current['opacity']
        new_indent = indent if indent is not None else current['indent']
        
        cursor.execute('''
            UPDATE watermarks 
            SET position = ?, size_percent = ?, opacity = ?, indent = ?, updated_at = ?
            WHERE user_id = ? AND channel_id = ? AND donor_id = ?
        ''', (new_position, new_size, new_opacity, new_indent, updated_at, user_id, channel_id, donor_id))
        
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        print(f"❌ Помилка оновлення налаштувань водяного знаку: {e}")
        return False


def delete_watermark(user_id: int, channel_id: str, donor_id: str):
    """Видаляє водяний знак з БД та файл з диска"""
    try:
        # Інвалідуємо кеш при видаленні
        invalidate_watermark_cache(user_id, channel_id, donor_id)
        watermark = get_watermark(user_id, channel_id, donor_id)
        
        cursor.execute('''
            DELETE FROM watermarks 
            WHERE user_id = ? AND channel_id = ? AND donor_id = ?
        ''', (user_id, channel_id, donor_id))
        
        conn.commit()
        
        if watermark and 'file_path' in watermark:
            try:
                if os.path.exists(watermark['file_path']):
                    os.remove(watermark['file_path'])
                    print(f"✅ Локальний файл водяного знаку видалено: {watermark['file_path']}")
            except Exception as file_error:
                print(f"⚠️ Помилка видалення локального файлу: {file_error}")
        
        return cursor.rowcount > 0
    except Exception as e:
        print(f"❌ Помилка видалення водяного знаку: {e}")
        return False


def has_watermark(user_id: int, channel_id: str, donor_id: str):
    """Перевіряє чи існує водяний знак (з кешуванням)"""
    try:
        # Перевіряємо тимчасові вотермарки (не кешуємо, бо вони динамічні)
        temp_data = get_temp_watermark(user_id, channel_id, donor_id)
        if temp_data:
            return True
        
        # Перевіряємо кеш
        cache_key = _get_cache_key(user_id, channel_id, donor_id)
        if cache_key in _watermark_cache:
            cached_value, timestamp = _watermark_cache[cache_key]
            if _is_cache_valid(timestamp):
                return cached_value
            else:
                # Кеш застарів, видаляємо
                del _watermark_cache[cache_key]
        
        # Очищаємо застарілі записи (раз на ~100 викликів для оптимізації)
        if len(_watermark_cache) > 1000:
            _clear_expired_cache()
        
        # Запит до БД
        cursor.execute('''
            SELECT COUNT(*) FROM watermarks 
            WHERE user_id = ? AND channel_id = ? AND donor_id = ?
        ''', (user_id, channel_id, donor_id))
        
        result = cursor.fetchone()
        has_wm = result[0] > 0 if result else False
        
        # Зберігаємо в кеш
        _watermark_cache[cache_key] = (has_wm, time.time())
        
        return has_wm
    except Exception as e:
        print(f"❌ Помилка перевірки наявності водяного знаку: {e}")
        return False


def commit_temp_watermark(user_id, channel_id, donor_id):
    """Зберігає тимчасовий водяний знак назавжди"""
    temp_data = get_temp_watermark(user_id, channel_id, donor_id)
    if temp_data:
        # Зберігаємо назавжди
        result = save_watermark(
            user_id, channel_id, donor_id,
            temp_data['watermark_data'],
            temp_data['position'],
            temp_data['size_percent'],
            temp_data['opacity'],
            temp_data['indent']
        )
        if result:
            # Очищуємо тимчасові дані
            clear_temp_watermark(user_id, channel_id, donor_id)
            print(f"✅ Водяний знак збережено назавжди для {user_id}-{channel_id}-{donor_id}")
        return result
    return False
