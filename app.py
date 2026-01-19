"""
Облачное хранилище файлов и альбомов
Flask Application - CloudVault
"""

import os
import sqlite3
import uuid
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, abort, jsonify
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# Конфигурация приложения
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-in-production'
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
app.config['ALBUMS_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads', 'albums')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB максимальный размер файла

# Расширения файлов
ALLOWED_EXTENSIONS = {
    'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp',  # Изображения
    'pdf', 'txt', 'doc', 'docx', 'xls', 'xlsx',  # Документы
    'zip', 'rar', '7z',                           # Архивы
}

ALLOWED_PHOTO_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

# Инициализация базы данных
def init_db():
    """Инициализация базы данных SQLite"""
    conn = sqlite3.connect('oblako.db')
    cursor = conn.cursor()
    
    # Таблица пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица файлов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            original_name TEXT NOT NULL,
            file_type TEXT NOT NULL,
            file_size INTEGER NOT NULL,
            upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Таблица альбомов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS albums (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            cover_photo TEXT,
            photo_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Таблица фотографий
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS photos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            album_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            original_name TEXT NOT NULL,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (album_id) REFERENCES albums (id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    conn.commit()
    conn.close()

# Проверка расширения файла
def allowed_file(filename):
    """Проверка допустимости расширения файла"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def allowed_photo(filename):
    """Проверка допустимости расширения фото"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_PHOTO_EXTENSIONS

# Класс пользователя для Flask-Login
class User(UserMixin):
    def __init__(self, id, username, email):
        self.id = id
        self.username = username
        self.email = email

# Инициализация Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    """Загрузка пользователя по ID"""
    conn = sqlite3.connect('oblako.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, username, email FROM users WHERE id = ?', (user_id,))
    user_data = cursor.fetchone()
    conn.close()
    
    if user_data:
        return User(user_data[0], user_data[1], user_data[2])
    return None

# ==================== РОУТЫ ====================

@app.route('/')
def index():
    """Главная страница - перенаправление на dashboard или вход"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Страница входа"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        conn = sqlite3.connect('oblako.db')
        cursor = conn.cursor()
        cursor.execute('SELECT id, username, email, password_hash FROM users WHERE username = ?', (username,))
        user_data = cursor.fetchone()
        conn.close()
        
        if user_data and check_password_hash(user_data[3], password):
            user = User(user_data[0], user_data[1], user_data[2])
            login_user(user)
            flash('Добро пожаловать, {0}!'.format(user.username), 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Неверное имя пользователя или пароль', 'error')
    
    return render_template('index.html', mode='login')

@app.route('/register', methods=['GET', 'POST'])
def register():
    """Регистрация нового пользователя"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        password_confirm = request.form.get('password_confirm')
        
        # Валидация данных
        if password != password_confirm:
            flash('Пароли не совпадают', 'error')
            return render_template('index.html', mode='register')
        
        if len(password) < 6:
            flash('Пароль должен содержать минимум 6 символов', 'error')
            return render_template('index.html', mode='register')
        
        try:
            conn = sqlite3.connect('oblako.db')
            cursor = conn.cursor()
            
            # Проверка существующего пользователя
            cursor.execute('SELECT id FROM users WHERE username = ? OR email = ?', (username, email))
            if cursor.fetchone():
                flash('Пользователь с таким именем или email уже существует', 'error')
                conn.close()
                return render_template('index.html', mode='register')
            
            # Создание нового пользователя
            password_hash = generate_password_hash(password)
            cursor.execute('INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)',
                          (username, email, password_hash))
            conn.commit()
            user_id = cursor.lastrowid
            conn.close()
            
            flash('Регистрация успешна! Теперь вы можете войти.', 'success')
            return redirect(url_for('login'))
            
        except Exception as e:
            flash('Ошибка при регистрации: {0}'.format(str(e)), 'error')
    
    return render_template('index.html', mode='register')

@app.route('/logout')
@login_required
def logout():
    """Выход из системы"""
    logout_user()
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    """Панель управления - список файлов"""
    conn = sqlite3.connect('oblako.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, filename, original_name, file_type, file_size, upload_date
        FROM files WHERE user_id = ? ORDER BY upload_date DESC
    ''', (current_user.id,))
    files = cursor.fetchall()
    conn.close()
    
    # Форматирование данных файлов
    files_list = []
    images_count = 0
    docs_count = 0
    for f in files:
        file_type = f[3]
        if file_type in ['png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp']:
            thumbnail = url_for('static', filename='uploads/albums/' + f[1])
            images_count += 1
        elif file_type in ['pdf', 'doc', 'docx', 'txt']:
            thumbnail = None
            docs_count += 1
        else:
            thumbnail = None
        
        files_list.append({
            'id': f[0],
            'filename': f[1],
            'original_name': f[2],
            'file_type': file_type,
            'file_size': f[4],
            'upload_date': f[5],
            'thumbnail': thumbnail
        })
    
    return render_template('files.html', files=files_list, images_count=images_count, docs_count=docs_count)

@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    """Загрузка файлов"""
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('Файл не выбран', 'error')
            return redirect(request.url)
        
        file = request.files['file']
        if file.filename == '':
            flash('Файл не выбран', 'error')
            return redirect(request.url)
        
        if file and allowed_file(file.filename):
            # Безопасное имя файла
            original_name = secure_filename(file.filename)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
            filename = timestamp + str(uuid.uuid4().hex[:8]) + '_' + original_name
            
            # Создание директории если не существует
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            
            # Сохранение файла
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            
            # Определение типа файла
            ext = original_name.rsplit('.', 1)[1].lower()
            
            # Размер файла
            file_size = os.path.getsize(file_path)
            
            # Сохранение в базу данных
            conn = sqlite3.connect('oblako.db')
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO files (user_id, filename, original_name, file_type, file_size)
                VALUES (?, ?, ?, ?, ?)
            ''', (current_user.id, filename, original_name, ext, file_size))
            conn.commit()
            conn.close()
            
            flash('Файл "{0}" успешно загружен'.format(original_name), 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Недопустимый тип файла. Разрешены: изображения, документы, архивы', 'error')
    
    return render_template('upload.html')

@app.route('/uploads/<filename>')
@login_required
def uploaded_file(filename):
    """Скачивание файла"""
    conn = sqlite3.connect('oblako.db')
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, original_name FROM files WHERE filename = ?', (filename,))
    file_data = cursor.fetchone()
    conn.close()
    
    if file_data is None:
        abort(404)
    
    # Проверка прав доступа
    if file_data[0] != current_user.id:
        abort(403)
    
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, download_name=file_data[1])

@app.route('/delete/file/<int:file_id>')
@login_required
def delete_file(file_id):
    """Удаление файла"""
    conn = sqlite3.connect('oblako.db')
    cursor = conn.cursor()
    cursor.execute('SELECT filename, user_id FROM files WHERE id = ?', (file_id,))
    file_data = cursor.fetchone()
    
    if file_data is None:
        conn.close()
        flash('Файл не найден', 'error')
        return redirect(url_for('dashboard'))
    
    if file_data[1] != current_user.id:
        conn.close()
        abort(403)
    
    # Удаление файла с диска
    try:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], file_data[0])
        if os.path.exists(file_path):
            os.remove(file_path)
    except Exception as e:
        flash('Ошибка при удалении файла: {0}'.format(str(e)), 'error')
    
    # Удаление из базы данных
    cursor.execute('DELETE FROM files WHERE id = ?', (file_id,))
    conn.commit()
    conn.close()
    
    flash('Файл удалён', 'success')
    return redirect(url_for('dashboard'))

# ==================== АЛЬБОМЫ ====================

@app.route('/albums')
@login_required
def albums():
    """Список альбомов"""
    conn = sqlite3.connect('oblako.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, title, description, cover_photo, photo_count, created_at
        FROM albums WHERE user_id = ? ORDER BY created_at DESC
    ''', (current_user.id,))
    albums_list = cursor.fetchall()
    conn.close()
    
    albums_data = []
    for a in albums_list:
        cover_url = None
        if a[3]:
            cover_url = url_for('static', filename='uploads/albums/' + str(a[0]) + '/' + a[3])
        
        albums_data.append({
            'id': a[0],
            'title': a[1],
            'description': a[2],
            'cover_photo': cover_url,
            'photo_count': a[4],
            'created_at': a[5]
        })
    
    return render_template('albums.html', albums=albums_data)

@app.route('/album/new', methods=['GET', 'POST'])
@login_required
def new_album():
    """Создание нового альбома"""
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        
        if not title:
            flash('Название альбома обязательно', 'error')
            return render_template('album_edit.html', album=None)
        
        conn = sqlite3.connect('oblako.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO albums (user_id, title, description) VALUES (?, ?, ?)
        ''', (current_user.id, title, description))
        conn.commit()
        album_id = cursor.lastrowid
        conn.close()
        
        # Создание папки для альбома
        album_folder = os.path.join(app.config['ALBUMS_FOLDER'], str(album_id))
        os.makedirs(album_folder, exist_ok=True)
        
        flash('Альбом создан', 'success')
        return redirect(url_for('view_album', album_id=album_id))
    
    return render_template('album_edit.html', album=None)

@app.route('/album/<int:album_id>')
@login_required
def view_album(album_id):
    """Просмотр альбома"""
    conn = sqlite3.connect('oblako.db')
    cursor = conn.cursor()
    
    # Проверка доступа
    cursor.execute('SELECT id, title, description, cover_photo, photo_count FROM albums WHERE id = ? AND user_id = ?', 
                  (album_id, current_user.id))
    album = cursor.fetchone()
    
    if album is None:
        conn.close()
        flash('Альбом не найден', 'error')
        return redirect(url_for('albums'))
    
    # Получаем фотографии
    cursor.execute('''
        SELECT id, filename, original_name, description, created_at
        FROM photos WHERE album_id = ? ORDER BY created_at DESC
    ''', (album_id,))
    photos = cursor.fetchall()
    conn.close()
    
    photos_data = []
    for p in photos:
        photo_url = url_for('static', filename='uploads/albums/' + str(album_id) + '/' + p[1])
        photos_data.append({
            'id': p[0],
            'filename': p[1],
            'original_name': p[2],
            'description': p[3],
            'created_at': p[4],
            'url': photo_url
        })
    
    album_data = {
        'id': album[0],
        'title': album[1],
        'description': album[2],
        'cover_photo': album[3],
        'photo_count': album[4]
    }
    
    return render_template('album_view.html', album=album_data, photos=photos_data)

@app.route('/album/<int:album_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_album(album_id):
    """Редактирование альбома"""
    conn = sqlite3.connect('oblako.db')
    cursor = conn.cursor()
    
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        
        if not title:
            flash('Название альбома обязательно', 'error')
            return render_template('album_edit.html', album={'id': album_id, 'title': title, 'description': description})
        
        cursor.execute('''
            UPDATE albums SET title = ?, description = ? WHERE id = ? AND user_id = ?
        ''', (title, description, album_id, current_user.id))
        conn.commit()
        conn.close()
        
        flash('Альбом обновлён', 'success')
        return redirect(url_for('view_album', album_id=album_id))
    
    cursor.execute('SELECT id, title, description FROM albums WHERE id = ? AND user_id = ?', 
                  (album_id, current_user.id))
    album = cursor.fetchone()
    conn.close()
    
    if album is None:
        flash('Альбом не найден', 'error')
        return redirect(url_for('albums'))
    
    return render_template('album_edit.html', album={'id': album[0], 'title': album[1], 'description': album[2]})

@app.route('/album/<int:album_id>/add_photo', methods=['POST'])
@login_required
def add_photo(album_id):
    """Добавление фотографии в альбом"""
    # Проверка доступа к альбому
    conn = sqlite3.connect('oblako.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, photo_count FROM albums WHERE id = ? AND user_id = ?', (album_id, current_user.id))
    album = cursor.fetchone()
    
    if album is None:
        conn.close()
        return jsonify({'error': 'Альбом не найден'}), 404
    
    if 'photo' not in request.files:
        conn.close()
        return jsonify({'error': 'Файл не выбран'}), 400
    
    photo = request.files['photo']
    if photo.filename == '':
        conn.close()
        return jsonify({'error': 'Файл не выбран'}), 400
    
    if photo and allowed_photo(photo.filename):
        # Безопасное имя файла
        original_name = secure_filename(photo.filename)
        ext = original_name.rsplit('.', 1)[1].lower()
        filename = str(uuid.uuid4().hex[:16]) + '.' + ext
        
        # Создание директории альбома
        album_folder = os.path.join(app.config['ALBUMS_FOLDER'], str(album_id))
        os.makedirs(album_folder, exist_ok=True)
        
        # Сохранение файла
        file_path = os.path.join(album_folder, filename)
        photo.save(file_path)
        
        # Сохранение в базу данных
        cursor.execute('''
            INSERT INTO photos (album_id, user_id, filename, original_name) VALUES (?, ?, ?, ?)
        ''', (album_id, current_user.id, filename, original_name))
        photo_id = cursor.lastrowid
        
        # Обновление счётчика и обложки
        new_count = album[1] + 1
        cover_photo = None
        if album[1] == 0:
            # Первое фото - делаем обложкой
            cover_photo = filename
        
        cursor.execute('''
            UPDATE albums SET photo_count = ?, cover_photo = ? WHERE id = ?
        ''', (new_count, cover_photo, album_id))
        
        conn.commit()
        conn.close()
        
        photo_url = url_for('static', filename='uploads/albums/' + str(album_id) + '/' + filename)
        
        return jsonify({
            'success': True,
            'photo': {
                'id': photo_id,
                'filename': filename,
                'original_name': original_name,
                'url': photo_url
            }
        })
    else:
        conn.close()
        return jsonify({'error': 'Недопустимый формат изображения. Разрешены: PNG, JPG, JPEG, GIF, WebP'}), 400

@app.route('/album/<int:album_id>/set_cover/<int:photo_id>')
@login_required
def set_cover(album_id, photo_id):
    """Установка фото как обложки альбома"""
    conn = sqlite3.connect('oblako.db')
    cursor = conn.cursor()
    
    # Проверка доступа и фото
    cursor.execute('''
        SELECT p.filename FROM photos p 
        JOIN albums a ON p.album_id = a.id 
        WHERE p.id = ? AND a.id = ? AND a.user_id = ?
    ''', (photo_id, album_id, current_user.id))
    photo = cursor.fetchone()
    
    if photo is None:
        conn.close()
        flash('Фото не найдено', 'error')
        return redirect(url_for('view_album', album_id=album_id))
    
    # Обновление обложки
    cursor.execute('UPDATE albums SET cover_photo = ? WHERE id = ?', (photo[0], album_id))
    conn.commit()
    conn.close()
    
    flash('Обложка альбома обновлена', 'success')
    return redirect(url_for('view_album', album_id=album_id))

@app.route('/photo/<int:photo_id>/delete')
@login_required
def delete_photo(photo_id):
    """Удаление фотографии"""
    conn = sqlite3.connect('oblako.db')
    cursor = conn.cursor()
    
    # Получаем информацию о фото
    cursor.execute('''
        SELECT p.filename, p.album_id, a.cover_photo FROM photos p
        JOIN albums a ON p.album_id = a.id
        WHERE p.id = ? AND p.user_id = ?
    ''', (photo_id, current_user.id))
    photo_data = cursor.fetchone()
    
    if photo_data is None:
        conn.close()
        flash('Фото не найдено', 'error')
        return redirect(url_for('albums'))
    
    filename, album_id, cover_photo = photo_data
    
    # Удаление файла
    try:
        photo_path = os.path.join(app.config['ALBUMS_FOLDER'], str(album_id), filename)
        if os.path.exists(photo_path):
            os.remove(photo_path)
    except Exception as e:
        flash('Ошибка при удалении файла: {0}'.format(str(e)), 'error')
    
    # Удаление из базы
    cursor.execute('DELETE FROM photos WHERE id = ?', (photo_id,))
    
    # Обновление счётчика и обложки
    cursor.execute('UPDATE albums SET photo_count = photo_count - 1 WHERE id = ?', (album_id,))
    
    # Если удалённое фото было обложкой, выбираем новое
    if cover_photo == filename:
        cursor.execute('SELECT filename FROM photos WHERE album_id = ? LIMIT 1', (album_id,))
        new_cover = cursor.fetchone()
        new_cover_name = new_cover[0] if new_cover else None
        cursor.execute('UPDATE albums SET cover_photo = ? WHERE id = ?', (new_cover_name, album_id))
    
    conn.commit()
    conn.close()
    
    flash('Фото удалено', 'success')
    return redirect(url_for('view_album', album_id=album_id))

@app.route('/album/<int:album_id>/delete')
@login_required
def delete_album(album_id):
    """Удаление альбома"""
    conn = sqlite3.connect('oblako.db')
    cursor = conn.cursor()
    
    # Проверка доступа
    cursor.execute('SELECT id FROM albums WHERE id = ? AND user_id = ?', (album_id, current_user.id))
    if not cursor.fetchone():
        conn.close()
        flash('Альбом не найден', 'error')
        return redirect(url_for('albums'))
    
    # Удаление файлов альбома
    try:
        album_folder = os.path.join(app.config['ALBUMS_FOLDER'], str(album_id))
        if os.path.exists(album_folder):
            import shutil
            shutil.rmtree(album_folder)
    except Exception as e:
        flash('Ошибка при удалении файлов: {0}'.format(str(e)), 'error')
    
    # Удаление из базы (каскадное удаление фото)
    cursor.execute('DELETE FROM albums WHERE id = ?', (album_id,))
    conn.commit()
    conn.close()
    
    flash('Альбом удалён', 'success')
    return redirect(url_for('albums'))

@app.errorhandler(404)
def page_not_found(e):
    """Страница 404"""
    return render_template('404.html'), 404

@app.errorhandler(403)
def forbidden(e):
    """Страница 403"""
    return render_template('404.html'), 403

@app.errorhandler(500)
def internal_error(e):
    """Страница 500"""
    return render_template('404.html'), 500

if __name__ == '__main__':
    # Создание директорий
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['ALBUMS_FOLDER'], exist_ok=True)
    
    # Инициализация базы данных
    init_db()
    
    # Запуск приложения
    app.run(host='0.0.0.0', port=5000, debug=True)
