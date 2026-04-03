import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice, PreCheckoutQuery
import sqlite3
import json
import threading
import time
import os
import requests
import re
from datetime import datetime, timedelta

# ==================== КОНФИГ ====================
BOT_TOKEN = "8789730707:AAFviuMjcPpnZeGIgY_KoduvUCaGngEowTA"
ADMIN_ID = 6747528307  # ТВОЙ ID
CHANNEL_LINK = "https://t.me/VanillaGram"

# Бесплатная нейросеть
OPENROUTER_API_KEY = "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"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

PRICE_COPYRIGHT = 100
PRICE_AI_PROMPT = 50
PRICE_PREMIUM_BOT = 350

DB_PATH = "vanilla_gram.db"
MEDIA_DIR = "media"
os.makedirs(MEDIA_DIR, exist_ok=True)

# ==================== БАЗА ДАННЫХ (СОЗДАЁТСЯ ПЕРВОЙ) ====================
print("🔄 Создание базы данных...")
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
c = conn.cursor()

# Таблица пользователей
c.execute('''CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    reg_date TIMESTAMP
)''')

# Таблица ботов пользователей
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
    total_users INTEGER DEFAULT 0
)''')

# Добавляем недостающие колонки (для совместимости)
for col in ['auto_reply_always', 'auto_reply_text', 'ai_enabled', 'ai_prompt', 'total_messages', 'total_users']:
    try:
        c.execute(f"ALTER TABLE user_bots ADD COLUMN {col}")
    except:
        pass

# Операторы
c.execute('''CREATE TABLE IF NOT EXISTS bot_operators (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bot_token TEXT,
    operator_id INTEGER,
    tag TEXT,
    added_at TIMESTAMP
)''')

# Теги
c.execute('''CREATE TABLE IF NOT EXISTS bot_tags (
    bot_token TEXT,
    tag_name TEXT,
    PRIMARY KEY (bot_token, tag_name)
)''')

# Подписчики рассылки
c.execute('''CREATE TABLE IF NOT EXISTS newsletter_subs (
    bot_token TEXT,
    user_id INTEGER,
    PRIMARY KEY (bot_token, user_id)
)''')

# Платежи
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

# Состояния пользователей
c.execute('''CREATE TABLE IF NOT EXISTS user_states (
    user_id INTEGER PRIMARY KEY,
    state TEXT,
    data TEXT
)''')

# Статистика диалогов
c.execute('''CREATE TABLE IF NOT EXISTS bot_stats (
    bot_token TEXT,
    user_id INTEGER,
    messages_count INTEGER DEFAULT 0,
    last_activity TIMESTAMP,
    PRIMARY KEY (bot_token, user_id)
)''')

# Настройки конструктора
c.execute('''CREATE TABLE IF NOT EXISTS constructor_settings (
    key TEXT PRIMARY KEY,
    value TEXT
)''')
c.execute("INSERT OR IGNORE INTO constructor_settings (key, value) VALUES ('welcome_text', '🌟 *ДОБРО ПОЖАЛОВАТЬ В VANILLAGRAM!* 🌟\n\nБесплатный конструктор Telegram ботов\n▫️ Безлимит операторов\n▫️ Теги\n▫️ Нейросеть (бесплатно)\n▫️ Рассылка\n▫️ Топ ботов\n\nИспользуй команды ниже:')")
conn.commit()
print("✅ База данных создана")

# ==================== СОЗДАНИЕ БОТА ====================
print("🔄 Запуск бота...")
bot = telebot.TeleBot(BOT_TOKEN)

# Установка команд
try:
    bot.set_my_commands([
        telebot.types.BotCommand("/start", "Главное меню"),
        telebot.types.BotCommand("/addbot", "Добавить бота"),
        telebot.types.BotCommand("/mybot", "Мои боты"),
        telebot.types.BotCommand("/admin", "Админ панель"),
        telebot.types.BotCommand("/top", "Топ ботов")
    ])
    print("✅ Команды установлены")
except Exception as e:
    print(f"⚠️ Не удалось установить команды (возможно блокировка API): {e}")

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================
def save_state(user_id, state, data=None):
    c.execute("INSERT OR REPLACE INTO user_states (user_id, state, data) VALUES (?, ?, ?)", 
              (user_id, state, json.dumps(data) if data else None))
    conn.commit()

def get_state(user_id):
    c.execute("SELECT state, data FROM user_states WHERE user_id=?", (user_id,))
    row = c.fetchone()
    return (row[0], json.loads(row[1]) if row and row[1] else None) if row else (None, None)

def clear_state(user_id):
    c.execute("DELETE FROM user_states WHERE user_id=?", (user_id,))
    conn.commit()

def get_main_photo():
    path = os.path.join(MEDIA_DIR, "menu.jpg")
    return open(path, 'rb') if os.path.exists(path) else None

def call_free_ai(user_message, system_prompt="Ты дружелюбный помощник. Отвечай кратко и полезно."):
    try:
        headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": "nousresearch/hermes-3-llama-3.1-405b:free",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            "max_tokens": 300
        }
        resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=30)
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"AI error: {e}")
    return None

# ==================== КЛАВИАТУРЫ ====================
def main_reply_keyboard():
    from telebot.types import ReplyKeyboardMarkup, KeyboardButton
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(KeyboardButton("/addbot"), KeyboardButton("/mybot"))
    kb.add(KeyboardButton("/admin"), KeyboardButton("/top"))
    return kb

def my_bots_keyboard(user_id, page=0):
    items_per_page = 5
    c.execute("SELECT bot_token, bot_username FROM user_bots WHERE user_id=? AND is_active=1", (user_id,))
    bots = c.fetchall()
    total = len(bots)
    start = page * items_per_page
    end = start + items_per_page
    page_bots = bots[start:end]
    
    kb = InlineKeyboardMarkup(row_width=1)
    for token, username in page_bots:
        kb.add(InlineKeyboardButton(f"🤖 @{username}", callback_data=f"edit_{token}"))
    
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("◀️ НАЗАД", callback_data=f"mybots_page_{page-1}"))
    if end < total:
        nav_buttons.append(InlineKeyboardButton("ВПЕРЕД ▶️", callback_data=f"mybots_page_{page+1}"))
    if nav_buttons:
        kb.row(*nav_buttons)
    kb.add(InlineKeyboardButton("🔙 ГЛАВНОЕ МЕНЮ", callback_data="back_start"))
    return kb, total, page

def bot_settings_keyboard(bot_token):
    c.execute("SELECT bot_username, welcome_text, has_copyright, require_sub, welcome_photo, auto_reply_always, auto_reply_text, ai_enabled FROM user_bots WHERE bot_token=?", (bot_token,))
    row = c.fetchone()
    if not row:
        return None
    username, welcome, copyright, req_sub, photo, auto_reply, auto_text, ai_enabled = row
    c.execute("SELECT COUNT(*) FROM bot_operators WHERE bot_token=?", (bot_token,))
    op_count = c.fetchone()[0]
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("📝 ПРИВЕТСТВИЕ", callback_data=f"welcome_{bot_token}"))
    kb.add(InlineKeyboardButton("🖼 ФОТО", callback_data=f"photo_{bot_token}"))
    kb.add(InlineKeyboardButton("👥 ОПЕРАТОРЫ", callback_data=f"operators_{bot_token}"))
    kb.add(InlineKeyboardButton("🏷 ТЕГИ", callback_data=f"tags_{bot_token}"))
    kb.add(InlineKeyboardButton("🔒 ПОДПИСКА", callback_data=f"subscribe_{bot_token}"))
    kb.add(InlineKeyboardButton("🤖 НЕЙРОСЕТЬ", callback_data=f"ai_{bot_token}"))
    kb.add(InlineKeyboardButton("⚙️ АВТООТВЕТЧИК", callback_data=f"autoreply_{bot_token}"))
    if copyright:
        kb.add(InlineKeyboardButton("✨ УБРАТЬ КОПИРАЙТ (100⭐)", callback_data=f"copyright_{bot_token}"))
    kb.add(InlineKeyboardButton("🔙 НАЗАД", callback_data="my_bots"))
    status = f"📷 Фото: {'✅' if photo else '❌'}\n🔒 Подписка: {'✅' if req_sub else '❌'}\n© Копирайт: {'✅' if copyright else '❌'}\n👥 Операторы: {op_count}\n🤖 Нейросеть: {'✅' if ai_enabled else '❌'}\n⚙️ Автоответ: {'✅' if auto_reply else '❌'}"
    return kb, status, username

def admin_keyboard():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("📊 СТАТИСТИКА", callback_data="admin_stats"))
    kb.add(InlineKeyboardButton("✏️ ИЗМЕНИТЬ ПРИВЕТСТВИЕ", callback_data="admin_edit_welcome"))
    kb.add(InlineKeyboardButton("📢 РАССЫЛКА", callback_data="admin_mailing"))
    kb.add(InlineKeyboardButton("🗑 УДАЛИТЬ КОПИРАЙТ", callback_data="admin_remove_copyright"))
    kb.add(InlineKeyboardButton("🔙 НАЗАД", callback_data="back_start"))
    return kb

# ==================== ОБРАБОТЧИКИ КОМАНД ====================
@bot.message_handler(commands=['start'])
def start(message):
    c.execute("INSERT OR IGNORE INTO users (user_id, username, reg_date) VALUES (?, ?, ?)", 
              (message.from_user.id, message.from_user.username, datetime.now()))
    conn.commit()
    photo = get_main_photo()
    c.execute("SELECT value FROM constructor_settings WHERE key='welcome_text'")
    welcome_text = c.fetchone()[0]
    try:
        if photo:
            bot.send_photo(message.chat.id, photo, caption=welcome_text, reply_markup=main_reply_keyboard(), parse_mode='Markdown')
        else:
            bot.send_message(message.chat.id, welcome_text, reply_markup=main_reply_keyboard(), parse_mode='Markdown')
    except Exception as e:
        print(f"Start error: {e}")

@bot.message_handler(commands=['addbot'])
def addbot_cmd(message):
    save_state(message.from_user.id, "waiting_token")
    bot.send_message(message.chat.id, "🔑 *Введите токен бота от @BotFather*\n\nПример: `1234567890:ABCdefGHIjkl`", parse_mode='Markdown')

@bot.message_handler(commands=['mybot'])
def mybot_cmd(message):
    c.execute("SELECT COUNT(*) FROM user_bots WHERE user_id=? AND is_active=1", (message.from_user.id,))
    count = c.fetchone()[0]
    if count == 0:
        bot.send_message(message.chat.id, "❌ *У вас нет ботов*\n\nДобавьте через /addbot", parse_mode='Markdown')
        return
    kb, total, page = my_bots_keyboard(message.from_user.id, 0)
    bot.send_message(message.chat.id, f"🎮 *ТВОИ БОТЫ* (стр. {page+1}/{(total+4)//5})", reply_markup=kb, parse_mode='Markdown')

@bot.message_handler(commands=['admin'])
def admin_cmd(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "❌ Нет доступа")
        return
    bot.send_message(message.chat.id, "🔐 *АДМИН ПАНЕЛЬ*", reply_markup=admin_keyboard(), parse_mode='Markdown')

@bot.message_handler(commands=['top'])
def top_cmd(message):
    c.execute("SELECT bot_username, total_messages, total_users FROM user_bots ORDER BY total_messages DESC LIMIT 10")
    top = c.fetchall()
    if not top:
        text = "🏆 *ТОП БОТОВ*\n\nПока нет данных"
    else:
        lines = []
        for i, (username, msgs, users) in enumerate(top, 1):
            lines.append(f"{i}. @{username} — 📨 {msgs} сообщ., 👥 {users} польз.")
        text = "🏆 *ТОП БОТОВ ПО АКТИВНОСТИ*\n\n" + "\n".join(lines)
    bot.send_message(message.chat.id, text, parse_mode='Markdown')

# ==================== ОБРАБОТЧИК СООБЩЕНИЙ (СОСТОЯНИЯ) ====================
@bot.message_handler(func=lambda m: True)
def handle_all_messages(message):
    user_id = message.from_user.id
    state, data = get_state(user_id)
    text = message.text.strip()

    if state == "waiting_token":
        token = text
        try:
            test_bot = telebot.TeleBot(token)
            me = test_bot.get_me()
            c.execute('''INSERT INTO user_bots 
                (user_id, bot_token, bot_username, welcome_text, created_at, total_messages, total_users)
                VALUES (?, ?, ?, ?, ?, 0, 0)''',
                (user_id, token, me.username, f"Добро пожаловать! Этот бот создан с помощью @VanillaGramBot", datetime.now()))
            c.execute("INSERT INTO bot_operators (bot_token, operator_id, added_at) VALUES (?, ?, ?)", (token, user_id, datetime.now()))
            conn.commit()
            clear_state(user_id)
            bot.send_message(message.chat.id, f"✅ *Бот @{me.username} успешно создан!*\n\nУправляй им через /mybot", parse_mode='Markdown')
            threading.Thread(target=run_user_bot, args=(token, me.username, user_id), daemon=True).start()
        except Exception as e:
            bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")
        return

    if state == "waiting_welcome":
        c.execute("UPDATE user_bots SET welcome_text=? WHERE bot_token=?", (text, data["bot_token"]))
        conn.commit()
        clear_state(user_id)
        bot.send_message(message.chat.id, "✅ Приветствие обновлено!")
        return
    if state == "waiting_photo":
        bot.reply_to(message, "❌ Отправь фото, а не текст")
        return
    if state == "waiting_op_id":
        try:
            op_id = int(text)
            c.execute("INSERT OR IGNORE INTO bot_operators (bot_token, operator_id, added_at) VALUES (?, ?, ?)", 
                      (data["bot_token"], op_id, datetime.now()))
            conn.commit()
            try:
                bot.send_message(op_id, "🎉 Вы стали оператором бота!")
            except:
                pass
            bot.reply_to(message, "✅ Оператор добавлен")
        except:
            bot.reply_to(message, "❌ Введите числовой ID")
        clear_state(user_id)
        return
    if state == "waiting_tag_name":
        c.execute("INSERT OR IGNORE INTO bot_tags (bot_token, tag_name) VALUES (?, ?)", (data["bot_token"], text))
        conn.commit()
        clear_state(user_id)
        bot.reply_to(message, f"✅ Тег '{text}' создан")
        return
    if state == "waiting_channel":
        channel = text.replace("@", "")
        c.execute("UPDATE user_bots SET require_sub=1, required_channel=? WHERE bot_token=?", (channel, data["bot_token"]))
        conn.commit()
        clear_state(user_id)
        bot.send_message(message.chat.id, f"✅ Подписка настроена на @{channel}")
        return
    if state == "waiting_autoreply_text":
        if text.lower() == "отключить":
            c.execute("UPDATE user_bots SET auto_reply_always=0, auto_reply_text=NULL WHERE bot_token=?", (data["bot_token"],))
            bot.reply_to(message, "✅ Автоответчик выключен")
        else:
            c.execute("UPDATE user_bots SET auto_reply_always=1, auto_reply_text=? WHERE bot_token=?", (text, data["bot_token"]))
            bot.reply_to(message, f"✅ Автоответчик установлен:\n{text}")
        conn.commit()
        clear_state(user_id)
        return

    # Админские состояния
    if user_id == ADMIN_ID:
        if state == "admin_waiting_welcome":
            c.execute("UPDATE constructor_settings SET value=? WHERE key='welcome_text'", (text,))
            conn.commit()
            clear_state(user_id)
            bot.send_message(message.chat.id, "✅ Приветствие конструктора обновлено")
            return
        if state == "admin_waiting_mailing":
            c.execute("SELECT user_id FROM users")
            users = c.fetchall()
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
        if state == "admin_waiting_bot_id":
            if text.isdigit():
                c.execute("SELECT bot_token, bot_username FROM user_bots WHERE id=?", (int(text),))
            else:
                uname = text.replace("@", "")
                c.execute("SELECT bot_token, bot_username FROM user_bots WHERE bot_username=?", (uname,))
            row = c.fetchone()
            if row:
                c.execute("UPDATE user_bots SET has_copyright=0 WHERE bot_token=?", (row[0],))
                conn.commit()
                bot.send_message(message.chat.id, f"✅ Копирайт удалён у @{row[1]}")
            else:
                bot.send_message(message.chat.id, "❌ Бот не найден")
            clear_state(user_id)
            return

@bot.message_handler(content_types=['photo'])
def photo_handler(message):
    state, data = get_state(message.from_user.id)
    if state == "waiting_photo":
        photo_id = message.photo[-1].file_id
        c.execute("UPDATE user_bots SET welcome_photo=? WHERE bot_token=?", (photo_id, data["bot_token"]))
        conn.commit()
        clear_state(message.from_user.id)
        bot.reply_to(message, "✅ Фото установлено")

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

    if data.startswith("mybots_page_"):
        page = int(data.split("_")[-1])
        kb, total, _ = my_bots_keyboard(user_id, page)
        bot.edit_message_text(f"🎮 *ТВОИ БОТЫ* (стр. {page+1}/{(total+4)//5})", chat_id, msg_id, reply_markup=kb, parse_mode='Markdown')
        return

    if user_id == ADMIN_ID:
        if data == "admin_stats":
            c.execute("SELECT COUNT(*) FROM users")
            users_cnt = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM user_bots")
            bots_cnt = c.fetchone()[0]
            c.execute("SELECT SUM(total_messages) FROM user_bots")
            total_msgs = c.fetchone()[0] or 0
            bot.edit_message_text(f"📊 *СТАТИСТИКА*\n👥 Пользователей: {users_cnt}\n🤖 Ботов: {bots_cnt}\n💬 Всего сообщений: {total_msgs}", chat_id, msg_id, parse_mode='Markdown')
            return
        if data == "admin_edit_welcome":
            save_state(user_id, "admin_waiting_welcome")
            bot.edit_message_text("✏️ Отправь новый текст приветствия", chat_id, msg_id)
            return
        if data == "admin_mailing":
            save_state(user_id, "admin_waiting_mailing")
            bot.edit_message_text("📢 Отправь текст рассылки", chat_id, msg_id)
            return
        if data == "admin_remove_copyright":
            save_state(user_id, "admin_waiting_bot_id")
            bot.edit_message_text("Введи ID или username бота", chat_id, msg_id)
            return

    if data.startswith("edit_"):
        bot_token = data[5:]
        res = bot_settings_keyboard(bot_token)
        if res:
            kb, status, username = res
            bot.edit_message_text(f"⚙️ *@{username}*\n{status}", chat_id, msg_id, reply_markup=kb, parse_mode='Markdown')
        return
    if data.startswith("welcome_"):
        bot_token = data[8:]
        save_state(user_id, "waiting_welcome", {"bot_token": bot_token})
        bot.edit_message_text("📝 Отправь новый текст приветствия", chat_id, msg_id)
        return
    if data.startswith("photo_"):
        bot_token = data[6:]
        save_state(user_id, "waiting_photo", {"bot_token": bot_token})
        bot.edit_message_text("🖼 Отправь фото", chat_id, msg_id)
        return
    if data.startswith("subscribe_"):
        bot_token = data[10:]
        save_state(user_id, "waiting_channel", {"bot_token": bot_token})
        bot.edit_message_text("📢 Введи @username канала", chat_id, msg_id)
        return
    if data.startswith("autoreply_"):
        bot_token = data[10:]
        save_state(user_id, "waiting_autoreply_text", {"bot_token": bot_token})
        bot.edit_message_text("🤖 Введи текст автоответчика (или 'отключить')", chat_id, msg_id)
        return
    if data.startswith("ai_"):
        bot_token = data[3:]
        c.execute("SELECT ai_enabled, ai_prompt FROM user_bots WHERE bot_token=?", (bot_token,))
        row = c.fetchone()
        if row:
            enabled, prompt = row
            new_status = not enabled
            c.execute("UPDATE user_bots SET ai_enabled=? WHERE bot_token=?", (new_status, bot_token))
            if not prompt:
                c.execute("UPDATE user_bots SET ai_prompt='Ты дружелюбный помощник. Отвечай кратко и полезно.' WHERE bot_token=?", (bot_token,))
            conn.commit()
            bot.answer_callback_query(call.id, f"Нейросеть {'включена' if new_status else 'выключена'}")
            callback_query(call)
        return
    if data.startswith("operators_"):
        bot_token = data[10:]
        c.execute("SELECT id, operator_id, tag FROM bot_operators WHERE bot_token=?", (bot_token,))
        ops = c.fetchall()
        c.execute("SELECT tag_name FROM bot_tags WHERE bot_token=?", (bot_token,))
        tags = c.fetchall()
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(InlineKeyboardButton("➕ Добавить оператора", callback_data=f"add_op_{bot_token}"))
        if tags:
            kb.add(InlineKeyboardButton("🏷 Назначить тег", callback_data=f"assign_tag_{bot_token}"))
        kb.add(InlineKeyboardButton("🔙 Назад", callback_data=f"edit_{bot_token}"))
        ops_text = "\n".join([f"• {op[1]} {op[2] or ''}" for op in ops]) if ops else "Нет"
        bot.edit_message_text(f"👥 *Операторы*\n{ops_text}\nТеги: {', '.join(t[0] for t in tags)}", chat_id, msg_id, reply_markup=kb, parse_mode='Markdown')
        return
    if data.startswith("add_op_"):
        bot_token = data[7:]
        save_state(user_id, "waiting_op_id", {"bot_token": bot_token})
        bot.edit_message_text("📱 Введи ID оператора (узнай у @userinfobot)", chat_id, msg_id)
        return
    if data.startswith("tags_"):
        bot_token = data[5:]
        c.execute("SELECT tag_name FROM bot_tags WHERE bot_token=?", (bot_token,))
        tags = c.fetchall()
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(InlineKeyboardButton("➕ Создать тег", callback_data=f"create_tag_{bot_token}"))
        for tag in tags:
            kb.add(InlineKeyboardButton(f"🏷 {tag[0]} ❌", callback_data=f"del_tag_{bot_token}_{tag[0]}"))
        kb.add(InlineKeyboardButton("🔙 Назад", callback_data=f"edit_{bot_token}"))
        bot.edit_message_text(f"🏷 *Теги*\n{chr(10).join([t[0] for t in tags]) or 'Нет тегов'}", chat_id, msg_id, reply_markup=kb, parse_mode='Markdown')
        return
    if data.startswith("create_tag_"):
        bot_token = data[11:]
        save_state(user_id, "waiting_tag_name", {"bot_token": bot_token})
        bot.edit_message_text("📝 Введи название тега", chat_id, msg_id)
        return
    if data.startswith("del_tag_"):
        parts = data.split("_")
        bot_token = parts[2]
        tag_name = "_".join(parts[3:])
        c.execute("DELETE FROM bot_tags WHERE bot_token=? AND tag_name=?", (bot_token, tag_name))
        conn.commit()
        bot.answer_callback_query(call.id, f"Тег {tag_name} удалён")
        callback_query(call)
        return
    if data.startswith("assign_tag_"):
        bot_token = data[11:]
        c.execute("SELECT id, operator_id FROM bot_operators WHERE bot_token=?", (bot_token,))
        ops = c.fetchall()
        if not ops:
            bot.answer_callback_query(call.id, "Нет операторов")
            return
        kb = InlineKeyboardMarkup(row_width=1)
        for op_id, op_user in ops:
            kb.add(InlineKeyboardButton(f"👤 {op_user}", callback_data=f"tag_op_{bot_token}_{op_id}"))
        bot.edit_message_text("Выбери оператора", chat_id, msg_id, reply_markup=kb)
        return
    if data.startswith("tag_op_"):
        parts = data.split("_")
        bot_token = parts[2]
        op_db_id = parts[3]
        c.execute("SELECT tag_name FROM bot_tags WHERE bot_token=?", (bot_token,))
        tags = c.fetchall()
        if not tags:
            bot.answer_callback_query(call.id, "Нет тегов")
            return
        kb = InlineKeyboardMarkup(row_width=1)
        for tag in tags:
            kb.add(InlineKeyboardButton(f"🏷 {tag[0]}", callback_data=f"set_tag_{bot_token}_{op_db_id}_{tag[0]}"))
        bot.edit_message_text("Выбери тег", chat_id, msg_id, reply_markup=kb)
        return
    if data.startswith("set_tag_"):
        parts = data.split("_")
        bot_token = parts[2]
        op_db_id = parts[3]
        tag_name = "_".join(parts[4:])
        c.execute("UPDATE bot_operators SET tag=? WHERE id=?", (tag_name, op_db_id))
        conn.commit()
        bot.answer_callback_query(call.id, f"Тег {tag_name} назначен")
        callback_query(call)
        return
    if data.startswith("copyright_"):
        bot_token = data[10:]
        payment_id = f"copy_{user_id}_{int(time.time())}"
        c.execute("INSERT INTO payments (user_id, amount, type, status, payment_id, bot_token, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                  (user_id, PRICE_COPYRIGHT, "copyright", "pending", payment_id, bot_token, datetime.now()))
        conn.commit()
        kb = InlineKeyboardMarkup().add(InlineKeyboardButton("💎 Оплатить 100⭐", callback_data=f"pay_copy_{payment_id}"))
        bot.edit_message_text("✨ Удаление копирайта 100⭐", chat_id, msg_id, reply_markup=kb)
        return
    if data.startswith("pay_copy_"):
        payment_id = data[9:]
        bot.send_invoice(chat_id, title="Удаление копирайта", description="Убрать надпись о создателе", invoice_payload=payment_id, provider_token="", currency="XTR", prices=[LabeledPrice(label="Удаление", amount=PRICE_COPYRIGHT)], start_parameter="remove_copyright")
        return

    bot.answer_callback_query(call.id, "Функция в разработке")

# ==================== ПЛАТЕЖИ ====================
@bot.pre_checkout_query_handler(func=lambda q: True)
def pre_checkout(q):
    bot.answer_pre_checkout_query(q.id, ok=True)

@bot.message_handler(content_types=['successful_payment'])
def on_successful_payment(message):
    payment_id = message.successful_payment.invoice_payload
    c.execute("SELECT type, bot_token FROM payments WHERE payment_id=?", (payment_id,))
    row = c.fetchone()
    if row:
        ptype, bot_token = row
        c.execute("UPDATE payments SET status='completed' WHERE payment_id=?", (payment_id,))
        if ptype == "copyright":
            c.execute("UPDATE user_bots SET has_copyright=0 WHERE bot_token=?", (bot_token,))
            bot.send_message(message.chat.id, "✅ Копирайт удалён!")
        conn.commit()

# ==================== ЗАПУСК БОТА ПОЛЬЗОВАТЕЛЯ ====================
def run_user_bot(token, username, owner_id):
    def worker():
        ub = telebot.TeleBot(token)
        @ub.message_handler(commands=['start'])
        def user_start(m):
            c.execute("SELECT welcome_text, welcome_photo, has_copyright, require_sub, required_channel, auto_reply_always, auto_reply_text, ai_enabled, ai_prompt FROM user_bots WHERE bot_token=?", (token,))
            row = c.fetchone()
            c.execute("INSERT OR IGNORE INTO newsletter_subs (bot_token, user_id) VALUES (?, ?)", (token, m.from_user.id))
            conn.commit()
            if row:
                text, photo, copyright, req_sub, channel, auto_always, auto_text, ai_enabled, ai_prompt = row
                if req_sub and channel:
                    try:
                        member = ub.get_chat_member(f"@{channel}", m.from_user.id)
                        if member.status in ['left', 'kicked']:
                            kb = InlineKeyboardMarkup().add(InlineKeyboardButton("📢 Подписаться", url=f"https://t.me/{channel}"), InlineKeyboardButton("✅ Проверить", callback_data="check_sub"))
                            ub.send_message(m.chat.id, f"🔒 Подпишись на @{channel}", reply_markup=kb)
                            return
                    except:
                        pass
                final_text = text
                if copyright:
                    final_text += f"\n\n✨ Создано с помощью @VanillaGramBot"
                if photo:
                    ub.send_photo(m.chat.id, photo, caption=final_text, parse_mode='Markdown')
                else:
                    ub.send_message(m.chat.id, final_text, parse_mode='Markdown')
        @ub.callback_query_handler(func=lambda c: c.data == "check_sub")
        def check_sub(c):
            c.execute("SELECT required_channel FROM user_bots WHERE bot_token=?", (token,))
            channel = c.fetchone()[0]
            try:
                member = ub.get_chat_member(f"@{channel}", c.from_user.id)
                if member.status in ['member', 'administrator', 'creator']:
                    ub.answer_callback_query(c.id, "✅ Спасибо!")
                    ub.delete_message(c.message.chat.id, c.message.message_id)
                    user_start(c.message)
                else:
                    ub.answer_callback_query(c.id, "❌ Не подписан", show_alert=True)
            except:
                ub.answer_callback_query(c.id, "❌ Ошибка", show_alert=True)
        @ub.message_handler(func=lambda m: True)
        def handle_msg(m):
            c.execute("INSERT OR IGNORE INTO bot_stats (bot_token, user_id, messages_count, last_activity) VALUES (?, ?, 0, ?)", (token, m.from_user.id, datetime.now()))
            c.execute("UPDATE bot_stats SET messages_count = messages_count + 1, last_activity = ? WHERE bot_token=? AND user_id=?", (datetime.now(), token, m.from_user.id))
            c.execute("UPDATE user_bots SET total_messages = total_messages + 1 WHERE bot_token=?", (token,))
            c.execute("SELECT COUNT(DISTINCT user_id) FROM bot_stats WHERE bot_token=?", (token,))
            unique_users = c.fetchone()[0]
            c.execute("UPDATE user_bots SET total_users = ? WHERE bot_token=?", (unique_users, token))
            conn.commit()
            c.execute("SELECT auto_reply_always, auto_reply_text, ai_enabled, ai_prompt FROM user_bots WHERE bot_token=?", (token,))
            row = c.fetchone()
            if row:
                auto_always, auto_text, ai_enabled, ai_prompt = row
                if auto_always and auto_text:
                    ub.reply_to(m, auto_text)
                    return
                if ai_enabled:
                    ai_answer = call_free_ai(m.text, ai_prompt or "Ты дружелюбный помощник.")
                    if ai_answer:
                        ub.reply_to(m, ai_answer)
                        return
            c.execute("SELECT operator_id FROM bot_operators WHERE bot_token=? LIMIT 1", (token,))
            op = c.fetchone()
            if op:
                bot.send_message(op[0], f"📩 *Новое сообщение от @{m.from_user.username or m.from_user.first_name}*\n\n{m.text}", parse_mode='Markdown')
                ub.reply_to(m, "✅ Сообщение отправлено оператору")
            else:
                ub.reply_to(m, "❌ Нет операторов")
        try:
            ub.infinity_polling(timeout=60)
        except:
            pass
    threading.Thread(target=worker, daemon=True).start()

# ==================== ЗАПУСК ГЛАВНОГО БОТА ====================
if __name__ == "__main__":
    print("🤖 VanillaGram запущен")
    print(f"Админ ID: {ADMIN_ID}")
    print(f"Папка media: {MEDIA_DIR}")
    print("=" * 50)
    print("Главное меню — через команды /addbot, /mybot, /admin, /top")
    print("Все настройки — через инлайн-кнопки")
    print("=" * 50)
    print("Если бот не отвечает, возможно блокировка Telegram API.")
    print("Включи VPN и перезапусти бота.")
    print("=" * 50)
    
    while True:
        try:
            bot.infinity_polling(timeout=60)
        except Exception as e:
            print(f"Ошибка: {e}. Переподключение через 10 секунд...")
            time.sleep(10)