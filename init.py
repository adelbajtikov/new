import sqlite3
DATABASE = 'database/donations.db'
# Добавьте этот код перед использованием таблицы donations
# Добавьте в начало app.py (перед созданием таблиц)
def init_db():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    # Проверяем существование столбца status в таблице donations
    cursor.execute("PRAGMA table_info(donations)")
    columns = [column[1] for column in cursor.fetchall()]
    
    if 'status' not in columns:
        cursor.execute("ALTER TABLE donations ADD COLUMN status TEXT DEFAULT 'pending'")
    
    if 'receipt_path' not in columns:
        cursor.execute("ALTER TABLE donations ADD COLUMN receipt_path TEXT")
    
    conn.commit()
    conn.close()

# Вызовите при старте приложения
init_db()