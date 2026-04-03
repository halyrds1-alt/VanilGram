import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice, PreCheckoutQuery
import sqlite3
import json
import threading
import time
import os
import requests
from datetime import datetime, timedelta
import logging

# ==================== КОНФИГ ====================
TOKEN = "8789730707:AAFviuMjcPpnZeGIgY_KoduvUCaGngEowTA"
CHANNEL_LINK = "https://t.me/VanillaGram"
OPENROUTER_API_KEY = "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"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

PRICE_PREMIUM_BOT = 350
PRICE_AI_PROMPT = 50
PRICE_COPYRIGHT = 100

# ID администратора (укажи свой Telegram ID)
ADMIN_ID = 8666834683  # <-- ВСТАВЬ СВОЙ ID

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vanilla_gram.db")
MEDIA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "media")
os.makedirs(MEDIA_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ==================== БАЗА ДАННЫХ ====================
def init_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        reg_date TIMESTAMP
    )''')
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
        threads_enabled INTEGER DEFAULT 1,
        user_data_enabled INTEGER DEFAULT 1,
        antiflood_enabled INTEGER DEFAULT 0,
        auto_reply_always INTEGER DEFAULT 0,
        auto_reply_text TEXT,
        interrupt_flow INTEGER DEFAULT 1,
        tags_enabled INTEGER DEFAULT 1
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS bot_operators (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bot_token TEXT,
        operator_id INTEGER,
        tag TEXT,
        added_at TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS bot_tags (
        bot_token TEXT,
        tag_name TEXT,
        PRIMARY KEY (bot_token, tag_name)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS bot_dialogs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bot_token TEXT,
        user_id INTEGER,
        operator_id INTEGER,
        tag TEXT,
        last_message_at TIMESTAMP,
        active INTEGER DEFAULT 1
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS newsletter_subs (
        bot_token TEXT,
        user_id INTEGER,
        PRIMARY KEY (bot_token, user_id)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS ai_prompts (
        bot_token TEXT,
        prompt_text TEXT,
        is_active INTEGER DEFAULT 1,
        PRIMARY KEY (bot_token)
    )''')
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
    c.execute('''CREATE TABLE IF NOT EXISTS user_states (
        user_id INTEGER PRIMARY KEY,
        state TEXT,
        data TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS constructor_settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )''')
    # Добавляем настройки конструктора по умолчанию
    c.execute("INSERT OR IGNORE INTO constructor_settings (key, value) VALUES ('welcome_text', '🌟 *ДОБРО ПОЖАЛОВАТЬ В VANILLAGRAM!* 🌟\n\nБесплатный конструктор Telegram ботов\n▫️ Безлимит операторов\n▫️ Теги и автоответчик\n▫️ Рассылка подписчикам\n▫️ Обязательная подписка\n\n*Выбери действие:*')")
    conn.commit()
    conn.close()
    logger.info("✅ База данных готова")

init_db()

# ==================== БОТ ====================
bot = telebot.TeleBot(TOKEN)
bot.set_my_commands([
    telebot.types.BotCommand("/start", "Главное меню"),
    telebot.types.BotCommand("/addbot", "Добавить бота"),
    telebot.types.BotCommand("/mybot", "Мои боты"),
    telebot.types.BotCommand("/admin", "Админ панель")
])

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
    return open(path, 'rb') if os.path.exists(path) else None

def get_constructor_welcome_text():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT value FROM constructor_settings WHERE key='welcome_text'")
    row = c.fetchone()
    conn.close()
    return row[0] if row else "🌟 *ДОБРО ПОЖАЛОВАТЬ В VANILLAGRAM!* 🌟\n\nБесплатный конструктор Telegram ботов\n\n*Выбери действие:*"

# ==================== КЛАВИАТУРЫ ====================
def main_keyboard():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("➕ ДОБАВИТЬ БОТА", callback_data="add_bot"),
        InlineKeyboardButton("🤖 МОИ БОТЫ", callback_data="my_bots")
    )
    kb.add(
        InlineKeyboardButton("✨ ПРЕМИУМ БОТ (350⭐)", callback_data="premium_bot"),
        InlineKeyboardButton("📢 НАШ КАНАЛ", url=CHANNEL_LINK)
    )
    kb.add(InlineKeyboardButton("📖 ПОМОЩЬ", callback_data="help"))
    return kb

def my_bots_keyboard(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT bot_token, bot_username FROM user_bots WHERE user_id=? AND is_active=1", (user_id,))
    bots = c.fetchall()
    conn.close()
    kb = InlineKeyboardMarkup(row_width=1)
    for token, username in bots:
        kb.add(InlineKeyboardButton(f"🤖 @{username}", callback_data=f"edit_{token}"))
    kb.add(InlineKeyboardButton("🔙 НАЗАД", callback_data="back_start"))
    return kb

def bot_settings_keyboard(bot_token):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT bot_username, welcome_text, has_copyright, require_sub, welcome_photo, threads_enabled, user_data_enabled, antiflood_enabled, auto_reply_always, interrupt_flow, tags_enabled, auto_reply_text FROM user_bots WHERE bot_token=?", (bot_token,))
    row = c.fetchone()
    c.execute("SELECT COUNT(*) FROM bot_operators WHERE bot_token=?", (bot_token,))
    op_count = c.fetchone()[0]
    c.execute("SELECT tag_name FROM bot_tags WHERE bot_token=?", (bot_token,))
    tags = c.fetchall()
    conn.close()
    if not row:
        return None
    username, welcome, copyright, req_sub, photo, threads, user_data, antiflood, auto_reply, interrupt, tags_enabled, auto_reply_text = row
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("📝 ПРИВЕТСТВИЕ", callback_data=f"welcome_{bot_token}"),
        InlineKeyboardButton("🖼 ФОТО", callback_data=f"photo_{bot_token}"),
        InlineKeyboardButton("👥 ОПЕРАТОРЫ", callback_data=f"operators_{bot_token}"),
        InlineKeyboardButton("🏷 ТЕГИ", callback_data=f"tags_{bot_token}"),
        InlineKeyboardButton("🔒 ПОДПИСКА", callback_data=f"subscribe_{bot_token}"),
        InlineKeyboardButton("🤖 НЕЙРОСЕТЬ (50⭐)", callback_data=f"ai_prompt_{bot_token}"),
        InlineKeyboardButton("⚙️ НАСТРОЙКИ", callback_data=f"settings_{bot_token}"),
        InlineKeyboardButton("🤖 АВТООТВЕТЧИК", callback_data=f"autoreply_{bot_token}")
    )
    if copyright:
        kb.add(InlineKeyboardButton("✨ УБРАТЬ КОПИРАЙТ (100⭐)", callback_data=f"copyright_{bot_token}"))
    kb.add(InlineKeyboardButton("🔙 НАЗАД", callback_data="my_bots"))
    status = f"📷 Фото: {'✅' if photo else '❌'}\n🔒 Подписка: {'✅' if req_sub else '❌'}\n© Копирайт: {'✅' if copyright else '❌'}\n👥 Операторы: {op_count}\n🏷 Теги: {len(tags)}\n🔄 Потоки: {'✅' if threads else '❌'}\n📊 Данные: {'✅' if user_data else '❌'}\n🚫 Антифлуд: {'✅' if antiflood else '❌'}\n🤖 Автоответ: {'✅' if auto_reply else '❌'}\n⏸ Прерывать: {'✅' if interrupt else '❌'}"
    return kb, status, username

def admin_keyboard():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("📊 СТАТИСТИКА", callback_data="admin_stats"),
        InlineKeyboardButton("✏️ ИЗМЕНИТЬ ПРИВЕТСТВИЕ", callback_data="admin_edit_welcome"),
        InlineKeyboardButton("📢 РАССЫЛКА", callback_data="admin_mailing"),
        InlineKeyboardButton("🗑 УДАЛИТЬ КОПИРАЙТ (по ID бота)", callback_data="admin_remove_copyright"),
        InlineKeyboardButton("🔙 НАЗАД", callback_data="back_start")
    )
    return kb

# ==================== /start ====================
@bot.message_handler(commands=['start'])
def start(message):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, username, reg_date) VALUES (?, ?, ?)",
              (message.from_user.id, message.from_user.username, datetime.now()))
    conn.commit()
    conn.close()
    photo = get_main_photo()
    text = get_constructor_welcome_text()
    if photo:
        bot.send_photo(message.chat.id, photo, caption=text, reply_markup=main_keyboard(), parse_mode='Markdown')
    else:
        bot.send_message(message.chat.id, text, reply_markup=main_keyboard(), parse_mode='Markdown')

# ==================== /addbot ====================
@bot.message_handler(commands=['addbot'])
def addbot_cmd(message):
    save_state(message.from_user.id, "waiting_token")
    bot.send_message(message.chat.id, "🔑 *Введите токен бота от @BotFather*\n\nПример: `1234567890:ABCdefGHIjkl`", parse_mode='Markdown')

# ==================== /mybot ====================
@bot.message_handler(commands=['mybot'])
def mybot_cmd(message):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT bot_token, bot_username FROM user_bots WHERE user_id=? AND is_active=1", (message.from_user.id,))
    bots = c.fetchall()
    conn.close()
    if not bots:
        bot.send_message(message.chat.id, "❌ *У вас нет ботов*\n\nДобавьте через /addbot", parse_mode='Markdown')
        return
    bot.send_message(message.chat.id, "🎮 *ТВОИ БОТЫ:*", reply_markup=my_bots_keyboard(message.from_user.id), parse_mode='Markdown')

# ==================== /admin ====================
@bot.message_handler(commands=['admin'])
def admin_cmd(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "❌ У вас нет доступа к этой команде.")
        return
    text = "🔐 *АДМИН ПАНЕЛЬ VANILLAGRAM*\n\nВыберите действие:"
    bot.send_message(message.chat.id, text, reply_markup=admin_keyboard(), parse_mode='Markdown')

# ==================== ОБРАБОТЧИК ВСЕХ CALLBACK ====================
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    data = call.data
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    msg_id = call.message.message_id

    # Глобальные кнопки
    if data == "back_start":
        start(call.message)
        bot.delete_message(chat_id, msg_id)
        return
    if data == "add_bot":
        addbot_cmd(call.message)
        return
    if data == "my_bots":
        mybot_cmd(call.message)
        return
    if data == "help":
        text = """📖 *ПОМОЩЬ VANILLAGRAM*

*Команды:*
/start - Главное меню
/addbot - Добавить бота
/mybot - Мои боты

*Бесплатно:*
• Безлимит операторов
• Теги и автоответчик
• Потоки сообщений
• Рассылка
• Обязательная подписка

*Платно:*
• Свой промпт нейросети - 50⭐
• Удаление копирайта - 100⭐
• Бот под ключ - 350⭐

*Канал:* https://t.me/VanillaGram"""
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("🔙 НАЗАД", callback_data="back_start"))
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=kb, parse_mode='Markdown')
        return
    if data == "premium_bot":
        save_state(user_id, "waiting_premium_desc")
        bot.edit_message_text("✨ *Опиши какого бота нужно создать*\n⚠️ *Обязательно укажи API токен!*\n\nПример: 'Бот для пиццерии, токен: 123456:ABCdef'", chat_id, msg_id, parse_mode='Markdown')
        return

    # Админ-панель
    if user_id == ADMIN_ID:
        if data == "admin_stats":
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM users")
            total_users = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM user_bots")
            total_bots = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM bot_operators")
            total_ops = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM payments WHERE status='completed'")
            total_payments = c.fetchone()[0]
            c.execute("SELECT SUM(amount) FROM payments WHERE status='completed'")
            total_stars = c.fetchone()[0] or 0
            conn.close()
            stats = f"📊 *СТАТИСТИКА КОНСТРУКТОРА*\n\n👥 Пользователей: {total_users}\n🤖 Ботов: {total_bots}\n👥 Операторов: {total_ops}\n💳 Платежей: {total_payments}\n⭐ Звезд заработано: {total_stars}"
            bot.edit_message_text(stats, chat_id, msg_id, parse_mode='Markdown')
            return
        if data == "admin_edit_welcome":
            save_state(user_id, "admin_waiting_welcome")
            bot.edit_message_text("✏️ *Отправьте новый текст приветствия для конструктора* (можно с Markdown)", chat_id, msg_id, parse_mode='Markdown')
            return
        if data == "admin_mailing":
            save_state(user_id, "admin_waiting_mailing_text")
            bot.edit_message_text("📢 *Отправьте текст рассылки для всех пользователей*", chat_id, msg_id, parse_mode='Markdown')
            return
        if data == "admin_remove_copyright":
            save_state(user_id, "admin_waiting_bot_id")
            bot.edit_message_text("🗑 *Введите ID бота (цифру из базы данных) или username бота* для удаления копирайта.\n\nID можно узнать через /admin_stats", chat_id, msg_id, parse_mode='Markdown')
            return

    # Редактирование бота
    if data.startswith("edit_"):
        bot_token = data.replace("edit_", "")
        res = bot_settings_keyboard(bot_token)
        if res:
            kb, status, username = res
            bot.edit_message_text(f"⚙️ *@{username}*\n\n{status}", chat_id, msg_id, reply_markup=kb, parse_mode='Markdown')
        return

    if data.startswith("welcome_"):
        bot_token = data.replace("welcome_", "")
        save_state(user_id, "waiting_welcome", {"bot_token": bot_token})
        bot.edit_message_text("📝 *Отправь новый текст приветствия*", chat_id, msg_id, parse_mode='Markdown')
        return

    if data.startswith("photo_"):
        bot_token = data.replace("photo_", "")
        save_state(user_id, "waiting_photo", {"bot_token": bot_token})
        bot.edit_message_text("🖼 *Отправь фото*", chat_id, msg_id, parse_mode='Markdown')
        return

    if data.startswith("operators_"):
        bot_token = data.replace("operators_", "")
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT id, operator_id, tag FROM bot_operators WHERE bot_token=?", (bot_token,))
        ops = c.fetchall()
        c.execute("SELECT tag_name FROM bot_tags WHERE bot_token=?", (bot_token,))
        tags = c.fetchall()
        conn.close()
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(InlineKeyboardButton("➕ ДОБАВИТЬ ОПЕРАТОРА", callback_data=f"add_op_{bot_token}"))
        if tags:
            kb.add(InlineKeyboardButton("🏷 НАЗНАЧИТЬ ТЕГ", callback_data=f"assign_tag_{bot_token}"))
        kb.add(InlineKeyboardButton("🔙 НАЗАД", callback_data=f"edit_{bot_token}"))
        ops_text = "\n".join([f"• {op[1]} {'🏷 '+op[2] if op[2] else ''}" for op in ops]) if ops else "Нет операторов"
        bot.edit_message_text(f"👥 *ОПЕРАТОРЫ*\n\n{ops_text}\n\nТеги: {', '.join([t[0] for t in tags]) if tags else 'нет'}", chat_id, msg_id, reply_markup=kb, parse_mode='Markdown')
        return

    if data.startswith("add_op_"):
        bot_token = data.replace("add_op_", "")
        save_state(user_id, "waiting_op_id", {"bot_token": bot_token})
        bot.edit_message_text("📱 *Введи ID оператора* (узнать через @userinfobot)", chat_id, msg_id, parse_mode='Markdown')
        return

    if data.startswith("assign_tag_"):
        bot_token = data.replace("assign_tag_", "")
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT id, operator_id FROM bot_operators WHERE bot_token=?", (bot_token,))
        ops = c.fetchall()
        conn.close()
        if not ops:
            bot.answer_callback_query(call.id, "Нет операторов", show_alert=True)
            return
        kb = InlineKeyboardMarkup(row_width=1)
        for op_id, op_user in ops:
            kb.add(InlineKeyboardButton(f"👤 {op_user}", callback_data=f"tag_op_{bot_token}_{op_id}"))
        bot.edit_message_text("👥 *Выбери оператора*", chat_id, msg_id, reply_markup=kb, parse_mode='Markdown')
        return

    if data.startswith("tag_op_"):
        parts = data.split("_")
        bot_token = parts[2]
        op_db_id = parts[3]
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT tag_name FROM bot_tags WHERE bot_token=?", (bot_token,))
        tags = c.fetchall()
        conn.close()
        save_state(user_id, "waiting_tag_select", {"bot_token": bot_token, "op_id": op_db_id})
        kb = InlineKeyboardMarkup(row_width=1)
        for tag in tags:
            kb.add(InlineKeyboardButton(f"🏷 {tag[0]}", callback_data=f"set_tag_{bot_token}_{op_db_id}_{tag[0]}"))
        kb.add(InlineKeyboardButton("🔙 НАЗАД", callback_data=f"operators_{bot_token}"))
        bot.edit_message_text("🏷 *Выбери тег*", chat_id, msg_id, reply_markup=kb, parse_mode='Markdown')
        return

    if data.startswith("set_tag_"):
        parts = data.split("_")
        bot_token = parts[2]
        op_db_id = parts[3]
        tag_name = "_".join(parts[4:])
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE bot_operators SET tag=? WHERE id=?", (tag_name, op_db_id))
        conn.commit()
        conn.close()
        bot.answer_callback_query(call.id, f"Тег '{tag_name}' назначен!")
        bot.edit_message_text("✅ *Тег назначен!*", chat_id, msg_id)
        return

    if data.startswith("tags_"):
        bot_token = data.replace("tags_", "")
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT tag_name FROM bot_tags WHERE bot_token=?", (bot_token,))
        tags = c.fetchall()
        conn.close()
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(InlineKeyboardButton("➕ СОЗДАТЬ ТЕГ", callback_data=f"create_tag_{bot_token}"))
        for tag in tags:
            kb.add(InlineKeyboardButton(f"🏷 {tag[0]} ❌", callback_data=f"del_tag_{bot_token}_{tag[0]}"))
        kb.add(InlineKeyboardButton("🔙 НАЗАД", callback_data=f"edit_{bot_token}"))
        tags_text = "\n".join([f"• {t[0]}" for t in tags]) if tags else "Нет тегов"
        bot.edit_message_text(f"🏷 *ТЕГИ БОТА*\n\n{tags_text}", chat_id, msg_id, reply_markup=kb, parse_mode='Markdown')
        return

    if data.startswith("create_tag_"):
        bot_token = data.replace("create_tag_", "")
        save_state(user_id, "waiting_tag_name", {"bot_token": bot_token})
        bot.edit_message_text("📝 *Введи название тега*", chat_id, msg_id, parse_mode='Markdown')
        return

    if data.startswith("del_tag_"):
        parts = data.split("_")
        bot_token = parts[2]
        tag_name = "_".join(parts[3:])
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM bot_tags WHERE bot_token=? AND tag_name=?", (bot_token, tag_name))
        c.execute("UPDATE bot_operators SET tag=NULL WHERE bot_token=? AND tag=?", (bot_token, tag_name))
        conn.commit()
        conn.close()
        bot.answer_callback_query(call.id, f"Тег '{tag_name}' удален")
        callback_handler(call)
        return

    if data.startswith("subscribe_"):
        bot_token = data.replace("subscribe_", "")
        save_state(user_id, "waiting_channel", {"bot_token": bot_token})
        bot.edit_message_text("📢 *Введи @username канала*\nБот должен быть админом!", chat_id, msg_id, parse_mode='Markdown')
        return

    if data.startswith("ai_prompt_"):
        bot_token = data.replace("ai_prompt_", "")
        payment_id = f"ai_{user_id}_{int(time.time())}"
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO payments (user_id, amount, type, status, payment_id, bot_token, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                  (user_id, PRICE_AI_PROMPT, "ai_prompt", "pending", payment_id, bot_token, datetime.now()))
        conn.commit()
        conn.close()
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("💎 ОПЛАТИТЬ 50⭐", callback_data=f"pay_ai_{payment_id}"))
        kb.add(InlineKeyboardButton("🔙 НАЗАД", callback_data=f"edit_{bot_token}"))
        bot.edit_message_text("🤖 *НАСТРОЙКА НЕЙРОСЕТИ*\nСтоимость: 50⭐\nПосле оплаты сможешь задать свой промпт", chat_id, msg_id, reply_markup=kb, parse_mode='Markdown')
        return

    if data.startswith("settings_"):
        bot_token = data.replace("settings_", "")
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT threads_enabled, user_data_enabled, antiflood_enabled, auto_reply_always, interrupt_flow, tags_enabled FROM user_bots WHERE bot_token=?", (bot_token,))
        row = c.fetchone()
        conn.close()
        if row:
            threads, user_data, antiflood, auto_reply, interrupt, tags_enabled = row
            kb = InlineKeyboardMarkup(row_width=2)
            kb.add(
                InlineKeyboardButton(f"{'✅' if threads else '❌'} ПОТОКИ", callback_data=f"toggle_threads_{bot_token}"),
                InlineKeyboardButton(f"{'✅' if user_data else '❌'} ДАННЫЕ", callback_data=f"toggle_userdata_{bot_token}")
            )
            kb.add(
                InlineKeyboardButton(f"{'✅' if antiflood else '❌'} АНТИФЛУД", callback_data=f"toggle_antiflood_{bot_token}"),
                InlineKeyboardButton(f"{'✅' if auto_reply else '❌'} АВТООТВЕТ", callback_data=f"toggle_autoreply_{bot_token}")
            )
            kb.add(
                InlineKeyboardButton(f"{'✅' if interrupt else '❌'} ПРЕРЫВАТЬ", callback_data=f"toggle_interrupt_{bot_token}"),
                InlineKeyboardButton(f"{'✅' if tags_enabled else '❌'} ТЕГИ", callback_data=f"toggle_tags_{bot_token}")
            )
            kb.add(InlineKeyboardButton("🔙 НАЗАД", callback_data=f"edit_{bot_token}"))
            bot.edit_message_text("⚙️ *НАСТРОЙКИ БОТА*", chat_id, msg_id, reply_markup=kb, parse_mode='Markdown')
        return

    if data.startswith("toggle_"):
        parts = data.split("_")
        setting = parts[1]
        bot_token = parts[2]
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        if setting == "threads":
            c.execute("UPDATE user_bots SET threads_enabled = NOT threads_enabled WHERE bot_token=?", (bot_token,))
        elif setting == "userdata":
            c.execute("UPDATE user_bots SET user_data_enabled = NOT user_data_enabled WHERE bot_token=?", (bot_token,))
        elif setting == "antiflood":
            c.execute("UPDATE user_bots SET antiflood_enabled = NOT antiflood_enabled WHERE bot_token=?", (bot_token,))
        elif setting == "autoreply":
            c.execute("UPDATE user_bots SET auto_reply_always = NOT auto_reply_always WHERE bot_token=?", (bot_token,))
        elif setting == "interrupt":
            c.execute("UPDATE user_bots SET interrupt_flow = NOT interrupt_flow WHERE bot_token=?", (bot_token,))
        elif setting == "tags":
            c.execute("UPDATE user_bots SET tags_enabled = NOT tags_enabled WHERE bot_token=?", (bot_token,))
        conn.commit()
        conn.close()
        callback_handler(call)
        return

    if data.startswith("autoreply_"):
        bot_token = data.replace("autoreply_", "")
        save_state(user_id, "waiting_autoreply_text", {"bot_token": bot_token})
        bot.edit_message_text("🤖 *Введи текст автоответчика*\nЭтот текст будет отправляться пользователям автоматически.\n\nОтправь 'отключить' чтобы выключить.", chat_id, msg_id, parse_mode='Markdown')
        return

    if data.startswith("copyright_"):
        bot_token = data.replace("copyright_", "")
        payment_id = f"copy_{user_id}_{int(time.time())}"
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO payments (user_id, amount, type, status, payment_id, bot_token, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                  (user_id, PRICE_COPYRIGHT, "copyright", "pending", payment_id, bot_token, datetime.now()))
        conn.commit()
        conn.close()
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("💎 ОПЛАТИТЬ 100⭐", callback_data=f"pay_copy_{payment_id}"))
        kb.add(InlineKeyboardButton("🔙 НАЗАД", callback_data=f"edit_{bot_token}"))
        bot.edit_message_text("✨ *УДАЛЕНИЕ КОПИРАЙТА*\nСтоимость: 100⭐\nПосле оплаты исчезнет надпись 'Создано с помощью @VanillaGramBot'", chat_id, msg_id, reply_markup=kb, parse_mode='Markdown')
        return

    if data.startswith("pay_ai_"):
        payment_id = data.replace("pay_ai_", "")
        bot.send_invoice(chat_id, title="🤖 Нейросеть", description="Свой промпт для нейросети", invoice_payload=payment_id, provider_token="", currency="XTR", prices=[LabeledPrice(label="Промпт", amount=PRICE_AI_PROMPT)], start_parameter="ai_prompt")
        return
    if data.startswith("pay_copy_"):
        payment_id = data.replace("pay_copy_", "")
        bot.send_invoice(chat_id, title="✨ Удаление копирайта", description="Убрать надпись о создателе", invoice_payload=payment_id, provider_token="", currency="XTR", prices=[LabeledPrice(label="Удаление", amount=PRICE_COPYRIGHT)], start_parameter="remove_copyright")
        return

    bot.answer_callback_query(call.id, "Функция в разработке")

# ==================== ОБРАБОТЧИК СООБЩЕНИЙ (СОСТОЯНИЯ) ====================
@bot.message_handler(func=lambda m: get_state(m.from_user.id)[0] is not None)
def state_handler(message):
    state, data = get_state(message.from_user.id)
    user_id = message.from_user.id
    text = message.text.strip()

    # Админские состояния
    if user_id == ADMIN_ID:
        if state == "admin_waiting_welcome":
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("UPDATE constructor_settings SET value=? WHERE key='welcome_text'", (text,))
            conn.commit()
            conn.close()
            clear_state(user_id)
            bot.send_message(message.chat.id, "✅ *Приветствие конструктора обновлено!*", parse_mode='Markdown')
            return
        if state == "admin_waiting_mailing_text":
            # Рассылка всем пользователям
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT user_id FROM users")
            users = c.fetchall()
            conn.close()
            success = 0
            for u in users:
                try:
                    bot.send_message(u[0], f"📢 *РАССЫЛКА ОТ АДМИНИСТРАЦИИ*\n\n{text}", parse_mode='Markdown')
                    success += 1
                except:
                    pass
                time.sleep(0.05)
            clear_state(user_id)
            bot.send_message(message.chat.id, f"✅ *Рассылка завершена!*\nДоставлено: {success} из {len(users)}", parse_mode='Markdown')
            return
        if state == "admin_waiting_bot_id":
            # Поиск бота по ID или username
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            if text.isdigit():
                c.execute("SELECT bot_token, bot_username FROM user_bots WHERE id=?", (int(text),))
            else:
                username = text.replace("@", "")
                c.execute("SELECT bot_token, bot_username FROM user_bots WHERE bot_username=?", (username,))
            row = c.fetchone()
            if not row:
                bot.send_message(message.chat.id, "❌ Бот не найден!")
                clear_state(user_id)
                return
            bot_token, bot_username = row
            c.execute("UPDATE user_bots SET has_copyright=0 WHERE bot_token=?", (bot_token,))
            conn.commit()
            conn.close()
            clear_state(user_id)
            bot.send_message(message.chat.id, f"✅ *Копирайт удален у бота @{bot_username}!*", parse_mode='Markdown')
            return

    # Обычные состояния
    if state == "waiting_token":
        token = text
        try:
            test = telebot.TeleBot(token)
            me = test.get_me()
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute('''INSERT INTO user_bots (user_id, bot_token, bot_username, welcome_text, created_at, threads_enabled, user_data_enabled, antiflood_enabled, auto_reply_always, interrupt_flow, tags_enabled)
                         VALUES (?, ?, ?, ?, ?, 1, 1, 0, 0, 1, 1)''',
                      (user_id, token, me.username, f"Добро пожаловать! Этот бот создан с помощью @VanillaGramBot", datetime.now()))
            c.execute("INSERT INTO bot_operators (bot_token, operator_id, added_at) VALUES (?, ?, ?)", (token, user_id, datetime.now()))
            conn.commit()
            conn.close()
            clear_state(user_id)
            bot.send_message(message.chat.id, f"✅ *Бот @{me.username} добавлен!*\nИспользуй /mybot для настройки", parse_mode='Markdown')
        except Exception as e:
            bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")
        return

    if state == "waiting_welcome":
        bot_token = data["bot_token"]
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE user_bots SET welcome_text=? WHERE bot_token=?", (text, bot_token))
        conn.commit()
        conn.close()
        clear_state(user_id)
        bot.send_message(message.chat.id, "✅ *Приветствие обновлено!*", parse_mode='Markdown')
        return

    if state == "waiting_photo":
        bot.reply_to(message, "❌ Отправь фото, а не текст")
        return

    if state == "waiting_op_id":
        try:
            op_id = int(text)
            bot_token = data["bot_token"]
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("INSERT OR IGNORE INTO bot_operators (bot_token, operator_id, added_at) VALUES (?, ?, ?)", (bot_token, op_id, datetime.now()))
            conn.commit()
            conn.close()
            try:
                bot.send_message(op_id, "🎉 *Ты стал оператором бота!* Отвечай на сообщения пользователей.", parse_mode='Markdown')
            except:
                pass
            bot.reply_to(message, "✅ *Оператор добавлен!*", parse_mode='Markdown')
        except:
            bot.reply_to(message, "❌ Введи числовой ID!")
        clear_state(user_id)
        return

    if state == "waiting_tag_name":
        tag_name = text
        bot_token = data["bot_token"]
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO bot_tags (bot_token, tag_name) VALUES (?, ?)", (bot_token, tag_name))
        conn.commit()
        conn.close()
        clear_state(user_id)
        bot.reply_to(message, f"✅ *Тег '{tag_name}' создан!*", parse_mode='Markdown')
        return

    if state == "waiting_channel":
        channel = text.replace("@", "")
        bot_token = data["bot_token"]
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE user_bots SET require_sub=1, required_channel=? WHERE bot_token=?", (channel, bot_token))
        conn.commit()
        conn.close()
        clear_state(user_id)
        bot.reply_to(message, f"✅ *Подписка настроена!*\nКанал: @{channel}", parse_mode='Markdown')
        return

    if state == "waiting_autoreply_text":
        bot_token = data["bot_token"]
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        if text.lower() == "отключить":
            c.execute("UPDATE user_bots SET auto_reply_always=0, auto_reply_text=NULL WHERE bot_token=?", (bot_token,))
            bot.reply_to(message, "✅ *Автоответчик выключен!*", parse_mode='Markdown')
        else:
            c.execute("UPDATE user_bots SET auto_reply_always=1, auto_reply_text=? WHERE bot_token=?", (text, bot_token))
            bot.reply_to(message, f"✅ *Автоответчик установлен!*\n\nТекст: {text}", parse_mode='Markdown')
        conn.commit()
        conn.close()
        clear_state(user_id)
        return

    if state == "waiting_premium_desc":
        desc = text
        import re
        token_match = re.search(r'token[:\s]+([A-Za-z0-9:_-]+)', desc, re.IGNORECASE)
        if not token_match:
            bot.reply_to(message, "❌ *Ты не указал API токен бота!*\nОбязательно добавь 'токен: 123456:ABCdef'", parse_mode='Markdown')
            return
        user_token = token_match.group(1)
        payment_id = f"premium_{user_id}_{int(time.time())}"
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO payments (user_id, amount, type, status, payment_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                  (user_id, PRICE_PREMIUM_BOT, "premium_bot", "pending", payment_id, datetime.now()))
        conn.commit()
        conn.close()
        save_state(user_id, "waiting_premium_pay", {"desc": desc, "token": user_token, "payment_id": payment_id})
        try:
            bot.send_invoice(message.chat.id, title="✨ Создание бота под ключ", description=f"Бот по описанию: {desc[:50]}...", invoice_payload=payment_id, provider_token="", currency="XTR", prices=[LabeledPrice(label="Создание", amount=PRICE_PREMIUM_BOT)], start_parameter="premium_bot")
        except Exception as e:
            bot.send_message(message.chat.id, f"❌ Ошибка платежа: {e}")
            clear_state(user_id)
        return

    if state == "waiting_premium_pay":
        pass

# ==================== ФОТО ====================
@bot.message_handler(content_types=['photo'])
def photo_handler(message):
    state, data = get_state(message.from_user.id)
    if state == "waiting_photo":
        photo_id = message.photo[-1].file_id
        bot_token = data["bot_token"]
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE user_bots SET welcome_photo=? WHERE bot_token=?", (photo_id, bot_token))
        conn.commit()
        conn.close()
        clear_state(message.from_user.id)
        bot.reply_to(message, "✅ *Фото установлено!*", parse_mode='Markdown')

# ==================== ПЛАТЕЖИ ====================
@bot.pre_checkout_query_handler(func=lambda q: True)
def pre_checkout(q):
    bot.answer_pre_checkout_query(q.id, ok=True)

@bot.message_handler(content_types=['successful_payment'])
def successful_payment(message):
    payment = message.successful_payment
    payment_id = payment.invoice_payload
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT type, bot_token, user_id FROM payments WHERE payment_id=?", (payment_id,))
    row = c.fetchone()
    if row:
        ptype, bot_token, user_id = row
        c.execute("UPDATE payments SET status='completed' WHERE payment_id=?", (payment_id,))
        if ptype == "copyright":
            c.execute("UPDATE user_bots SET has_copyright=0 WHERE bot_token=?", (bot_token,))
            bot.send_message(message.chat.id, "✅ *Копирайт удален!*", parse_mode='Markdown')
        elif ptype == "ai_prompt":
            save_state(user_id, "waiting_ai_prompt", {"bot_token": bot_token})
            bot.send_message(message.chat.id, "🤖 *Введи свой промпт для нейросети*\nПример: 'Ты злая саркастичная нейросеть'", parse_mode='Markdown')
        elif ptype == "premium_bot":
            state, data = get_state(user_id)
            if data:
                desc = data.get("desc", "")
                user_token = data.get("token", "")
                bot.send_message(message.chat.id, "🔄 *Генерирую бота...* Подожди до 30 секунд", parse_mode='Markdown')
                def generate():
                    prompt = f"Создай простого Telegram бота на Python с telebot. Бот должен: {desc}. Используй токен: {user_token}. Выдай только готовый код."
                    try:
                        headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
                        payload = {"model": "openai/gpt-3.5-turbo", "messages": [{"role": "user", "content": prompt}], "max_tokens": 2000}
                        resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=60)
                        if resp.status_code == 200:
                            code = resp.json()["choices"][0]["message"]["content"]
                            bot_folder = os.path.join(os.path.dirname(__file__), "generated_bots")
                            os.makedirs(bot_folder, exist_ok=True)
                            file_path = os.path.join(bot_folder, f"bot_{user_id}_{int(time.time())}.py")
                            with open(file_path, 'w', encoding='utf-8') as f:
                                f.write(code)
                            bot.send_message(message.chat.id, f"✅ *Бот создан!*\nКод сохранен: {file_path}\nЗапусти командой: `python {file_path}`", parse_mode='Markdown')
                        else:
                            bot.send_message(message.chat.id, "❌ Ошибка генерации")
                    except Exception as e:
                        bot.send_message(message.chat.id, f"❌ Ошибка: {e}")
                threading.Thread(target=generate, daemon=True).start()
                clear_state(user_id)
    conn.commit()
    conn.close()

# ==================== ЗАПУСК БОТА ПОЛЬЗОВАТЕЛЯ ====================
def start_user_bot(token, username, owner_id):
    def run():
        ub = telebot.TeleBot(token)
        @ub.message_handler(commands=['start'])
        def ub_start(m):
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT welcome_text, welcome_photo, has_copyright, require_sub, required_channel, auto_reply_always, auto_reply_text FROM user_bots WHERE bot_token=?", (token,))
            row = c.fetchone()
            c.execute("INSERT OR IGNORE INTO newsletter_subs (bot_token, user_id) VALUES (?, ?)", (token, m.from_user.id))
            conn.commit()
            conn.close()
            if row:
                text, photo, copyright, req_sub, channel, auto_reply, auto_text = row
                if req_sub and channel:
                    try:
                        member = ub.get_chat_member(f"@{channel}", m.from_user.id)
                        if member.status in ['left', 'kicked']:
                            kb = InlineKeyboardMarkup()
                            kb.add(InlineKeyboardButton("📢 Подписаться", url=f"https://t.me/{channel}"))
                            kb.add(InlineKeyboardButton("✅ Проверить", callback_data="check_sub"))
                            ub.send_message(m.chat.id, f"🔒 *Подпишись на @{channel}*", reply_markup=kb, parse_mode='Markdown')
                            return
                    except:
                        pass
                final_text = text
                if copyright:
                    final_text += f"\n\n✨ *Создано с помощью @VanillaGramBot*"
                if photo:
                    ub.send_photo(m.chat.id, photo, caption=final_text, parse_mode='Markdown')
                else:
                    ub.send_message(m.chat.id, final_text, parse_mode='Markdown')
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
                    ub.answer_callback_query(c.id, "✅ Спасибо за подписку!")
                    ub.delete_message(c.message.chat.id, c.message.message_id)
                    ub_start(c.message)
                else:
                    ub.answer_callback_query(c.id, "❌ Ты не подписан!", show_alert=True)
            except:
                ub.answer_callback_query(c.id, "❌ Ошибка!", show_alert=True)
        @ub.message_handler(func=lambda m: True)
        def handle_message(m):
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT auto_reply_always, auto_reply_text FROM user_bots WHERE bot_token=?", (token,))
            row = c.fetchone()
            if row and row[0] == 1 and row[1]:
                ub.reply_to(m, row[1])
                conn.close()
                return
            c.execute("SELECT operator_id FROM bot_operators WHERE bot_token=? LIMIT 1", (token,))
            op = c.fetchone()
            conn.close()
            if op:
                op_id = op[0]
                forward_text = f"📩 *Новое сообщение*\nОт: @{m.from_user.username or m.from_user.first_name}\n\n{m.text}"
                bot.send_message(op_id, forward_text, parse_mode='Markdown')
                ub.reply_to(m, "✅ Сообщение отправлено оператору!")
            else:
                ub.reply_to(m, "❌ Нет свободных операторов")
        try:
            ub.infinity_polling(timeout=60)
        except:
            pass
    threading.Thread(target=run, daemon=True).start()

# ==================== ЗАПУСК ====================
if __name__ == "__main__":
    print("=" * 50)
    print("🤖 VanillaGram - Конструктор ботов (ФИНАЛ)")
    print("=" * 50)
    print(f"📁 Папка с media: {MEDIA_DIR}")
    print("   Положи туда menu.jpg для красивого старта")
    print(f"📢 Канал: {CHANNEL_LINK}")
    print(f"👑 Админ ID: {ADMIN_ID}")
    print("=" * 50)
    print("✅ Функции:")
    print("   • Безлимит операторов")
    print("   • Теги операторов")
    print("   • Автоответчик")
    print("   • Рассылка")
    print("   • Платежи Stars")
    print("   • Админ панель")
    print("=" * 50)
    bot.infinity_polling(timeout=60)