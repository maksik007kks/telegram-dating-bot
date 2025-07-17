import os
import sqlite3
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

# === ИНИЦИАЛИЗАЦИЯ БД ===
conn = sqlite3.connect("users.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    name TEXT,
    age INTEGER,
    gender TEXT,
    bio TEXT,
    photo TEXT,
    state TEXT
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS likes (
    liker_id INTEGER,
    liked_id INTEGER,
    PRIMARY KEY (liker_id, liked_id)
)
''')

conn.commit()

GENDERS = ['Парень', 'Девушка']

# === КОМАНДЫ ===
def start(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    cursor.execute("INSERT OR REPLACE INTO users (user_id, state) VALUES (?, ?)", (user_id, 'name'))
    conn.commit()
    update.message.reply_text("Привет! Как тебя зовут?")

def help_command(update: Update, context: CallbackContext):
    update.message.reply_text("/start — заполнить анкету\n/match — найти совпадения\n/profile — моя анкета\n/stop — удалить анкету")

def stop(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
    conn.commit()
    update.message.reply_text("Твоя анкета удалена.", reply_markup=ReplyKeyboardRemove())

def profile(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    cursor.execute("SELECT name, age, gender, bio FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        update.message.reply_text("Анкета не найдена. Напиши /start")
        return
    name, age, gender, bio = row
    update.message.reply_text(f"Имя: {name}\nВозраст: {age}\nПол: {gender}\nО себе: {bio}")

def handle_message(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    cursor.execute("SELECT state FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        update.message.reply_text("Напиши /start для начала.")
        return
    state = row[0]

    if state == 'name':
        cursor.execute("UPDATE users SET name = ?, state = 'age' WHERE user_id = ?", (text, user_id))
        update.message.reply_text("Сколько тебе лет?")

    elif state == 'age':
        if not text.isdigit():
            update.message.reply_text("Введи возраст числом.")
            return
        cursor.execute("UPDATE users SET age = ?, state = 'gender' WHERE user_id = ?", (int(text), user_id))
        update.message.reply_text(
            "Кто ты по полу?",
            reply_markup=ReplyKeyboardMarkup([[g] for g in GENDERS], one_time_keyboard=True, resize_keyboard=True)
        )

    elif state == 'gender':
        if text not in GENDERS:
            update.message.reply_text("Пожалуйста, выбери из кнопок.")
            return
        cursor.execute("UPDATE users SET gender = ?, state = 'bio' WHERE user_id = ?", (text, user_id))
        update.message.reply_text("Расскажи немного о себе:", reply_markup=ReplyKeyboardRemove())

    elif state == 'bio':
        cursor.execute("UPDATE users SET bio = ?, state = 'photo' WHERE user_id = ?", (text, user_id))
        update.message.reply_text("Отправь фотографию профиля.")

    elif state == 'browse':
        if text.lower() == 'лайк':
            handle_like(update, context)
        elif text.lower() == 'дальше':
            show_profile(update, context)
        else:
            update.message.reply_text("Нажми 'Лайк' или 'Дальше'.")

    conn.commit()

def handle_photo(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    cursor.execute("SELECT state FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row or row[0] != 'photo':
        update.message.reply_text("Сейчас не время для фото.")
        return

    photo = update.message.photo[-1]
    file = photo.get_file()
    path = f"photos/{user_id}.jpg"
    os.makedirs("photos", exist_ok=True)
    file.download(path)

    cursor.execute("UPDATE users SET photo = ?, state = 'browse' WHERE user_id = ?", (path, user_id))
    conn.commit()
    update.message.reply_text("Анкета создана ✅ Напиши /match для поиска")

def show_profile(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    cursor.execute("SELECT gender FROM users WHERE user_id = ?", (user_id,))
    my_gender = cursor.fetchone()[0]
    target_gender = 'Девушка' if my_gender == 'Парень' else 'Парень'

    cursor.execute("SELECT liked_id FROM likes WHERE liker_id = ?", (user_id,))
    liked = [row[0] for row in cursor.fetchall()]

    cursor.execute("SELECT user_id, name, age, bio, photo FROM users WHERE gender = ? AND user_id != ?", (target_gender, user_id))
    for uid, name, age, bio, photo in cursor.fetchall():
        if uid in liked:
            continue
        context.user_data['current'] = uid
        caption = f"Имя: {name}\nВозраст: {age}\nО себе: {bio}"
        if photo and os.path.exists(photo):
            update.message.reply_photo(photo=open(photo, 'rb'), caption=caption,
                                       reply_markup=ReplyKeyboardMarkup([["Лайк", "Дальше"]], resize_keyboard=True))
        else:
            update.message.reply_text(caption,
                                      reply_markup=ReplyKeyboardMarkup([["Лайк", "Дальше"]], resize_keyboard=True))
        return

    update.message.reply_text("Анкеты закончились 🥲")

def handle_like(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    target_id = context.user_data.get('current')
    if not target_id:
        update.message.reply_text("Нет текущей анкеты.")
        return

    cursor.execute("INSERT OR IGNORE INTO likes (liker_id, liked_id) VALUES (?, ?)", (user_id, target_id))
    cursor.execute("SELECT 1 FROM likes WHERE liker_id = ? AND liked_id = ?", (target_id, user_id))
    if cursor.fetchone():
        update.message.reply_text("\U0001F496 Это взаимно! Напишите друг другу в Telegram!")
    conn.commit()
    show_profile(update, context)

def run_bot():
    TOKEN = os.environ.get("TOKEN")
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    # handlers ...
    updater.start_polling()
    print("Бот запущен!")

    updater.idle()  # ОСТАВЬ ТАК — но вызови из __main__


