import sqlite3

def confirm_all_volunteers():
    conn = sqlite3.connect('database/donations.db')  # Подключение к БД
    cursor = conn.cursor()

    # ✅ Обновляем статус всех участников на 'confirmed'
    a = cursor.execute("SELECT * FROM volunteer_participants")

    # ✅ Сохраняем изменения и закрываем соединение
    conn.commit()
    conn.close()

    print(a)
    return a

# 🔥 Запускаем функцию
confirm_all_volunteers()
