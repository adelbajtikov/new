import sqlite3
DATABASE = 'database/donations.db'
# Добавьте этот код перед использованием таблицы donations
# Добавьте в начало app.py (перед созданием таблиц)
# В вашем коде где-то в начале (после создания других таблиц)
def get_db_connection():
    return sqlite3.connect(DATABASE)
conn = get_db_connection()
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS organization_posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        org_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        image_url TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (org_id) REFERENCES organizations(id)
    )
''')
conn.commit()
conn.close()