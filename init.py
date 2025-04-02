import sqlite3
DATABASE = 'database/donations.db'
# Добавьте этот код перед использованием таблицы donations
# Добавьте в начало app.py (перед созданием таблиц)
# В вашем коде где-то в начале (после создания других таблиц)
def get_db_connection():
    return sqlite3.connect(DATABASE)
conn = get_db_connection()
def update_db_structure():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Проверяем, есть ли столбцы is_completed и completed_at в таблице campaigns
    cursor.execute("PRAGMA table_info(campaigns)")
    columns = [column[1] for column in cursor.fetchall()]
    
    if 'is_completed' not in columns:
        cursor.execute("ALTER TABLE campaigns ADD COLUMN is_completed BOOLEAN DEFAULT 0")
    
    if 'completed_at' not in columns:
        cursor.execute("ALTER TABLE campaigns ADD COLUMN completed_at DATETIME")
    
    conn.commit()
    conn.close()

# Вызываем при запуске приложения
update_db_structure()
