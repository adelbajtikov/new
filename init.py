import sqlite3
import os

DATABASE = os.path.abspath("database/donations.db")

conn = sqlite3.connect(DATABASE)
cursor = conn.cursor()

try:
    cursor.execute("ALTER TABLE users ADD COLUMN blocked INTEGER DEFAULT 0;")
    print("✅ Колонка 'blocked' успешно добавлена в таблицу users.")
except sqlite3.OperationalError:
    print("⚠️ Колонка 'blocked' уже существует.")

conn.commit()
conn.close()
