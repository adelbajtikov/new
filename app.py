from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
import sqlite3
import pandas as pd
from flask import Flask, jsonify, request
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from datetime import datetime
import nltk
from nltk.corpus import stopwords
from sklearn.feature_extraction.text import TfidfVectorizer

import fitz  # PyMuPDF - работа с PDF
app = Flask(__name__)
UPLOAD_FOLDER = 'static/uploads'
RECEIPTS_FOLDER = 'static/uploads/receipts'
os.makedirs(RECEIPTS_FOLDER, exist_ok=True)  # Создаёт папку, если её нет
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER 
# Path to the SQLite database
DATABASE = 'database/donations.db'
app.secret_key = 'root_123'
ADMIN_USERNAME = 'root_123'
ADMIN_PASSWORD = '4444'

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


@app.route('/leaderboard')
def leaderboard():
    # Получаем топ пользователей, сортируя по полю points (очки)
    top_users = get_db_connection().execute("""
        SELECT id, username, avatar, points 
        FROM users 
        ORDER BY points DESC NULLS LAST 
        LIMIT 50
    """).fetchall()

    conn = get_db_connection()

    user = None

    if session.get("user_id"):
        user = conn.execute(
            "SELECT * FROM users WHERE id = ?", (session["user_id"],)
        ).fetchone()

    return render_template('leaderboard.html', top_users=top_users, user=user)

@app.route('/admin')
def admin_dashboard():
    if 'admin' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    
    try:
        users = conn.execute("SELECT id, username, blocked FROM users").fetchall()
        organizations = conn.execute("SELECT id, name, blocked FROM organizations").fetchall()
        
        # Исправленный запрос для донатов
        donations = conn.execute("""
            SELECT 
                d.id, 
                d.amount, 
                d.created_at, 
                d.user_id,
                c.title as campaign_title,
                d.receipt_path
            FROM donations d
            LEFT JOIN campaigns c ON d.campaign_id = c.id
            ORDER BY d.created_at DESC
        """).fetchall()
        
        return render_template(
            'admin.html',
            users=users,
            organizations=organizations,
            donations=donations
        )
    except Exception as e:
        print(f"Ошибка: {e}")
        return "Ошибка сервера", 500
    finally:
        conn.close()

@app.route('/admin/confirm_donation/<int:donation_id>', methods=['POST'])
def confirm_donation(donation_id):
    if 'admin' not in session:
        return jsonify({'error': 'Доступ запрещен'}), 403
    
    conn = get_db_connection()
    
    # Получаем сумму пожертвования
    donation = conn.execute('SELECT amount, campaign_id FROM donations WHERE id = ?', (donation_id,)).fetchone()
    
    # Обновляем статус
    conn.execute("UPDATE donations SET status = 'confirmed' WHERE id = ?", (donation_id,))
    
    # Обновляем собранную сумму в кампании
    conn.execute('''
        UPDATE campaigns 
        SET collected = collected + ? 
        WHERE id = ?
    ''', (donation['amount'], donation['campaign_id']))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'message': 'Пожертвование подтверждено'})

@app.route('/admin/reject_donation/<int:donation_id>', methods=['POST'])
def reject_donation(donation_id):
    if 'admin' not in session:
        return jsonify({'error': 'Доступ запрещен'}), 403
    
    conn = get_db_connection()
    conn.execute("UPDATE donations SET status = 'rejected' WHERE id = ?", (donation_id,))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'message': 'Пожертвование отклонено'})


@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    flash('Вы вышли из админ-панели', 'info')
    return redirect(url_for('login'))

@app.route('/admin/block_user/<int:user_id>', methods=['POST'])
def block_user(user_id):
    if 'admin' not in session:
        return jsonify({'error': 'Доступ запрещен'}), 403
    
    conn = get_db_connection()
    conn.execute("UPDATE users SET blocked = 1 WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'message': 'Пользователь заблокирован'})

@app.route('/admin/view_receipt/<int:donation_id>')
def view_receipt(donation_id):
    conn = get_db_connection()
    donation = conn.execute("""
        SELECT d.id, d.amount, d.created_at, d.message, d.receipt_path, 
               c.title as campaign_title 
        FROM donations d 
        JOIN campaigns c ON d.campaign_id = c.id 
        WHERE d.id = ?
    """, (donation_id,)).fetchone()
    conn.close()
    donation = dict(donation)  # Преобразуем sqlite.Row в словарь
    donation["receipt_path"] = donation["receipt_path"].replace("\\", "/")
    if not donation:
        return "Чек не найден", 404
    
    return render_template('receipt.html', donation=donation)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
@app.route('/admin/unblock_user/<int:user_id>', methods=['POST'])
def unblock_user(user_id):
    if 'admin' not in session:
        return jsonify({'error': 'Доступ запрещен'}), 403
    
    conn = get_db_connection()
    conn.execute("UPDATE users SET blocked = 0 WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'message': 'Пользователь разблокирован'})
     
@app.route('/organization/<int:org_id>/posts')
def organization_posts(org_id):
    conn = get_db_connection()
    
    # Получаем данные организации
    organization = conn.execute(
        "SELECT * FROM organizations WHERE id = ?", 
        (org_id,)
    ).fetchone()
    
    if not organization:
        flash('Организация не найдена', 'danger')
        return redirect(url_for('organizations'))
    
    # Получаем публикации организации
    posts = conn.execute(
        "SELECT * FROM organization_posts WHERE org_id = ? ORDER BY created_at DESC",
        (org_id,)
    ).fetchall()
    
    # Проверяем, подписан ли текущий пользователь
    is_following = False
    if session.get('user_id'):
        follow = conn.execute(
            "SELECT * FROM followers WHERE user_id = ? AND organization_id = ?",
            (session['user_id'], org_id)
        ).fetchone()
        is_following = bool(follow)
    
    conn.close()
    
    return render_template(
        'organization_posts.html',
        organization=organization,
        posts=posts,
        is_following=is_following,
        user=user if 'user_id' in session else None
    )

@app.route('/organization/create_post', methods=['GET', 'POST'])
def create_organization_post():
    if 'org_id' not in session:
        flash('Только организации могут создавать посты', 'danger')
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        org_id = session['org_id']
        
        # Обработка загрузки изображения
        if 'image' not in request.files:
            flash('Файл не выбран', 'danger')
            return redirect(request.url)
        
        file = request.files['image']
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            image_url = filepath
        else:
            flash('Недопустимый формат файла', 'danger')
            return redirect(request.url)
        
        conn = get_db_connection()
        conn.execute(
            "INSERT INTO organization_posts (org_id, title, content, image_url) VALUES (?, ?, ?, ?)",
            (org_id, title, content, image_url)
        )
        conn.commit()
        conn.close()
        
        flash('Пост успешно создан!', 'success')
        return redirect(url_for('organization_posts', org_id=org_id))
    
    return render_template('create_organization_post.html')
# Функция поиска похожих кампаний
def delete_old_entries():
    conn = sqlite3.connect("database/donations.db")
    cursor = conn.cursor()
    
    today = datetime.today().strftime('%Y-%m-%d')
    
    cursor.execute("DELETE FROM volunteering_opportunities WHERE date < ?", (today,))
    
    conn.commit()
    conn.close()
    print("✅ Автоматически удалены старые кампании и волонтёрские акции!")

# Удаляем старые записи перед запуском сервера
delete_old_entries()
# Загружаем стоп-слова
nltk.download('stopwords')
russian_stopwords = stopwords.words('english')
def get_similar_volunteering(opportunity_id, top_n=3):
    conn = sqlite3.connect('database/donations.db')
    df = pd.read_sql_query("SELECT id, title, description FROM volunteering_opportunities", conn)
    conn.close()

    print("📌 Загруженные волонтерские программы:")
    print(df)

    if df.empty:
        print("❌ Нет волонтерских программ в базе!")
        return []

    if opportunity_id not in df["id"].tolist():
        print(f"❌ Волонтерская программа с ID {opportunity_id} не найдена!")
        return []

    df["description"] = df["description"].fillna("")  # Убираем пустые значения

    vectorizer = TfidfVectorizer()
    tfidf_matrix = vectorizer.fit_transform(df["description"])

    idx = df[df["id"] == opportunity_id].index[0]
    print(f"🔍 Индекс программы: {idx}")

    cosine_sim = cosine_similarity(tfidf_matrix[idx], tfidf_matrix).flatten()
    similar_indices = cosine_sim.argsort()[-(top_n + 1):-1][::-1]
    print(f"✅ Найдены похожие программы (индексы): {similar_indices}")

    recommended = df.iloc[similar_indices].to_dict(orient="records")
    print(f"✅ Рекомендации: {recommended}")

    return recommended
@app.route('/recommend_volunteering/<int:opportunity_id>')
def recommend_volunteering(opportunity_id):
    recommendations = get_similar_volunteering(opportunity_id)
    return jsonify(recommendations)

# В тех местах, где выводится сумма собранных средств
@app.route('/campaign/<int:campaign_id>')
def campaign_details(campaign_id):
    conn = get_db_connection()
    campaign = conn.execute('''
        SELECT *, 
        (SELECT SUM(amount) FROM donations 
         WHERE campaign_id = ? AND status = 'confirmed') as collected
        FROM campaigns WHERE id = ?
    ''', (campaign_id, campaign_id)).fetchone()
    conn.close()
    # ...
@app.route('/volunteering/<int:opportunity_id>')
def volunteering_details(opportunity_id):
    conn = get_db_connection()
    opportunity = conn.execute('SELECT * FROM volunteering_opportunities WHERE id = ?', (opportunity_id,)).fetchone()
    user_id = session.get("user_id")
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()

    if not opportunity:
        return "Волонтёрская программа не найдена", 404

    return render_template('volunteering_details.html', opportunity=opportunity, user = user)

# ✅ Функция поиска похожих кампаний
def get_similar_campaigns(campaign_id, top_n=3):
    conn = sqlite3.connect('database/donations.db')
    df = pd.read_sql_query("SELECT id, title, description FROM campaigns", conn)
    conn.close()

    # 🔹 Логируем, что получили из базы
    print("📌 Загруженные кампании из БД:")
    print(df)

    if df.empty:
        print("❌ Нет кампаний в базе!")
        return []

    # 🔹 Проверяем, есть ли нужный campaign_id
    if campaign_id not in df["id"].tolist():
        print(f"❌ Кампания с ID {campaign_id} не найдена!")
        return []

    # 🔹 Заполняем пустые описания, чтобы избежать ошибок
    df["description"] = df["description"].fillna("")

    # 🔹 Векторизация (убираем stop_words)
    vectorizer = TfidfVectorizer()
    tfidf_matrix = vectorizer.fit_transform(df["description"])

    # 🔹 Находим индекс кампании
    idx = df[df["id"] == campaign_id].index[0]
    print(f"🔍 Индекс кампании: {idx}")

    # 🔹 Вычисляем косинусное сходство
    cosine_sim = cosine_similarity(tfidf_matrix[idx], tfidf_matrix).flatten()

    # 🔹 Находим top_n самых похожих
    similar_indices = cosine_sim.argsort()[-(top_n + 1):-1][::-1]
    print(f"✅ Найдены похожие кампании (индексы): {similar_indices}")

    recommended = df.iloc[similar_indices].to_dict(orient="records")
    print(f"✅ Рекомендации: {recommended}")

    return recommended


@app.route('/recommend_campaigns/<int:campaign_id>')
def recommend_campaigns(campaign_id):
    recommendations = get_similar_campaigns(campaign_id)
    return jsonify(recommendations)
def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row  
    return conn
@app.route('/volunteering.html')
def volunteering():
    conn = get_db_connection()

    # Получение списка волонтерских акций
    opportunities = conn.execute('SELECT * FROM volunteering_opportunities').fetchall()
    
    # Получение данных пользователя, если он авторизован
    user = None
    if session.get('user_id'):
        user = conn.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()

    conn.close()

    return render_template('volunteering.html', opportunities=opportunities, user=user)
def delete_old_campaigns():
    conn = get_db_connection()
    cursor = conn.cursor()

    today = datetime.today().strftime('%Y-%m-%d')  # Получаем текущую дату

    # Удаляем устаревшие волонтёрские программы
    cursor.execute("DELETE FROM volunteering_opportunities WHERE date < ?", (today,))

    # Удаляем устаревшие кампании (если у них есть дата завершения)

    conn.commit()
    conn.close()
    print("✅ Старые кампании и акции удалены!")

delete_old_campaigns()


@app.route("/", methods=["GET", "POST"])
def home():
    query = ""
    campaigns = []
    user = None  
    conn = get_db_connection()

    # Проверяем, авторизован ли пользователь
    if session.get("user_id"):
        user = conn.execute(
            "SELECT * FROM users WHERE id = ?", (session["user_id"],)
        ).fetchone()

    if request.method == "POST":
        query = request.form.get("query", "")
        if query:
            campaigns = conn.execute(
                "SELECT * FROM campaigns WHERE title LIKE ? OR description LIKE ?",
                (f"%{query}%", f"%{query}%"),
            ).fetchall()
        else:
            campaigns = conn.execute("SELECT * FROM campaigns").fetchall()
    else:
        campaigns = conn.execute("SELECT * FROM campaigns").fetchall()

    # Проверяем, есть ли хотя бы одна кампания
    campaign = conn.execute("SELECT * FROM campaigns ORDER BY id LIMIT 1").fetchone()

    if campaign:
        percentage_collected = (campaign['collected'] / campaign['goal']) * 100 if campaign['goal'] else 0
    else:
        campaign = None  # Если нет кампаний, передаем None
        percentage_collected = 0
    ads = conn.execute("SELECT * FROM ads").fetchall()

    conn.close()

    return render_template(
        "index.html",
        user=user,
        campaign=campaign,
        campaigns=campaigns,
        percentage_collected=percentage_collected,
        query=query,
        ads = ads,
    )

@app.route('/donate/<int:campaign_id>', methods=['GET', 'POST'])
def donate(campaign_id):
    conn = get_db_connection()
    campaign = conn.execute('SELECT * FROM campaigns WHERE id = ?', (campaign_id,)).fetchone()
    user_id = session.get('user_id')
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone() if user_id else None

    if not campaign:
        conn.close()
        return "Кампания не найдена", 404

    if request.method == 'POST':
        try:
            name = request.form['name']
            amount = float(request.form['amount'])
            message = request.form.get('message', '')

            # Обработка файла чека
            if 'receipt' not in request.files:
                return jsonify({'success': False, 'error': 'Чек обязателен'}), 400

            receipt = request.files['receipt']
            if receipt.filename == '':
                return jsonify({'success': False, 'error': 'Файл не выбран'}), 400

            if receipt and allowed_file(receipt.filename):
                filename = secure_filename(receipt.filename)
                filepath = os.path.join(RECEIPTS_FOLDER, filename)
                receipt.save(filepath)

                # Сохраняем в базу
                conn.execute(
                    '''INSERT INTO donations 
                    (campaign_id, name, amount, message, user_id, receipt_path, status, created_at) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                    (campaign_id, name, amount, message, user_id, filepath, 'pending', datetime.now())
                )
                conn.commit()
                conn.close()
                return jsonify({'success': True})
            else:
                return jsonify({'success': False, 'error': 'Недопустимый формат файла'}), 400
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    # GET-запрос - показываем форму
    return render_template('donate.html', campaign=campaign, user=user)
@app.route('/get_payment_history')
def get_payment_history():
    if not session.get('user_id'):
        return jsonify([])  # Если не авторизован — пустой список

    user_id = session['user_id']
    conn = get_db_connection()

    payments = conn.execute("""
        SELECT d.amount, d.message, d.created_at AS date, c.title AS campaign_title
        FROM donations d
        JOIN campaigns c ON d.campaign_id = c.id
        WHERE d.user_id = ?
        ORDER BY d.created_at DESC
    """, (user_id,)).fetchall()

    conn.close()

    return jsonify([dict(payment) for payment in payments])



@app.route('/join_volunteering/<int:opportunity_id>', methods=['POST'])
def join_volunteering(opportunity_id):
    if not session.get('user_id'):
        return jsonify({"message": "Вы должны быть авторизованы!"}), 403

    user_id = session['user_id']
    conn = get_db_connection()

    # Проверяем, не участвует ли уже пользователь
    existing = conn.execute(
        "SELECT * FROM volunteer_participants WHERE user_id = ? AND opportunity_id = ?",
        (user_id, opportunity_id)
    ).fetchone()
    
    if existing:
        conn.close()
        return jsonify({"message": "Вы уже участвуете в этой программе!"})

    # ✅ Автоматически устанавливаем статус 'confirmed' и начисляем 10 баллов
    conn.execute(
        "INSERT INTO volunteer_participants (user_id, opportunity_id, status) VALUES (?, ?, ?)",
        (user_id, opportunity_id, "confirmed")
    )
    conn.execute("UPDATE users SET points = points + 10 WHERE id = ?", (user_id,))
    
    conn.commit()
    conn.close()

    return jsonify({"message": "Вы успешно записались на волонтёрскую программу! 10 баллов начислено."})

@app.route('/confirm_volunteer/<int:user_id>/<int:opportunity_id>', methods=['POST'])
def confirm_volunteer(user_id, opportunity_id):
    conn = get_db_connection()

    # Обновляем статус участника
    conn.execute("UPDATE volunteer_participants SET status = 'confirmed' WHERE user_id = ? AND opportunity_id = ?",
                 (user_id, opportunity_id))

    # Начисляем пользователю баллы
    conn.execute("UPDATE users SET points = points + 10 WHERE id = ?", (user_id,))

    conn.commit()
    conn.close()

    return jsonify({"message": "Участие подтверждено! 10 баллов начислено."})
@app.route('/thank_you')
def thank_you():
    return render_template('thank_you.html')
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')

        conn = get_db_connection()
        cursor = conn.cursor()

        # Простая вставка в таблицу users (без разделения на типы аккаунтов)
        cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed_password))

        conn.commit()
        conn.close()

        flash('Регистрация успешна!', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')




@app.route('/profile')
def profile():
    if not session.get('user_id'):
        flash('Сначала войдите в систему!', 'danger')
        return redirect(url_for('login'))

    conn = get_db_connection()
    user_id = session['user_id']

    # ✅ Получаем данные пользователя
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    # ✅ Кампании, созданные пользователем
    campaigns = conn.execute(
        "SELECT * FROM campaigns WHERE user_id = ?", (user_id,)
    ).fetchall()

    # ✅ Волонтёрские программы, созданные пользователем
    user_opportunities = conn.execute(
        """SELECT v.*, 
        (SELECT COUNT(*) FROM volunteer_participants WHERE opportunity_id = v.id) AS participant_count
        FROM volunteering_opportunities v WHERE v.user_id = ?""",
        (user_id,)
    ).fetchall()
    user_opportunities = [dict(row) for row in user_opportunities]

    # ✅ Участники этих программ
    for opportunity in user_opportunities:
        participants = conn.execute("""
            SELECT u.id AS user_id, u.username, vp.status 
            FROM volunteer_participants vp 
            JOIN users u ON vp.user_id = u.id 
            WHERE vp.opportunity_id = ?
        """, (opportunity['id'],)).fetchall()
        opportunity['participants'] = [dict(participant) for participant in participants] if participants else []

    # ✅ Кампании, в которых user участвует
    participated_campaigns = conn.execute("""
        SELECT c.* FROM donations d
        JOIN campaigns c ON d.campaign_id = c.id
        WHERE d.user_id = ?
        GROUP BY c.id
    """, (user_id,)).fetchall()

    # ✅ Волонтерские акции, в которых user участвует
    participated_opportunities = conn.execute("""
        SELECT DISTINCT v.*
        FROM volunteer_participants vp
        JOIN volunteering_opportunities v ON vp.opportunity_id = v.id
        WHERE vp.user_id = ? AND vp.status = 'confirmed'
    """, (user_id,)).fetchall()
    # ✅ Волонтёрские инициативы, созданные пользователем
    volunteer_initiatives = conn.execute(
        """SELECT v.*, 
        (SELECT COUNT(*) FROM volunteer_participants WHERE opportunity_id = v.id) AS participant_count
        FROM volunteering_opportunities v WHERE v.user_id = ?""",
        (user_id,)
    ).fetchall()

    # ✅ Преобразуем в список словарей
    volunteer_initiatives = [dict(row) for row in volunteer_initiatives]
    donations = conn.execute("""
        SELECT d.amount, d.message, d.created_at, c.title
        FROM donations d
        JOIN campaigns c ON d.campaign_id = c.id
        WHERE d.user_id = ?
        ORDER BY d.created_at DESC
    """, (user_id,)).fetchall()
    conn.close()
    return render_template(
        'profile.html',
        user=user,
        campaigns=campaigns,  
        user_opportunities=user_opportunities,
        volunteer_initiatives=volunteer_initiatives,
        participated_campaigns=participated_campaigns,  # ✅ Добавили кампании, где user участвует
        participated_opportunities=participated_opportunities,  # ✅ Добавили акции, где user участвует
        donations = donations
    )
@app.route('/update_avatar', methods=['GET', 'POST'])
def update_avatar():
    if not session.get('user_id'):
        flash('Сначала войдите в систему!', 'danger')
        return redirect(url_for('login'))

    if request.method == 'POST':
        if 'avatar' not in request.files:
            flash('Файл не выбран', 'danger')
            return redirect(request.url)

        file = request.files['avatar']

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            # Обновляем путь к аватарке в базе данных
            conn = get_db_connection()
            conn.execute(
                'UPDATE users SET avatar = ? WHERE id = ?',
                (filepath, session['user_id'])
            )
            conn.commit()
            conn.close()

            flash('Аватарка успешно обновлена!', 'success')
            return redirect(url_for('profile'))
        else:
            flash('Недопустимый формат файла. Разрешены: PNG, JPG, JPEG, GIF.', 'danger')

    return render_template('update_avatar.html')
# Вход
# Вход
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        # 1️⃣ Проверяем, если зашел админ
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['admin'] = True
            session['role'] = "admin"
            flash('Вы вошли как администратор!', 'success')
            return redirect(url_for('admin_dashboard'))

        # 2️⃣ Подключаемся к БД
        conn = get_db_connection()
        cursor = conn.cursor()

        # 3️⃣ Проверяем в таблице пользователей
        user = cursor.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        if user:
            if user['blocked']:  # Проверяем, если пользователь заблокирован
                flash('Ваш аккаунт заблокирован!', 'danger')
                conn.close()
                return redirect(url_for('login'))

            if check_password_hash(user['password'], password):
                session['user_id'] = user['id']
                session['username'] = user['username']
                session['role'] = "user"  # ✅ Указываем роль
                flash('Вы успешно вошли!', 'success')
                conn.close()
                return redirect(url_for('home'))

        # 4️⃣ Проверяем в таблице организаций
        organization = cursor.execute('SELECT * FROM organizations WHERE name = ?', (username,)).fetchone()
        if organization:
            if organization['blocked']:
                flash('Ваша организация заблокирована!', 'danger')
                conn.close()
                return redirect(url_for('login'))

            if check_password_hash(organization['password'], password):
                session['org_id'] = organization['id']
                session['username'] = organization['name']
                session['role'] = "organization"
                flash('Вы вошли как организация!', 'success')
                conn.close()
                return redirect(url_for('organization_dashboard', org_id=organization['id']))


        conn.close()
        flash('Неверное имя пользователя или пароль.', 'danger')

    return render_template('login.html')
@app.route('/organization/edit', methods=['GET', 'POST'])
def edit_organization_profile():
    if 'org_id' not in session:
        flash('Вы должны войти как организация!', 'danger')
        return redirect(url_for('login'))

    conn = get_db_connection()
    organization = conn.execute("SELECT * FROM organizations WHERE id = ?", (session['org_id'],)).fetchone()

    if not organization:
        flash("Организация не найдена!", "danger")
        conn.close()
        return redirect(url_for("organizations"))

    if request.method == 'POST':
        new_name = request.form['name']
        new_description = request.form['description']
        new_image_url = request.form['image_url']

        conn.execute("UPDATE organizations SET name = ?, description = ?, image_url = ? WHERE id = ?", 
                     (new_name, new_description, new_image_url, session['org_id']))
        conn.commit()
        conn.close()

        flash('Профиль обновлён!', 'success')
        return redirect(url_for('organization_dashboard', org_id=session['org_id']))

    conn.close()
    return render_template('edit_organization_profile.html', organization=organization)



# Выход из аккаунта
@app.route('/logout')
def logout():
    session.clear()
    flash('Вы вышли из аккаунта.', 'info')
    return redirect(url_for('login'))
@app.route('/organizations')
def organizations():
    conn = get_db_connection()
    organizations = conn.execute("SELECT * FROM organizations").fetchall()
    user = None
    if session.get('user_id'):
        user = conn.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    conn.close()
    return render_template('organizations.html', organizations=organizations, user = user)
@app.route('/create_campaign', methods=['GET', 'POST'])
def create_campaign():
    if not session.get('user_id'):
        flash('Сначала войдите в систему!', 'danger')
        return redirect(url_for('login'))

    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (session['user_id'],)).fetchone()
    conn.close()

    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        goal = float(request.form['goal'])
        days_left = int(request.form['days_left'])
        payment_details = request.form['payment_details']

        if 'image' not in request.files:
            flash('Файл изображения не выбран', 'danger')
            return redirect(request.url)

        file = request.files['image']
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            image_url = f'static/uploads/{filename}'
        else:
            flash('Недопустимый формат файла', 'danger')
            return redirect(request.url)

        conn = get_db_connection()
        conn.execute(
            'INSERT INTO campaigns (title, description, image_url, goal, collected, days_left, user_id, payment_details) '
            'VALUES (?, ?, ?, ?, 0, ?, ?, ?)',
            (title, description, image_url, goal, days_left, session['user_id'], payment_details)
        )
        conn.commit()
        conn.close()

        flash('Кампания успешно создана!', 'success')
        return redirect(url_for('profile'))

    return render_template('create_campaign.html', user=user)  # ✅ Передаём user в шаблон



def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
@app.route('/participate/<int:opportunity_id>', methods=['POST'])
def participate(opportunity_id):
    if not session.get('user_id'):
        return jsonify({'success': False, 'error': 'Вы должны быть авторизованы'}), 403

    conn = get_db_connection()
    user_id = session['user_id']

    # Проверяем, есть ли уже запись об участии
    existing_participation = conn.execute(
        "SELECT * FROM volunteer_participants WHERE user_id = ? AND opportunity_id = ?",
        (user_id, opportunity_id)
    ).fetchone()

    if existing_participation:
        return jsonify({'success': False, 'error': 'Вы уже зарегистрированы на эту программу'}), 400

    # Добавляем пользователя в список участников
    conn.execute(
        "INSERT INTO volunteer_participants (user_id, opportunity_id, status) VALUES (?, ?, ?)",
        (user_id, opportunity_id, 'confirmed')
    )
    conn.execute(
        "UPDATE users SET points = points + 10 WHERE id = ?",
        (user_id,)
    )
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': 'Вы успешно зарегистрировались на участие!'})
@app.route('/create_volunteering', methods=['GET', 'POST'])
def create_volunteering():
    if not session.get('user_id'):
        flash('Сначала войдите в систему!', 'danger')
        return redirect(url_for('login'))

    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()

    if request.method == 'POST':
        try:
            title = request.form.get('title')
            description = request.form.get('description')
            date = request.form.get('date')
            button_text = request.form.get('button_text')

            print(f"📌 Данные получены из формы: {title=}, {description=}, {date=}, {button_text=}")

            if not title or not description or not date:
                flash('Заполните все поля!', 'danger')
                return redirect(url_for('create_volunteering'))

            if 'image' not in request.files:
                flash('Файл изображения не выбран', 'danger')
                return redirect(request.url)

            file = request.files['image']
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
            else:
                flash('Недопустимый формат файла', 'danger')
                return redirect(request.url)

            print(f"📌 Файл сохранён в: {filepath}")

            # Проверяем session['user_id']
            user_id = session.get('user_id')
            if not user_id:
                print("❌ Ошибка: session['user_id'] пустой!")
                flash('Ошибка: Пользователь не авторизован!', 'danger')
                return redirect(url_for('login'))

            # Пробуем вставить в базу
            try:
                conn.execute(
                    'INSERT INTO volunteering_opportunities (title, description, date, image_url, button_text, user_id) VALUES (?, ?, ?, ?, ?, ?)',
                    (title, description, date, filepath, button_text, user_id)
                )
                print("✅ Данные отправлены в БД!")
                conn.commit()
                print("✅ Изменения сохранены в БД!")
            except Exception as e:
                print(f"❌ Ошибка при вставке в БД: {e}")

            conn.close()
            flash('Волонтёрская программа успешно создана!', 'success')
            return redirect(url_for('volunteering'))

        except Exception as e:
            flash(f'Ошибка: {str(e)}', 'danger')
            print(f"❌ Ошибка в обработке формы: {e}")

    conn.close()
    return render_template('create_volunteering.html', user=user)


@app.route('/get_participants/<int:opportunity_id>')
def get_participants(opportunity_id):
    conn = get_db_connection()
    participants = conn.execute("""
        SELECT u.username FROM volunteer_participants vp
        JOIN users u ON vp.user_id = u.id
        WHERE vp.opportunity_id = ? AND vp.status = 'confirmed'
    """, (opportunity_id,)).fetchall()
    conn.close()

    return jsonify([dict(participant) for participant in participants])

@app.route('/admin/ads', methods=['GET', 'POST'])
def manage_ads():
    if 'admin' not in session:
        return redirect(url_for('admin_login'))

    conn = get_db_connection()

    if request.method == 'POST':
        title = request.form['title']
        image_url = request.form['image_url']
        link = request.form['link']

        conn.execute("INSERT INTO ads (title, image_url, link) VALUES (?, ?, ?)", 
                     (title, image_url, link))
        conn.commit()
        flash('Реклама добавлена!', 'success')

    ads = conn.execute("SELECT * FROM ads").fetchall()
    conn.close()

    return render_template('admin_ads.html', ads=ads)

@app.route('/admin/delete_ad/<int:ad_id>', methods=['POST'])
def delete_ad(ad_id):
    if 'admin' not in session:
        return jsonify({'error': 'Доступ запрещен'}), 403

    conn = get_db_connection()
    conn.execute("DELETE FROM ads WHERE id = ?", (ad_id,))
    conn.commit()
    conn.close()

    flash('Реклама удалена!', 'success')
    return redirect(url_for('manage_ads'))

@app.route('/organization/profile')
def organization_profile():
    if 'org_id' not in session:
        flash('Вы должны войти как организация!', 'danger')
        return redirect(url_for('login'))

    conn = get_db_connection()
    organization = conn.execute("SELECT * FROM organizations WHERE id = ?", (session['org_id'],)).fetchone()
    followers = conn.execute("SELECT users.username FROM followers JOIN users ON followers.user_id = users.id WHERE followers.organization_id = ?", (session['org_id'],)).fetchall()
    conn.close()

    return render_template('organization_profile.html', organization=organization, followers=followers)
@app.route('/follow_organization/<int:organization_id>', methods=['POST'])
def follow_organization(organization_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Вы должны быть авторизованы!'}), 403

    user_id = session['user_id']
    conn = get_db_connection()

    # Проверяем, подписан ли уже пользователь
    existing_follow = conn.execute(
        "SELECT * FROM followers WHERE user_id = ? AND organization_id = ?",
        (user_id, organization_id)
    ).fetchone()

    if existing_follow:
        conn.close()
        return jsonify({'success': False, 'error': 'Вы уже подписаны на эту организацию!'}), 400

    # ✅ Добавляем пользователя в таблицу followers
    conn.execute(
        "INSERT INTO followers (user_id, organization_id) VALUES (?, ?)",
        (user_id, organization_id)
    )
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': 'Вы успешно подписались на организацию!'})
@app.route('/admin/block_organization/<int:org_id>', methods=['POST'])
def block_organization(org_id):
    if 'admin' not in session:
        return jsonify({'error': 'Доступ запрещен'}), 403
    
    conn = get_db_connection()
    conn.execute("UPDATE organizations SET blocked = 1 WHERE id = ?", (org_id,))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'message': 'Организация заблокирована'})


@app.route('/admin/unblock_organization/<int:org_id>', methods=['POST'])
def unblock_organization(org_id):
    if 'admin' not in session:
        return jsonify({'error': 'Доступ запрещен'}), 403
    
    conn = get_db_connection()
    conn.execute("UPDATE organizations SET blocked = 0 WHERE id = ?", (org_id,))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'message': 'Организация разблокирована'})

if __name__ == '__main__':
    app.run(debug=True)
