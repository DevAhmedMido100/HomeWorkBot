import os
import logging
import sqlite3
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, CallbackQueryHandler
from telegram.error import TelegramError
import requests
from flask import Flask

# إعدادات البوت
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID', 8087077168))

app = Flask(__name__)

# إعداد التسجيل
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# قاعدة البيانات
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
        
        # إرسال إشعار للمطور
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
            logging.error(f"Error sending admin notification: {e}")
    
    conn.close()

def send_message_to_admin(message):
    try:
        requests.post(
            f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage',
            json={'chat_id': ADMIN_ID, 'text': message}
        )
    except:
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

# التحقق من الاشتراك في القناة
async def check_subscription(user_id, context: CallbackContext):
    try:
        chat_member = await context.bot.get_chat_member('@TepthonHelp', user_id)
        return chat_member.status in ['member', 'administrator', 'creator']
    except TelegramError:
        return False

# الذكاء الاصطناعي المبسط
async def call_ai_api(text=None, image_url=None):
    try:
        if text:
            # محاكاة للذكاء الاصطناعي - يمكنك استبدالها بـ API حقيقي
            responses = {
                'رياضيات': 'حل المسألة الرياضية: ... 🖤',
                'علوم': 'شرح الدرس العلمي: ... 🖤', 
                'فيزياء': 'تحليل المسألة الفيزيائية: ... 🖤',
                'كيمياء': 'تفسير التفاعل الكيميائي: ... 🖤'
            }
            
            for key, response in responses.items():
                if key in text.lower():
                    return response
            
            return f"تم استلام سؤالك: {text}\n\nجاري البحث عن الإجابة المثالية لك 🖤."
        
        elif image_url:
            return "تم استلام الصورة بنجاح 🖤.\nجاري تحليل المحتوى التعليمي في الصورة 🖤."
            
    except Exception as e:
        return f"عذراً، حدث خطأ في المعالجة 🖤. حاول مرة أخرى."

# أوامر البوت
async def start(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    username = update.effective_user.username or "بدون يوزر"
    first_name = update.effective_user.first_name or "مستخدم"
    
    if update.effective_chat.type != "private":
        return
    
    if is_banned(user_id):
        await update.message.reply_text("تم حظرك من استخدام البوت 🖤.")
        return
    
    # التحقق من الاشتراك
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
        [InlineKeyboardButton("تـحـلـيـل صـورة 🖼", callback_data="analyze_image")],
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
    await update.message.reply_text("جـاري الـبـحـث عـن إجـابـة 🖤.")
    response = await call_ai_api(text=text)
    await update.message.reply_text(response)

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
    
    await update.message.reply_text("جـاري تـحـلـيـل الـصـورة 🖤.")
    response = await call_ai_api(image_url="temp_image")
    await update.message.reply_text(response)

# أوامر المطور
async def admin_broadcast(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("هـذا الامـر للمـطـور فـقـط 🖤.")
        return
    
    if not context.args:
        await update.message.reply_text("اسـتـخـدم: /broadcast <الرسالة> 🖤.")
        return
    
    message = " ".join(context.args)
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM users WHERE is_banned = 0')
    users = cursor.fetchall()
    conn.close()
    
    success = 0
    failed = 0
    
    for user in users:
        try:
            await context.bot.send_message(user[0], f"📢 إشـعـار من المطور:\n\n{message}")
            success += 1
        except:
            failed += 1
    
    await update.message.reply_text(f"تم الارسال 🖤.\nنجح: {success} 🖤.\nفشل: {failed} 🖤.")

async def admin_ban(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("هـذا الامـر للمـطـور فـقـط 🖤.")
        return
    
    if not context.args:
        await update.message.reply_text("اسـتـخـدم: /ban <user_id> 🖤.")
        return
    
    try:
        target_id = int(context.args[0])
        ban_user(target_id)
        await update.message.reply_text(f"تم حـظـر الـمـسـتـخـدم {target_id} 🖤.")
    except ValueError:
        await update.message.reply_text("رقـم الـمـسـتـخـدم غـيـر صـحـيـح 🖤.")

async def admin_unban(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("هـذا الامـر للمـطـور فـقـط 🖤.")
        return
    
    if not context.args:
        await update.message.reply_text("اسـتـخـدم: /unban <user_id> 🖤.")
        return
    
    try:
        target_id = int(context.args[0])
        unban_user(target_id)
        await update.message.reply_text(f"تم فـك حـظـر الـمـسـتـخـدم {target_id} 🖤.")
    except ValueError:
        await update.message.reply_text("رقـم الـمـسـتـخـدم غـيـر صـحـيـح 🖤.")

async def admin_stats(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("هـذا الامـر للمـطـور فـقـط 🖤.")
        return
    
    total_users = get_user_count()
    stats_text = f"""
📊 إحـصـائـيـات الـبـوت 🖤:

👥 عـدد الـمـسـتـخـدمـيـن: {total_users} 🖤.
📅 تـاريـخ الـيـوم: {datetime.now().strftime('%Y/%m/%d')} 🖤.
    """
    await update.message.reply_text(stats_text)

# معالجة الأزرار
async def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    
    if not await check_subscription(user_id, context):
        await query.edit_message_text("يـجـب الاشـتـراك في @TepthonHelp اولاً 🖤.")
        return
    
    if query.data == "check_subscription":
        if await check_subscription(user_id, context):
            await query.edit_message_text("شـكـراً لاشـتـراكـك 🖤.\nاسـتـخـدم /start لـبـدء الاسـتـخـدام 🖤.")
        else:
            await query.edit_message_text("لـم يـتـم الاشـتـراك بـعـد 🖤.\nاشـتـرك ثـم اعـد المحاولة 🖤.")
    
    elif query.data == "solve_math":
        await query.edit_message_text("ارسـل الـمـسـألـة الـريـاضـيـة 🧮.\nوسـأحـاول حـلـهـا لـك 🖤.")
    
    elif query.data == "analyze_image":
        await query.edit_message_text("ارسـل الـصـورة الـتـي تـريـد تـحـلـيـلـهـا 🖼.\nوسـأقـوم بـتـحـلـيـلـهـا 🖤.")
    
    elif query.data == "help":
        help_text = """
🆘 الـمـسـاعـدة 🖤:

• لـحـل مـسـألـة: اخـتـر "حـل مـسـألـة" ثـم ارسـل الـمـسـألـة 🖤.
• لـتـحـلـيـل صـورة: اخـتـر "تـحـلـيـل صـورة" ثـم ارسـل الـصـورة 🖤.
• للاتـصـال بـالـمـطـور: @TepthonHelp 🖤.

بـوت مـسـاعـدة دراسـيـة 🖤.
        """
        await query.edit_message_text(help_text)

# إعداد البوت الرئيسي
def main():
    init_db()
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    # handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("broadcast", admin_broadcast))
    application.add_handler(CommandHandler("ban", admin_ban))
    application.add_handler(CommandHandler("unban", admin_unban))
    application.add_handler(CommandHandler("stats", admin_stats))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.PHOTO, handle_image))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # تشغيل البوت
    application.run_polling()

@app.route('/')
def home():
    return "البوت يعمل بنجاح 🖤."

if __name__ == '__main__':
    main() من 
