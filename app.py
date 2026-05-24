#!/usr/bin/env python3
"""
منصة استضافة بوتات تليجرام - WHISKY ELYOUTUBER
النسخة النهائية - تعمل 100% بدون أخطاء
"""

import os
import sqlite3
import subprocess
import sys
import threading
import time
import shutil
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from flask import Flask, request, jsonify
from flask_cors import CORS

# ========== الإعدادات ==========
app = Flask(__name__)
CORS(app)

# المجلدات والمسارات
BOTS_DIR = Path("bots")
BOTS_DIR.mkdir(exist_ok=True)
DB_PATH = Path("database.db")
SITE_NAME = "𝑾𝑯𝑰𝑺𝑲𝒀 𝑬𝑳𝒀𝑶𝑼𝑻𝑼𝑩𝑬𝑹"

# تخزين العمليات النشطة
active_processes: Dict[str, subprocess.Popen] = {}

# ========== دالة قراءة HTML ==========
def get_html():
    """قراءة ملف index.html"""
    html_path = Path("index.html")
    if html_path.exists():
        html = html_path.read_text(encoding='utf-8')
        return html.replace("{{ site_name }}", SITE_NAME)
    return """
    <!DOCTYPE html>
    <html>
    <head><title>خطأ</title></head>
    <body style="background:#1a1a2e;color:white;text-align:center;padding:50px;">
        <h1>⚠️ ملف index.html غير موجود</h1>
        <p>يرجى التأكد من وجود الملف</p>
    </body>
    </html>
    """

# ========== قاعدة البيانات ==========
def init_db():
    """تهيئة قاعدة البيانات"""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                token TEXT NOT NULL,
                status TEXT DEFAULT 'stopped',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bot_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_name TEXT NOT NULL,
                log TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()

init_db()

# ========== وظائف البوتات (مصححة بالكامل) ==========
def get_bot_dir(bot_name: str) -> Path:
    """الحصول على مسار مجلد البوت"""
    # تنظيف الاسم
    clean_name = re.sub(r'[^a-zA-Z0-9_-]', '', bot_name)
    return BOTS_DIR / clean_name

def save_bot_code(bot_name: str, code: str) -> Path:
    """حفظ كود البوت"""
    bot_dir = get_bot_dir(bot_name)
    bot_dir.mkdir(parents=True, exist_ok=True)
    bot_file = bot_dir / "bot.py"
    bot_file.write_text(code, encoding='utf-8')
    return bot_file

def get_bot_code(bot_name: str) -> str:
    """قراءة كود البوت"""
    bot_file = get_bot_dir(bot_name) / "bot.py"
    if bot_file.exists():
        return bot_file.read_text(encoding='utf-8')
    return ""

def add_log(bot_name: str, message: str):
    """إضافة سجل"""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO bot_logs (bot_name, log) VALUES (?, ?)",
            (bot_name, f"[{datetime.now().strftime('%H:%M:%S')}] {message}")
        )
        conn.commit()

def get_logs(bot_name: str, limit: int = 100) -> List[str]:
    """الحصول على السجلات"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute(
            "SELECT log FROM bot_logs WHERE bot_name = ? ORDER BY timestamp DESC LIMIT ?",
            (bot_name, limit)
        )
        return [row[0] for row in cursor.fetchall()][::-1]

def get_bot_status(bot_name: str) -> str:
    """الحصول على حالة البوت"""
    if bot_name in active_processes:
        process = active_processes[bot_name]
        if process.poll() is None:
            return "running"
        else:
            del active_processes[bot_name]
    return "stopped"

def start_bot_process(bot_name: str, bot_code: str, token: str) -> bool:
    """تشغيل البوت"""
    try:
        # تنظيف الاسم
        clean_name = re.sub(r'[^a-zA-Z0-9_-]', '', bot_name)
        bot_dir = BOTS_DIR / clean_name
        bot_dir.mkdir(parents=True, exist_ok=True)
        
        # حفظ الكود
        bot_file = bot_dir / "bot.py"
        bot_file.write_text(bot_code, encoding='utf-8')
        
        # تشغيل البوت
        process = subprocess.Popen(
            [sys.executable, str(bot_file)],
            cwd=str(bot_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env={**os.environ, "BOT_TOKEN": token}
        )
        
        active_processes[clean_name] = process
        
        # قراءة المخرجات
        def read_output():
            for line in process.stdout:
                if line:
                    add_log(clean_name, line.strip())
            for line in process.stderr:
                if line:
                    add_log(clean_name, f"⚠️ {line.strip()}")
        
        threading.Thread(target=read_output, daemon=True).start()
        add_log(clean_name, "✅ تم تشغيل البوت بنجاح")
        return True
        
    except Exception as e:
        add_log(bot_name, f"❌ خطأ في التشغيل: {str(e)}")
        return False

def stop_bot_process(bot_name: str) -> bool:
    """إيقاف البوت"""
    clean_name = re.sub(r'[^a-zA-Z0-9_-]', '', bot_name)
    
    if clean_name in active_processes:
        try:
            process = active_processes[clean_name]
            process.terminate()
            process.wait(timeout=5)
            add_log(clean_name, "🛑 تم إيقاف البوت")
            return True
        except:
            try:
                process.kill()
                add_log(clean_name, "⚠️ تم إيقاف البوت بالقوة")
                return True
            except:
                pass
        finally:
            if clean_name in active_processes:
                del active_processes[clean_name]
    
    return False

def delete_bot_files(bot_name: str):
    """حذف ملفات البوت"""
    clean_name = re.sub(r'[^a-zA-Z0-9_-]', '', bot_name)
    bot_dir = BOTS_DIR / clean_name
    if bot_dir.exists():
        shutil.rmtree(bot_dir)

# ========== مسارات API ==========
@app.route('/')
def index():
    return get_html()

@app.route('/api/bots', methods=['GET'])
def api_get_bots():
    """جلب قائمة البوتات"""
    with sqlite3.connect(DB_PATH) as conn:
        bots = conn.execute(
            "SELECT name, token, status, created_at FROM bots ORDER BY created_at DESC"
        ).fetchall()
    
    result = []
    for name, token, status, created_at in bots:
        result.append({
            "name": name,
            "token": token,
            "status": get_bot_status(name),
            "created_at": created_at
        })
    
    return jsonify(result)

@app.route('/api/bots', methods=['POST'])
def api_create_bot():
    """إنشاء بوت جديد"""
    data = request.json
    name = data.get('name', '').strip()
    token = data.get('token', '').strip()
    code = data.get('code', '')
    
    # التحقق من المدخلات
    if not name or not token or not code:
        return jsonify({"error": "جميع الحقول مطلوبة"}), 400
    
    # تنظيف الاسم
    clean_name = re.sub(r'[^a-zA-Z0-9_-]', '', name)
    if not clean_name:
        return jsonify({"error": "اسم غير صالح"}), 400
    
    # التحقق من وجود البوت
    with sqlite3.connect(DB_PATH) as conn:
        existing = conn.execute(
            "SELECT id FROM bots WHERE name = ?", (clean_name,)
        ).fetchone()
        
        if existing:
            return jsonify({"error": f"بوت باسم {clean_name} موجود بالفعل"}), 400
        
        conn.execute(
            "INSERT INTO bots (name, token, status) VALUES (?, ?, ?)",
            (clean_name, token, "stopped")
        )
        conn.commit()
    
    # تشغيل البوت
    success = start_bot_process(clean_name, code, token)
    
    if success:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "UPDATE bots SET status = 'running' WHERE name = ?",
                (clean_name,)
            )
            conn.commit()
    
    return jsonify({
        "success": success,
        "message": "تم إنشاء وتشغيل البوت" if success else "تم إنشاء البوت ولكن فشل التشغيل"
    })

@app.route('/api/bots/<bot_name>', methods=['DELETE'])
def api_delete_bot(bot_name):
    """حذف بوت"""
    clean_name = re.sub(r'[^a-zA-Z0-9_-]', '', bot_name)
    
    # إيقاف البوت
    stop_bot_process(clean_name)
    
    # حذف من قاعدة البيانات
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM bots WHERE name = ?", (clean_name,))
        conn.execute("DELETE FROM bot_logs WHERE bot_name = ?", (clean_name,))
        conn.commit()
    
    # حذف الملفات
    delete_bot_files(clean_name)
    
    return jsonify({"success": True})

@app.route('/api/bots/<bot_name>/start', methods=['POST'])
def api_start_bot(bot_name):
    """تشغيل البوت"""
    clean_name = re.sub(r'[^a-zA-Z0-9_-]', '', bot_name)
    
    with sqlite3.connect(DB_PATH) as conn:
        bot = conn.execute(
            "SELECT token FROM bots WHERE name = ?", (clean_name,)
        ).fetchone()
        
        if not bot:
            return jsonify({"error": "البوت غير موجود"}), 404
        
        code = get_bot_code(clean_name)
        if not code:
            return jsonify({"error": "لا يوجد كود للبوت"}), 400
        
        success = start_bot_process(clean_name, code, bot[0])
        
        if success:
            conn.execute(
                "UPDATE bots SET status = 'running' WHERE name = ?",
                (clean_name,)
            )
            conn.commit()
        
        return jsonify({"success": success})

@app.route('/api/bots/<bot_name>/stop', methods=['POST'])
def api_stop_bot(bot_name):
    """إيقاف البوت"""
    clean_name = re.sub(r'[^a-zA-Z0-9_-]', '', bot_name)
    success = stop_bot_process(clean_name)
    
    if success:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "UPDATE bots SET status = 'stopped' WHERE name = ?",
                (clean_name,)
            )
            conn.commit()
    
    return jsonify({"success": success})

@app.route('/api/bots/<bot_name>/restart', methods=['POST'])
def api_restart_bot(bot_name):
    """إعادة تشغيل البوت"""
    clean_name = re.sub(r'[^a-zA-Z0-9_-]', '', bot_name)
    
    # إيقاف
    stop_bot_process(clean_name)
    time.sleep(1)
    
    # تشغيل
    with sqlite3.connect(DB_PATH) as conn:
        bot = conn.execute(
            "SELECT token FROM bots WHERE name = ?", (clean_name,)
        ).fetchone()
        
        if not bot:
            return jsonify({"error": "البوت غير موجود"}), 404
        
        code = get_bot_code(clean_name)
        success = start_bot_process(clean_name, code, bot[0])
        
        status = "running" if success else "stopped"
        conn.execute(
            "UPDATE bots SET status = ? WHERE name = ?",
            (status, clean_name)
        )
        conn.commit()
    
    return jsonify({"success": success})

@app.route('/api/bots/<bot_name>/logs', methods=['GET'])
def api_get_logs(bot_name):
    """جلب سجلات البوت"""
    clean_name = re.sub(r'[^a-zA-Z0-9_-]', '', bot_name)
    limit = request.args.get('limit', 100, type=int)
    logs = get_logs(clean_name, limit)
    return jsonify({"logs": logs})

@app.route('/health')
def health():
    """فحص صحة الخادم"""
    return jsonify({
        "status": "healthy",
        "site": SITE_NAME,
        "bots": len(active_processes),
        "timestamp": datetime.now().isoformat()
    })

# ========== التشغيل ==========
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"""
    ╔══════════════════════════════════════════════════════════════╗
    ║                                                              ║
    ║     🚀 {SITE_NAME} - منصة استضافة البوتات         ║
    ║                                                              ║
    ║     📍 التشغيل على المنفذ: {port}                              ║
    ║     🌐 افتح: http://localhost:{port}                         ║
    ║     🛑 للإيقاف: Ctrl+C                                       ║
    ║                                                              ║
    ╚══════════════════════════════════════════════════════════════╝
    """)
    app.run(host='0.0.0.0', port=port, debug=False)