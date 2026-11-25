from datetime import datetime
from database_functions.connection import conn, cursor


def create_folders_table():
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS folders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            folder_name TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            created_date TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            channels_count INTEGER DEFAULT 0
        )
    ''')
    conn.commit()


def add_folder(folder_name: str, user_id: int):
    cursor.execute(
        "SELECT id FROM folders WHERE folder_name = ? AND user_id = ? AND is_active = 1",
        (folder_name, user_id)
    )
    existing = cursor.fetchone()
    
    if existing:
        return None
    
    current_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute('''
        INSERT INTO folders (folder_name, user_id, created_date, is_active, channels_count)
        VALUES (?, ?, ?, 1, 0)
    ''', (folder_name, user_id, current_date))
    conn.commit()
    return cursor.lastrowid


def get_folder_by_id(folder_id: int):
    cursor.execute("SELECT * FROM folders WHERE id = ?", (folder_id,))
    return cursor.fetchone()


def get_user_folders(user_id: int, only_active: bool = True):
    if only_active:
        cursor.execute(
            "SELECT * FROM folders WHERE user_id = ? AND is_active = 1 ORDER BY created_date DESC",
            (user_id,)
        )
    else:
        cursor.execute(
            "SELECT * FROM folders WHERE user_id = ? ORDER BY created_date DESC",
            (user_id,)
        )
    return cursor.fetchall()


def update_folder_name(folder_id: int, new_name: str):
    cursor.execute(
        "UPDATE folders SET folder_name = ? WHERE id = ?",
        (new_name, folder_id)
    )
    conn.commit()
    return cursor.rowcount > 0


def delete_folder(folder_id: int):
    cursor.execute("UPDATE folders SET is_active = 0 WHERE id = ?", (folder_id,))
    conn.commit()
    return cursor.rowcount > 0


def update_channels_count(folder_id: int):
    cursor.execute('''
        UPDATE folders 
        SET channels_count = (
            SELECT COUNT(*) 
            FROM channels 
            WHERE folder_id = ? AND is_active = 1
        )
        WHERE id = ?
    ''', (folder_id, folder_id))
    conn.commit()


def check_folder_exists(folder_name: str, user_id: int):
    cursor.execute(
        "SELECT id FROM folders WHERE folder_name = ? AND user_id = ? AND is_active = 1",
        (folder_name, user_id)
    )
    return cursor.fetchone() is not None
