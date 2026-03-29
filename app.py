import os
import requests
import re
import threading
import time
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# --- ⚙️ CONFIG (ฉบับ Backend รวมศูนย์) ---
GITHUB_USERNAME = "mrtharatoy"
REPO_NAME = "siamganesh-online-backend" # 👈 ชี้ไปที่บ้านหลังใหม่แล้ว
BRANCH = "main"

# ดึงค่าจาก Environment Variables
MAHABUCHA_PAGE_ID = os.environ.get('MAHABUCHA_PAGE_ID')
MAHABUCHA_TOKEN = os.environ.get('MAHABUCHA_TOKEN')
MUTETEAM_PAGE_ID = os.environ.get('MUTETEAM_PAGE_ID')
MUTETEAM_TOKEN = os.environ.get('MUTETEAM_TOKEN')
VERIFY_TOKEN = os.environ.get('VERIFY_TOKEN')
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')

# แยกตะกร้าเก็บรูปเป็น 2 เพจ
CACHED_FILES = {
    "mahabucha": {},
    "muteteam": {}
}
FILES_LOADED = False
lock = threading.Lock() 

# --- 1. โหลดรายชื่อรูปจากทั้ง 2 โฟลเดอร์ ---
def update_file_list():
    global CACHED_FILES, FILES_LOADED
    print("🔄 Loading file lists from GitHub...")
    headers = {"User-Agent": "Bot", "Accept": "application/vnd.github.v3+json"}
    if GITHUB_TOKEN: headers["Authorization"] = f"token {GITHUB_TOKEN}"
    
    pages = ["mahabucha", "muteteam"]
    
    for page in pages:
        api_url = f"https://api.github.com/repos/{GITHUB_USERNAME}/{REPO_NAME}/contents/images/{page}?ref={BRANCH}"
        try:
            r = requests.get(api_url, headers=headers, timeout=15)
            if r.status_code == 200:
                data = r.json()
                temp_cache = {}
                for item in data:
                    if item['type'] == 'file' and item['name'] != '.keep': 
                        key = item['name'].rsplit('.', 1)[0].strip().lower()
                        temp_cache[key] = item['name']
                CACHED_FILES[page] = temp_cache
                print(f"✅ {page.upper()} READY: {len(temp_cache)} images.")
            else:
                print(f"⚠️ Github Error for {page}: {r.status_code} - {r.text}")
        except Exception as e:
            print(f"❌ Error loading files for {page}: {e}")
            
    FILES_LOADED = True

def get_image_url(page_name, filename):
    return f"https://raw.githubusercontent.com/{GITHUB_USERNAME}/{REPO_NAME}/{BRANCH}/images/{page_name}/{filename}"

# --- ฟังก์ชันสั่งงาน Facebook (สลับ Token อัตโนมัติ) ---
def get_page_token(page_id):
    if page_id == MAHABUCHA_PAGE_ID: return MAHABUCHA_TOKEN
    elif page_id == MUTETEAM_PAGE_ID: return MUTETEAM_TOKEN
    return None

def take_thread_control(recipient_id, page_id):
    token = get_page_token(page_id)
    if not token: return
    params = {"access_token": token}
    data = {"recipient": {"id": recipient_id}}
    requests.post("https://graph.facebook.com/v19.0/me/take_thread_control", params=params, json=data)

def send_message(recipient_id, text, page_id):
    token = get_page_token(page_id)
    if not token: return
    params = {"access_token": token}
    data = {"recipient": {"id": recipient_id}, "message": {"text": text, "metadata": "BOT_SENT_THIS"}}
    r = requests.post("https://graph.facebook.com/v19.0/me/messages", params=params, json=data)
    
    if r.status_code != 200:
        data_tag = {"recipient": {"id": recipient_id}, "messaging_type": "MESSAGE_TAG", "tag": "CONFIRMED_EVENT_UPDATE", "message": {"text": text, "metadata": "BOT_SENT_THIS"}}
        requests.post("https://graph.facebook.com/v19.0/me/messages", params=params, json=data_tag)

def send_image(recipient_id, image_url, page_id):
    token = get_page_token(page_id)
    if not token: return
    params = {"access_token": token}
    data = {"recipient": {"id": recipient_id}, "message": {"attachment": {"type": "image", "payload": {"url": image_url, "is_reusable": True}}, "metadata": "BOT_SENT_THIS"}}
    r = requests.post("https://graph.facebook.com/v19.0/me/messages", params=params, json=data)
    
    if r.status_code != 200:
        data_tag = {"recipient": {"id": recipient_id}, "messaging_type": "MESSAGE_TAG", "tag": "CONFIRMED_EVENT_UPDATE", "message": {"attachment": {"type": "image", "payload": {"url": image_url, "is_reusable": True}}, "metadata": "BOT_SENT_THIS"}}
        requests.post("https://graph.facebook.com/v19.0/me/messages", params=params, json=data_tag)

# --- 2. LOGIC กรองรหัสสำหรับบอท Messenger ---
def process_message(target_id, text, page_id):
    global FILES_LOADED
    
    page_name = "mahabucha" if page_id == MAHABUCHA_PAGE_ID else "muteteam" if page_id == MUTETEAM_PAGE_ID else None
    if not page_name: return 
    
    if not FILES_LOADED:
        with lock:
            if not FILES_LOADED:
                take_thread_control(target_id, page_id)
                send_message(target_id, "⏳ ระบบกำลังดึงข้อมูลภาพ กรุณารอสักครู่นะครับ...", page_id)
                update_file_list()
                if not FILES_LOADED:
                    send_message(target_id, "❌ ขออภัยครับ ระบบดึงข้อมูลขัดข้อง รบกวนแจ้งแอดมินครับ 🙏", page_id)
                    return

    current_cache = CACHED_FILES[page_name]

    text_cleaned = text.lower().replace(" ", "")
    exact_pattern = r'(?:269|999)[a-z0-9]{7}'
    valid_codes = re.findall(exact_pattern, text_cleaned)
    attempt_pattern = r'(?:269|999)[a-z0-9]*'
    all_attempts = re.findall(attempt_pattern, text_cleaned)

    found_actions = [] 
    unknown_codes = []

    for code in valid_codes:
        if code in current_cache:
            if (code, current_cache[code]) not in found_actions:
                found_actions.append((code, current_cache[code]))
        else:
            if code not in unknown_codes: unknown_codes.append(code)

    for code in all_attempts:
        if len(code) >= 5: 
            if code not in valid_codes and code not in unknown_codes:
                if code in current_cache:
                    if (code, current_cache[code]) not in found_actions:
                        found_actions.append((code, current_cache[code]))
                else:
                    unknown_codes.append(code)

    if not found_actions and not unknown_codes: return 

    if found_actions:
        take_thread_control(target_id, page_id)
        
        if page_name == "mahabucha":
            intro_msg = "📸 ขออนุญาตส่งภาพนะครับ\n\nรวมภาพงานพิธี กดได้ที่ link นี้\n\n -> https://siamganesh-online-frontend.vercel.app/\n\nหรือ รับชมได้ที่หน้าเพจ \"มหาบูชา\""
        else:
            intro_msg = "📸 ขออนุญาตส่งภาพนะครับ\n\nรวมภาพงานพิธี กดได้ที่ link นี้\n\n -> linktr.ee/muteteam\n\nหรือ รับชมได้ที่หน้าเพจ \"มูเตทีม\"\n\nทีมงานเทวาลัยสยามคเณศ ขอขอบคุณครับ"
            
        send_message(target_id, intro_msg, page_id)

        for code_key, filename in found_actions:
            send_message(target_id, f"ภาพถาดถวาย รหัส : {code_key.upper()}", page_id)
            send_image(target_id, get_image_url(page_name, filename), page_id)

    if unknown_codes:
        take_thread_control(target_id, page_id)
        msg = "⚠️ ขออภัยครับ \n \nไม่พบภาพถาดถวายจากรหัสของท่าน \n \nรบกวนรอแอดมินเข้ามาตรวจสอบให้ ซักครู่นะครับ ⏳"
        send_message(target_id, msg, page_id)

# --- 3. API สำหรับ Web Vercel ---
@app.route('/api/search', methods=['GET'])
def search_api():
    global FILES_LOADED
    
    page_param = request.args.get('page', '').strip().lower()
    code = request.args.get('code', '').strip() 
    
    if page_param not in ["mahabucha", "muteteam"]:
        return jsonify({"found": False, "message": "กรุณาระบุเพจที่ต้องการค้นหา (page=mahabucha หรือ page=muteteam)"}), 400
        
    if not code:
        return jsonify({"found": False, "message": "กรุณาระบุรหัสที่ต้องการค้นหา"}), 400

    if not re.match(r'^(269|999)[A-Za-z0-9]{7}$', code):
        return jsonify({"found": False, "message": "รูปแบบรหัสไม่ถูกต้อง (ต้องมี 10 หลักพอดีเป๊ะ)"}), 400

    if not FILES_LOADED:
        with lock:
            if not FILES_LOADED:
                update_file_list()
                
    if not FILES_LOADED:
        return jsonify({"found": False, "message": "ระบบกำลังเตรียมข้อมูลจาก GitHub กรุณากดค้นหาอีกครั้ง"}), 503

    matched_filename = None
    code_lower = code.lower()
    current_cache = CACHED_FILES.get(page_param, {})
    
    if code_lower in current_cache:
        actual_filename = current_cache[code_lower]
        exact_name_without_ext = actual_filename.rsplit('.', 1)[0]
        
        if exact_name_without_ext == code:
            matched_filename = actual_filename

    if matched_filename:
        image_url = get_image_url(page_param, matched_filename)
        return jsonify({
            "found": True, 
            "code": code, 
            "image_url": image_url,
            "filename": matched_filename
        }), 200
    else:
        return jsonify({"found": False, "message": "ไม่พบรูปภาพ (โปรดตรวจสอบตัวพิมพ์เล็ก-ใหญ่ให้ถูกต้อง)"}), 404

# --- 4. WEBHOOK ของ Facebook ---
@app.route('/', methods=['GET'])
def verify():
    if request.args.get("hub.mode") == "subscribe" and request.args.get("hub.verify_token") == VERIFY_TOKEN:
        return request.args.get("hub.challenge"), 200
    
    html_page = """
    <!DOCTYPE html>
    <html lang="th">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Siamganesh Online Backend</title>
        <link href="https://fonts.googleapis.com/css2?family=Sarabun:wght@400;700&display=swap" rel="stylesheet">
        <style>
            body { font-family: 'Sarabun', sans-serif; background-color: #f0f2f5; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
            .card { background: white; padding: 40px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); text-align: center; max-width: 450px; width: 90%; border-top: 5px solid #2c3e50; }
            h1 { color: #2c3e50; margin-bottom: 10px; }
            p { color: #555; font-size: 16px; line-height: 1.5; }
            .status-badge { display: inline-block; background-color: #2ecc71; color: white; padding: 10px 20px; border-radius: 50px; font-weight: bold; font-size: 14px; margin-top: 20px; box-shadow: 0 2px 5px rgba(46, 204, 113, 0.4); }
            .footer { margin-top: 30px; font-size: 12px; color: #aaa; }
        </style>
    </head>
    <body>
        <div class="card">
            <h1>ศูนย์รวม API สยามคเณศ</h1>
            <p>ระบบ Backend สำหรับจัดการแชทบอท มหาบูชา และ มูเตทีม</p>
            <div class="status-badge">🟢 ระบบกำลังทำงาน (Online)</div>
            <div class="footer">siamganesh-online-backend</div>
        </div>
    </body>
    </html>
    """
    return html_page, 200

@app.route('/', methods=['POST'])
def webhook():
    data = request.json
    if data['object'] == 'page':
        for entry in data['entry']:
            page_id = entry.get('id') 
            
            if 'messaging' in entry:
                for event in entry['messaging']:
                    if 'message' in event:
                        text = event['message'].get('text', '')
                        if event.get('message', {}).get('metadata') == "BOT_SENT_THIS": continue
                        
                        message_timestamp = event.get('timestamp')
                        if message_timestamp:
                            current_time = int(time.time() * 1000)
                            time_diff_seconds = (current_time - message_timestamp) / 1000
                            if time_diff_seconds > 300: 
                                continue
                        
                        is_echo = event.get('message', {}).get('is_echo', False)
                        if is_echo:
                            if 'recipient' in event and 'id' in event['recipient']:
                                process_message(event['recipient']['id'], text, page_id)
                        else:
                            process_message(event['sender']['id'], text, page_id)
    return "ok", 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
