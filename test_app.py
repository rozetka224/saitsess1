#!/usr/bin/env python3
"""
Тестовый скрипт для проверки работы CloudVault
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

# Тестирование импорта и логики
from app import app, init_db, allowed_file
import sqlite3

print("=" * 50)
print("Тестирование CloudVault")
print("=" * 50)

# Тест 1: Инициализация БД
print("\n1. Инициализация базы данных...")
try:
    if os.path.exists('oblako.db'):
        os.remove('oblako.db')
    init_db()
    print("   ✓ База данных создана успешно")
except Exception as e:
    print(f"   ✗ Ошибка: {e}")
    sys.exit(1)

# Тест 2: Проверка таблиц
print("\n2. Проверка таблиц в базе данных...")
conn = sqlite3.connect('oblako.db')
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cursor.fetchall()]
expected_tables = ['users', 'files', 'notes']
for table in expected_tables:
    if table in tables:
        print(f"   ✓ Таблица '{table}' существует")
    else:
        print(f"   ✗ Таблица '{table}' не найдена")
conn.close()

# Тест 3: Регистрация пользователя
print("\n3. Тестирование регистрации пользователя...")
with app.test_client() as client:
    # Регистрация
    response = client.post('/register', data={
        'username': 'testuser',
        'email': 'test@test.com',
        'password': 'testpass123',
        'password_confirm': 'testpass123'
    }, follow_redirects=True)
    if response.status_code == 200:
        print("   ✓ Регистрация прошла успешно")
    else:
        print(f"   ✗ Ошибка регистрации: {response.status_code}")
    
    # Вход
    response = client.post('/login', data={
        'username': 'testuser',
        'password': 'testpass123'
    }, follow_redirects=True)
    if response.status_code == 200:
        print("   ✓ Вход выполнен успешно")
    else:
        print(f"   ✗ Ошибка входа: {response.status_code}")
    
    # Создание заметки
    print("\n4. Тестирование создания заметки...")
    response = client.post('/note/new', data={
        'title': 'Тестовая заметка',
        'content': 'Это тестовое содержимое заметки'
    }, follow_redirects=True)
    if response.status_code == 200:
        print("   ✓ Заметка создана успешно")
    else:
        print(f"   ✗ Ошибка создания заметки: {response.status_code}")
    
    # Просмотр списка заметок
    print("\n5. Тестирование просмотра заметок...")
    response = client.get('/notes')
    if response.status_code == 200:
        print("   ✓ Страница заметок загружена успешно")
        if 'Тестовая заметка' in response.data.decode():
            print("   ✓ Заметка отображается в списке")
        else:
            print("   ✗ Заметка не найдена в списке")
    else:
        print(f"   ✗ Ошибка загрузки заметок: {response.status_code}")

print("\n" + "=" * 50)
print("Тестирование завершено!")
print("=" * 50)
