import os
import requests
import re
import threading
import time # 👈 เพิ่มไลบรารีสำหรับจัดการเวลา
from flask import Flask, request
from flask import Flask, request, jsonify # 👈 เพิ่ม jsonify
from flask_cors import CORS # 👈 เพิ่มไลบรารี CORS

app = Flask(__name__)
CORS(app) # 👈 เปิดทางให้ Vercel โทรมาคุยได้

# --- CONFIG (มหาบูชา) ---
GITHUB_USERNAME = "mrtharatoy"
REPO_NAME = "fb-mahabucha-bot" 
BRANCH = "main"
FOLDER_NAME = "images" 
PAGE_ACCESS_TOKEN = os.environ.get('PAGE_ACCESS_TOKEN')
VERIFY_TOKEN = os.environ.get('VERIFY_TOKEN')
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')

CACHED_FILES = {}
FILES_LOADED = False
lock = threading.Lock() 

# --- 1. โหลดรายชื่อรูป ---
def update_file_list():
    global CACHED_FILES, FILES_LOADED
    print("🔄 Loading file list from GitHub...")
    api_url = f"https://api.github.com/repos/{GITHUB_USERNAME}/{REPO_NAME}/contents/{FOLDER_NAME}?ref={BRANCH}"
    headers = {"User-Agent": "Bot", "Accept": "application/vnd.github.v3+json"}
    if GITHUB_TOKEN: headers["Authorization"] = f"token {GITHUB_TOKEN}"
    
    try:
        r = requests.get(api_url, headers=headers, timeout=15)
        if r.status_code == 200:
            data = r.json()
            temp_cache = {}
            for item in data:
                if item['type'] == 'file':
                    key = item['name'].rsplit('.', 1)[0].strip().lower()
                    temp_cache[key] = item['name']
            
            CACHED_FILES = temp_cache
            FILES_LOADED = True
            print(f"✅ FILES READY: {len(CACHED_FILES)} images.")
        else:
            print(f"⚠️ Github Error: {r.status_code} - {r.text}")
    except Exception as e:
        print(f"❌ Error loading files: {e}")

def get_image_url(filename):
    return f"https://raw.githubusercontent.com/{GITHUB_USERNAME}/{REPO_NAME}/{BRANCH}/{FOLDER_NAME}/{filename}"

def take_thread_control(recipient_id):
    params = {"access_token": PAGE_ACCESS_TOKEN}
    data = {"recipient": {"id": recipient_id}}
    requests.post("https://graph.facebook.com/v19.0/me/take_thread_control", params=params, json=data)

def send_message(recipient_id, text):
    params = {"access_token": PAGE_ACCESS_TOKEN}
    data = {"recipient": {"id": recipient_id}, "message": {"text": text, "metadata": "BOT_SENT_THIS"}}
    r = requests.post("https://graph.facebook.com/v19.0/me/messages", params=params, json=data)
    
    if r.status_code != 200:
        data_tag = {"recipient": {"id": recipient_id}, "messaging_type": "MESSAGE_TAG", "tag": "CONFIRMED_EVENT_UPDATE", "message": {"text": text, "metadata": "BOT_SENT_THIS"}}
        requests.post("https://graph.facebook.com/v19.0/me/messages", params=params, json=data_tag)

def send_image(recipient_id, image_url):
    params = {"access_token": PAGE_ACCESS_TOKEN}
    data = {"recipient": {"id": recipient_id}, "message": {"attachment": {"type": "image", "payload": {"url": image_url, "is_reusable": True}}, "metadata": "BOT_SENT_THIS"}}
    r = requests.post("https://graph.facebook.com/v19.0/me/messages", params=params, json=data)
    
    if r.status_code != 200:
        data_tag = {"recipient": {"id": recipient_id}, "messaging_type": "MESSAGE_TAG", "tag": "CONFIRMED_EVENT_UPDATE", "message": {"attachment": {"type": "image", "payload": {"url": image_url, "is_reusable": True}}, "metadata": "BOT_SENT_THIS"}}
        requests.post("https://graph.facebook.com/v19.0/me/messages", params=params, json=data_tag)

# --- 2. LOGIC กรองรหัส ---
def process_message(target_id, text, is_admin_sender):
    global FILES_LOADED
    
    if not FILES_LOADED:
        with lock:
            if not FILES_LOADED:
                take_thread_control(target_id)
                send_message(target_id, "⏳ ระบบกำลังดึงข้อมูลภาพ กรุณารอสักครู่นะครับ...")
                update_file_list()
                if not FILES_LOADED:
                    send_message(target_id, "❌ ขออภัยครับ ระบบดึงข้อมูลขัดข้อง รบกวนแจ้งแอดมินครับ 🙏")
                    return

    text_cleaned = text.lower().replace(" ", "")
    exact_pattern = r'(?:269|999)[a-z0-9]{7}'
    valid_codes = re.findall(exact_pattern, text_cleaned)
    attempt_pattern = r'(?:269|999)[a-z0-9]*'
    all_attempts = re.findall(attempt_pattern, text_cleaned)

    found_actions = [] 
    unknown_codes = []

    for code in valid_codes:
        if code in CACHED_FILES:
            if (code, CACHED_FILES[code]) not in found_actions:
                found_actions.append((code, CACHED_FILES[code]))
        else:
            if code not in unknown_codes: unknown_codes.append(code)

    for code in all_attempts:
        if len(code) >= 5: 
            if code not in valid_codes and code not in unknown_codes:
                matched = next((k for k in CACHED_FILES.keys() if k in code), None)
                if matched:
                    if (matched, CACHED_FILES[matched]) not in found_actions:
                        found_actions.append((matched, CACHED_FILES[matched]))
                else:
                    unknown_codes.append(code)

    if not found_actions and not unknown_codes: return 

    if found_actions:
        take_thread_control(target_id)
        intro_msg = (
            "📸 ขออนุญาตส่งภาพนะครับ\n\n"
            "รวมภาพงานพิธี กดได้ที่ link นี้\n\n"
            " -> https://siamganesh-online.vercel.app/\n\n"
            "หรือ รับชมได้ที่หน้าเพจ \"มหาบูชา\""
        )
        send_message(target_id, intro_msg)

        for code_key, filename in found_actions:
            send_message(target_id, f"ภาพถาดถวาย รหัส : {code_key.upper()}")
            send_image(target_id, get_image_url(filename))

    if unknown_codes:
        take_thread_control(target_id)
        msg = (
            "⚠️ ขออภัยครับ \n \n"
            "ไม่พบภาพถาดถวายจากรหัสของท่าน \n \n"
            "รบกวนรอแอดมินเข้ามาตรวจสอบให้ ซักครู่นะครับ ⏳"
        )
        send_message(target_id, msg)

    # --- โค้ด API สำหรับ Vercel (ปรับปรุงเป็น Exact Match) ---
    @app.route('/api/search', methods=['GET'])
    def search_api():
        # 1. รับค่าที่แอดมินพิมพ์มา (ไม่ใช้ .lower() เพื่อรักษาตัวพิมพ์เล็ก-ใหญ่ไว้)
        code = request.args.get('code', '').strip() 
        
        if not code:
            return jsonify({"found": False, "message": "กรุณาระบุรหัสที่ต้องการค้นหา"}), 400
    
        if not FILES_LOADED:
            return jsonify({"found": False, "message": "ระบบกำลังเตรียมข้อมูล กรุณาลองใหม่ในอีก 1 นาที"}), 503
    
        matched_filename = None
        code_lower = code.lower() # แปลงชั่วคราวเพื่อไปควานหาในระบบ
        
        # 2. เช็คว่ารหัสนี้มีในระบบไหม
        if code_lower in CACHED_FILES:
            actual_filename = CACHED_FILES[code_lower] # ดึงชื่อไฟล์จริงออกมา (เช่น '269AbC1234.jpg')
            exact_name_without_ext = actual_filename.rsplit('.', 1)[0] # ตัดนามสกุลไฟล์ออก
            
            # 3. นำชื่อไฟล์จริง มาเทียบกับรหัสที่พิมพ์มา "แบบตรงกันเป๊ะๆ (Exact Match)"
            if exact_name_without_ext == code:
                matched_filename = actual_filename
    
        # 4. ส่งผลลัพธ์กลับไปหา Vercel
        if matched_filename:
            image_url = get_image_url(matched_filename)
            return jsonify({
                "found": True, 
                "code": code, 
                "image_url": image_url
            }), 200
        else:
            # ถ้าพิมพ์ผิดแม้แต่ตัวเดียว (เช่น พิมพ์เล็กแทนพิมพ์ใหญ่) หรือหาไม่เจอ จะเด้งมาตรงนี้ทันที
            return jsonify({"found": False, "message": "ไม่พบรูปภาพจากรหัสนี้ (โปรดตรวจสอบตัวพิมพ์เล็ก-ใหญ่ให้ถูกต้อง)"}), 404
            
# --- 3. WEBHOOK ---
@app.route('/', methods=['GET'])
def verify():
    if request.args.get("hub.mode") == "subscribe" and request.args.get("hub.verify_token") == VERIFY_TOKEN:
        return request.args.get("hub.challenge"), 200
    return "Bot Running", 200

@app.route('/', methods=['POST'])
def webhook():
    data = request.json
    if data['object'] == 'page':
        for entry in data['entry']:
            if 'messaging' in entry:
                for event in entry['messaging']:
                    if 'message' in event:
                        text = event['message'].get('text', '')
                        if event.get('message', {}).get('metadata') == "BOT_SENT_THIS": continue
                        
                        # 🔥 ด่านสกัดกั้นข้อความเก่าค้างท่อ (กันบอทย้อนตอบตอนเปิดเซิร์ฟ)
                        message_timestamp = event.get('timestamp')
                        if message_timestamp:
                            current_time = int(time.time() * 1000) # เวลาปัจจุบัน
                            time_diff_seconds = (current_time - message_timestamp) / 1000
                            # ถ้าข้อความส่งมาเกิน 5 นาทีที่แล้ว (300 วินาที) ข้ามเลย!
                            if time_diff_seconds > 300:
                                print(f"⏳ Ignored old message from {time_diff_seconds} seconds ago.")
                                continue
                        
                        is_echo = event.get('message', {}).get('is_echo', False)
                        if is_echo:
                            if 'recipient' in event and 'id' in event['recipient']:
                                process_message(event['recipient']['id'], text, is_admin_sender=True)
                        else:
                            process_message(event['sender']['id'], text, is_admin_sender=False)
    return "ok", 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
