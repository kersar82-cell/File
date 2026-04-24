import os
import gc
import asyncio
import requests
import datetime
import openpyxl
from aiogram import Bot, Dispatcher, executor, types
from supabase import create_client, Client

# ================= কনফিগারেশন (আপনার তথ্য দিন) =================
# ১. আপনার নতুন ২য় বটের টোকেন (যেটি প্রাইভেট চ্যানেলে বসে থাকবে)
WORKER_BOT_TOKEN = "8731153350:AAF2nnUj7e2ej37kZEzcc-_Pc4bbvoFyqN4"

# ২. আপনার আসল মেইন বটের টোকেন (ইউজারকে মেসেজ পাঠানোর জন্য)
MAIN_BOT_TOKEN = "8203253229:AAGlZpmZ2TDWVtGts5bqcLWE96TDY9CmnQs" 

# ৩. ডাটাবেস এবং চ্যানেল সেটিংস
SUPABASE_URL = "https://wvczkeugwcfhyizibafs.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Ind2Y3prZXVnd2NmaHlpemliYWZzIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NjE2NzQ1NywiZXhwIjoyMDkxNzQzNDU3fQ.xERE9HIq7fttGUaow9VwKn_A1YaoRr-w7OMf4eFJm3I"
FILE_STORAGE_CHANNEL = -1003992295257 # আপনার প্রাইভেট চ্যানেল আইডি

# কাজের রেট লিস্ট (হিসাবের জন্য)
IG_RATES = {"IG 2fa": 2.30, "IG Cookies": 3.90, "IG Mother Account": 8.0}
FB_RATES = {"FB 00 Fnd 2fa": 5.80}

# বট এবং ডাটাবেস চালু করা
bot = Bot(token=WORKER_BOT_TOKEN)
dp = Dispatcher(bot)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

print("🚀 Worker Bot is listening to the channel...")
# ================= কোর প্রসেসিং ইঞ্জিন (ফাইল রিসিভ ও গোনা) =================
@dp.message_handler(content_types=['document'], chat_type=[types.ChatType.CHANNEL, types.ChatType.SUPERGROUP])
async def process_channel_file(message: types.Message):
    # ১. শুধু নির্দিষ্ট চ্যানেল থেকে ফাইল নিবে
    if message.chat.id != FILE_STORAGE_CHANNEL:
        return

    # ২. ক্যাপশনে uid এবং cat আছে কিনা চেক
    caption = message.caption or ""
    if "uid:" not in caption or "cat:" not in caption:
        return

    try:
        # ৩. ক্যাপশন থেকে ইউজারের আইডি এবং ক্যাটাগরি আলাদা করা
        parts = caption.split("|")
        user_id = int(parts[0].split("uid:")[1].strip())
        category = parts[1].split("cat:")[1].strip()
        
        file_id = message.document.file_id
        file_name = message.document.file_name.lower()
        file_path = f"worker_{file_id}_{file_name}"
        
        id_count = 0
        
        # ৪. ফাইল সার্ভারে ডাউনলোড করা
        file_info = await bot.get_file(file_id)
        await bot.download_file(file_info.file_path, destination=file_path)

        # ৫. আইডি গোনা (openpyxl ব্যবহার করে)
        if file_name.endswith('.xlsx'):
            # read_only=True র‍্যাম বাঁচাবে এবং দ্রুত কাজ করবে
            wb = openpyxl.load_workbook(file_path, read_only=True)
            sheet = wb.active
            
            # values_only=True দিয়ে শুধু টেক্সট নেওয়া হচ্ছে
            for row in sheet.iter_rows(values_only=True):
                clean_row = [cell for cell in row if cell is not None and str(cell).strip() != ""]
                if clean_row:
                    id_count += 1
                    
            wb.close() # কাজ শেষে ফাইল বন্ধ করা
                    # ================= ধাপ ৩: ডাটাবেস আপডেট এবং মেসেজ পাঠানো =================
        if id_count > 0:
            # ১. রেট অনুযায়ী ব্যালেন্স বের করা
            rate = IG_RATES.get(category) or FB_RATES.get(category) or 0
            total_pending = id_count * rate
            today = datetime.date.today().strftime("%Y-%m-%d")
            
            # ২. Supabase: Daily Stats Update (আজকের কাজের হিসাব)
            stats_res = await asyncio.to_thread(supabase.table("daily_stats").select("file_count, single_id_count").eq("user_id", user_id).eq("date", today).execute)
            if stats_res.data:
                c_file = stats_res.data[0].get('file_count', 0)
                c_ids = stats_res.data[0].get('single_id_count', 0)
                await asyncio.to_thread(supabase.table("daily_stats").update({"file_count": c_file + 1, "single_id_count": c_ids + id_count}).eq("user_id", user_id).eq("date", today).execute)
            else:
                await asyncio.to_thread(supabase.table("daily_stats").insert({"user_id": user_id, "date": today, "file_count": 1, "single_id_count": id_count}).execute)

            # ৩. Supabase: Pending Balance Update (পেন্ডিং ব্যালেন্স যোগ করা)
            bal_res = await asyncio.to_thread(supabase.table("balances").select("pending_balance").eq("user_id", user_id).execute)
            if bal_res.data:
                c_pending = bal_res.data[0].get('pending_balance', 0)
                await asyncio.to_thread(supabase.table("balances").update({"pending_balance": c_pending + total_pending}).eq("user_id", user_id).execute)

            # ৪. ম্যাজিক: মেইন বটের টোকেন দিয়ে সরাসরি ইউজারকে সাকসেস মেসেজ পাঠানো!
            success_text = (
                f"✅ **আপনার ফাইল সফলভাবে প্রসেস এবং সাবমিট হয়েছে!**\n\n"
                f"📂 ক্যাটাগরি: {category}\n"
                f"📊 আপনার মোট আইডি: **{id_count} টি**\n"
                f"💰 পেন্ডিং ব্যালেন্সে যোগ হলো: **{total_pending:.2f} ৳**\n\n"
                f"🔥 এডমিন রিপোর্ট দিলে আপনার মেইন ব্যালেন্সে টাকা দিয়ে দেওয়া হবে!"
            )
            
            send_msg_url = f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/sendMessage"
            requests.post(send_msg_url, json={"chat_id": user_id, "text": success_text, "parse_mode": "Markdown"})
            
        else:
            # ফাইলে কোনো আইডি না থাকলে
            err_url = f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/sendMessage"
            requests.post(err_url, json={"chat_id": user_id, "text": "❌ আপনার ফাইলে কোনো আইডি পাওয়া যায়নি বা ফাইলটি ফাঁকা।"})

    except Exception as e:
        print(f"Worker Error: {e}")
        # ক্র্যাশ করলে ইউজারকে জানিয়ে দেওয়া
        err_url = f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/sendMessage"
        requests.post(err_url, json={"chat_id": user_id, "text": "❌ ফাইল প্রসেস করতে কারিগরি ত্রুটি হয়েছে। এডমিনকে জানান।"})

    finally:
        # ================= ধাপ ৪: মেমোরি ক্লিনআপ এবং বট স্টার্ট =================
        # 🧹 ম্যাজিক ক্লিনআপ: র‍্যাম একদম খালি করা (Garbage Collector)
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)
        gc.collect() # সাথে সাথে মেমোরি ক্লিয়ার!

import http.server
import socketserver
from threading import Thread

# রেন্ডারকে শান্ত রাখার জন্য ডামি সার্ভার (ফেক পোর্ট)
def keep_alive():
    def run():
        # রেন্ডার নিজে থেকে যে পোর্ট দিবে সেটা নিবে, না পেলে 8080 নিবে
        port = int(os.environ.get("PORT", 8080))
        Handler = http.server.SimpleHTTPRequestHandler
        try:
            with socketserver.TCPServer(("", port), Handler) as httpd:
                print(f"✅ Dummy Server is running on port {port}")
                httpd.serve_forever()
        except Exception as e:
            print(f"Port Error: {e}")
            
    t = Thread(target=run, daemon=True)
    t.start()

# ================= ধাপ ৪: মেমোরি ক্লিনআপ এবং বট স্টার্ট =================
if __name__ == '__main__':
    # ১. পোর্ট ওপেন করা
    keep_alive()
    
    # ২. বট রান করার কমান্ড
    executor.start_polling(dp, skip_updates=True)
    
