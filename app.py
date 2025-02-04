from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
import sqlite3
from flask import jsonify

app = Flask(__name__)
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
# Path to the SQLite database
DATABASE = 'database/donations.db'
app.secret_key = 'root_123'
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


@app.route("/", methods=["GET", "POST"])
def home():
    query = ""
    campaigns = []
    user = None  # Инициализируем переменную пользователя
    conn = get_db_connection()

    # Проверяем, авторизован ли пользователь
    if session.get("user_id"):
        user = conn.execute(
            "SELECT * FROM users WHERE id = ?", (session["user_id"],)
        ).fetchone()

    if request.method == "POST":
        # Поиск кампаний по запросу
        query = request.form.get("query", "")
        if query:
            campaigns = conn.execute(
                "SELECT * FROM campaigns WHERE title LIKE ? OR description LIKE ?",
                (f"%{query}%", f"%{query}%"),
            ).fetchall()
        else:
            campaigns = conn.execute("SELECT * FROM campaigns").fetchall()
    else:
        # Если нет поиска, показываем все кампании
        campaigns = conn.execute("SELECT * FROM campaigns").fetchall()

    # Получение основной кампании
    campaign = conn.execute("SELECT * FROM campaigns WHERE id = 1").fetchone()

    # Пожертвования для основной кампании
    donations = conn.execute(
        "SELECT * FROM donations WHERE campaign_id = 1 ORDER BY created_at DESC"
    ).fetchall()

    conn.close()

    # Рассчитываем процент сбора для основной кампании
    percentage_collected = (campaign['collected'] / campaign['goal']) * 100 if campaign['goal'] else 0

    return render_template(
        "index.html",
        user=user,  # Передаем данные пользователя в шаблон
        campaign=campaign,
        campaigns=campaigns,
        donations=donations,
        percentage_collected=percentage_collected,
        query=query,
    )


@app.route('/donate/<int:campaign_id>', methods=['GET', 'POST'])
def donate(campaign_id):
    conn = get_db_connection()
    campaign = conn.execute('SELECT * FROM campaigns WHERE id = ?', (campaign_id,)).fetchone()

    if not campaign:
        return "Кампания не найдена", 404

    if request.method == 'POST':
        name = request.form['name']
        amount = float(request.form['amount'])
        message = request.form.get('message', '')

        # Добавляем user_id, если пользователь авторизован
        user_id = session.get('user_id')

        conn.execute(
            'INSERT INTO donations (campaign_id, name, amount, message, user_id) VALUES (?, ?, ?, ?, ?)',
            (campaign_id, name, amount, message, user_id)
        )
        conn.execute('UPDATE campaigns SET collected = collected + ? WHERE id = ?', (amount, campaign_id))
        conn.commit()
        conn.close()

        return redirect(url_for('thank_you'))

    conn.close()
    return render_template('donate.html', campaign=campaign)

@app.route('/join_volunteering/<int:opportunity_id>', methods=['POST'])
def join_volunteering(opportunity_id):
    if not session.get('user_id'):
        return jsonify({"message": "Вы должны быть авторизованы!"}), 403

    user_id = session['user_id']
    conn = get_db_connection()

    # Проверяем, не участвует ли уже пользователь
    existing = conn.execute("SELECT * FROM volunteer_participants WHERE user_id = ? AND opportunity_id = ?",
                            (user_id, opportunity_id)).fetchone()
    if existing:
        conn.close()
        return jsonify({"message": "Вы уже участвуете в этой программе!"})

    # Добавляем запись о участии
    conn.execute("INSERT INTO volunteer_participants (user_id, opportunity_id, status) VALUES (?, ?, ?)",
                 (user_id, opportunity_id, "pending"))
    conn.commit()
    conn.close()

    return jsonify({"message": "Вы успешно записались на волонтёрскую программу!"})
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
        hashed_password = generate_password_hash(password)
        conn = get_db_connection()
        cursor = conn.cursor()
        # Проверка на существование пользователя
        cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
        if cursor.fetchone():
            flash('Пользователь с таким именем уже существует!', 'danger')
            return redirect(url_for('register'))
        
        # Сохранение нового пользователя
        cursor.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, hashed_password))
        conn.commit()
        conn.close()

        flash('Регистрация прошла успешно! Теперь вы можете войти.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')
@app.route('/profile')
def profile():
    if not session.get('user_id'):
        flash('Сначала войдите в систему!', 'danger')
        return redirect(url_for('login'))

    conn = get_db_connection()
    user_id = session['user_id']

    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    # Получаем организованные кампании
    # Преобразуем sqlite3.Row в обычный словарь
    user_opportunities = conn.execute(
        """SELECT v.*, 
        (SELECT COUNT(*) FROM volunteer_participants WHERE opportunity_id = v.id) AS participant_count
        FROM volunteering_opportunities v WHERE v.user_id = ?""",
        (user_id,)
    ).fetchall()

    # Преобразуем каждый Row в словарь
    user_opportunities = [dict(row) for row in user_opportunities]

    # Получаем участников для этих кампаний
    for opportunity in user_opportunities:
        participants = conn.execute("""
            SELECT u.id AS user_id, u.username, vp.status 
            FROM volunteer_participants vp 
            JOIN users u ON vp.user_id = u.id 
            WHERE vp.opportunity_id = ?
        """, (opportunity['id'],)).fetchall()

        # Если участников нет, создаем пустой список
        participants = [dict(participant) for participant in participants] if participants else []

        # Добавляем участников в opportunity
        opportunity['participants'] = participants


    # Получаем подтверждённые программы участника
    confirmed_opportunities = conn.execute("""
        SELECT v.* FROM volunteer_participants vp
        JOIN volunteering_opportunities v ON vp.opportunity_id = v.id
        WHERE vp.user_id = ? AND vp.status = 'confirmed'
    """, (user_id,)).fetchall()

    conn.close()

    return render_template(
        'profile.html',
        user=user,
        user_opportunities=user_opportunities,
        confirmed_opportunities=confirmed_opportunities
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
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()

        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            flash('Вы успешно вошли!', 'success')
            return redirect(url_for('home'))
        else:
            flash('Неправильное имя пользователя или пароль.', 'danger')
            return redirect(url_for('login'))

    return render_template('login.html')


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

    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        goal = float(request.form['goal'])
        days_left = int(request.form['days_left'])

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
            'INSERT INTO campaigns (title, description, image_url, goal, collected, days_left, user_id) VALUES (?, ?, ?, ?, 0, ?, ?)',
            (title, description, image_url, goal, days_left, session['user_id'])
        )
        conn.commit()
        conn.close()

        flash('Кампания успешно создана!', 'success')
        return redirect(url_for('profile'))

    return render_template('create_campaign.html')


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
        (user_id, opportunity_id, 'pending')
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
            date = request.form.get('date')  # Используем .get() вместо []
            button_text = request.form.get('button_text')

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

            conn.execute(
                'INSERT INTO volunteering_opportunities (title, description, date, image_url, button_text, user_id) VALUES (?, ?, ?, ?, ?, ?)',
                (title, description, date, filepath, button_text, session['user_id'])
            )
            conn.commit()
            conn.close()

            flash('Волонтёрская программа успешно создана!', 'success')
            return redirect(url_for('volunteering'))

        except Exception as e:
            flash(f'Ошибка: {str(e)}', 'danger')

    conn.close()
    return render_template('create_volunteering.html', user=user)

if __name__ == '__main__':
    app.run(debug=True)
