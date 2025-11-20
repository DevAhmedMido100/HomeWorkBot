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
import base64  # تمّت الإضافة لتحويل الصورة إلى base64 قبل إرسالها إلى Groq

# إعدادات البوت
BOT_TOKEN = os.getenv('BOT_TOKEN')
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
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

# الذكاء الاصطناعي باستخدام Groq API (نصوص)
async def call_groq_api(prompt, is_math=False):
    try:
        url = "https://api.groq.com/openai/v1/chat/completions"
        
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        
        if is_math:
            system_message = """أنت مساعد تعليمي متخصص في حل المسائل الرياضية والعلوم. 
            قدم حلولاً واضحة ومفصلة مع الخطوات.
            استخدم الرموز الرياضية عندما يكون ذلك مناسبًا.
            كن دقيقًا وواضحًا في تفسيرك."""
        else:
            system_message = """أنت مساعد تعليمي ذكي يساعد الطلاب في واجباتهم المدرسية.
            قدم إجابات مفيدة وواضحة ومنظمة.
            إذا كان السؤال غير واضح، اطلب توضيحًا."""
        
        data = {
            "messages": [
                {
                    "role": "system",
                    "content": system_message + "\n\nالرد باللغة العربية دائماً."
                },
                {
                    "role": "user", 
                    "content": prompt
                }
            ],
            "model": "llama-3.1-8b-instant",  # نموذج نصي
            "temperature": 0.3,
            "max_tokens": 1024,
            "top_p": 1,
            "stream": False
        }
        
        response = requests.post(url, headers=headers, json=data, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            # تعامُل آمن مع بنية الاستجابة
            try:
                return result['choices'][0]['message']['content']
            except:
                return json.dumps(result)
        else:
            return f"عذراً، حدث خطأ في المعالجة 🖤. رمز الخطأ: {response.status_code}"
            
    except Exception as e:
        logging.error(f"Groq API error: {e}")
        return f"عذراً، حدث خطأ في الاتصال 🖤. حاول مرة أخرى."

# ---- الدالة الجديدة: إرسال صورة + prompt إلى Groq (نموذج رؤية إن توفر) ----
async def call_groq_api_with_image(image_path, prompt_text):
    """
    يقرأ الصورة من image_path، يحولها إلى base64، ويرسلها مع prompt_text إلى Groq.
    ملاحظة: قد تحتاج تعديل حقل 'model' إلى موديل رؤية مُتاح لحسابك في Groq.
    """
    try:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        # اقرأ الصورة وحولها إلى base64
        with open(image_path, "rb") as f:
            img_bytes = f.read()
        img_b64 = base64.b64encode(img_bytes).decode("utf-8")
        # بناء محتوى الرسالة: نرسل صورة كـ input_image متبوعة بنص التوجيه
        # هذه البنية تعمل مع بعض واجهات Groq Vision — قد تحتاج تعديل لو كانت واجهتك مختلفة
        message_content = [
            {"type": "input_image", "image": f"data:image/jpeg;base64,{img_b64}"},
            {"type": "input_text", "text": prompt_text}
        ]
        data = {
            "messages": [
                {
                    "role": "user",
                    "content": message_content
                }
            ],
            # ملاحظة: غيّر اسم الموديل إذا كان لدى حسابك موديل رؤية مختلف
            "model": "llama-3.2-90b-vision-preview",
            "temperature": 0.2,
            "max_tokens": 1500,
            "top_p": 1,
            "stream": False
        }
        resp = requests.post(url, headers=headers, json=data, timeout=60)
        if resp.status_code == 200:
            j = resp.json()
            try:
                return j['choices'][0]['message']['content']
            except:
                return json.dumps(j)
        else:
            logging.error(f"Groq image API HTTP {resp.status_code}: {resp.text}")
            return f"عذراً، حدث خطأ في معالجة الصورة 🖤. رمز الخطأ: {resp.status_code}"
    except Exception as e:
        logging.error(f"call_groq_api_with_image error: {e}")
        return "عذراً، فشل إرسال الصورة إلى نموذج Groq 🖤."

# معالجة النصوص والصور (القديمة)
async def call_ai_api(text=None, image_url=None):
    try:
        if text:
            # تحديد إذا كان السؤال رياضياً
            math_keywords = ['رياضيات', 'math', 'مسألة', 'حل', 'equation', 'جبر', 'هندسة', 'حساب', 'نظرية']
            is_math = any(keyword in text.lower() for keyword in math_keywords)
            
            response = await call_groq_api(text, is_math)
            return response
        
        elif image_url:
            return "تم استلام الصورة بنجاح 🖤.\nحاليا لا يدعم البوت تحليل الصور، لكن يمكنك وصف المحتوى المكتوب في الصورة وسأساعدك 🖤."
            
    except Exception as e:
        logging.error(f"AI API error: {e}")
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
    
    # إظهار رسالة "جاري الكتابة"
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    await update.message.reply_text("جـاري الـبـحـث عـن إجـابـة 🖤.")
    response = await call_ai_api(text=text)
    await update.message.reply_text(response)

# **التعديل هنا فقط**: تحليل الصورة عبر Groq Vision وإرجاع حل/شرح
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
    
    await update.message.reply_text("جـاري تـحـلـيـل الـصـورة وطلب الحل من Groq 🖤...")
    
    try:
        # تنزيل الصورة
        photo = update.message.photo[-1]
        file = await photo.get_file()
        path = f"temp_image_{user_id}_{int(datetime.now().timestamp())}.jpg"
        await file.download_to_drive(path)
        
        # إعداد prompt واضح لطلب حل المسائل وشرحها باللغة العربية
        prompt_text = (
            "أنت مساعد تعليمي. في الصورة المرفقة يوجد سؤال/أسئلة مدرسية (رياضيات/فيزياء/كيمياء أو مسائل حسابية). "
            "اقرأ ما في الصورة، استخرج كل مسألة، ثم: \n"
            "1) اكتب النتيجة الصحيحة لكل مسألة.\n"
            "2) اشرح خطوات الحل خطوة بخطوة بشكل واضح للطالب.\n"
            "3) إذا كان هناك أخطاء شائعة، أشِر إليها ووضح التصحيح.\n"
            "أجب باللغة العربية وبنبرة ودودة ومناسبة للطلاب."
        )
        
        # استدعاء Groq مع الصورة والنص
        response = await call_groq_api_with_image(path, prompt_text)
        
        # حذف الملف المؤقت
        try:
            os.remove(path)
        except:
            pass
        
        # تقسيم الرد لو طويل
        if isinstance(response, str) and len(response) > 4000:
            parts = [response[i:i+4000] for i in range(0, len(response), 4000)]
            for part in parts:
                await update.message.reply_text(part)
        else:
            await update.message.reply_text(response)
    
    except Exception as e:
        logging.error(f"Image handler error: {e}")
        await update.message.reply_text("عذراً، حدث خطأ في معالجة الصورة 🖤.")

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
⚡ الـبـوت مـشـغـل بـ Groq AI 🖤.
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
    
    elif query.data == "explain_lesson":
        await query.edit_message_text("ارسـل الـدرس الـذي تـريـد شـرحـه 📚.\nوسـأقـوم بـشـرحـه لـك 🖤.")
    
    elif query.data == "help":
        help_text = """
🆘 الـمـسـاعـدة 🖤:

• لـحـل مـسـألـة: اخـتـر "حـل مـسـألـة" 🖤.
• لـشـرح دـرس: اخـتـر "شـرح دـرس" 🖤.
• للاتـصـال بـالـمـطـور: @TepthonHelp 🖤.

⚡ الـبـوت مـشـغـل بـ Groq AI 🖤.
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
    return "البوت يعمل بنجاح 🖤. - مشغل بـ Groq AI"

if __name__ == '__main__':
    main()
