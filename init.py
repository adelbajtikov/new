import sqlite3

DATABASE = 'database/donations.db'

conn = sqlite3.connect(DATABASE)
cursor = conn.cursor()

# Добавляем колонку status, если её нет
cursor.execute("""
    ALTER TABLE volunteering_opportunities ADD COLUMN status TEXT DEFAULT 'active'
""")

conn.commit()
conn.close()

print("Колонка status добавлена в volunteering_opportunities.")
