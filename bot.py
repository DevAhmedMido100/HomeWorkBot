import os
import logging
import sqlite3
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, CallbackQueryHandler
from telegram.error import TelegramError
import requests
import json
from flask import Flask

# OCR
from PIL import Image
import pytesseract

# إعداد البوت
BOT_TOKEN = os.getenv('BOT_TOKEN')
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
ADMIN_ID = int(os.getenv('ADMIN_ID', 8087077168))

app = Flask(__name__)

# تسجيل الأحداث
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ------------------ قاعدة البيانات ------------------
def init_db():
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            join_date TEXT,
            is_banned INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

def add_user(user_id, username, first_name):
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    if not cursor.fetchone():
        join_date = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
        cursor.execute(
            'INSERT INTO users (user_id, username, first_name, join_date) VALUES (?, ?, ?, ?)',
            (user_id, username, first_name, join_date)
        )
        conn.commit()
        try:
            message = f"""
ـ هـناك شخـص دخل الي بـوتك 🖤.
- الاسم {first_name} 🩵.
- اليوزر @{username} 💜.
- التوقيت {join_date} 🩷.
- الايدي {user_id} 💙.
            """
            send_message_to_admin(message)
        except Exception as e:
            logger.error(f"Error sending admin notification: {e}")
    conn.close()

def send_message_to_admin(message):
    try:
        requests.post(
            f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage',
            json={'chat_id': ADMIN_ID, 'text': message}
        )
    except Exception:
        pass

def get_user_count():
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM users')
    count = cursor.fetchone()[0]
    conn.close()
    return count

def ban_user(user_id):
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET is_banned = 1 WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

def unban_user(user_id):
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET is_banned = 0 WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

def is_banned(user_id):
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute('SELECT is_banned FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result and result[0] == 1

# ------------------ تحقق اشتراك القناة ------------------
async def check_subscription(user_id, context: CallbackContext):
    try:
        chat_member = await context.bot.get_chat_member('@TepthonHelp', user_id)
        return chat_member.status in ['member', 'administrator', 'creator']
    except TelegramError as e:
        logger.debug(f"check_subscription error: {e}")
        return False

# ------------------ Groq API ------------------
async def call_groq_api(prompt, is_math=False):
    try:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }

        system_message = (
            "أنت مساعد تعليمي متخصص في حل المسائل الرياضية والعلوم. "
            "قدم حلولاً واضحة ومفصلة مع الخطوات. استخدم الرموز الرياضية عندما يكون ذلك مناسبًا. "
            "كن دقيقًا وواضحًا في تفسيرك." if is_math else
            "أنت مساعد تعليمي ذكي يساعد الطلاب في واجباتهم المدرسية. "
            "قدم إجابات مفيدة وواضحة ومنظمة. إذا كان السؤال غير واضح، اطلب توضيحًا."
        )

        data = {
            "messages": [
                {"role": "system", "content": system_message + "\n\nالرد باللغة العربية دائماً."},
                {"role": "user", "content": prompt}
            ],
            "model": "llama-3.1-8b-instant",
            "temperature": 0.3,
            "max_tokens": 1024,
            "top_p": 1,
            "stream": False
        }

        resp = requests.post(url, headers=headers, json=data, timeout=30)
        if resp.status_code == 200:
            j = resp.json()
            try:
                return j['choices'][0]['message']['content']
            except Exception:
                return json.dumps(j)
        else:
            logger.error(f"Groq API HTTP {resp.status_code}: {resp.text}")
            return f"عذراً، حدث خطأ في المعالجة 🖤. رمز الخطأ: {resp.status_code}"
    except Exception as e:
        logger.error(f"Groq API error: {e}")
        return "عذراً، حدث خطأ في الاتصال 🖤. حاول مرة أخرى."

# ------------------ دالة عامة للنص ------------------
async def call_ai_api(text=None):
    try:
        if text:
            math_keywords = ['رياضيات', 'math', 'مسألة', 'حل', 'equation', 'جبر', 'هندسة', 'حساب', 'نظرية']
            is_math = any(keyword in text.lower() for keyword in math_keywords)
            return await call_groq_api(text, is_math=is_math)
        return "لا يوجد مدخل صالح."
    except Exception as e:
        logger.error(f"call_ai_api error: {e}")
        return "عذراً، حدث خطأ في المعالجة 🖤. حاول مرة أخرى."

# ------------------ أوامر البوت ------------------
async def start(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    username = update.effective_user.username or "بدون يوزر"
    first_name = update.effective_user.first_name or "مستخدم"

    if update.effective_chat.type != "private":
        return

    if is_banned(user_id):
        await update.message.reply_text("تم حظرك من استخدام البوت 🖤.")
        return

    if not await check_subscription(user_id, context):
        keyboard = [
            [InlineKeyboardButton("اشترك في القناة 🖤", url="https://t.me/TepthonHelp")],
            [InlineKeyboardButton("تـفـعـيـل 🖤", callback_data="check_subscription")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"عـزيـزي {first_name} 🖤.\nيـجـب الاشـتـراك في قـنـاة الـدعـم اولاً 🖤.",
            reply_markup=reply_markup
        )
        return

    add_user(user_id, username, first_name)

    keyboard = [
        [InlineKeyboardButton("حـل مـسـألـة 🧮", callback_data="solve_math")],
        [InlineKeyboardButton("شـرح دـرس 📚", callback_data="explain_lesson")],
        [InlineKeyboardButton("الـمـسـاعـدة 🆘", callback_data="help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    welcome_text = f"""
اهـلا بـك يـا {first_name} 🖤.
في بوت تحليل المسائل والصور ومساعدتك في واجباتك الدراسية 🖤.

اخـتـر واحـدة من الـخـيـارات الـتـالـيـة 🖤.
"""
    await update.message.reply_text(welcome_text, reply_markup=reply_markup)

async def handle_message(update: Update, context: CallbackContext):
    user_id = update.effective_user.id

    if update.effective_chat.type != "private":
        return

    if is_banned(user_id):
        await update.message.reply_text("تم حظرك من استخدام البوت 🖤.")
        return

    if not await check_subscription(user_id, context):
        await update.message.reply_text("يـجـب الاشـتـراك في @TepthonHelp اولاً 🖤.")
        return

    text = update.message.text
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    await update.message.reply_text("جـاري الـبـحـث عـن إجـابـة 🖤.")
    response = await call_ai_api(text=text)
    await update.message.reply_text(response)

# ------------------ handle_image مع pytesseract فقط ------------------
async def handle_image(update: Update, context: CallbackContext):
    user_id = update.effective_user.id

    if update.effective_chat.type != "private":
        return

    if is_banned(user_id):
        await update.message.reply_text("تم حظرك من استخدام البوت 🖤.")
        return

    if not await check_subscription(user_id, context):
        await update.message.reply_text("يـجـب الاشـتـراك في @TepthonHelp اولاً 🖤.")
        return

    await update.message.reply_text("جـاري تـحـلـيـل الـصـورة وقراءة النص 🖤.")

    photo = update.message.photo[-1]
    file = await photo.get_file()
    tmp_path = f"tmp_image_{user_id}_{int(datetime.now().timestamp())}.jpg"

    try:
        await file.download_to_drive(tmp_path)
        extracted_text = ""
        try:
            img = Image.open(tmp_path)
            extracted_text = pytesseract.image_to_string(img, lang='ara').strip()
        except Exception as e:
            logger.error(f"OCR error: {e}")
            extracted_text = ""

        if not extracted_text:
            await update.message.reply_text("لم أستطع قراءة نص واضح من الصورة 🖤.\nحاول إرسال صورة أوضح أو اكتب السؤال يدوياً.")
            return

        await update.message.reply_text("جـاري فهـم الـمـسـألة وطلب الحل من Groq 🖤...")

        math_keywords = ['رياضيات', 'مسألة', 'حل', 'سؤال', 'معادلة', 'جبر', 'هندسة', 'ناتج', 'حسب']
        is_math = any(k in extracted_text.lower() for k in math_keywords)

        response = await call_groq_api(extracted_text, is_math=is_math)
        if isinstance(response, str) and len(response) > 4000:
            parts = [response[i:i+4000] for i in range(0, len(response), 4000)]
            for part in parts:
                await update.message.reply_text(part)
        else:
            await update.message.reply_text(response)

    except Exception as e:
        logger.error(f"Image handler error: {e}")
        await update.message.reply_text("عذراً، حدث خطأ في معالجة الصورة 🖤.")
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except:
            pass

# ------------------ باقي أوامر المطور و الأزرار كما في كودك السابق ------------------
# (يمكن نسخها كما هي من الكود الأصلي بدون تغيير)

def main():
    init_db()
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.PHOTO, handle_image))
    # إضافة باقي CommandHandlers و CallbackQueryHandler كما في كودك

    application.run_polling()

@app.route('/')
def home():
    return "البوت يعمل بنجاح 🖤. - مشغل بـ Groq AI"

if __name__ == '__main__':
    main()
