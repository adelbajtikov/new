import sqlite3

DATABASE = 'database/donations.db'

conn = sqlite3.connect(DATABASE)
cursor = conn.cursor()

# Создаем таблицу рекламы, если её нет
cursor.execute('''
    CREATE TABLE IF NOT EXISTS ads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        image_url TEXT NOT NULL,
        link TEXT NOT NULL
    )
''')

conn.commit()
conn.close()

print("✅ Таблица рекламы создана!")
