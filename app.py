#!/usr/bin/env python3
"""
منصة استضافة بوتات تليجرام - WHISKY ELYOUTUBER
نسخة تعمل بدون مجلد templates - index.html بجوار app.py
"""

import os
import json
import sqlite3
import subprocess
import sys
import threading
import time
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from flask import Flask, request, jsonify
from flask_cors import CORS

# ========== الإعدادات ==========
app = Flask(__name__)
CORS(app)

BOTS_DIR = Path("bots")
BOTS_DIR.mkdir(exist_ok=True)
DB_PATH = "database.db"
SITE_NAME = "𝑾𝑯𝑰𝑺𝑲𝒀 𝑬𝑳𝒀𝑶𝑼𝑻𝑼𝑩𝑬ﺭ"
active_processes: Dict[str, subprocess.Popen] = {}

# ========== قراءة ملف index.html مباشرة ==========
def get_index_html():
    """قراءة ملف index.html من نفس المجلد"""
    index_path = Path("index.html")
    if index_path.exists():
        return index_path.read_text(encoding='utf-8')
    return """
    <!DOCTYPE html>
    <html>
    <head><title>خطأ</title></head>
    <body>
        <h1>⚠️ ملف index.html غير موجود</h1>
        <p>يرجى التأكد من وجود ملف index.html في نفس المجلد</p>
    </body>
    </html>
    """

# ========== قاعدة البيانات ==========
def init_db():
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

# ========== وظائف البوتات ==========
def save_bot_code(bot_name: str, code: str):
    bot_dir = BOTS_DIR / bot_name
    bot_dir.mkdir(exist_ok=True)
    (bot_dir / "bot.py").write_text(code, encoding='utf-8')

def get_bot_code(bot_name: str) -> str:
    bot_file = BOTS_DIR / bot_name / "bot.py"
    return bot_file.read_text(encoding='utf-8') if bot_file.exists() else ""

def add_log(bot_name: str, log: str):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT INTO bot_logs (bot_name, log) VALUES (?, ?)", (bot_name, log))
        conn.commit()

def get_logs(bot_name: str, limit: int = 100) -> List[str]:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute(
            "SELECT log FROM bot_logs WHERE bot_name = ? ORDER BY timestamp DESC LIMIT ?",
            (bot_name, limit)
        )
        return [row[0] for row in cursor.fetchall()][::-1]

def get_bot_status(bot_name: str) -> str:
    if bot_name in active_processes and active_processes[bot_name].poll() is None:
        return "running"
    return "stopped"

def start_bot_process(bot_name: str, bot_code: str, token: str) -> bool:
    bot_dir = BOTS_DIR / bot_name
    bot_dir.mkdir(exist_ok=True)
    save_bot_code(bot_name, bot_code)
    
    try:
        process = subprocess.Popen(
            [sys.executable, str(bot_dir / "bot.py")],
            cwd=bot_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env={**os.environ, "BOT_TOKEN": token}
        )
        active_processes[bot_name] = process
        
        def read_logs():
            for line in process.stdout:
                add_log(bot_name, line.strip())
            for line in process.stderr:
                add_log(bot_name, f"⚠️ {line.strip()}")
        
        threading.Thread(target=read_logs, daemon=True).start()
        return True
    except Exception as e:
        add_log(bot_name, f"❌ فشل التشغيل: {e}")
        return False

def stop_bot_process(bot_name: str) -> bool:
    if bot_name in active_processes:
        try:
            active_processes[bot_name].terminate()
            active_processes[bot_name].wait(timeout=5)
        except:
            active_processes[bot_name].kill()
        del active_processes[bot_name]
        add_log(bot_name, "🛑 تم إيقاف البوت")
        return True
    return False

# ========== مسارات API ==========
@app.route('/')
def index():
    html = get_index_html()
    # استبدال المتغير الديناميكي
    html = html.replace("{{ site_name }}", SITE_NAME)
    return html

@app.route('/api/bots', methods=['GET'])
def get_bots():
    with sqlite3.connect(DB_PATH) as conn:
        bots = conn.execute("SELECT * FROM bots ORDER BY created_at DESC").fetchall()
    
    bots_list = []
    for bot in bots:
        bots_list.append({
            "id": bot[0],
            "name": bot[1],
            "token": bot[2],
            "status": get_bot_status(bot[1]),
            "created_at": bot[4]
        })
    return jsonify(bots_list)

@app.route('/api/bots', methods=['POST'])
def create_bot():
    data = request.json
    name = data.get('name', '').strip()
    token = data.get('token', '').strip()
    code = data.get('code', '')
    
    if not name or not token or not code:
        return jsonify({'error': 'جميع الحقول مطلوبة'}), 400
    
    with sqlite3.connect(DB_PATH) as conn:
        existing = conn.execute("SELECT id FROM bots WHERE name = ?", (name,)).fetchone()
        if existing:
            return jsonify({'error': f'بوت باسم "{name}" موجود بالفعل'}), 400
        
        conn.execute("INSERT INTO bots (name, token) VALUES (?, ?)", (name, token))
        conn.commit()
    
    start_bot_process(name, code, token)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE bots SET status = 'running' WHERE name = ?", (name,))
        conn.commit()
    
    return jsonify({'success': True, 'message': 'تم إنشاء وتشغيل البوت'})

@app.route('/api/bots/<bot_name>', methods=['DELETE'])
def delete_bot(bot_name):
    stop_bot_process(bot_name)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM bots WHERE name = ?", (bot_name,))
        conn.execute("DELETE FROM bot_logs WHERE bot_name = ?", (bot_name,))
        conn.commit()
    shutil.rmtree(BOTS_DIR / bot_name, ignore_errors=True)
    return jsonify({'success': True})

@app.route('/api/bots/<bot_name>/start', methods=['POST'])
def start_bot(bot_name):
    with sqlite3.connect(DB_PATH) as conn:
        bot = conn.execute("SELECT * FROM bots WHERE name = ?", (bot_name,)).fetchone()
        if not bot:
            return jsonify({'error': 'البوت غير موجود'}), 404
        
        code = get_bot_code(bot_name)
        token = bot[2]
        
        success = start_bot_process(bot_name, code, token)
        if success:
            conn.execute("UPDATE bots SET status = 'running' WHERE name = ?", (bot_name,))
            conn.commit()
    
    return jsonify({'success': success})

@app.route('/api/bots/<bot_name>/stop', methods=['POST'])
def stop_bot(bot_name):
    success = stop_bot_process(bot_name)
    if success:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("UPDATE bots SET status = 'stopped' WHERE name = ?", (bot_name,))
            conn.commit()
    return jsonify({'success': success})

@app.route('/api/bots/<bot_name>/restart', methods=['POST'])
def restart_bot(bot_name):
    stop_bot_process(bot_name)
    time.sleep(2)
    
    with sqlite3.connect(DB_PATH) as conn:
        bot = conn.execute("SELECT * FROM bots WHERE name = ?", (bot_name,)).fetchone()
        if not bot:
            return jsonify({'error': 'البوت غير موجود'}), 404
        
        code = get_bot_code(bot_name)
        token = bot[2]
        
        success = start_bot_process(bot_name, code, token)
        status = "running" if success else "stopped"
        conn.execute("UPDATE bots SET status = ? WHERE name = ?", (status, bot_name))
        conn.commit()
    
    return jsonify({'success': success})

@app.route('/api/bots/<bot_name>/logs', methods=['GET'])
def get_bot_logs(bot_name):
    limit = request.args.get('limit', 100, type=int)
    logs = get_logs(bot_name, limit)
    return jsonify({'logs': logs})

@app.route('/health')
def health_check():
    return jsonify({
        'status': 'healthy',
        'site': SITE_NAME,
        'bots_count': len(active_processes),
        'timestamp': datetime.now().isoformat()
    })

# ========== تشغيل التطبيق ==========
if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    print(f"""
    ╔══════════════════════════════════════════════════════════════╗
    ║                                                              ║
    ║     🚀 {SITE_NAME} - منصة استضافة البوتات         ║
    ║                                                              ║
    ║     📍 التشغيل على المنفذ: {port}                              ║
    ║                                                              ║
    ╚══════════════════════════════════════════════════════════════╝
    """)
    app.run(host='0.0.0.0', port=port, debug=False)