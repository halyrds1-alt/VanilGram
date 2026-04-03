#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice, PreCheckoutQuery, ReplyKeyboardMarkup, KeyboardButton
import sqlite3
import json
import threading
import time
import os
import sys
import requests
import subprocess
from datetime import datetime, timedelta

# ==================== КОНФИГ ====================
BOT_TOKEN = "8789730707:AAFviuMjcPpnZeGIgY_KoduvUCaGngEowTA"
ADMIN_ID = 6747528307
CHANNEL_LINK = "https://t.me/VanillaGram"

OPENROUTER_API_KEY = "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"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

PRICE_PRO_BOT = 150
PRICE_PRO_BOT_EXTEND = 500
PRICE_COPYRIGHT = 100

# Определяем папку скрипта (гарантия, что БД будет рядом)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, "vanilla_gram.db")
MEDIA_DIR = os.path.join(SCRIPT_DIR, "media")
PRO_BOTS_DIR = os.path.join(SCRIPT_DIR, "pro_bots")
os.makedirs(MEDIA_DIR, exist_ok=True)
os.makedirs(PRO_BOTS_DIR, exist_ok=True)

print(f"📁 Папка скрипта: {SCRIPT_DIR}")
print(f"💾 База данных будет здесь: {DB_PATH}")

bot = telebot.TeleBot(BOT_TOKEN)

# ==================== БАЗА ДАННЫХ ====================
def init_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()
    
    # users
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        reg_date TIMESTAMP,
        balance INTEGER DEFAULT 0
    )''')
    
    # user_bots
    c.execute('''CREATE TABLE IF NOT EXISTS user_bots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        bot_token TEXT UNIQUE,
        bot_username TEXT,
        welcome_text TEXT,
        welcome_photo TEXT,
        is_active INTEGER DEFAULT 1,
        has_copyright INTEGER DEFAULT 1,
        require_sub INTEGER DEFAULT 0,
        required_channel TEXT,
        created_at TIMESTAMP,
        auto_reply_always INTEGER DEFAULT 0,
        auto_reply_text TEXT,
        ai_enabled INTEGER DEFAULT 0,
        ai_prompt TEXT,
        total_messages INTEGER DEFAULT 0,
        total_users INTEGER DEFAULT 0,
        theme_color TEXT DEFAULT 'primary',
        anonymous_mode INTEGER DEFAULT 1
    )''')
    
    # pro_bots
    c.execute('''CREATE TABLE IF NOT EXISTS pro_bots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        bot_token TEXT UNIQUE,
        bot_username TEXT,
        prompt TEXT,
        code TEXT,
        status TEXT DEFAULT 'active',
        created_at TIMESTAMP,
        expires_at TIMESTAMP,
        file_path TEXT,
        is_active INTEGER DEFAULT 1,
        fix_attempts INTEGER DEFAULT 0
    )''')
    
    # bot_operators
    c.execute('''CREATE TABLE IF NOT EXISTS bot_operators (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bot_token TEXT,
        operator_id INTEGER,
        tag_id INTEGER,
        added_at TIMESTAMP
    )''')
    
    # bot_tags
    c.execute('''CREATE TABLE IF NOT EXISTS bot_tags (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bot_token TEXT,
        tag_name TEXT,
        created_at TIMESTAMP
    )''')
    
    # bot_dialogs
    c.execute('''CREATE TABLE IF NOT EXISTS bot_dialogs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bot_token TEXT,
        user_id INTEGER,
        operator_id INTEGER,
        tag_id INTEGER,
        last_message_id INTEGER,
        last_message_at TIMESTAMP,
        is_active INTEGER DEFAULT 1
    )''')
    
    # newsletter_subs
    c.execute('''CREATE TABLE IF NOT EXISTS newsletter_subs (
        bot_token TEXT,
        user_id INTEGER,
        PRIMARY KEY (bot_token, user_id)
    )''')
    
    # payments
    c.execute('''CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount INTEGER,
        type TEXT,
        status TEXT,
        payment_id TEXT,
        bot_token TEXT,
        created_at TIMESTAMP
    )''')
    
    # user_states
    c.execute('''CREATE TABLE IF NOT EXISTS user_states (
        user_id INTEGER PRIMARY KEY,
        state TEXT,
        data TEXT
    )''')
    
    # bot_stats
    c.execute('''CREATE TABLE IF NOT EXISTS bot_stats (
        bot_token TEXT,
        user_id INTEGER,
        messages_count INTEGER DEFAULT 0,
        last_activity TIMESTAMP,
        PRIMARY KEY (bot_token, user_id)
    )''')
    
    # Меню и кнопки
    c.execute('''CREATE TABLE IF NOT EXISTS bot_menus (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bot_token TEXT,
        menu_name TEXT,
        menu_text TEXT,
        created_at TIMESTAMP
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS bot_menu_buttons (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        menu_id INTEGER,
        button_text TEXT,
        button_type TEXT,
        button_value TEXT,
        button_row INTEGER,
        button_order INTEGER
    )''')
    
    # constructor_settings
    c.execute('''CREATE TABLE IF NOT EXISTS constructor_settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )''')
    
    c.execute("INSERT OR IGNORE INTO constructor_settings (key, value) VALUES ('welcome_text', '🌟 *ДОБРО ПОЖАЛОВАТЬ В VANILLAGRAM!* 🌟\n\nБесплатный конструктор Telegram ботов\n▫️ Pro боты от ИИ за 150⭐\n▫️ Создание меню и кнопок\n▫️ 5 типов инлайн-кнопок\n▫️ Безлимит операторов\n▫️ Нейросеть (бесплатно)\n\nИспользуй команды ниже:')")
    c.execute("INSERT OR IGNORE INTO constructor_settings (key, value) VALUES ('ai_prompt_default', 'Ты дружелюбный AI помощник. Отвечай кратко, полезно и вежливо.')")
    conn.commit()
    conn.close()
    print(f"✅ База данных создана: {DB_PATH}")

init_db()

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================
def save_state(user_id, state, data=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO user_states (user_id, state, data) VALUES (?, ?, ?)",
              (user_id, state, json.dumps(data) if data else None))
    conn.commit()
    conn.close()

def get_state(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT state, data FROM user_states WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return (row[0], json.loads(row[1]) if row and row[1] else None) if row else (None, None)

def clear_state(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM user_states WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

def get_main_photo():
    path = os.path.join(MEDIA_DIR, "menu.jpg")
    if os.path.exists(path):
        try:
            return open(path, 'rb')
        except:
            return None
    return None

def get_user_balance(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0

def update_balance(user_id, amount):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, user_id))
    conn.commit()
    conn.close()

def call_ai(prompt, user_message):
    try:
        headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": "nousresearch/hermes-3-llama-3.1-405b:free",
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_message}
            ],
            "max_tokens": 500
        }
        resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=30)
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"AI error: {e}")
    return None

def generate_bot_code(prompt, bot_token):
    sys_prompt = f"""Ты эксперт по созданию Telegram ботов на Python с telebot.
Напиши полный рабочий код бота на Python. Токен: {bot_token}
Описание: {prompt}
Выдай только готовый код, без лишних комментариев.
Добавь /start, /help.
Код не должен содержать синтаксических ошибок."""
    return call_ai(sys_prompt, "Создай код бота")

def fix_bot_code(code, error_msg):
    prompt = f"Исправь ошибку в коде:\n{error_msg}\n\nКод:\n{code}\nВыдай только исправленный код."
    return call_ai(prompt, "Исправь код")

def test_bot_code(code):
    try:
        compile(code, '<string>', 'exec')
        return True, None
    except SyntaxError as e:
        return False, str(e)
    except Exception as e:
        return False, str(e)

def colored_button(text, callback_data, style=None):
    if style == "primary":
        return InlineKeyboardButton(f"🔵 {text}", callback_data=callback_data)
    elif style == "success":
        return InlineKeyboardButton(f"🟢 {text}", callback_data=callback_data)
    elif style == "danger":
        return InlineKeyboardButton(f"🔴 {text}", callback_data=callback_data)
    return InlineKeyboardButton(text, callback_data=callback_data)

# ==================== КЛАВИАТУРЫ ====================
def main_reply_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(KeyboardButton("/addbot"), KeyboardButton("/mybot"))
    kb.add(KeyboardButton("/pro_bot"), KeyboardButton("/top"))
    kb.add(KeyboardButton("/profile"), KeyboardButton("/admin"))
    return kb

def my_bots_keyboard(user_id, page=0):
    per_page = 5
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT bot_token, bot_username FROM user_bots WHERE user_id=? AND is_active=1", (user_id,))
    bots = c.fetchall()
    conn.close()
    total = len(bots)
    start = page * per_page
    end = start + per_page
    page_bots = bots[start:end]
    kb = InlineKeyboardMarkup(row_width=1)
    for token, username in page_bots:
        kb.add(colored_button(f"🤖 @{username}", f"edit|{token}", "primary"))
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"mybots_page|{page-1}"))
    if end < total:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"mybots_page|{page+1}"))
    if nav:
        kb.row(*nav)
    kb.add(InlineKeyboardButton("🔙 ГЛАВНОЕ МЕНЮ", callback_data="back_start"))
    return kb, total, page

def pro_bots_keyboard(user_id, page=0):
    per_page = 5
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, bot_username, expires_at, status FROM pro_bots WHERE user_id=? AND is_active=1", (user_id,))
    bots = c.fetchall()
    conn.close()
    total = len(bots)
    start = page * per_page
    end = start + per_page
    page_bots = bots[start:end]
    kb = InlineKeyboardMarkup(row_width=1)
    for pid, username, expires_at, status in page_bots:
        days_left = (datetime.strptime(expires_at, '%Y-%m-%d %H:%M:%S.%f') - datetime.now()).days if expires_at else 0
        icon = "🟢" if days_left > 0 and status == 'active' else "🔴"
        kb.add(colored_button(f"{icon} Pro @{username}", f"pro_edit|{pid}", "primary"))
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"probots_page|{page-1}"))
    if end < total:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"probots_page|{page+1}"))
    if nav:
        kb.row(*nav)
    kb.add(colored_button("➕ СОЗДАТЬ PRO БОТА (150⭐)", "create_pro_bot", "success"))
    kb.add(InlineKeyboardButton("🔙 ГЛАВНОЕ МЕНЮ", callback_data="back_start"))
    return kb, total, page

def bot_control_keyboard(bot_token, page=0):
    per_page = 10
    all_funcs = [
        ("📝 Приветствие", f"welcome|{bot_token}"),
        ("🖼 Фото", f"photo|{bot_token}"),
        ("👥 Операторы", f"operators|{bot_token}"),
        ("🏷 Теги", f"tags|{bot_token}"),
        ("🔒 Подписка", f"subscribe|{bot_token}"),
        ("🤖 Нейросеть", f"ai|{bot_token}"),
        ("⚙️ Автоответчик", f"autoreply|{bot_token}"),
        ("🎨 Цвет кнопок", f"color|{bot_token}"),
        ("👤 Анонимность", f"anonymous|{bot_token}"),
        ("📊 Статистика", f"stats|{bot_token}"),
        ("📢 Рассылка", f"mailing|{bot_token}"),
        ("📎 Медиа", f"media|{bot_token}"),
        ("📋 МЕНЮ И КНОПКИ", f"menus|{bot_token}"),
        ("⏸ Остановить", f"stop_bot|{bot_token}"),
        ("🗑 Удалить", f"delete_bot|{bot_token}"),
    ]
    total = len(all_funcs)
    start = page * per_page
    end = min(start + per_page, total)
    page_funcs = all_funcs[start:end]
    kb = InlineKeyboardMarkup(row_width=2)
    for text, cb in page_funcs:
        kb.add(colored_button(text, cb, "primary"))
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"bot_page|{bot_token}|{page-1}"))
    if end < total:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"bot_page|{bot_token}|{page+1}"))
    if nav:
        kb.row(*nav)
    kb.add(colored_button("🔙 НАЗАД", f"edit|{bot_token}", "danger"))
    return kb, total, page

def bot_settings_keyboard(bot_token):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT bot_username, welcome_text, has_copyright, require_sub, welcome_photo, auto_reply_always, auto_reply_text, ai_enabled, theme_color, anonymous_mode FROM user_bots WHERE bot_token=?", (bot_token,))
    row = c.fetchone()
    if not row:
        conn.close()
        return None
    username, welcome, copyright, req_sub, photo, auto_reply, auto_text, ai_enabled, theme_color, anonymous = row
    c.execute("SELECT COUNT(*) FROM bot_operators WHERE bot_token=?", (bot_token,))
    op_cnt = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM bot_tags WHERE bot_token=?", (bot_token,))
    tag_cnt = c.fetchone()[0]
    conn.close()
    status = (f"📷 Фото: {'✅' if photo else '❌'}\n🔒 Подписка: {'✅' if req_sub else '❌'}\n"
              f"© Копирайт: {'✅' if copyright else '❌'}\n👥 Операторы: {op_cnt}\n🏷 Теги: {tag_cnt}\n"
              f"🤖 Нейросеть: {'✅' if ai_enabled else '❌'}\n⚙️ Автоответ: {'✅' if auto_reply else '❌'}\n"
              f"🎨 Цвет: {theme_color}\n👤 Анонимность: {'✅' if anonymous else '❌'}")
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(colored_button("⚙️ УПРАВЛЕНИЕ", f"control|{bot_token}", "primary"))
    if copyright:
        kb.add(colored_button("✨ УБРАТЬ КОПИРАЙТ (100⭐)", f"copyright|{bot_token}", "danger"))
    kb.add(colored_button("🔙 НАЗАД", "my_bots", "danger"))
    return kb, status, username

# ==================== КЛАВИАТУРЫ ДЛЯ МЕНЮ И КНОПОК ====================
def menus_keyboard(bot_token, page=0):
    per_page = 5
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, menu_name, menu_text FROM bot_menus WHERE bot_token=?", (bot_token,))
    menus = c.fetchall()
    conn.close()
    total = len(menus)
    start = page * per_page
    end = start + per_page
    page_menus = menus[start:end]
    
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(colored_button("➕ СОЗДАТЬ НОВОЕ МЕНЮ", f"create_menu|{bot_token}", "success"))
    for mid, name, text in page_menus:
        kb.add(colored_button(f"📋 {name}", f"menu_edit|{bot_token}|{mid}", "primary"))
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"menus_page|{bot_token}|{page-1}"))
    if end < total:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"menus_page|{bot_token}|{page+1}"))
    if nav:
        kb.row(*nav)
    kb.add(colored_button("🔙 НАЗАД", f"edit|{bot_token}", "danger"))
    return kb, total, page

def menu_edit_keyboard(bot_token, menu_id, menu_name, menu_text):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, button_text, button_type, button_value, button_row, button_order FROM bot_menu_buttons WHERE menu_id=? ORDER BY button_row, button_order", (menu_id,))
    buttons = c.fetchall()
    conn.close()
    
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(colored_button("📝 ИЗМЕНИТЬ ТЕКСТ", f"menu_text|{bot_token}|{menu_id}", "primary"))
    kb.add(colored_button("🔘 ДОБАВИТЬ КНОПКУ", f"add_button|{bot_token}|{menu_id}", "success"))
    kb.add(colored_button("📤 СДЕЛАТЬ ОСНОВНЫМ", f"set_main_menu|{bot_token}|{menu_id}", "primary"))
    kb.add(colored_button("🗑 УДАЛИТЬ МЕНЮ", f"delete_menu|{bot_token}|{menu_id}", "danger"))
    kb.add(colored_button("🔙 НАЗАД", f"menus|{bot_token}", "danger"))
    
    # Список существующих кнопок
    btns_text = ""
    for btn in buttons:
        btn_id, btn_text, btn_type, btn_value, btn_row, btn_order = btn
        type_icon = {"url": "🔗", "profile": "👤", "callback": "🔘", "location": "📍", "contact": "📞"}.get(btn_type, "❓")
        btns_text += f"{type_icon} {btn_text} (ряд {btn_row+1}, порядок {btn_order+1})\n"
    
    info = f"📋 *Меню: {menu_name}*\n\nТекст:\n{menu_text[:100]}...\n\nКнопки:\n{btns_text if btns_text else 'Нет кнопок'}"
    return kb, info

def button_type_keyboard(bot_token, menu_id):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(colored_button("🔗 TELEGRAM КАНАЛ", f"btn_type|{bot_token}|{menu_id}|url", "primary"))
    kb.add(colored_button("👤 ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ", f"btn_type|{bot_token}|{menu_id}|profile", "primary"))
    kb.add(colored_button("🌐 ВНЕШНИЙ САЙТ", f"btn_type|{bot_token}|{menu_id}|website", "primary"))
    kb.add(colored_button("📍 ГЕОЛОКАЦИЯ", f"btn_type|{bot_token}|{menu_id}|location", "primary"))
    kb.add(colored_button("📞 КОНТАКТ", f"btn_type|{bot_token}|{menu_id}|contact", "primary"))
    kb.add(colored_button("🔙 НАЗАД", f"menu_edit|{bot_token}|{menu_id}", "danger"))
    return kb

def pro_bot_control_keyboard(pro_id):
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(colored_button("📥 СКАЧАТЬ КОД", f"pro_download|{pro_id}", "success"))
    kb.add(colored_button("🔄 ПРОДЛИТЬ (500⭐/30 дней)", f"pro_extend|{pro_id}", "primary"))
    kb.add(colored_button("❌ ОСТАНОВИТЬ", f"pro_stop|{pro_id}", "danger"))
    kb.add(InlineKeyboardButton("🔙 НАЗАД", callback_data="my_pro_bots"))
    return kb

def operators_keyboard(bot_token):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, operator_id FROM bot_operators WHERE bot_token=?", (bot_token,))
    ops = c.fetchall()
    conn.close()
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(colored_button("➕ ДОБАВИТЬ ОПЕРАТОРА", f"add_op|{bot_token}", "success"))
    for op_id, op_user in ops:
        kb.add(colored_button(f"👤 {op_user}", f"del_op|{bot_token}|{op_id}", "danger"))
    kb.add(colored_button("🔙 НАЗАД", f"edit|{bot_token}", "danger"))
    return kb

def tags_keyboard(bot_token):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, tag_name FROM bot_tags WHERE bot_token=?", (bot_token,))
    tags = c.fetchall()
    conn.close()
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(colored_button("➕ СОЗДАТЬ ТЕГ", f"create_tag|{bot_token}", "success"))
    for tid, tname in tags:
        kb.add(colored_button(f"🏷 {tname}", f"tag_menu|{bot_token}|{tid}", "primary"))
    kb.add(colored_button("🔙 НАЗАД", f"edit|{bot_token}", "danger"))
    return kb

def tag_operators_keyboard(bot_token, tag_id, tag_name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, operator_id FROM bot_operators WHERE bot_token=?", (bot_token,))
    ops = c.fetchall()
    conn.close()
    kb = InlineKeyboardMarkup(row_width=1)
    for op_id, op_user in ops:
        conn2 = sqlite3.connect(DB_PATH)
        c2 = conn2.cursor()
        c2.execute("SELECT id FROM bot_operators WHERE id=? AND tag_id=?", (op_id, tag_id))
        has = c2.fetchone()
        conn2.close()
        if has:
            kb.add(colored_button(f"✅ {op_user}", f"remove_op_tag|{bot_token}|{op_id}|{tag_id}", "danger"))
        else:
            kb.add(colored_button(f"👤 {op_user}", f"assign_op_tag|{bot_token}|{op_id}|{tag_id}", "success"))
    kb.add(colored_button("🔙 К ТЕГАМ", f"tags|{bot_token}", "danger"))
    return kb

def color_keyboard(bot_token):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(colored_button("🔵 СИНИЙ", f"set_color|{bot_token}|primary", "primary"))
    kb.add(colored_button("🟢 ЗЕЛЕНЫЙ", f"set_color|{bot_token}|success", "success"))
    kb.add(colored_button("🔴 КРАСНЫЙ", f"set_color|{bot_token}|danger", "danger"))
    kb.add(colored_button("🔙 НАЗАД", f"edit|{bot_token}", "danger"))
    return kb

def anonymous_keyboard(bot_token):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT anonymous_mode FROM user_bots WHERE bot_token=?", (bot_token,))
    mode = c.fetchone()[0]
    conn.close()
    kb = InlineKeyboardMarkup(row_width=1)
    if mode:
        kb.add(colored_button("❌ ВЫКЛЮЧИТЬ АНОНИМНОСТЬ", f"toggle_anonymous|{bot_token}", "danger"))
    else:
        kb.add(colored_button("✅ ВКЛЮЧИТЬ АНОНИМНОСТЬ", f"toggle_anonymous|{bot_token}", "success"))
    kb.add(colored_button("🔙 НАЗАД", f"edit|{bot_token}", "danger"))
    return kb

def admin_keyboard():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(colored_button("📊 СТАТИСТИКА", "admin_stats", "primary"))
    kb.add(colored_button("✏️ ИЗМЕНИТЬ ПРИВЕТСТВИЕ", "admin_edit_welcome", "primary"))
    kb.add(colored_button("📢 РАССЫЛКА", "admin_mailing", "success"))
    kb.add(colored_button("⭐ НАЧИСЛИТЬ ЗВЕЗДЫ", "admin_add_stars", "primary"))
    kb.add(colored_button("🗑 УДАЛИТЬ КОПИРАЙТ", "admin_remove_copyright", "danger"))
    kb.add(InlineKeyboardButton("🔙 НАЗАД", callback_data="back_start"))
    return kb

# ==================== ОБРАБОТЧИКИ КОМАНД ====================
@bot.message_handler(commands=['start'])
def start(message):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, username, reg_date, balance) VALUES (?, ?, ?, 0)",
              (message.from_user.id, message.from_user.username, datetime.now()))
    conn.commit()
    conn.close()
    photo = get_main_photo()
    conn2 = sqlite3.connect(DB_PATH)
    c2 = conn2.cursor()
    c2.execute("SELECT value FROM constructor_settings WHERE key='welcome_text'")
    welcome_text = c2.fetchone()[0]
    conn2.close()
    if photo:
        bot.send_photo(message.chat.id, photo, caption=welcome_text, reply_markup=main_reply_keyboard(), parse_mode='Markdown')
    else:
        bot.send_message(message.chat.id, welcome_text, reply_markup=main_reply_keyboard(), parse_mode='Markdown')

@bot.message_handler(commands=['addbot'])
def addbot_cmd(message):
    save_state(message.from_user.id, "waiting_token")
    bot.send_message(message.chat.id, "🔑 *Введите токен бота от @BotFather*\nПример: `123456:ABCdef`", parse_mode='Markdown')

@bot.message_handler(commands=['mybot'])
def mybot_cmd(message):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM user_bots WHERE user_id=? AND is_active=1", (message.from_user.id,))
    cnt = c.fetchone()[0]
    conn.close()
    if cnt == 0:
        bot.send_message(message.chat.id, "❌ *У вас нет обычных ботов*\nДобавьте через /addbot", parse_mode='Markdown')
        return
    kb, total, page = my_bots_keyboard(message.from_user.id, 0)
    bot.send_message(message.chat.id, f"🎮 *ТВОИ БОТЫ* (стр. {page+1}/{(total+4)//5})", reply_markup=kb, parse_mode='Markdown')

@bot.message_handler(commands=['pro_bot'])
def pro_bot_cmd(message):
    kb, total, page = pro_bots_keyboard(message.from_user.id, 0)
    bot.send_message(message.chat.id, "🤖 *PRO БОТЫ (ИИ ГЕНЕРАЦИЯ)*\nСоздание 150⭐ (24 ч), продление 500⭐/30 дней.", reply_markup=kb, parse_mode='Markdown')

@bot.message_handler(commands=['top'])
def top_cmd(message):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT bot_username, total_messages, total_users FROM user_bots ORDER BY total_messages DESC LIMIT 10")
    top = c.fetchall()
    conn.close()
    if not top:
        text = "🏆 *ТОП БОТОВ*\nПока нет данных"
    else:
        lines = [f"{i}. @{u} — 📨 {msgs} сообщ., 👥 {users} польз." for i, (u, msgs, users) in enumerate(top, 1)]
        text = "🏆 *ТОП БОТОВ ПО АКТИВНОСТИ*\n\n" + "\n".join(lines)
    bot.send_message(message.chat.id, text, parse_mode='Markdown')

@bot.message_handler(commands=['profile'])
def profile_cmd(message):
    bal = get_user_balance(message.from_user.id)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM user_bots WHERE user_id=?", (message.from_user.id,))
    bc = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM pro_bots WHERE user_id=? AND is_active=1", (message.from_user.id,))
    pc = c.fetchone()[0]
    conn.close()
    text = (f"👤 *ПРОФИЛЬ*\n🆔 ID: `{message.from_user.id}`\n👤 @{message.from_user.username}\n"
            f"🤖 Обычных ботов: {bc}\n🤖 Pro ботов: {pc}\n⭐ Баланс звезд: {bal}\n\n"
            f"💰 Купить звезды — @VanillaGram")
    bot.send_message(message.chat.id, text, parse_mode='Markdown')

@bot.message_handler(commands=['admin'])
def admin_cmd(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "❌ Нет доступа")
        return
    bot.send_message(message.chat.id, "🔐 *АДМИН ПАНЕЛЬ*", reply_markup=admin_keyboard(), parse_mode='Markdown')

# ==================== ОБРАБОТЧИК ТЕКСТА ====================
@bot.message_handler(func=lambda m: True)
def handle_text(message):
    user_id = message.from_user.id
    state, data = get_state(user_id)
    text = message.text.strip()

    if state == "waiting_token":
        token = text
        try:
            test = telebot.TeleBot(token)
            me = test.get_me()
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute('''INSERT INTO user_bots
                (user_id, bot_token, bot_username, welcome_text, created_at)
                VALUES (?, ?, ?, ?, ?)''',
                (user_id, token, me.username, f"Добро пожаловать! Бот создан через @VanillaGramBot", datetime.now()))
            c.execute("INSERT INTO bot_operators (bot_token, operator_id, added_at) VALUES (?, ?, ?)", (token, user_id, datetime.now()))
            conn.commit()
            conn.close()
            clear_state(user_id)
            bot.send_message(message.chat.id, f"✅ *Бот @{me.username} создан!*\nУправляй через /mybot", parse_mode='Markdown')
            threading.Thread(target=run_user_bot, args=(token, me.username, user_id), daemon=True).start()
        except Exception as e:
            bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")
        return

    if state == "waiting_welcome":
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE user_bots SET welcome_text=? WHERE bot_token=?", (text, data["bot_token"]))
        conn.commit()
        conn.close()
        clear_state(user_id)
        bot.send_message(message.chat.id, "✅ Приветствие обновлено!")
        return

    if state == "waiting_photo":
        bot.reply_to(message, "❌ Отправьте фото, а не текст")
        return

    if state == "waiting_op_id":
        try:
            op_id = int(text)
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("INSERT OR IGNORE INTO bot_operators (bot_token, operator_id, added_at) VALUES (?, ?, ?)",
                      (data["bot_token"], op_id, datetime.now()))
            conn.commit()
            conn.close()
            try:
                bot.send_message(op_id, "🎉 Вы стали оператором бота!")
            except:
                pass
            bot.reply_to(message, "✅ Оператор добавлен!")
        except:
            bot.reply_to(message, "❌ Введите числовой ID")
        clear_state(user_id)
        return

    if state == "waiting_tag_name":
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO bot_tags (bot_token, tag_name, created_at) VALUES (?, ?, ?)",
                  (data["bot_token"], text, datetime.now()))
        conn.commit()
        conn.close()
        clear_state(user_id)
        bot.reply_to(message, f"✅ Тег '{text}' создан!")
        return

    if state == "waiting_channel":
        channel = text.replace("@", "")
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE user_bots SET require_sub=1, required_channel=? WHERE bot_token=?", (channel, data["bot_token"]))
        conn.commit()
        conn.close()
        clear_state(user_id)
        bot.send_message(message.chat.id, f"✅ Обязательная подписка на @{channel}\nБот должен быть админом канала!")
        return

    if state == "waiting_autoreply_text":
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        if text.lower() == "отключить":
            c.execute("UPDATE user_bots SET auto_reply_always=0, auto_reply_text=NULL WHERE bot_token=?", (data["bot_token"],))
            bot.reply_to(message, "✅ Автоответчик выключен")
        else:
            c.execute("UPDATE user_bots SET auto_reply_always=1, auto_reply_text=? WHERE bot_token=?", (text, data["bot_token"]))
            bot.reply_to(message, f"✅ Автоответчик установлен:\n{text}")
        conn.commit()
        conn.close()
        clear_state(user_id)
        return

    if state == "waiting_ai_prompt":
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE user_bots SET ai_prompt=?, ai_enabled=1 WHERE bot_token=?", (text, data["bot_token"]))
        conn.commit()
        conn.close()
        clear_state(user_id)
        bot.send_message(message.chat.id, f"✅ Нейросеть включена с промптом:\n{text}")
        return

    if state == "waiting_pro_bot_prompt":
        save_state(user_id, "waiting_pro_bot_token", {"prompt": text})
        bot.send_message(message.chat.id, "🔑 *Введите токен для Pro бота* (от @BotFather)\nПример: `123456:ABCdef`", parse_mode='Markdown')
        return

    if state == "waiting_pro_bot_token":
        token = text
        prompt = data["prompt"]
        balance = get_user_balance(user_id)
        if balance < PRICE_PRO_BOT:
            bot.send_message(message.chat.id, f"❌ Недостаточно звезд! Нужно {PRICE_PRO_BOT}⭐. Ваш баланс: {balance}⭐")
            clear_state(user_id)
            return
        bot.send_message(message.chat.id, "🔄 Генерация кода через ИИ... (до 30 сек)")
        code = generate_bot_code(prompt, token)
        if not code:
            bot.send_message(message.chat.id, "❌ Ошибка генерации. Попробуйте позже.")
            clear_state(user_id)
            return
        ok, err = test_bot_code(code)
        attempts = 1
        while not ok and attempts <= 3:
            bot.send_message(message.chat.id, f"⚠️ Ошибка в коде. Исправляю (попытка {attempts}/3)...\n{err[:200]}")
            code = fix_bot_code(code, err)
            if not code:
                break
            ok, err = test_bot_code(code)
            attempts += 1
        if not ok:
            bot.send_message(message.chat.id, "❌ Не удалось создать рабочий бот после 3 попыток. Звезды не списаны.")
            clear_state(user_id)
            return
        filename = f"pro_bot_{user_id}_{int(time.time())}.py"
        filepath = os.path.join(PRO_BOTS_DIR, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(code)
        try:
            test_bot = telebot.TeleBot(token)
            me = test_bot.get_me()
            bot_username = me.username
        except:
            bot_username = "unknown"
        expires_at = datetime.now() + timedelta(days=1)
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''INSERT INTO pro_bots
            (user_id, bot_token, bot_username, prompt, code, created_at, expires_at, file_path, fix_attempts)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (user_id, token, bot_username, prompt, code, datetime.now(), expires_at, filepath, attempts-1))
        conn.commit()
        conn.close()
        update_balance(user_id, -PRICE_PRO_BOT)
        clear_state(user_id)
        bot.send_message(message.chat.id, f"✅ *Pro бот @{bot_username} создан!*\nРаботает 24 ч. Продление 500⭐/30 дней.\nСписано {PRICE_PRO_BOT}⭐. Баланс: {get_user_balance(user_id)}⭐", parse_mode='Markdown')
        threading.Thread(target=run_pro_bot, args=(token, bot_username, user_id, filepath), daemon=True).start()
        return

    # СОЗДАНИЕ МЕНЮ (название)
    if state == "waiting_menu_name":
        menu_name = text
        bot_token = data["bot_token"]
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO bot_menus (bot_token, menu_name, menu_text, created_at) VALUES (?, ?, ?, ?)",
                  (bot_token, menu_name, "Новое меню", datetime.now()))
        menu_id = c.lastrowid
        conn.commit()
        conn.close()
        save_state(user_id, "waiting_menu_text", {"bot_token": bot_token, "menu_id": menu_id, "menu_name": menu_name})
        bot.send_message(message.chat.id, "📝 *Введите текст для этого меню* (можно с Markdown)", parse_mode='Markdown')
        return

    # СОЗДАНИЕ МЕНЮ (текст)
    if state == "waiting_menu_text":
        menu_text = text
        menu_id = data["menu_id"]
        bot_token = data["bot_token"]
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE bot_menus SET menu_text=? WHERE id=?", (menu_text, menu_id))
        conn.commit()
        conn.close()
        clear_state(user_id)
        bot.send_message(message.chat.id, f"✅ Меню '{data['menu_name']}' создано! Теперь добавьте кнопки.")
        # Открываем меню редактирования
        kb, info = menu_edit_keyboard(bot_token, menu_id, data["menu_name"], menu_text)
        bot.send_message(message.chat.id, info, reply_markup=kb, parse_mode='Markdown')
        return

    # ИЗМЕНЕНИЕ ТЕКСТА МЕНЮ
    if state == "waiting_edit_menu_text":
        menu_id = data["menu_id"]
        bot_token = data["bot_token"]
        menu_name = data["menu_name"]
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE bot_menus SET menu_text=? WHERE id=?", (text, menu_id))
        conn.commit()
        conn.close()
        clear_state(user_id)
        kb, info = menu_edit_keyboard(bot_token, menu_id, menu_name, text)
        bot.send_message(message.chat.id, "✅ Текст обновлен!\n\n" + info, reply_markup=kb, parse_mode='Markdown')
        return

    # НАЗВАНИЕ КНОПКИ
    if state == "waiting_button_text":
        button_text = text
        bot_token = data["bot_token"]
        menu_id = data["menu_id"]
        button_type = data["button_type"]
        save_state(user_id, f"waiting_button_value_{button_type}", {"bot_token": bot_token, "menu_id": menu_id, "button_text": button_text, "button_type": button_type})
        
        prompts = {
            "url": "🔗 *Введите ссылку*\nПример: https://t.me/канал или https://example.com",
            "profile": "👤 *Кнопка профиля*\nПри нажатии пользователь увидит свой ID, username и баланс",
            "website": "🌐 *Введите URL сайта*\nПример: https://example.com",
            "location": "📍 *Кнопка геолокации*\nПри нажатии бот запросит геопозицию",
            "contact": "📞 *Кнопка контакта*\nПри нажатии бот запросит номер телефона"
        }
        bot.send_message(message.chat.id, prompts.get(button_type, "Введите значение"), parse_mode='Markdown')
        return

    # ЗНАЧЕНИЕ ДЛЯ КНОПКИ (URL)
    if state == "waiting_button_value_url":
        button_value = text
        bot_token = data["bot_token"]
        menu_id = data["menu_id"]
        button_text = data["button_text"]
        button_type = data["button_type"]
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM bot_menu_buttons WHERE menu_id=?", (menu_id,))
        btn_count = c.fetchone()[0]
        button_row = btn_count // 2
        button_order = btn_count % 2
        c.execute("INSERT INTO bot_menu_buttons (menu_id, button_text, button_type, button_value, button_row, button_order) VALUES (?, ?, ?, ?, ?, ?)",
                  (menu_id, button_text, button_type, button_value, button_row, button_order))
        conn.commit()
        conn.close()
        clear_state(user_id)
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT menu_name, menu_text FROM bot_menus WHERE id=?", (menu_id,))
        menu_name, menu_text = c.fetchone()
        conn.close()
        kb, info = menu_edit_keyboard(bot_token, menu_id, menu_name, menu_text)
        bot.send_message(message.chat.id, f"✅ Кнопка '{button_text}' добавлена!\n\n{info}", reply_markup=kb, parse_mode='Markdown')
        return

    # ПРОФИЛЬ (автоматическое значение)
    if state == "waiting_button_value_profile":
        bot_token = data["bot_token"]
        menu_id = data["menu_id"]
        button_text = data["button_text"]
        button_type = data["button_type"]
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM bot_menu_buttons WHERE menu_id=?", (menu_id,))
        btn_count = c.fetchone()[0]
        button_row = btn_count // 2
        button_order = btn_count % 2
        c.execute("INSERT INTO bot_menu_buttons (menu_id, button_text, button_type, button_value, button_row, button_order) VALUES (?, ?, ?, ?, ?, ?)",
                  (menu_id, button_text, button_type, "profile", button_row, button_order))
        conn.commit()
        conn.close()
        clear_state(user_id)
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT menu_name, menu_text FROM bot_menus WHERE id=?", (menu_id,))
        menu_name, menu_text = c.fetchone()
        conn.close()
        kb, info = menu_edit_keyboard(bot_token, menu_id, menu_name, menu_text)
        bot.send_message(message.chat.id, f"✅ Кнопка '{button_text}' добавлена!\n\n{info}", reply_markup=kb, parse_mode='Markdown')
        return

    # ЗНАЧЕНИЕ ДЛЯ КНОПКИ (WEBSITE)
    if state == "waiting_button_value_website":
        button_value = text
        bot_token = data["bot_token"]
        menu_id = data["menu_id"]
        button_text = data["button_text"]
        button_type = data["button_type"]
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM bot_menu_buttons WHERE menu_id=?", (menu_id,))
        btn_count = c.fetchone()[0]
        button_row = btn_count // 2
        button_order = btn_count % 2
        c.execute("INSERT INTO bot_menu_buttons (menu_id, button_text, button_type, button_value, button_row, button_order) VALUES (?, ?, ?, ?, ?, ?)",
                  (menu_id, button_text, button_type, button_value, button_row, button_order))
        conn.commit()
        conn.close()
        clear_state(user_id)
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT menu_name, menu_text FROM bot_menus WHERE id=?", (menu_id,))
        menu_name, menu_text = c.fetchone()
        conn.close()
        kb, info = menu_edit_keyboard(bot_token, menu_id, menu_name, menu_text)
        bot.send_message(message.chat.id, f"✅ Кнопка '{button_text}' добавлена!\n\n{info}", reply_markup=kb, parse_mode='Markdown')
        return

    # ЗНАЧЕНИЕ ДЛЯ КНОПКИ (LOCATION) - не требует значения
    if state == "waiting_button_value_location":
        bot_token = data["bot_token"]
        menu_id = data["menu_id"]
        button_text = data["button_text"]
        button_type = data["button_type"]
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM bot_menu_buttons WHERE menu_id=?", (menu_id,))
        btn_count = c.fetchone()[0]
        button_row = btn_count // 2
        button_order = btn_count % 2
        c.execute("INSERT INTO bot_menu_buttons (menu_id, button_text, button_type, button_value, button_row, button_order) VALUES (?, ?, ?, ?, ?, ?)",
                  (menu_id, button_text, button_type, "location", button_row, button_order))
        conn.commit()
        conn.close()
        clear_state(user_id)
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT menu_name, menu_text FROM bot_menus WHERE id=?", (menu_id,))
        menu_name, menu_text = c.fetchone()
        conn.close()
        kb, info = menu_edit_keyboard(bot_token, menu_id, menu_name, menu_text)
        bot.send_message(message.chat.id, f"✅ Кнопка '{button_text}' добавлена!\n\n{info}", reply_markup=kb, parse_mode='Markdown')
        return

    # ЗНАЧЕНИЕ ДЛЯ КНОПКИ (CONTACT) - не требует значения
    if state == "waiting_button_value_contact":
        bot_token = data["bot_token"]
        menu_id = data["menu_id"]
        button_text = data["button_text"]
        button_type = data["button_type"]
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM bot_menu_buttons WHERE menu_id=?", (menu_id,))
        btn_count = c.fetchone()[0]
        button_row = btn_count // 2
        button_order = btn_count % 2
        c.execute("INSERT INTO bot_menu_buttons (menu_id, button_text, button_type, button_value, button_row, button_order) VALUES (?, ?, ?, ?, ?, ?)",
                  (menu_id, button_text, button_type, "contact", button_row, button_order))
        conn.commit()
        conn.close()
        clear_state(user_id)
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT menu_name, menu_text FROM bot_menus WHERE id=?", (menu_id,))
        menu_name, menu_text = c.fetchone()
        conn.close()
        kb, info = menu_edit_keyboard(bot_token, menu_id, menu_name, menu_text)
        bot.send_message(message.chat.id, f"✅ Кнопка '{button_text}' добавлена!\n\n{info}", reply_markup=kb, parse_mode='Markdown')
        return

    # Админские состояния
    if user_id == ADMIN_ID:
        if state == "admin_waiting_welcome":
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("UPDATE constructor_settings SET value=? WHERE key='welcome_text'", (text,))
            conn.commit()
            conn.close()
            clear_state(user_id)
            bot.send_message(message.chat.id, "✅ Приветствие конструктора обновлено!")
            return
        if state == "admin_waiting_mailing":
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT user_id FROM users")
            users = c.fetchall()
            conn.close()
            success = 0
            for u in users:
                try:
                    bot.send_message(u[0], f"📢 *РАССЫЛКА ОТ АДМИНА*\n\n{text}", parse_mode='Markdown')
                    success += 1
                except:
                    pass
                time.sleep(0.05)
            bot.send_message(message.chat.id, f"✅ Рассылка завершена: {success}/{len(users)}")
            clear_state(user_id)
            return
        if state == "admin_waiting_stars":
            parts = text.split()
            if len(parts) == 2:
                try:
                    uid = int(parts[0])
                    amt = int(parts[1])
                    update_balance(uid, amt)
                    bot.send_message(message.chat.id, f"✅ Начислено {amt}⭐ пользователю {uid}")
                    try:
                        bot.send_message(uid, f"⭐ Вам начислено {amt} звезд!")
                    except:
                        pass
                except:
                    bot.send_message(message.chat.id, "❌ Неверный формат. Введите: `ID сумма`")
            else:
                bot.send_message(message.chat.id, "❌ Неверный формат. Введите: `ID сумма`")
            clear_state(user_id)
            return
        if state == "admin_waiting_bot_id":
            if text.isdigit():
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                c.execute("SELECT bot_token, bot_username FROM user_bots WHERE id=?", (int(text),))
                row = c.fetchone()
                if row:
                    c.execute("UPDATE user_bots SET has_copyright=0 WHERE bot_token=?", (row[0],))
                    conn.commit()
                    bot.send_message(message.chat.id, f"✅ Копирайт удалён у @{row[1]}")
                else:
                    bot.send_message(message.chat.id, "❌ Бот не найден")
                conn.close()
            else:
                bot.send_message(message.chat.id, "❌ Введите ID бота")
            clear_state(user_id)
            return

@bot.message_handler(content_types=['photo'])
def photo_handler(message):
    state, data = get_state(message.from_user.id)
    if state == "waiting_photo":
        photo_id = message.photo[-1].file_id
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE user_bots SET welcome_photo=? WHERE bot_token=?", (photo_id, data["bot_token"]))
        conn.commit()
        conn.close()
        clear_state(message.from_user.id)
        bot.reply_to(message, "✅ Фото установлено!")

# ==================== CALLBACK-ОБРАБОТЧИК ====================
@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    user_id = call.from_user.id
    data = call.data
    chat_id = call.message.chat.id
    msg_id = call.message.message_id

    if data == "back_start":
        start(call.message)
        bot.delete_message(chat_id, msg_id)
        return

    if data.startswith("mybots_page|"):
        page = int(data.split("|")[1])
        kb, total, _ = my_bots_keyboard(user_id, page)
        bot.edit_message_text(f"🎮 *ТВОИ БОТЫ* (стр. {page+1}/{(total+4)//5})", chat_id, msg_id, reply_markup=kb, parse_mode='Markdown')
        return

    if data.startswith("probots_page|"):
        page = int(data.split("|")[1])
        kb, total, _ = pro_bots_keyboard(user_id, page)
        bot.edit_message_text("🤖 *PRO БОТЫ*", chat_id, msg_id, reply_markup=kb, parse_mode='Markdown')
        return

    if data == "create_pro_bot":
        save_state(user_id, "waiting_pro_bot_prompt")
        bal = get_user_balance(user_id)
        bot.edit_message_text(f"✨ *Создание Pro бота (150⭐)*\nОтправьте описание бота.\nПример: 'Бот для пиццерии с меню'\nВаш баланс: {bal}⭐", chat_id, msg_id, parse_mode='Markdown')
        return

    if data == "my_pro_bots":
        kb, total, page = pro_bots_keyboard(user_id, 0)
        bot.edit_message_text("🤖 *PRO БОТЫ*", chat_id, msg_id, reply_markup=kb, parse_mode='Markdown')
        return

    if data.startswith("pro_edit|"):
        pro_id = int(data.split("|")[1])
        kb = pro_bot_control_keyboard(pro_id)
        bot.edit_message_text("⚙️ *УПРАВЛЕНИЕ PRO БОТОМ*", chat_id, msg_id, reply_markup=kb, parse_mode='Markdown')
        return

    if data.startswith("pro_download|"):
        pro_id = int(data.split("|")[1])
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT file_path, bot_username FROM pro_bots WHERE id=? AND user_id=?", (pro_id, user_id))
        row = c.fetchone()
        conn.close()
        if row and os.path.exists(row[0]):
            with open(row[0], 'rb') as f:
                bot.send_document(chat_id, f, caption=f"📁 Код бота @{row[1]}")
        else:
            bot.answer_callback_query(call.id, "Файл не найден")
        return

    if data.startswith("pro_extend|"):
        pro_id = int(data.split("|")[1])
        balance = get_user_balance(user_id)
        if balance < PRICE_PRO_BOT_EXTEND:
            bot.answer_callback_query(call.id, f"Недостаточно звезд! Нужно {PRICE_PRO_BOT_EXTEND}⭐", show_alert=True)
            return
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT expires_at FROM pro_bots WHERE id=? AND user_id=?", (pro_id, user_id))
        row = c.fetchone()
        if row:
            new_exp = datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S.%f') + timedelta(days=30)
            c.execute("UPDATE pro_bots SET expires_at=? WHERE id=?", (new_exp, pro_id))
            update_balance(user_id, -PRICE_PRO_BOT_EXTEND)
            conn.commit()
            bot.answer_callback_query(call.id, f"Продлено на 30 дней! Списано {PRICE_PRO_BOT_EXTEND}⭐", show_alert=True)
        conn.close()
        return

    if data.startswith("pro_stop|"):
        pro_id = int(data.split("|")[1])
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE pro_bots SET is_active=0 WHERE id=? AND user_id=?", (pro_id, user_id))
        conn.commit()
        conn.close()
        bot.answer_callback_query(call.id, "Бот остановлен")
        return

    if data.startswith("edit|"):
        bot_token = data.split("|")[1]
        res = bot_settings_keyboard(bot_token)
        if res:
            kb, status, username = res
            bot.edit_message_text(f"⚙️ *@{username}*\n{status}", chat_id, msg_id, reply_markup=kb, parse_mode='Markdown')
        return

    if data.startswith("control|"):
        bot_token = data.split("|")[1]
        kb, total, page = bot_control_keyboard(bot_token, 0)
        bot.edit_message_text(f"⚙️ *УПРАВЛЕНИЕ БОТОМ* (стр. {page+1}/{(total+9)//10})", chat_id, msg_id, reply_markup=kb, parse_mode='Markdown')
        return

    if data.startswith("bot_page|"):
        parts = data.split("|")
        bot_token = parts[1]
        page = int(parts[2])
        kb, total, _ = bot_control_keyboard(bot_token, page)
        bot.edit_message_text(f"⚙️ *УПРАВЛЕНИЕ БОТОМ* (стр. {page+1}/{(total+9)//10})", chat_id, msg_id, reply_markup=kb, parse_mode='Markdown')
        return

    # МЕНЮ И КНОПКИ
    if data.startswith("menus|"):
        bot_token = data.split("|")[1]
        kb, total, page = menus_keyboard(bot_token, 0)
        bot.edit_message_text(f"📋 *МЕНЮ БОТА*\nСтраница {page+1}/{(total+4)//5}", chat_id, msg_id, reply_markup=kb, parse_mode='Markdown')
        return

    if data.startswith("menus_page|"):
        parts = data.split("|")
        bot_token = parts[1]
        page = int(parts[2])
        kb, total, _ = menus_keyboard(bot_token, page)
        bot.edit_message_text(f"📋 *МЕНЮ БОТА*\nСтраница {page+1}/{(total+4)//5}", chat_id, msg_id, reply_markup=kb, parse_mode='Markdown')
        return

    if data.startswith("create_menu|"):
        bot_token = data.split("|")[1]
        save_state(user_id, "waiting_menu_name", {"bot_token": bot_token})
        bot.edit_message_text("📝 *Введите название нового меню*", chat_id, msg_id, parse_mode='Markdown')
        return

    if data.startswith("menu_edit|"):
        parts = data.split("|")
        bot_token = parts[1]
        menu_id = int(parts[2])
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT menu_name, menu_text FROM bot_menus WHERE id=?", (menu_id,))
        menu_name, menu_text = c.fetchone()
        conn.close()
        kb, info = menu_edit_keyboard(bot_token, menu_id, menu_name, menu_text)
        bot.edit_message_text(info, chat_id, msg_id, reply_markup=kb, parse_mode='Markdown')
        return

    if data.startswith("menu_text|"):
        parts = data.split("|")
        bot_token = parts[1]
        menu_id = int(parts[2])
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT menu_name FROM bot_menus WHERE id=?", (menu_id,))
        menu_name = c.fetchone()[0]
        conn.close()
        save_state(user_id, "waiting_edit_menu_text", {"bot_token": bot_token, "menu_id": menu_id, "menu_name": menu_name})
        bot.edit_message_text("📝 *Введите новый текст для меню* (поддерживается Markdown)", chat_id, msg_id, parse_mode='Markdown')
        return

    if data.startswith("add_button|"):
        parts = data.split("|")
        bot_token = parts[1]
        menu_id = int(parts[2])
        kb = button_type_keyboard(bot_token, menu_id)
        bot.edit_message_text("🔘 *Выберите тип кнопки*", chat_id, msg_id, reply_markup=kb, parse_mode='Markdown')
        return

    if data.startswith("btn_type|"):
        parts = data.split("|")
        bot_token = parts[1]
        menu_id = int(parts[2])
        button_type = parts[3]
        save_state(user_id, "waiting_button_text", {"bot_token": bot_token, "menu_id": menu_id, "button_type": button_type})
        bot.edit_message_text("📝 *Введите текст для кнопки*", chat_id, msg_id, parse_mode='Markdown')
        return

    if data.startswith("delete_menu|"):
        parts = data.split("|")
        bot_token = parts[1]
        menu_id = int(parts[2])
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM bot_menus WHERE id=?", (menu_id,))
        c.execute("DELETE FROM bot_menu_buttons WHERE menu_id=?", (menu_id,))
        conn.commit()
        conn.close()
        bot.answer_callback_query(call.id, "Меню удалено")
        callback_query(call)
        return

    if data.startswith("set_main_menu|"):
        parts = data.split("|")
        bot_token = parts[1]
        menu_id = int(parts[2])
        # Сохраняем ID основного меню в отдельную таблицу или в user_bots
        # Пока просто уведомляем
        bot.answer_callback_query(call.id, "Это меню теперь будет основным при /start", show_alert=True)
        return

    # Остальные функции
    if data.startswith("welcome|"):
        bot_token = data.split("|")[1]
        save_state(user_id, "waiting_welcome", {"bot_token": bot_token})
        bot.edit_message_text("📝 Отправь новый текст приветствия", chat_id, msg_id)
        return

    if data.startswith("photo|"):
        bot_token = data.split("|")[1]
        save_state(user_id, "waiting_photo", {"bot_token": bot_token})
        bot.edit_message_text("🖼 Отправь фото", chat_id, msg_id)
        return

    if data.startswith("operators|"):
        bot_token = data.split("|")[1]
        kb = operators_keyboard(bot_token)
        bot.edit_message_text("👥 *ОПЕРАТОРЫ*", chat_id, msg_id, reply_markup=kb, parse_mode='Markdown')
        return

    if data.startswith("add_op|"):
        bot_token = data.split("|")[1]
        save_state(user_id, "waiting_op_id", {"bot_token": bot_token})
        bot.edit_message_text("📱 Введи ID оператора (@userinfobot)", chat_id, msg_id)
        return

    if data.startswith("del_op|"):
        parts = data.split("|")
        bot_token = parts[1]
        op_id = int(parts[2])
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM bot_operators WHERE id=? AND bot_token=?", (op_id, bot_token))
        conn.commit()
        conn.close()
        bot.answer_callback_query(call.id, "Оператор удалён")
        callback_query(call)
        return

    if data.startswith("tags|"):
        bot_token = data.split("|")[1]
        kb = tags_keyboard(bot_token)
        bot.edit_message_text("🏷 *ТЕГИ*", chat_id, msg_id, reply_markup=kb, parse_mode='Markdown')
        return

    if data.startswith("create_tag|"):
        bot_token = data.split("|")[1]
        save_state(user_id, "waiting_tag_name", {"bot_token": bot_token})
        bot.edit_message_text("📝 Введи название тега", chat_id, msg_id)
        return

    if data.startswith("tag_menu|"):
        parts = data.split("|")
        bot_token = parts[1]
        tag_id = int(parts[2])
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT tag_name FROM bot_tags WHERE id=?", (tag_id,))
        tag_name = c.fetchone()[0]
        conn.close()
        kb = tag_operators_keyboard(bot_token, tag_id, tag_name)
        bot.edit_message_text(f"🏷 *Тег: {tag_name}*", chat_id, msg_id, reply_markup=kb, parse_mode='Markdown')
        return

    if data.startswith("assign_op_tag|"):
        parts = data.split("|")
        bot_token = parts[1]
        op_id = int(parts[2])
        tag_id = int(parts[3])
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE bot_operators SET tag_id=? WHERE id=?", (tag_id, op_id))
        conn.commit()
        conn.close()
        bot.answer_callback_query(call.id, "Тег назначен")
        callback_query(call)
        return

    if data.startswith("remove_op_tag|"):
        parts = data.split("|")
        bot_token = parts[1]
        op_id = int(parts[2])
        tag_id = int(parts[3])
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE bot_operators SET tag_id=NULL WHERE id=?", (op_id,))
        conn.commit()
        conn.close()
        bot.answer_callback_query(call.id, "Тег снят")
        callback_query(call)
        return

    if data.startswith("subscribe|"):
        bot_token = data.split("|")[1]
        save_state(user_id, "waiting_channel", {"bot_token": bot_token})
        bot.edit_message_text("📢 Введи @username канала (бот должен быть админом)", chat_id, msg_id)
        return

    if data.startswith("ai|"):
        bot_token = data.split("|")[1]
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT ai_enabled FROM user_bots WHERE bot_token=?", (bot_token,))
        enabled = c.fetchone()[0]
        if not enabled:
            save_state(user_id, "waiting_ai_prompt", {"bot_token": bot_token})
            bot.edit_message_text("🤖 *Включение нейросети*\nОтправь промпт (как отвечать ИИ)", chat_id, msg_id, parse_mode='Markdown')
        else:
            c.execute("UPDATE user_bots SET ai_enabled=0 WHERE bot_token=?", (bot_token,))
            conn.commit()
            bot.answer_callback_query(call.id, "Нейросеть выключена")
            callback_query(call)
        conn.close()
        return

    if data.startswith("autoreply|"):
        bot_token = data.split("|")[1]
        save_state(user_id, "waiting_autoreply_text", {"bot_token": bot_token})
        bot.edit_message_text("🤖 *Автоответчик*\nОтправь текст (или 'отключить')", chat_id, msg_id, parse_mode='Markdown')
        return

    if data.startswith("color|"):
        bot_token = data.split("|")[1]
        kb = color_keyboard(bot_token)
        bot.edit_message_text("🎨 *ВЫБЕРИ ЦВЕТ*", chat_id, msg_id, reply_markup=kb, parse_mode='Markdown')
        return

    if data.startswith("set_color|"):
        parts = data.split("|")
        bot_token = parts[1]
        color = parts[2]
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE user_bots SET theme_color=? WHERE bot_token=?", (color, bot_token))
        conn.commit()
        conn.close()
        bot.answer_callback_query(call.id, f"Цвет изменён на {color}")
        callback_query(call)
        return

    if data.startswith("anonymous|"):
        bot_token = data.split("|")[1]
        kb = anonymous_keyboard(bot_token)
        bot.edit_message_text("👤 *АНОНИМНЫЙ РЕЖИМ*", chat_id, msg_id, reply_markup=kb, parse_mode='Markdown')
        return

    if data.startswith("toggle_anonymous|"):
        bot_token = data.split("|")[1]
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE user_bots SET anonymous_mode = NOT anonymous_mode WHERE bot_token=?", (bot_token,))
        conn.commit()
        conn.close()
        bot.answer_callback_query(call.id, "Режим изменён")
        callback_query(call)
        return

    if data.startswith("stats|"):
        bot_token = data.split("|")[1]
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT total_messages, total_users FROM user_bots WHERE bot_token=?", (bot_token,))
        msgs, users = c.fetchone()
        conn.close()
        bot.answer_callback_query(call.id, f"Сообщений: {msgs}\nПользователей: {users}", show_alert=True)
        return

    if data.startswith("mailing|"):
        bot_token = data.split("|")[1]
        save_state(user_id, "waiting_mailing_text", {"bot_token": bot_token})
        bot.edit_message_text("📢 Отправь текст рассылки для подписчиков бота", chat_id, msg_id)
        return

    if data.startswith("media|"):
        bot.edit_message_text("📎 *ОБМЕН МЕДИА*\nПоддерживаются текст, фото, документы, видео, аудио, голосовые, геолокация, контакты.", chat_id, msg_id, parse_mode='Markdown')
        return

    if data.startswith("stop_bot|"):
        bot_token = data.split("|")[1]
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE user_bots SET is_active=0 WHERE bot_token=?", (bot_token,))
        conn.commit()
        conn.close()
        bot.answer_callback_query(call.id, "Бот остановлен")
        callback_query(call)
        return

    if data.startswith("delete_bot|"):
        bot_token = data.split("|")[1]
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM user_bots WHERE bot_token=?", (bot_token,))
        c.execute("DELETE FROM bot_operators WHERE bot_token=?", (bot_token,))
        c.execute("DELETE FROM bot_tags WHERE bot_token=?", (bot_token,))
        c.execute("DELETE FROM bot_dialogs WHERE bot_token=?", (bot_token,))
        c.execute("DELETE FROM newsletter_subs WHERE bot_token=?", (bot_token,))
        conn.commit()
        conn.close()
        bot.answer_callback_query(call.id, "Бот удалён")
        callback_query(call)
        return

    if data.startswith("copyright|"):
        bot_token = data.split("|")[1]
        payment_id = f"copy_{user_id}_{int(time.time())}"
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO payments (user_id, amount, type, status, payment_id, bot_token, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                  (user_id, PRICE_COPYRIGHT, "copyright", "pending", payment_id, bot_token, datetime.now()))
        conn.commit()
        conn.close()
        kb = InlineKeyboardMarkup().add(colored_button("💎 Оплатить 100⭐", f"pay_copy|{payment_id}", "success"))
        bot.edit_message_text("✨ *Удаление копирайта* 100⭐", chat_id, msg_id, reply_markup=kb, parse_mode='Markdown')
        return

    if data.startswith("pay_copy|"):
        payment_id = data.split("|")[1]
        bot.send_invoice(chat_id, title="Удаление копирайта", description="Убрать надпись о создателе", invoice_payload=payment_id, provider_token="", currency="XTR", prices=[LabeledPrice(label="Удаление", amount=PRICE_COPYRIGHT)], start_parameter="remove_copyright")
        return

    if user_id == ADMIN_ID:
        if data == "admin_stats":
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM users")
            uc = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM user_bots")
            bc = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM pro_bots")
            pc = c.fetchone()[0]
            c.execute("SELECT SUM(total_messages) FROM user_bots")
            msgs = c.fetchone()[0] or 0
            conn.close()
            bot.edit_message_text(f"📊 *СТАТИСТИКА*\n👥 Пользователей: {uc}\n🤖 Обычных ботов: {bc}\n🤖 Pro ботов: {pc}\n💬 Всего сообщений: {msgs}", chat_id, msg_id, parse_mode='Markdown')
            return
        if data == "admin_edit_welcome":
            save_state(user_id, "admin_waiting_welcome")
            bot.edit_message_text("✏️ Отправь новый текст приветствия для конструктора", chat_id, msg_id)
            return
        if data == "admin_mailing":
            save_state(user_id, "admin_waiting_mailing")
            bot.edit_message_text("📢 Отправь текст рассылки для всех пользователей", chat_id, msg_id)
            return
        if data == "admin_add_stars":
            save_state(user_id, "admin_waiting_stars")
            bot.edit_message_text("⭐ Введите: `ID сумма`\nПример: `6747528307 100`", chat_id, msg_id, parse_mode='Markdown')
            return
        if data == "admin_remove_copyright":
            save_state(user_id, "admin_waiting_bot_id")
            bot.edit_message_text("🗑 Введите ID бота (цифру из БД) или username", chat_id, msg_id)
            return

    bot.answer_callback_query(call.id, "Функция в разработке")

# ==================== ПЛАТЕЖИ ====================
@bot.pre_checkout_query_handler(func=lambda q: True)
def pre_checkout(q):
    bot.answer_pre_checkout_query(q.id, ok=True)

@bot.message_handler(content_types=['successful_payment'])
def on_payment(message):
    payment_id = message.successful_payment.invoice_payload
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT type, bot_token FROM payments WHERE payment_id=?", (payment_id,))
    row = c.fetchone()
    if row:
        ptype, bot_token = row
        c.execute("UPDATE payments SET status='completed' WHERE payment_id=?", (payment_id,))
        if ptype == "copyright":
            c.execute("UPDATE user_bots SET has_copyright=0 WHERE bot_token=?", (bot_token,))
            bot.send_message(message.chat.id, "✅ Копирайт удалён!")
        conn.commit()
    conn.close()

# ==================== ЗАПУСК ПОЛЬЗОВАТЕЛЬСКОГО БОТА ====================
def run_user_bot(token, username, owner_id):
    def worker():
        ub = telebot.TeleBot(token)
        
        def build_menu_kb(menu_id):
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT button_text, button_type, button_value, button_row, button_order FROM bot_menu_buttons WHERE menu_id=? ORDER BY button_row, button_order", (menu_id,))
            buttons = c.fetchall()
            conn.close()
            if not buttons:
                return None
            max_row = max([b[3] for b in buttons]) if buttons else 0
            kb = InlineKeyboardMarkup(row_width=2)
            current_row = 0
            row_buttons = []
            for btn in buttons:
                btn_text, btn_type, btn_value, btn_row, btn_order = btn
                if btn_row != current_row and row_buttons:
                    kb.add(*row_buttons)
                    row_buttons = []
                    current_row = btn_row
                if btn_type == "url":
                    row_buttons.append(InlineKeyboardButton(btn_text, url=btn_value))
                elif btn_type == "profile":
                    row_buttons.append(InlineKeyboardButton(btn_text, callback_data="profile"))
                elif btn_type == "website":
                    row_buttons.append(InlineKeyboardButton(btn_text, url=btn_value))
                elif btn_type == "location":
                    row_buttons.append(InlineKeyboardButton(btn_text, callback_data="location"))
                elif btn_type == "contact":
                    row_buttons.append(InlineKeyboardButton(btn_text, callback_data="contact"))
                else:
                    row_buttons.append(InlineKeyboardButton(btn_text, callback_data=btn_value))
            if row_buttons:
                kb.add(*row_buttons)
            return kb
        
        @ub.message_handler(commands=['start'])
        def ub_start(m):
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT welcome_text, welcome_photo, has_copyright, require_sub, required_channel, auto_reply_always, auto_reply_text, ai_enabled, ai_prompt, anonymous_mode FROM user_bots WHERE bot_token=?", (token,))
            row = c.fetchone()
            c.execute("INSERT OR IGNORE INTO newsletter_subs (bot_token, user_id) VALUES (?, ?)", (token, m.from_user.id))
            # Ищем основное меню
            c.execute("SELECT id, menu_text FROM bot_menus WHERE bot_token=? LIMIT 1", (token,))
            menu = c.fetchone()
            conn.commit()
            conn.close()
            if row:
                text, photo, copyright, req_sub, channel, auto_always, auto_text, ai_enabled, ai_prompt, anonymous = row
                if req_sub and channel:
                    try:
                        member = ub.get_chat_member(f"@{channel}", m.from_user.id)
                        if member.status in ['left', 'kicked']:
                            kb = InlineKeyboardMarkup()
                            kb.add(InlineKeyboardButton("📢 Подписаться", url=f"https://t.me/{channel}"))
                            kb.add(InlineKeyboardButton("✅ Проверить", callback_data="check_sub"))
                            ub.send_message(m.chat.id, f"🔒 Подпишись на @{channel}", reply_markup=kb)
                            return
                    except:
                        pass
                final_text = text
                if copyright:
                    final_text += f"\n\n✨ Создано с помощью @VanillaGramBot"
                
                # Если есть меню, показываем его вместо обычного приветствия
                if menu:
                    menu_id, menu_text = menu
                    final_text = menu_text
                    if copyright:
                        final_text += f"\n\n✨ Создано с помощью @VanillaGramBot"
                    menu_kb = build_menu_kb(menu_id)
                    if menu_kb:
                        if photo:
                            try:
                                ub.send_photo(m.chat.id, photo, caption=final_text, reply_markup=menu_kb, parse_mode='Markdown')
                            except:
                                ub.send_message(m.chat.id, final_text, reply_markup=menu_kb, parse_mode='Markdown')
                        else:
                            ub.send_message(m.chat.id, final_text, reply_markup=menu_kb, parse_mode='Markdown')
                        return
                
                if photo:
                    try:
                        ub.send_photo(m.chat.id, photo, caption=final_text, parse_mode='Markdown')
                    except:
                        ub.send_message(m.chat.id, final_text, parse_mode='Markdown')
                else:
                    ub.send_message(m.chat.id, final_text, parse_mode='Markdown')
        
        @ub.callback_query_handler(func=lambda c: c.data in ["profile", "location", "contact"])
        def handle_special_buttons(c):
            if c.data == "profile":
                bal = get_user_balance(c.from_user.id)
                text = f"👤 *Ваш профиль*\n🆔 ID: `{c.from_user.id}`\n👤 Username: @{c.from_user.username or 'нет'}\n⭐ Баланс звезд: {bal}"
                ub.answer_callback_query(c.id)
                ub.send_message(c.message.chat.id, text, parse_mode='Markdown')
            elif c.data == "location":
                kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
                kb.add(KeyboardButton("📍 Отправить геолокацию", request_location=True))
                ub.send_message(c.message.chat.id, "Нажмите кнопку ниже, чтобы отправить геолокацию:", reply_markup=kb)
            elif c.data == "contact":
                kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
                kb.add(KeyboardButton("📞 Отправить контакт", request_contact=True))
                ub.send_message(c.message.chat.id, "Нажмите кнопку ниже, чтобы отправить контакт:", reply_markup=kb)
        
        @ub.callback_query_handler(func=lambda c: c.data == "check_sub")
        def check_sub(c):
            conn = sqlite3.connect(DB_PATH)
            c2 = conn.cursor()
            c2.execute("SELECT required_channel FROM user_bots WHERE bot_token=?", (token,))
            channel = c2.fetchone()[0]
            conn.close()
            try:
                member = ub.get_chat_member(f"@{channel}", c.from_user.id)
                if member.status in ['member', 'administrator', 'creator']:
                    ub.answer_callback_query(c.id, "✅ Спасибо!")
                    ub.delete_message(c.message.chat.id, c.message.message_id)
                    ub_start(c.message)
                else:
                    ub.answer_callback_query(c.id, "❌ Не подписан", show_alert=True)
            except:
                ub.answer_callback_query(c.id, "❌ Ошибка", show_alert=True)
        
        @ub.message_handler(func=lambda m: True, content_types=['text','photo','document','video','audio','voice','location','contact'])
        def handle_msg(m):
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("INSERT OR IGNORE INTO bot_stats (bot_token, user_id, messages_count, last_activity) VALUES (?, ?, 0, ?)", (token, m.from_user.id, datetime.now()))
            c.execute("UPDATE bot_stats SET messages_count = messages_count + 1, last_activity = ? WHERE bot_token=? AND user_id=?", (datetime.now(), token, m.from_user.id))
            c.execute("UPDATE user_bots SET total_messages = total_messages + 1 WHERE bot_token=?", (token,))
            c.execute("SELECT COUNT(DISTINCT user_id) FROM bot_stats WHERE bot_token=?", (token,))
            unique = c.fetchone()[0]
            c.execute("UPDATE user_bots SET total_users = ? WHERE bot_token=?", (unique, token))
            conn.commit()
            
            c.execute("SELECT auto_reply_always, auto_reply_text, ai_enabled, ai_prompt FROM user_bots WHERE bot_token=?", (token,))
            row = c.fetchone()
            if row:
                auto_always, auto_text, ai_enabled, ai_prompt = row
                if auto_always and auto_text:
                    ub.reply_to(m, auto_text)
                    conn.close()
                    return
                if ai_enabled and m.content_type == 'text':
                    ub.send_chat_action(m.chat.id, 'typing')
                    ans = call_ai(ai_prompt, m.text)
                    if ans:
                        ub.reply_to(m, ans)
                        conn.close()
                        return
            
            c.execute("SELECT id, operator_id FROM bot_dialogs WHERE bot_token=? AND user_id=? AND is_active=1", (token, m.from_user.id))
            dialog = c.fetchone()
            if not dialog:
                c.execute("SELECT id, operator_id FROM bot_operators WHERE bot_token=? LIMIT 1", (token,))
                op = c.fetchone()
                if op:
                    op_id = op[1]
                    c.execute("INSERT INTO bot_dialogs (bot_token, user_id, operator_id, last_message_at, is_active) VALUES (?, ?, ?, ?, 1)", (token, m.from_user.id, op_id, datetime.now()))
                else:
                    conn.close()
                    ub.reply_to(m, "❌ Нет свободных операторов")
                    return
            else:
                op_id = dialog[1]
            c.execute("SELECT anonymous_mode FROM user_bots WHERE bot_token=?", (token,))
            anonymous = c.fetchone()[0]
            conn.close()
            if anonymous:
                from_text = "👤 Пользователь (анонимно)"
            else:
                from_text = f"👤 @{m.from_user.username or m.from_user.first_name} (ID: {m.from_user.id})"
            caption = f"📩 *Новое сообщение*\n{from_text}\n\n"
            try:
                if m.content_type == 'text':
                    bot.send_message(op_id, caption + m.text, parse_mode='Markdown')
                elif m.content_type == 'photo':
                    bot.send_photo(op_id, m.photo[-1].file_id, caption=caption, parse_mode='Markdown')
                elif m.content_type == 'document':
                    bot.send_document(op_id, m.document.file_id, caption=caption, parse_mode='Markdown')
                elif m.content_type == 'video':
                    bot.send_video(op_id, m.video.file_id, caption=caption, parse_mode='Markdown')
                elif m.content_type == 'audio':
                    bot.send_audio(op_id, m.audio.file_id, caption=caption, parse_mode='Markdown')
                elif m.content_type == 'voice':
                    bot.send_voice(op_id, m.voice.file_id, caption=caption, parse_mode='Markdown')
                elif m.content_type == 'location':
                    bot.send_location(op_id, m.location.latitude, m.location.longitude)
                    bot.send_message(op_id, caption, parse_mode='Markdown')
                elif m.content_type == 'contact':
                    bot.send_contact(op_id, m.contact.phone_number, m.contact.first_name, last_name=m.contact.last_name)
                    bot.send_message(op_id, caption, parse_mode='Markdown')
                ub.reply_to(m, "✅ Сообщение отправлено оператору!")
            except:
                ub.reply_to(m, "❌ Ошибка при отправке")
        
        @bot.message_handler(func=lambda m: True)
        def operator_reply(m):
            if not m.reply_to_message:
                return
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT bot_token FROM bot_operators WHERE operator_id=?", (m.from_user.id,))
            bts = c.fetchall()
            if not bts:
                conn.close()
                return
            for (bt,) in bts:
                c.execute("SELECT id, user_id FROM bot_dialogs WHERE bot_token=? AND operator_id=? AND is_active=1 ORDER BY last_message_at DESC LIMIT 1", (bt, m.from_user.id))
                diag = c.fetchone()
                if diag:
                    dia_id, uid = diag
                    c.execute("UPDATE bot_dialogs SET last_message_at=? WHERE id=?", (datetime.now(), dia_id))
                    conn.commit()
                    conn.close()
                    user_bot = telebot.TeleBot(bt)
                    try:
                        if m.content_type == 'text':
                            user_bot.send_message(uid, f"📝 *Ответ оператора:*\n\n{m.text}", parse_mode='Markdown')
                        elif m.content_type == 'photo':
                            user_bot.send_photo(uid, m.photo[-1].file_id, caption="📝 *Ответ оператора:*", parse_mode='Markdown')
                        elif m.content_type == 'document':
                            user_bot.send_document(uid, m.document.file_id, caption="📝 *Ответ оператора:*", parse_mode='Markdown')
                        elif m.content_type == 'video':
                            user_bot.send_video(uid, m.video.file_id, caption="📝 *Ответ оператора:*", parse_mode='Markdown')
                        elif m.content_type == 'audio':
                            user_bot.send_audio(uid, m.audio.file_id, caption="📝 *Ответ оператора:*", parse_mode='Markdown')
                        elif m.content_type == 'voice':
                            user_bot.send_voice(uid, m.voice.file_id, caption="📝 *Ответ оператора:*", parse_mode='Markdown')
                        elif m.content_type == 'location':
                            user_bot.send_location(uid, m.location.latitude, m.location.longitude)
                            user_bot.send_message(uid, "📝 *Ответ оператора:*", parse_mode='Markdown')
                        bot.reply_to(m, "✅ Ответ отправлен пользователю!")
                    except Exception as e:
                        bot.reply_to(m, f"❌ Ошибка: {e}")
                    return
            conn.close()
        
        try:
            ub.infinity_polling(timeout=60)
        except:
            pass
    threading.Thread(target=worker, daemon=True).start()

def run_pro_bot(token, username, owner_id, filepath):
    def worker():
        try:
            subprocess.Popen([sys.executable, filepath], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except:
            pass
    threading.Thread(target=worker, daemon=True).start()

# ==================== ЗАПУСК ====================
if __name__ == "__main__":
    print("="*60)
    print("🤖 VanillaGram — ФИНАЛЬНАЯ ВЕРСИЯ")
    print("="*60)
    print(f"✅ БД: {DB_PATH}")
    print(f"✅ Админ ID: {ADMIN_ID}")
    print(f"✅ Папка media: {MEDIA_DIR}")
    print("="*60)
    print("Команды: /addbot, /mybot, /pro_bot, /top, /profile, /admin")
    print("5 типов кнопок: канал, профиль, сайт, геолокация, контакт")
    print("Создание разделов (меню) с привязкой кнопок")
    print("="*60)
    while True:
        try:
            bot.infinity_polling(timeout=60)
        except Exception as e:
            print(f"⚠️ Ошибка: {e}. Переподключение через 10 сек...")
            time.sleep(10)