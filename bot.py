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
CHANNEL_LINK = "https://t.me/VanillaGram"
ADMIN_ID = 6747528307

OPENROUTER_API_KEY = "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"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

PRICE_PREMIUM_BOT = 350
PRICE_AI_PROMPT = 50
PRICE_COPYRIGHT = 100

DB_PATH = "vanilla_gram.db"
MEDIA_DIR = "media"
os.makedirs(MEDIA_DIR, exist_ok=True)

# ==================== БАЗА ДАННЫХ ====================
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
c = conn.cursor()

c.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, reg_date TIMESTAMP)''')
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
    bot_status INTEGER DEFAULT 1
)''')
c.execute('''CREATE TABLE IF NOT EXISTS bot_operators (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bot_token TEXT,
    operator_id INTEGER,
    tag TEXT,
    added_at TIMESTAMP
)''')
c.execute('''CREATE TABLE IF NOT EXISTS bot_tags (bot_token TEXT, tag_name TEXT, PRIMARY KEY (bot_token, tag_name))''')
c.execute('''CREATE TABLE IF NOT EXISTS bot_menus (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bot_token TEXT,
    menu_id TEXT,
    menu_name TEXT,
    text TEXT,
    buttons TEXT,
    parent_menu TEXT,
    created_at TIMESTAMP
)''')
c.execute('''CREATE TABLE IF NOT EXISTS newsletter_subs (bot_token TEXT, user_id INTEGER, PRIMARY KEY (bot_token, user_id))''')
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
c.execute('''CREATE TABLE IF NOT EXISTS user_states (user_id INTEGER PRIMARY KEY, state TEXT, data TEXT)''')
c.execute('''CREATE TABLE IF NOT EXISTS constructor_settings (key TEXT PRIMARY KEY, value TEXT)''')
c.execute("INSERT OR IGNORE INTO constructor_settings (key, value) VALUES ('welcome_text', '🌟 *ДОБРО ПОЖАЛОВАТЬ В VANILLAGRAM!* 🌟\n\nБесплатный конструктор Telegram ботов\n\n*Выбери действие:*')")
conn.commit()

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================
def save_state(user_id, state, data=None):
    c.execute("INSERT OR REPLACE INTO user_states (user_id, state, data) VALUES (?, ?, ?)", (user_id, state, json.dumps(data) if data else None))
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

def get_constructor_welcome():
    c.execute("SELECT value FROM constructor_settings WHERE key='welcome_text'")
    row = c.fetchone()
    return row[0] if row else "🌟 Добро пожаловать!"

def call_free_ai(user_message, system_prompt="Ты дружелюбный помощник. Отвечай кратко и полезно."):
    try:
        headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": "nousresearch/hermes-3-llama-3.1-405b:free",
            "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_message}],
            "max_tokens": 300
        }
        resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=30)
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"]
        return None
    except:
        return None

# ==================== ЗАПУСК/ОСТАНОВКА БОТА ПОЛЬЗОВАТЕЛЯ ====================
user_bots_threads = {}
user_bots_instances = {}

def stop_user_bot(bot_token):
    """Остановка бота пользователя"""
    if bot_token in user_bots_threads:
        try:
            if bot_token in user_bots_instances:
                user_bots_instances[bot_token].stop_polling()
            user_bots_threads[bot_token].join(timeout=1)
        except:
            pass
        del user_bots_threads[bot_token]
        if bot_token in user_bots_instances:
            del user_bots_instances[bot_token]
    c.execute("UPDATE user_bots SET bot_status=0 WHERE bot_token=?", (bot_token,))
    conn.commit()
    return True

def start_user_bot(bot_token, bot_username, owner_id):
    """Запуск бота пользователя с поддержкой меню и кнопок"""
    if bot_token in user_bots_threads:
        stop_user_bot(bot_token)
    
    def run():
        try:
            ub = telebot.TeleBot(bot_token)
            user_bots_instances[bot_token] = ub
            
            # Загрузка меню из БД
            def load_menu(menu_id="main"):
                c.execute("SELECT text, photo_id, buttons FROM bot_menus WHERE bot_token=? AND menu_id=?", (bot_token, menu_id))
                row = c.fetchone()
                if row:
                    text, photo_id, buttons_json = row
                    buttons = json.loads(buttons_json) if buttons_json else []
                    kb = InlineKeyboardMarkup(row_width=2)
                    for btn in buttons:
                        if btn['type'] == 'url':
                            kb.add(InlineKeyboardButton(btn['text'], url=btn['target']))
                        elif btn['type'] == 'callback':
                            kb.add(InlineKeyboardButton(btn['text'], callback_data=f"menu_{btn['target']}"))
                        elif btn['type'] == 'channel':
                            kb.add(InlineKeyboardButton(btn['text'], url=f"https://t.me/{btn['target'].replace('@', '')}"))
                    return text, photo_id, kb
                return None, None, None
            
            @ub.message_handler(commands=['start'])
            def user_start(m):
                # Проверка подписки
                c.execute("SELECT require_sub, required_channel FROM user_bots WHERE bot_token=?", (bot_token,))
                req_sub, channel = c.fetchone()
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
                
                # Подписка на рассылку
                c.execute("INSERT OR IGNORE INTO newsletter_subs (bot_token, user_id) VALUES (?, ?)", (bot_token, m.from_user.id))
                conn.commit()
                
                # Загрузка главного меню
                text, photo_id, kb = load_menu("main")
                if text is None:
                    c.execute("SELECT welcome_text, welcome_photo, has_copyright FROM user_bots WHERE bot_token=?", (bot_token,))
                    row = c.fetchone()
                    if row:
                        text, photo, copyright = row
                        if copyright:
                            text += f"\n\n✨ *Создано с помощью @VanillaGramBot*"
                        if photo:
                            ub.send_photo(m.chat.id, photo, caption=text, parse_mode='Markdown')
                        else:
                            ub.send_message(m.chat.id, text, parse_mode='Markdown')
                    else:
                        ub.send_message(m.chat.id, "Добро пожаловать!", parse_mode='Markdown')
                else:
                    if photo_id:
                        ub.send_photo(m.chat.id, photo_id, caption=text, reply_markup=kb, parse_mode='Markdown')
                    else:
                        ub.send_message(m.chat.id, text, reply_markup=kb, parse_mode='Markdown')
            
            @ub.callback_query_handler(func=lambda call: call.data.startswith("menu_"))
            def menu_callback(call):
                menu_id = call.data.replace("menu_", "")
                text, photo_id, kb = load_menu(menu_id)
                if text:
                    if photo_id:
                        ub.edit_message_media(telebot.types.InputMediaPhoto(photo_id, caption=text, parse_mode='Markdown'), call.message.chat.id, call.message.message_id, reply_markup=kb)
                    else:
                        ub.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=kb, parse_mode='Markdown')
                ub.answer_callback_query(call.id)
            
            @ub.callback_query_handler(func=lambda call: call.data == "check_sub")
            def check_sub(c):
                c.execute("SELECT required_channel FROM user_bots WHERE bot_token=?", (bot_token,))
                channel = c.fetchone()[0]
                try:
                    member = ub.get_chat_member(f"@{channel}", c.from_user.id)
                    if member.status in ['member', 'administrator', 'creator']:
                        ub.answer_callback_query(c.id, "✅ Спасибо за подписку!")
                        ub.delete_message(c.message.chat.id, c.message.message_id)
                        user_start(c.message)
                    else:
                        ub.answer_callback_query(c.id, "❌ Ты не подписан!", show_alert=True)
                except:
                    ub.answer_callback_query(c.id, "❌ Ошибка!", show_alert=True)
            
            @ub.message_handler(func=lambda m: True)
            def handle_msg(m):
                # Проверка на автоответ
                c.execute("SELECT auto_reply_always, auto_reply_text, ai_enabled, ai_prompt FROM user_bots WHERE bot_token=?", (bot_token,))
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
                
                # Отправка оператору
                c.execute("SELECT operator_id FROM bot_operators WHERE bot_token=? LIMIT 1", (bot_token,))
                op = c.fetchone()
                if op:
                    bot.send_message(op[0], f"📩 Новое сообщение от @{m.from_user.username or m.from_user.first_name}\nБот: @{bot_username}\n\n{m.text}")
                    ub.reply_to(m, "✅ Сообщение отправлено оператору!")
                else:
                    ub.reply_to(m, "❌ Нет доступных операторов")
            
            ub.infinity_polling(timeout=60)
        except Exception as e:
            logger.error(f"User bot error: {e}")
    
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    user_bots_threads[bot_token] = thread
    c.execute("UPDATE user_bots SET bot_status=1 WHERE bot_token=?", (bot_token,))
    conn.commit()
    return True

# ==================== СОЗДАНИЕ БОТА ====================
bot = telebot.TeleBot(BOT_TOKEN)
bot.set_my_commands([
    telebot.types.BotCommand("/start", "Главное меню"),
    telebot.types.BotCommand("/addbot", "Добавить бота"),
    telebot.types.BotCommand("/mybot", "Мои боты"),
    telebot.types.BotCommand("/admin", "Админ панель")
])

# ==================== КЛАВИАТУРЫ ====================
def main_keyboard():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton("➕ ДОБАВИТЬ БОТА", callback_data="add_bot"), InlineKeyboardButton("🤖 МОИ БОТЫ", callback_data="my_bots"))
    kb.add(InlineKeyboardButton("✨ ПРЕМИУМ БОТ (350⭐)", callback_data="premium_bot"), InlineKeyboardButton("📢 НАШ КАНАЛ", url=CHANNEL_LINK))
    kb.add(InlineKeyboardButton("📖 ПОМОЩЬ", callback_data="help"))
    return kb

def my_bots_keyboard(user_id):
    c.execute("SELECT bot_token, bot_username, bot_status FROM user_bots WHERE user_id=? AND is_active=1", (user_id,))
    bots = c.fetchall()
    kb = InlineKeyboardMarkup(row_width=1)
    for token, username, status in bots:
        status_icon = "🟢" if status else "🔴"
        kb.add(InlineKeyboardButton(f"{status_icon} @{username}", callback_data=f"edit_{token}"))
    kb.add(InlineKeyboardButton("🔙 НАЗАД", callback_data="back_start"))
    return kb

def bot_settings_keyboard(bot_token):
    c.execute("SELECT bot_username, welcome_text, has_copyright, require_sub, welcome_photo, auto_reply_always, auto_reply_text, ai_enabled, bot_status FROM user_bots WHERE bot_token=?", (bot_token,))
    row = c.fetchone()
    c.execute("SELECT COUNT(*) FROM bot_operators WHERE bot_token=?", (bot_token,))
    op_count = c.fetchone()[0]
    if not row: return None
    username, welcome, copyright, req_sub, photo, auto_reply, auto_text, ai_enabled, bot_status = row
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("📝 ПРИВЕТСТВИЕ", callback_data=f"welcome_{bot_token}"))
    kb.add(InlineKeyboardButton("🖼 ФОТО", callback_data=f"photo_{bot_token}"))
    kb.add(InlineKeyboardButton("🔘 МЕНЮ И КНОПКИ", callback_data=f"menus_{bot_token}"))
    kb.add(InlineKeyboardButton("👥 ОПЕРАТОРЫ", callback_data=f"operators_{bot_token}"))
    kb.add(InlineKeyboardButton("🏷 ТЕГИ", callback_data=f"tags_{bot_token}"))
    kb.add(InlineKeyboardButton("🔒 ПОДПИСКА", callback_data=f"subscribe_{bot_token}"))
    kb.add(InlineKeyboardButton("🤖 НЕЙРОСЕТЬ", callback_data=f"ai_{bot_token}"))
    kb.add(InlineKeyboardButton("⚙️ АВТООТВЕТЧИК", callback_data=f"autoreply_{bot_token}"))
    kb.add(InlineKeyboardButton(f"{'⏸ ОСТАНОВИТЬ' if bot_status else '▶️ ЗАПУСТИТЬ'}", callback_data=f"toggle_bot_{bot_token}"))
    if copyright:
        kb.add(InlineKeyboardButton("✨ УБРАТЬ КОПИРАЙТ (100⭐)", callback_data=f"copyright_{bot_token}"))
    kb.add(InlineKeyboardButton("🔙 НАЗАД", callback_data="my_bots"))
    status = f"📷 Фото: {'✅' if photo else '❌'}\n🔒 Подписка: {'✅' if req_sub else '❌'}\n© Копирайт: {'✅' if copyright else '❌'}\n👥 Операторы: {op_count}\n🤖 Нейросеть: {'✅' if ai_enabled else '❌'}\n⚙️ Автоответ: {'✅' if auto_reply else '❌'}\n🟢 Статус: {'Работает' if bot_status else 'Остановлен'}"
    return kb, status, username

def admin_keyboard():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("📊 СТАТИСТИКА", callback_data="admin_stats"))
    kb.add(InlineKeyboardButton("✏️ ИЗМЕНИТЬ ПРИВЕТСТВИЕ", callback_data="admin_edit_welcome"))
    kb.add(InlineKeyboardButton("📢 РАССЫЛКА", callback_data="admin_mailing"))
    kb.add(InlineKeyboardButton("🗑 УДАЛИТЬ КОПИРАЙТ", callback_data="admin_remove_copyright"))
    kb.add(InlineKeyboardButton("🔙 НАЗАД", callback_data="back_start"))
    return kb

# ==================== МЕНЮ ДЛЯ СОЗДАНИЯ КНОПОК ====================
def menus_keyboard(bot_token):
    c.execute("SELECT id, menu_id, menu_name FROM bot_menus WHERE bot_token=?", (bot_token,))
    menus = c.fetchall()
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("➕ СОЗДАТЬ ГЛАВНОЕ МЕНЮ", callback_data=f"create_main_menu_{bot_token}"))
    kb.add(InlineKeyboardButton("➕ СОЗДАТЬ ПОДМЕНЮ", callback_data=f"create_submenu_{bot_token}"))
    for menu in menus:
        kb.add(InlineKeyboardButton(f"📋 {menu[2]}", callback_data=f"edit_menu_{bot_token}_{menu[1]}"))
    kb.add(InlineKeyboardButton("🔙 НАЗАД", callback_data=f"edit_{bot_token}"))
    return kb

def create_menu_keyboard(bot_token, menu_id=None, menu_name=None, text=None, buttons=None):
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("✏️ ТЕКСТ", callback_data=f"menu_text_{bot_token}_{menu_id or 'new'}"))
    kb.add(InlineKeyboardButton("🖼 ФОТО", callback_data=f"menu_photo_{bot_token}_{menu_id or 'new'}"))
    kb.add(InlineKeyboardButton("➕ ДОБАВИТЬ КНОПКУ", callback_data=f"menu_add_btn_{bot_token}_{menu_id or 'new'}"))
    if buttons:
        kb.add(InlineKeyboardButton("🗑 ОЧИСТИТЬ КНОПКИ", callback_data=f"menu_clear_btns_{bot_token}_{menu_id or 'new'}"))
    kb.add(InlineKeyboardButton("💾 СОХРАНИТЬ", callback_data=f"menu_save_{bot_token}_{menu_id or 'new'}"))
    kb.add(InlineKeyboardButton("🔙 НАЗАД", callback_data=f"menus_{bot_token}"))
    return kb

def add_button_keyboard(bot_token, menu_id):
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("🔗 ССЫЛКА (URL)", callback_data=f"btn_url_{bot_token}_{menu_id}"))
    kb.add(InlineKeyboardButton("📢 ПЕРЕХОД В КАНАЛ", callback_data=f"btn_channel_{bot_token}_{menu_id}"))
    kb.add(InlineKeyboardButton("📋 ПЕРЕХОД В МЕНЮ", callback_data=f"btn_menu_{bot_token}_{menu_id}"))
    kb.add(InlineKeyboardButton("🔙 НАЗАД", callback_data=f"edit_menu_{bot_token}_{menu_id}"))
    return kb

# ==================== /start ====================
@bot.message_handler(commands=['start'])
def start(message):
    c.execute("INSERT OR IGNORE INTO users (user_id, username, reg_date) VALUES (?, ?, ?)", (message.from_user.id, message.from_user.username, datetime.now()))
    conn.commit()
    photo = get_main_photo()
    text = get_constructor_welcome()
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
    c.execute("SELECT bot_token, bot_username FROM user_bots WHERE user_id=? AND is_active=1", (message.from_user.id,))
    bots = c.fetchall()
    if not bots:
        bot.send_message(message.chat.id, "❌ *У вас нет ботов*\n\nДобавьте через /addbot", parse_mode='Markdown')
        return
    bot.send_message(message.chat.id, "🎮 *ТВОИ БОТЫ:*", reply_markup=my_bots_keyboard(message.from_user.id), parse_mode='Markdown')

# ==================== /admin ====================
@bot.message_handler(commands=['admin'])
def admin_cmd(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "❌ Нет доступа")
        return
    bot.send_message(message.chat.id, "🔐 *АДМИН ПАНЕЛЬ*", reply_markup=admin_keyboard(), parse_mode='Markdown')

# ==================== ОБРАБОТЧИК СООБЩЕНИЙ ====================
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
            c.execute('''INSERT INTO user_bots (user_id, bot_token, bot_username, welcome_text, created_at, bot_status) VALUES (?, ?, ?, ?, ?, 1)''',
                      (user_id, token, me.username, f"Добро пожаловать! Этот бот создан с помощью @VanillaGramBot", datetime.now()))
            c.execute("INSERT INTO bot_operators (bot_token, operator_id, added_at) VALUES (?, ?, ?)", (token, user_id, datetime.now()))
            conn.commit()
            clear_state(user_id)
            bot.send_message(message.chat.id, f"✅ *Бот @{me.username} добавлен и запущен!*\nИспользуй /mybot для настройки", parse_mode='Markdown')
            start_user_bot(token, me.username, user_id)
        except Exception as e:
            bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")
        return

    if state == "waiting_welcome":
        c.execute("UPDATE user_bots SET welcome_text=? WHERE bot_token=?", (text, data["bot_token"]))
        conn.commit()
        clear_state(user_id)
        bot.send_message(message.chat.id, "✅ Приветствие обновлено!")
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

    if state == "waiting_op_id":
        try:
            op_id = int(text)
            c.execute("INSERT OR IGNORE INTO bot_operators (bot_token, operator_id, added_at) VALUES (?, ?, ?)", (data["bot_token"], op_id, datetime.now()))
            conn.commit()
            bot.send_message(op_id, "🎉 Вы стали оператором бота!")
            bot.reply_to(message, "✅ Оператор добавлен")
        except:
            bot.reply_to(message, "❌ Нужен числовой ID")
        clear_state(user_id)
        return

    if state == "waiting_tag_name":
        c.execute("INSERT OR IGNORE INTO bot_tags (bot_token, tag_name) VALUES (?, ?)", (data["bot_token"], text))
        conn.commit()
        clear_state(user_id)
        bot.reply_to(message, f"✅ Тег '{text}' создан")
        return

    # Создание меню - текст
    if state == "waiting_menu_text":
        c.execute("UPDATE bot_menus SET text=? WHERE bot_token=? AND menu_id=?", (text, data["bot_token"], data["menu_id"]))
        conn.commit()
        clear_state(user_id)
        bot.send_message(message.chat.id, "✅ Текст сохранен!")

    # Создание меню - название кнопки
    if state == "waiting_btn_text":
        save_state(user_id, "waiting_btn_target", {"bot_token": data["bot_token"], "menu_id": data["menu_id"], "btn_type": data["btn_type"], "btn_text": text})
        if data["btn_type"] == "url":
            bot.send_message(message.chat.id, "🔗 *Введи ссылку (URL)*\nПример: https://example.com", parse_mode='Markdown')
        elif data["btn_type"] == "channel":
            bot.send_message(message.chat.id, "📢 *Введи username канала*\nПример: @channel или channel", parse_mode='Markdown')
        elif data["btn_type"] == "menu":
            c.execute("SELECT menu_id, menu_name FROM bot_menus WHERE bot_token=?", (data["bot_token"],))
            menus = c.fetchall()
            if menus:
                kb = InlineKeyboardMarkup(row_width=1)
                for mid, name in menus:
                    kb.add(InlineKeyboardButton(name, callback_data=f"btn_select_target_{data['bot_token']}_{data['menu_id']}_{mid}"))
                bot.send_message(message.chat.id, "📋 *Выбери целевое меню*", reply_markup=kb, parse_mode='Markdown')
            else:
                bot.send_message(message.chat.id, "❌ Нет созданных меню. Сначала создай меню!")
                clear_state(user_id)
        return

    if state == "waiting_btn_target":
        target = text
        btn = {"text": data["btn_text"], "type": data["btn_type"], "target": target}
        c.execute("SELECT buttons FROM bot_menus WHERE bot_token=? AND menu_id=?", (data["bot_token"], data["menu_id"]))
        row = c.fetchone()
        buttons = json.loads(row[0]) if row and row[0] else []
        buttons.append(btn)
        c.execute("UPDATE bot_menus SET buttons=? WHERE bot_token=? AND menu_id=?", (json.dumps(buttons), data["bot_token"], data["menu_id"]))
        conn.commit()
        clear_state(user_id)
        bot.send_message(message.chat.id, f"✅ Кнопка '{data['btn_text']}' добавлена!")

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
                    bot.send_message(u[0], f"📢 *РАССЫЛКА*\n\n{text}", parse_mode='Markdown')
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

# ==================== ФОТО ====================
@bot.message_handler(content_types=['photo'])
def photo_handler(message):
    state, data = get_state(message.from_user.id)
    if state == "waiting_photo":
        photo_id = message.photo[-1].file_id
        c.execute("UPDATE user_bots SET welcome_photo=? WHERE bot_token=?", (photo_id, data["bot_token"]))
        conn.commit()
        clear_state(message.from_user.id)
        bot.reply_to(message, "✅ Фото установлено")
    if state == "waiting_menu_photo":
        c.execute("UPDATE bot_menus SET photo_id=? WHERE bot_token=? AND menu_id=?", (photo_id, data["bot_token"], data["menu_id"]))
        conn.commit()
        clear_state(message.from_user.id)
        bot.reply_to(message, "✅ Фото для меню установлено")

# ==================== CALLBACK ОБРАБОТЧИК ====================
@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    user_id = call.from_user.id
    data = call.data
    chat_id = call.message.chat.id
    msg_id = call.message.message_id

    # Глобальные
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
        text = "📖 *Помощь*\n/addbot - добавить бота\n/mybot - мои боты\n/admin - админка\n\nБесплатная нейросеть для ответов!"
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 Назад", callback_data="back_start")), parse_mode='Markdown')
        return
    if data == "premium_bot":
        save_state(user_id, "waiting_premium_desc")
        bot.edit_message_text("✨ Опиши бота и укажи токен. Пример: 'Бот для магазина, токен: 123:ABC'", chat_id, msg_id)
        return

    # Админка
    if user_id == ADMIN_ID:
        if data == "admin_stats":
            c.execute("SELECT COUNT(*) FROM users")
            users_cnt = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM user_bots")
            bots_cnt = c.fetchone()[0]
            bot.edit_message_text(f"📊 Статистика:\nПользователей: {users_cnt}\nБотов: {bots_cnt}", chat_id, msg_id)
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

    # Редактирование бота
    if data.startswith("edit_"):
        bot_token = data[5:]
        res = bot_settings_keyboard(bot_token)
        if res:
            kb, status, username = res
            bot.edit_message_text(f"⚙️ *@{username}*\n{status}", chat_id, msg_id, reply_markup=kb, parse_mode='Markdown')
        return

    # Управление меню
    if data.startswith("menus_"):
        bot_token = data[6:]
        bot.edit_message_text("📋 *УПРАВЛЕНИЕ МЕНЮ*", chat_id, msg_id, reply_markup=menus_keyboard(bot_token), parse_mode='Markdown')
        return

    if data.startswith("create_main_menu_"):
        bot_token = data[18:]
        menu_id = "main"
        c.execute("INSERT OR IGNORE INTO bot_menus (bot_token, menu_id, menu_name, text, created_at) VALUES (?, ?, ?, ?, ?)",
                  (bot_token, menu_id, "Главное меню", "Главное меню бота", datetime.now()))
        conn.commit()
        bot.edit_message_text("✏️ *Редактирование главного меню*", chat_id, msg_id, reply_markup=create_menu_keyboard(bot_token, menu_id, "Главное меню"), parse_mode='Markdown')
        return

    if data.startswith("create_submenu_"):
        bot_token = data[15:]
        menu_id = f"sub_{int(time.time())}"
        c.execute("INSERT INTO bot_menus (bot_token, menu_id, menu_name, text, created_at) VALUES (?, ?, ?, ?, ?)",
                  (bot_token, menu_id, "Новое меню", "Текст меню", datetime.now()))
        conn.commit()
        bot.edit_message_text("✏️ *Редактирование меню*", chat_id, msg_id, reply_markup=create_menu_keyboard(bot_token, menu_id, "Новое меню"), parse_mode='Markdown')
        return

    if data.startswith("edit_menu_"):
        parts = data.split("_")
        bot_token = parts[2]
        menu_id = parts[3]
        bot.edit_message_text("✏️ *Редактирование меню*", chat_id, msg_id, reply_markup=create_menu_keyboard(bot_token, menu_id), parse_mode='Markdown')
        return

    if data.startswith("menu_text_"):
        parts = data.split("_")
        bot_token = parts[2]
        menu_id = parts[3]
        save_state(user_id, "waiting_menu_text", {"bot_token": bot_token, "menu_id": menu_id})
        bot.edit_message_text("📝 *Введи текст для меню* (поддерживается Markdown)", chat_id, msg_id, parse_mode='Markdown')
        return

    if data.startswith("menu_photo_"):
        parts = data.split("_")
        bot_token = parts[2]
        menu_id = parts[3]
        save_state(user_id, "waiting_menu_photo", {"bot_token": bot_token, "menu_id": menu_id})
        bot.edit_message_text("🖼 *Отправь фото для меню*", chat_id, msg_id, parse_mode='Markdown')
        return

    if data.startswith("menu_add_btn_"):
        parts = data.split("_")
        bot_token = parts[3]
        menu_id = parts[4]
        bot.edit_message_text("➕ *Выбери тип кнопки*", chat_id, msg_id, reply_markup=add_button_keyboard(bot_token, menu_id), parse_mode='Markdown')
        return

    if data.startswith("btn_url_"):
        parts = data.split("_")
        bot_token = parts[2]
        menu_id = parts[3]
        save_state(user_id, "waiting_btn_text", {"bot_token": bot_token, "menu_id": menu_id, "btn_type": "url"})
        bot.edit_message_text("🔗 *Введи название кнопки*", chat_id, msg_id, parse_mode='Markdown')
        return

    if data.startswith("btn_channel_"):
        parts = data.split("_")
        bot_token = parts[2]
        menu_id = parts[3]
        save_state(user_id, "waiting_btn_text", {"bot_token": bot_token, "menu_id": menu_id, "btn_type": "channel"})
        bot.edit_message_text("📢 *Введи название кнопки*", chat_id, msg_id, parse_mode='Markdown')
        return

    if data.startswith("btn_menu_"):
        parts = data.split("_")
        bot_token = parts[2]
        menu_id = parts[3]
        save_state(user_id, "waiting_btn_text", {"bot_token": bot_token, "menu_id": menu_id, "btn_type": "menu"})
        bot.edit_message_text("📋 *Введи название кнопки*", chat_id, msg_id, parse_mode='Markdown')
        return

    if data.startswith("btn_select_target_"):
        parts = data.split("_")
        bot_token = parts[3]
        menu_id = parts[4]
        target_menu = parts[5]
        state, state_data = get_state(user_id)
        if state == "waiting_btn_text":
            btn = {"text": state_data["btn_text"], "type": "callback", "target": target_menu}
            c.execute("SELECT buttons FROM bot_menus WHERE bot_token=? AND menu_id=?", (bot_token, menu_id))
            row = c.fetchone()
            buttons = json.loads(row[0]) if row and row[0] else []
            buttons.append(btn)
            c.execute("UPDATE bot_menus SET buttons=? WHERE bot_token=? AND menu_id=?", (json.dumps(buttons), bot_token, menu_id))
            conn.commit()
            clear_state(user_id)
            bot.answer_callback_query(call.id, "Кнопка добавлена!")
            bot.edit_message_text("✅ Кнопка добавлена!", chat_id, msg_id)
        return

    if data.startswith("menu_clear_btns_"):
        parts = data.split("_")
        bot_token = parts[3]
        menu_id = parts[4]
        c.execute("UPDATE bot_menus SET buttons='[]' WHERE bot_token=? AND menu_id=?", (bot_token, menu_id))
        conn.commit()
        bot.answer_callback_query(call.id, "Кнопки очищены")
        bot.edit_message_text("✅ Кнопки очищены", chat_id, msg_id)
        return

    if data.startswith("menu_save_"):
        bot.edit_message_text("✅ Меню сохранено!", chat_id, msg_id)
        return

    # Включение/выключение бота
    if data.startswith("toggle_bot_"):
        bot_token = data[11:]
        c.execute("SELECT bot_status, bot_username FROM user_bots WHERE bot_token=?", (bot_token,))
        status, username = c.fetchone()
        if status == 1:
            stop_user_bot(bot_token)
            bot.answer_callback_query(call.id, f"Бот @{username} остановлен")
        else:
            start_user_bot(bot_token, username, user_id)
            bot.answer_callback_query(call.id, f"Бот @{username} запущен")
        callback_query(call)
        return

    # Остальные настройки
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
        c.execute("SELECT ai_enabled FROM user_bots WHERE bot_token=?", (bot_token,))
        row = c.fetchone()
        if row:
            new_status = not row[0]
            c.execute("UPDATE user_bots SET ai_enabled=? WHERE bot_token=?", (new_status, bot_token))
            if not row[0]:
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
        bot.edit_message_text(f"👥 Операторы\n{ops_text}\nТеги: {', '.join(t[0] for t in tags)}", chat_id, msg_id, reply_markup=kb, parse_mode='Markdown')
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
        bot.edit_message_text(f"🏷 Теги\n{chr(10).join([t[0] for t in tags]) or 'Нет тегов'}", chat_id, msg_id, reply_markup=kb, parse_mode='Markdown')
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

# ==================== ЗАПУСК ====================
if __name__ == "__main__":
    print("=" * 50)
    print("🤖 VanillaGram - Конструктор ботов")
    print("=" * 50)
    print(f"✅ Бот запущен")
    print(f"📁 Папка media: {MEDIA_DIR}")
    print(f"👑 Админ ID: {ADMIN_ID}")
    print("=" * 50)
    
    # Запускаем уже существующих ботов при старте
    c.execute("SELECT bot_token, bot_username, user_id FROM user_bots WHERE is_active=1 AND bot_status=1")
    bots = c.fetchall()
    for token, username, owner_id in bots:
        start_user_bot(token, username, owner_id)
        time.sleep(0.5)
    
    bot.infinity_polling(timeout=60)