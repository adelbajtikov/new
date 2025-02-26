import sqlite3

DATABASE = "database/donations.db"  # Укажи путь к своей БД

def add_blocked_column():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    # Проверяем, есть ли колонка blocked, чтобы избежать ошибки
    cursor.execute("PRAGMA table_info(organizations)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if 'blocked' not in columns:
        cursor.execute("ALTER TABLE organizations ADD COLUMN blocked INTEGER DEFAULT 0")
        conn.commit()
        print("✅ Колонка 'blocked' добавлена в таблицу organizations!")
    else:
        print("⚠ Колонка 'blocked' уже существует.")

    conn.close()

if __name__ == "__main__":
    add_blocked_column()
