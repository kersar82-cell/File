import os
import gc
import openpyxl
from aiogram import Bot, Dispatcher, executor, types
from flask import Flask
from threading import Thread

# ================= কনফিগারেশন =================
# শুধু নতুন ২য় বটের টোকেন দিতে হবে (Supabase বা মেইন বটের টোকেন লাগবে না)
WORKER_BOT_TOKEN = "এখানে_নতুন_২য়_বটের_টোকেন_দিতে_হবে"
FILE_STORAGE_CHANNEL = -1003992295257

bot = Bot(token=WORKER_BOT_TOKEN)
dp = Dispatcher(bot)

print("🚀 Worker Bot is listening to the channel...")

# ================= কোর প্রসেসিং ইঞ্জিন =================
@dp.message_handler(content_types=['document'], chat_type=[types.ChatType.CHANNEL, types.ChatType.SUPERGROUP])
async def process_channel_file(message: types.Message):
    # শুধু নির্দিষ্ট চ্যানেল থেকে ফাইল নিবে
    if message.chat.id != FILE_STORAGE_CHANNEL:
        return

    caption = message.caption or ""
    
    # ক্যাপশনে uid এবং cat চেক
    if "uid:" not in caption.lower() or "cat:" not in caption.lower():
        return

    try:
        parts = caption.split("|")
        user_id = int(parts[0].split(":", 1)[1].strip())
        category = parts[1].split(":", 1)[1].strip()
        
        file_id = message.document.file_id
        file_name = message.document.file_name.lower()
        file_path = f"worker_{file_id}_{file_name}"
        
        id_count = 0
        
        # ফাইল ডাউনলোড
        file_info = await bot.get_file(file_id)
        await bot.download_file(file_info.file_path, destination=file_path)

        # আইডি গোনা (শুধু openpyxl দিয়ে)
        if file_name.endswith('.xlsx'):
            wb = openpyxl.load_workbook(file_path, read_only=True)
            sheet = wb.active
            for row in sheet.iter_rows(values_only=True):
                clean_row = [cell for cell in row if cell is not None and str(cell).strip() != ""]
                if clean_row:
                    id_count += 1
            wb.close()
            
        # কাজ শেষে চ্যানেলে মেসেজ পাঠানো
        if id_count > 0:
            result_text = f"DONE | uid:{user_id} | cat:{category} | count:{id_count}"
            await bot.send_message(chat_id=FILE_STORAGE_CHANNEL, text=result_text)
            print(f"✅ Result sent to channel: {result_text}")
        else:
            await bot.send_message(chat_id=FILE_STORAGE_CHANNEL, text=f"EMPTY | uid:{user_id}")
            
    except Exception as e:
        print(f"Worker Error: {e}")
        # এরর হলে চ্যানেলে জানিয়ে দেওয়া
        await bot.send_message(chat_id=FILE_STORAGE_CHANNEL, text=f"ERROR | uid:{user_id} | msg:File processing failed")

    finally:
        # মেমোরি ক্লিনআপ
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)
        gc.collect()

# ================= রেন্ডার সার্ভার (যাতে পোর্ট এরর না আসে) =================
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Worker Bot is Alive and Running!"

def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

def keep_alive():
    t = Thread(target=run, daemon=True)
    t.start()

if __name__ == '__main__':
    keep_alive()
    print("🤖 Bot polling started...")
    executor.start_polling(dp, skip_updates=True)
    
