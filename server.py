#!/usr/bin/env python3
import os
import sys
import json
import tempfile
import time
import hashlib
import sqlite3
import requests
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS

try:
    import pefile
    import capstone
except ImportError:
    print("❌ يرجى تثبيت المكتبات المطلوبة:")
    print("pip3 install flask flask-cors pefile capstone requests")
    sys.exit(1)

# ================================================================
# إعدادات البوت والتطبيق
# ================================================================
TOKEN = "8602190557:AAGXAF9elW1heKnZhNTxUSxPkkQzd45RagM"  # ضع توكن البوت هنا
CHAT_ID = "755037218"  # ضع معرف الدردشة الخاص بك هنا
ADMIN_IDS = [CHAT_ID]  # قائمة المعرفات المسموح لها بالتحكم

# ملف قاعدة البيانات
DB_FILE = 'bot_data.db'

app = Flask(__name__)
CORS(app)

# ================================================================
# إعداد قاعدة البيانات
# ================================================================

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS visitors
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  fingerprint TEXT UNIQUE,
                  ip TEXT,
                  user_agent TEXT,
                  device_type TEXT,
                  browser TEXT,
                  os TEXT,
                  country TEXT,
                  city TEXT,
                  first_visit TIMESTAMP,
                  last_visit TIMESTAMP,
                  visit_count INTEGER DEFAULT 1)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS texts
                 (key TEXT PRIMARY KEY,
                  value TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS messages
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  content TEXT,
                  user_ip TEXT,
                  fingerprint TEXT,
                  status TEXT,
                  sent_at TIMESTAMP)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS settings
                 (key TEXT PRIMARY KEY,
                  value TEXT)''')
    
    default_texts = {
        'welcome_message': '🔍 مرحباً بك في أداة استخراج الأوفستات المتقدمة',
        'header_description': 'استخراج آلاف أوفستات الحماية تلقائياً وتحويلها إلى هوكات احترافية',
        'analysis_complete': '✅ تم استخراج الأوفستات بنجاح',
        'error_message': '❌ حدث خطأ أثناء التحليل',
        'drop_zone_text': 'اسحب ملف <strong>.so</strong> هنا أو <span style="color:#00c8ff;">اضغط</span> للاختيار',
        'upload_button': 'رفع الملف',
        'footer_text': 'تم بناؤها لأغراض تعليمية وهندسة عكسية — استخدمها بمسؤولية.'
    }
    
    for key, value in default_texts.items():
        c.execute('INSERT OR IGNORE INTO texts (key, value) VALUES (?, ?)', (key, value))
    
    c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', ('bot_status', 'active'))
    c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', ('total_visitors', '0'))
    c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', ('unique_visitors', '0'))
    c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', ('last_update', datetime.now().isoformat()))
    
    conn.commit()
    conn.close()

init_db()

# ================================================================
# دوال قاعدة البيانات
# ================================================================

def get_text(key):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT value FROM texts WHERE key = ?', (key,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None

def set_text(key, value):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('UPDATE texts SET value = ? WHERE key = ?', (value, key))
    conn.commit()
    conn.close()

def get_setting(key):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT value FROM settings WHERE key = ?', (key,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None

def set_setting(key, value):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('UPDATE settings SET value = ? WHERE key = ?', (value, key))
    conn.commit()
    conn.close()

def generate_fingerprint(ip, user_agent):
    data = f"{ip}|{user_agent}"
    return hashlib.md5(data.encode()).hexdigest()

def add_visitor(ip, user_agent, device_type, browser, os_name, country, city):
    conn = get_db_connection()
    c = conn.cursor()
    
    fingerprint = generate_fingerprint(ip, user_agent)
    
    c.execute('SELECT id, visit_count FROM visitors WHERE fingerprint = ?', (fingerprint,))
    existing = c.fetchone()
    
    if existing:
        c.execute('UPDATE visitors SET last_visit = ?, visit_count = visit_count + 1 WHERE fingerprint = ?',
                  (datetime.now(), fingerprint))
        visitor_id = existing[0]
        is_new = False
    else:
        c.execute('''INSERT INTO visitors 
                     (fingerprint, ip, user_agent, device_type, browser, os, country, city, first_visit, last_visit, visit_count)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                  (fingerprint, ip, user_agent, device_type, browser, os_name, country, city, datetime.now(), datetime.now(), 1))
        visitor_id = c.lastrowid
        is_new = True
        
        unique_total = int(get_setting('unique_visitors') or 0) + 1
        set_setting('unique_visitors', str(unique_total))
    
    total = int(get_setting('total_visitors') or 0) + 1
    set_setting('total_visitors', str(total))
    
    conn.commit()
    conn.close()
    
    return visitor_id, fingerprint, is_new, total

def get_visitor_stats():
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute('SELECT COUNT(*) FROM visitors')
    total = c.fetchone()[0]
    
    unique = int(get_setting('unique_visitors') or 0)
    
    c.execute('SELECT COUNT(*) FROM visitors WHERE date(last_visit) = date("now")')
    today = c.fetchone()[0]
    
    c.execute('SELECT COUNT(*) FROM visitors WHERE date(last_visit) >= date("now", "-7 days")')
    week = c.fetchone()[0]
    
    c.execute('SELECT device_type, COUNT(*) FROM visitors GROUP BY device_type')
    devices = c.fetchall()
    
    c.execute('SELECT browser, COUNT(*) FROM visitors GROUP BY browser')
    browsers = c.fetchall()
    
    c.execute('SELECT os, COUNT(*) FROM visitors GROUP BY os')
    oss = c.fetchall()
    
    c.execute('SELECT country, COUNT(*) FROM visitors GROUP BY country ORDER BY COUNT(*) DESC LIMIT 10')
    countries = c.fetchall()
    
    conn.close()
    
    return {
        'total': total,
        'unique': unique,
        'today': today,
        'week': week,
        'devices': devices,
        'browsers': browsers,
        'os': oss,
        'countries': countries
    }

def get_recent_visitors(limit=10):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''SELECT id, fingerprint, ip, device_type, browser, os, country, city, 
                  first_visit, last_visit, visit_count 
                  FROM visitors ORDER BY last_visit DESC LIMIT ?''', (limit,))
    results = c.fetchall()
    conn.close()
    return results

def get_visitor_by_fingerprint(fingerprint):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''SELECT id, fingerprint, ip, user_agent, device_type, browser, os, country, city, 
                  first_visit, last_visit, visit_count 
                  FROM visitors WHERE fingerprint = ?''', (fingerprint,))
    result = c.fetchone()
    conn.close()
    return result

def add_message(content, user_ip, fingerprint, status='pending'):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('INSERT INTO messages (content, user_ip, fingerprint, status, sent_at) VALUES (?, ?, ?, ?, ?)',
              (content, user_ip, fingerprint, status, datetime.now()))
    message_id = c.lastrowid
    conn.commit()
    conn.close()
    return message_id

def get_pending_messages():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT id, content, user_ip, fingerprint, sent_at FROM messages WHERE status = "pending" ORDER BY sent_at DESC')
    results = c.fetchall()
    conn.close()
    return results

def update_message_status(message_id, status):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('UPDATE messages SET status = ? WHERE id = ?', (status, message_id))
    conn.commit()
    conn.close()

# ================================================================
# دوال التحليل
# ================================================================

TARGET_OFFSETS = {
    'AntiCheat_Check_1': {
        'patterns': [b'\x8B\x05', b'\x48\x8B\x05', b'\x89\x05'],
        'strings': ['AntiCheat', 'Check', 'Protect'],
        'type': 'Integer',
        'description': 'فحص الحماية الأساسي'
    },
    'AntiCheat_Check_2': {
        'patterns': [b'\x8B\x0D', b'\x48\x8B\x0D', b'\x89\x0D'],
        'strings': ['AntiCheat', 'Check', 'Protect'],
        'type': 'Integer',
        'description': 'فحص الحماية الثانوي'
    },
    'AntiCheat_Flag_1': {
        'patterns': [b'\x8B\x05', b'\x48\x8B\x05', b'\x89\x05'],
        'strings': ['AntiCheat', 'Flag', 'Protect'],
        'type': 'Integer',
        'description': 'علم الحماية الأول'
    },
    'AntiCheat_Flag_2': {
        'patterns': [b'\x8B\x0D', b'\x48\x8B\x0D', b'\x89\x0D'],
        'strings': ['AntiCheat', 'Flag', 'Protect'],
        'type': 'Integer',
        'description': 'علم الحماية الثاني'
    },
    'AntiCheat_Timer_1': {
        'patterns': [b'\xF3\x0F\x10\x05', b'\x48\x8D\x0D', b'\xF3\x0F\x11\x05'],
        'strings': ['AntiCheat', 'Timer', 'Protect'],
        'type': 'Float',
        'description': 'مؤقت الحماية الأول'
    },
    'AntiCheat_Timer_2': {
        'patterns': [b'\xF3\x0F\x10\x0D', b'\x48\x8D\x15', b'\xF3\x0F\x11\x0D'],
        'strings': ['AntiCheat', 'Timer', 'Protect'],
        'type': 'Float',
        'description': 'مؤقت الحماية الثاني'
    },
    'AntiCheat_Status': {
        'patterns': [b'\x8B\x05', b'\x48\x8B\x05', b'\x89\x05'],
        'strings': ['AntiCheat', 'Status', 'Protect'],
        'type': 'Integer',
        'description': 'حالة الحماية الحالية'
    },
    'AntiCheat_Level': {
        'patterns': [b'\x8B\x0D', b'\x48\x8B\x0D', b'\x89\x0D'],
        'strings': ['AntiCheat', 'Level', 'Protect'],
        'type': 'Integer',
        'description': 'مستوى الحماية'
    },
    'AntiCheat_Score': {
        'patterns': [b'\xF3\x0F\x10\x05', b'\x48\x8D\x0D', b'\xF3\x0F\x11\x05'],
        'strings': ['AntiCheat', 'Score', 'Protect'],
        'type': 'Float',
        'description': 'نقاط الحماية'
    },
    'AntiCheat_Count': {
        'patterns': [b'\x8B\x05', b'\x48\x8B\x05', b'\x89\x05'],
        'strings': ['AntiCheat', 'Count', 'Protect'],
        'type': 'Integer',
        'description': 'عدد فحوصات الحماية'
    },
    'Memory_Protect_Base': {
        'patterns': [b'\x48\x8B\x05', b'\x48\x8B\x0D', b'\x48\x8B\x15'],
        'strings': ['Memory', 'Protect', 'Base'],
        'type': 'Pointer',
        'description': 'قاعدة حماية الذاكرة'
    },
    'Memory_Protect_Size': {
        'patterns': [b'\x8B\x05', b'\x48\x8B\x05', b'\x89\x05'],
        'strings': ['Memory', 'Protect', 'Size'],
        'type': 'Integer',
        'description': 'حجم منطقة حماية الذاكرة'
    },
    'Memory_Protect_Flag': {
        'patterns': [b'\x8B\x0D', b'\x48\x8B\x0D', b'\x89\x0D'],
        'strings': ['Memory', 'Protect', 'Flag'],
        'type': 'Integer',
        'description': 'علم حماية الذاكرة'
    },
    'Memory_Protect_Check': {
        'patterns': [b'\x8B\x05', b'\x48\x8B\x05', b'\x89\x05'],
        'strings': ['Memory', 'Protect', 'Check'],
        'type': 'Integer',
        'description': 'فحص حماية الذاكرة'
    },
    'Memory_Protect_Timer': {
        'patterns': [b'\xF3\x0F\x10\x05', b'\x48\x8D\x0D', b'\xF3\x0F\x11\x05'],
        'strings': ['Memory', 'Protect', 'Timer'],
        'type': 'Float',
        'description': 'مؤقت حماية الذاكرة'
    },
    'Code_Protect_Base': {
        'patterns': [b'\x48\x8B\x05', b'\x48\x8B\x0D', b'\x48\x8B\x15'],
        'strings': ['Code', 'Protect', 'Base'],
        'type': 'Pointer',
        'description': 'قاعدة حماية الكود'
    },
    'Code_Protect_Size': {
        'patterns': [b'\x8B\x05', b'\x48\x8B\x05', b'\x89\x05'],
        'strings': ['Code', 'Protect', 'Size'],
        'type': 'Integer',
        'description': 'حجم منطقة حماية الكود'
    },
    'Code_Protect_Check': {
        'patterns': [b'\x8B\x0D', b'\x48\x8B\x0D', b'\x89\x0D'],
        'strings': ['Code', 'Protect', 'Check'],
        'type': 'Integer',
        'description': 'فحص حماية الكود'
    },
    'Code_Protect_Hash': {
        'patterns': [b'\x8B\x05', b'\x48\x8B\x05', b'\x89\x05'],
        'strings': ['Code', 'Protect', 'Hash'],
        'type': 'Integer',
        'description': 'هاش حماية الكود'
    },
    'Input_Protect_Status': {
        'patterns': [b'\x8B\x05', b'\x48\x8B\x05', b'\x89\x05'],
        'strings': ['Input', 'Protect', 'Status'],
        'type': 'Integer',
        'description': 'حالة حماية المدخلات'
    },
    'Input_Protect_Check': {
        'patterns': [b'\x8B\x0D', b'\x48\x8B\x0D', b'\x89\x0D'],
        'strings': ['Input', 'Protect', 'Check'],
        'type': 'Integer',
        'description': 'فحص حماية المدخلات'
    },
    'Input_Protect_Timer': {
        'patterns': [b'\xF3\x0F\x10\x05', b'\x48\x8D\x0D', b'\xF3\x0F\x11\x05'],
        'strings': ['Input', 'Protect', 'Timer'],
        'type': 'Float',
        'description': 'مؤقت حماية المدخلات'
    },
    'Network_Protect_Status': {
        'patterns': [b'\x8B\x05', b'\x48\x8B\x05', b'\x89\x05'],
        'strings': ['Network', 'Protect', 'Status'],
        'type': 'Integer',
        'description': 'حالة حماية الشبكة'
    },
    'Network_Protect_Check': {
        'patterns': [b'\x8B\x0D', b'\x48\x8B\x0D', b'\x89\x0D'],
        'strings': ['Network', 'Protect', 'Check'],
        'type': 'Integer',
        'description': 'فحص حماية الشبكة'
    },
    'Network_Protect_Packet': {
        'patterns': [b'\x8B\x05', b'\x48\x8B\x05', b'\x89\x05'],
        'strings': ['Network', 'Protect', 'Packet'],
        'type': 'Integer',
        'description': 'حماية حزمة الشبكة'
    },
    'File_Protect_Status': {
        'patterns': [b'\x8B\x05', b'\x48\x8B\x05', b'\x89\x05'],
        'strings': ['File', 'Protect', 'Status'],
        'type': 'Integer',
        'description': 'حالة حماية الملفات'
    },
    'File_Protect_Check': {
        'patterns': [b'\x8B\x0D', b'\x48\x8B\x0D', b'\x89\x0D'],
        'strings': ['File', 'Protect', 'Check'],
        'type': 'Integer',
        'description': 'فحص حماية الملفات'
    },
    'File_Protect_Hash': {
        'patterns': [b'\x8B\x05', b'\x48\x8B\x05', b'\x89\x05'],
        'strings': ['File', 'Protect', 'Hash'],
        'type': 'Integer',
        'description': 'هاش حماية الملفات'
    },
    'Process_Protect_Status': {
        'patterns': [b'\x8B\x05', b'\x48\x8B\x05', b'\x89\x05'],
        'strings': ['Process', 'Protect', 'Status'],
        'type': 'Integer',
        'description': 'حالة حماية العمليات'
    },
    'Process_Protect_Check': {
        'patterns': [b'\x8B\x0D', b'\x48\x8B\x0D', b'\x89\x0D'],
        'strings': ['Process', 'Protect', 'Check'],
        'type': 'Integer',
        'description': 'فحص حماية العمليات'
    },
    'Process_Protect_ID': {
        'patterns': [b'\x8B\x05', b'\x48\x8B\x05', b'\x89\x05'],
        'strings': ['Process', 'Protect', 'ID'],
        'type': 'Integer',
        'description': 'معرف حماية العمليات'
    },
    'Hardware_Protect_Status': {
        'patterns': [b'\x8B\x05', b'\x48\x8B\x05', b'\x89\x05'],
        'strings': ['Hardware', 'Protect', 'Status'],
        'type': 'Integer',
        'description': 'حالة حماية الأجهزة'
    },
    'Hardware_Protect_Check': {
        'patterns': [b'\x8B\x0D', b'\x48\x8B\x0D', b'\x89\x0D'],
        'strings': ['Hardware', 'Protect', 'Check'],
        'type': 'Integer',
        'description': 'فحص حماية الأجهزة'
    },
    'Hardware_Protect_Flag': {
        'patterns': [b'\x8B\x05', b'\x48\x8B\x05', b'\x89\x05'],
        'strings': ['Hardware', 'Protect', 'Flag'],
        'type': 'Integer',
        'description': 'علم حماية الأجهزة'
    },
    'App_Protect_Status': {
        'patterns': [b'\x8B\x05', b'\x48\x8B\x05', b'\x89\x05'],
        'strings': ['App', 'Protect', 'Status'],
        'type': 'Integer',
        'description': 'حالة حماية التطبيقات'
    },
    'App_Protect_Check': {
        'patterns': [b'\x8B\x0D', b'\x48\x8B\x0D', b'\x89\x0D'],
        'strings': ['App', 'Protect', 'Check'],
        'type': 'Integer',
        'description': 'فحص حماية التطبيقات'
    },
    'App_Protect_Version': {
        'patterns': [b'\x8B\x05', b'\x48\x8B\x05', b'\x89\x05'],
        'strings': ['App', 'Protect', 'Version'],
        'type': 'Integer',
        'description': 'إصدار حماية التطبيقات'
    },
    'System_Protect_Status': {
        'patterns': [b'\x8B\x05', b'\x48\x8B\x05', b'\x89\x05'],
        'strings': ['System', 'Protect', 'Status'],
        'type': 'Integer',
        'description': 'حالة حماية النظام'
    },
    'System_Protect_Check': {
        'patterns': [b'\x8B\x0D', b'\x48\x8B\x0D', b'\x89\x0D'],
        'strings': ['System', 'Protect', 'Check'],
        'type': 'Integer',
        'description': 'فحص حماية النظام'
    },
    'System_Protect_Level': {
        'patterns': [b'\x8B\x05', b'\x48\x8B\x05', b'\x89\x05'],
        'strings': ['System', 'Protect', 'Level'],
        'type': 'Integer',
        'description': 'مستوى حماية النظام'
    },
    'Game_Protect_Status': {
        'patterns': [b'\x8B\x05', b'\x48\x8B\x05', b'\x89\x05'],
        'strings': ['Game', 'Protect', 'Status'],
        'type': 'Integer',
        'description': 'حالة حماية اللعبة'
    },
    'Game_Protect_Check': {
        'patterns': [b'\x8B\x0D', b'\x48\x8B\x0D', b'\x89\x0D'],
        'strings': ['Game', 'Protect', 'Check'],
        'type': 'Integer',
        'description': 'فحص حماية اللعبة'
    },
    'Game_Protect_Version': {
        'patterns': [b'\x8B\x05', b'\x48\x8B\x05', b'\x89\x05'],
        'strings': ['Game', 'Protect', 'Version'],
        'type': 'Integer',
        'description': 'إصدار حماية اللعبة'
    },
    'Game_Protect_Level': {
        'patterns': [b'\x8B\x0D', b'\x48\x8B\x0D', b'\x89\x0D'],
        'strings': ['Game', 'Protect', 'Level'],
        'type': 'Integer',
        'description': 'مستوى حماية اللعبة'
    },
    'Game_Protect_Timer': {
        'patterns': [b'\xF3\x0F\x10\x05', b'\x48\x8D\x0D', b'\xF3\x0F\x11\x05'],
        'strings': ['Game', 'Protect', 'Timer'],
        'type': 'Float',
        'description': 'مؤقت حماية اللعبة'
    },
    'UI_Protect_Status': {
        'patterns': [b'\x8B\x05', b'\x48\x8B\x05', b'\x89\x05'],
        'strings': ['UI', 'Protect', 'Status'],
        'type': 'Integer',
        'description': 'حالة حماية الواجهة'
    },
    'UI_Protect_Check': {
        'patterns': [b'\x8B\x0D', b'\x48\x8B\x0D', b'\x89\x0D'],
        'strings': ['UI', 'Protect', 'Check'],
        'type': 'Integer',
        'description': 'فحص حماية الواجهة'
    },
    'UI_Protect_Flag': {
        'patterns': [b'\x8B\x05', b'\x48\x8B\x05', b'\x89\x05'],
        'strings': ['UI', 'Protect', 'Flag'],
        'type': 'Integer',
        'description': 'علم حماية الواجهة'
    },
    'Audio_Protect_Status': {
        'patterns': [b'\x8B\x05', b'\x48\x8B\x05', b'\x89\x05'],
        'strings': ['Audio', 'Protect', 'Status'],
        'type': 'Integer',
        'description': 'حالة حماية الصوت'
    },
    'Audio_Protect_Check': {
        'patterns': [b'\x8B\x0D', b'\x48\x8B\x0D', b'\x89\x0D'],
        'strings': ['Audio', 'Protect', 'Check'],
        'type': 'Integer',
        'description': 'فحص حماية الصوت'
    },
    'Video_Protect_Status': {
        'patterns': [b'\x8B\x05', b'\x48\x8B\x05', b'\x89\x05'],
        'strings': ['Video', 'Protect', 'Status'],
        'type': 'Integer',
        'description': 'حالة حماية الفيديو'
    },
    'Video_Protect_Check': {
        'patterns': [b'\x8B\x0D', b'\x48\x8B\x0D', b'\x89\x0D'],
        'strings': ['Video', 'Protect', 'Check'],
        'type': 'Integer',
        'description': 'فحص حماية الفيديو'
    },
    'Video_Protect_Flag': {
        'patterns': [b'\x8B\x05', b'\x48\x8B\x05', b'\x89\x05'],
        'strings': ['Video', 'Protect', 'Flag'],
        'type': 'Integer',
        'description': 'علم حماية الفيديو'
    },
}

def find_strings(data):
    strings = []
    for i in range(len(data) - 4):
        if 32 <= data[i] <= 126:
            j = i
            while j < len(data) and 32 <= data[j] <= 126:
                j += 1
            if j - i >= 4:
                strings.append((i, data[i:j].decode('ascii', errors='ignore')))
                i = j
    return strings

def find_offsets_by_patterns(data, patterns):
    positions = []
    for pattern in patterns:
        pos = data.find(pattern)
        while pos != -1:
            positions.append((pos, pattern))
            pos = data.find(pattern, pos + 1)
    return positions

def find_offsets_by_strings(strings, target_strings):
    positions = []
    for offset, string in strings:
        for target in target_strings:
            if target in string:
                positions.append((offset, string))
                break
    return positions

stop_analysis = False

def analyze_so_file(file_path, progress_callback=None):
    global stop_analysis
    stop_analysis = False
    
    with open(file_path, 'rb') as f:
        data = f.read()
    
    all_strings = find_strings(data)
    results = []
    found_offsets = set()
    
    total = len(TARGET_OFFSETS)
    current = 0
    
    for offset_name, info in TARGET_OFFSETS.items():
        if stop_analysis:
            break
            
        current += 1
        if progress_callback:
            progress_callback(current / total * 100)
        
        pattern_positions = find_offsets_by_patterns(data, info['patterns'])
        string_positions = find_offsets_by_strings(all_strings, info['strings'])
        
        for pos, _ in pattern_positions:
            if pos not in found_offsets:
                confidence = 'متوسطة'
                for str_pos, _ in string_positions:
                    if abs(pos - str_pos) < 0x2000:
                        confidence = 'عالية'
                        break
                
                address = hex(pos + 0x1000)
                results.append({
                    'name': offset_name,
                    'address': address.upper(),
                    'type': info['type'],
                    'description': info['description'],
                    'confidence': confidence
                })
                found_offsets.add(pos)
                break
    
    return results

def generate_hook(lib_name, offsets):
    hook_code = f"""
// ================================================================
// HOOK GENERATED FOR: {lib_name}
// ================================================================

#include <memory>
#include <vector>
#include <cstdint>
#include <string>

struct OffsetInfo {{
    std::string name;
    uintptr_t address;
    std::string type;
    std::string description;
    std::string confidence;
}};

std::vector<OffsetInfo> extracted_offsets = {{
"""
    
    for offset in offsets:
        confidence = offset.get('confidence', 'متوسطة')
        hook_code += f"""    {{ "{offset['name']}", {offset['address']}", "{offset['type']}", "{offset['description']}", "{confidence}" }},
"""
    
    hook_code += """};

void enable_hooks() {{
    // هنا يتم وضع كود تفعيل الهوك
}}

void disable_hooks() {{
    // هنا يتم وضع كود تعطيل الهوك
}}

void update_offsets(const std::vector<OffsetInfo>& new_offsets) {{
    extracted_offsets = new_offsets;
}}

std::vector<OffsetInfo> get_offsets() {{
    return extracted_offsets;
}}
"""
    return hook_code

# ================================================================
# دوال التيلجرام (Webhook)
# ================================================================

def send_telegram_message(message, chat_id=None):
    try:
        if chat_id is None:
            chat_id = CHAT_ID
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        data = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML"
        }
        response = requests.post(url, data=data)
        return response.json()
    except Exception as e:
        print(f"❌ خطأ في إرسال رسالة التيلجرام: {e}")
        return None

def send_visitor_notification(visitor_data):
    message = f"""
🆕 <b>زائر جديد للموقع!</b>

📌 <b>معلومات الزائر:</b>
🔹 <b>البصمة (Fingerprint):</b> <code>{visitor_data['fingerprint']}</code>
👤 <b>الجهاز:</b> {visitor_data['device_type']}
🌐 <b>المتصفح:</b> {visitor_data['browser']}
💻 <b>نظام التشغيل:</b> {visitor_data['os']}
📍 <b>الدولة:</b> {visitor_data['country']}
🏙️ <b>المدينة:</b> {visitor_data['city']}
📡 <b>IP:</b> {visitor_data['ip']}
📅 <b>الوقت:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

📊 <b>إحصائيات:</b>
👥 إجمالي الزيارات: {visitor_data['total_visitors']}
👤 زوار فريدين: {visitor_data['unique_visitors']}
📅 اليوم: {visitor_data['today_visitors']}
📆 هذا الأسبوع: {visitor_data['week_visitors']}
"""
    return send_telegram_message(message)

def set_webhook():
    """تثبيت Webhook للبوت"""
    url = f"https://api.telegram.org/bot{TOKEN}/setWebhook"
    webhook_url = "https://your-domain.com/webhook"  # غيّر هذا إلى رابطك الحقيقي
    data = {"url": webhook_url}
    response = requests.post(url, data=data)
    return response.json()

# ================================================================
# مسارات Flask
# ================================================================

@app.before_request
def track_visitor():
    try:
        if request.path == '/favicon.ico' or request.path == '/webhook':
            return
        
        ip = request.remote_addr
        user_agent = request.headers.get('User-Agent', 'Unknown')
        
        device_type = 'Unknown'
        browser = 'Unknown'
        os_name = 'Unknown'
        
        if user_agent:
            if 'Mobile' in user_agent:
                device_type = 'Mobile'
            elif 'Tablet' in user_agent:
                device_type = 'Tablet'
            else:
                device_type = 'Desktop'
            
            if 'Chrome' in user_agent:
                browser = 'Chrome'
            elif 'Firefox' in user_agent:
                browser = 'Firefox'
            elif 'Safari' in user_agent:
                browser = 'Safari'
            elif 'Edge' in user_agent:
                browser = 'Edge'
            elif 'Opera' in user_agent:
                browser = 'Opera'
            
            if 'Windows' in user_agent:
                os_name = 'Windows'
            elif 'Mac OS' in user_agent:
                os_name = 'macOS'
            elif 'Linux' in user_agent:
                os_name = 'Linux'
            elif 'Android' in user_agent:
                os_name = 'Android'
            elif 'iOS' in user_agent:
                os_name = 'iOS'
        
        country = 'Unknown'
        city = 'Unknown'
        try:
            response = requests.get(f'http://ip-api.com/json/{ip}', timeout=3)
            if response.status_code == 200:
                data = response.json()
                country = data.get('country', 'Unknown')
                city = data.get('city', 'Unknown')
        except:
            pass
        
        visitor_id, fingerprint, is_new, total = add_visitor(ip, user_agent, device_type, browser, os_name, country, city)
        
        if is_new:
            stats = get_visitor_stats()
            visitor_data = {
                'fingerprint': fingerprint,
                'ip': ip,
                'device_type': device_type,
                'browser': browser,
                'os': os_name,
                'country': country,
                'city': city,
                'total_visitors': total,
                'unique_visitors': stats['unique'],
                'today_visitors': stats['today'],
                'week_visitors': stats['week']
            }
            
            send_visitor_notification(visitor_data)
            print(f"🟢 زائر جديد: {fingerprint[:8]}... | {ip} | {country}")
        
    except Exception as e:
        print(f"خطأ في تتبع الزائر: {e}")

@app.route('/')
def index():
    welcome_message = get_text('welcome_message') or '🔍 مرحباً بك في أداة استخراج الأوفستات المتقدمة'
    header_description = get_text('header_description') or 'استخراج آلاف أوفستات الحماية تلقائياً وتحويلها إلى هوكات احترافية'
    drop_zone_text = get_text('drop_zone_text') or 'اسحب ملف <strong>.so</strong> هنا أو <span style="color:#00c8ff;">اضغط</span> للاختيار'
    analysis_complete = get_text('analysis_complete') or '✅ تم استخراج الأوفستات بنجاح'
    footer_text = get_text('footer_text') or 'تم بناؤها لأغراض تعليمية وهندسة عكسية — استخدمها بمسؤولية.'
    
    html = f"""
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{welcome_message}</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; font-family: 'Tajawal', 'Segoe UI', sans-serif; }}
            body {{ 
                background: #0a0a1a; 
                color: #e8edf5; 
                height: 100vh;
                overflow: hidden;
            }}
            #bg-canvas {{
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                z-index: -1;
                pointer-events: none;
            }}
            .container {{
                position: relative;
                z-index: 1;
                width: 95%;
                max-width: 1200px;
                margin: 30px auto;
                background: rgba(13, 17, 31, 0.85);
                backdrop-filter: blur(20px);
                padding: 30px;
                border-radius: 40px;
                border: 1px solid rgba(0, 200, 255, 0.1);
                box-shadow: 0 30px 80px rgba(0, 0, 0, 0.8);
                max-height: 90vh;
                overflow-y: auto;
            }}
            .header {{ text-align: center; margin-bottom: 25px; }}
            .header h1 {{ 
                font-size: 2.8rem; 
                background: linear-gradient(135deg, #00c8ff, #7a5af5, #ff00ff);
                -webkit-background-clip: text; 
                -webkit-text-fill-color: transparent; 
                text-shadow: 0 0 40px rgba(0, 200, 255, 0.2);
            }}
            .header p {{ color: #8892a8; font-size: 1.1rem; margin-top: 8px; }}
            
            .tabs {{
                display: flex;
                gap: 10px;
                margin-bottom: 20px;
                border-bottom: 1px solid rgba(255,255,255,0.05);
                padding-bottom: 10px;
            }}
            .tab-btn {{
                padding: 10px 25px;
                border: none;
                border-radius: 30px;
                background: transparent;
                color: #b0b9cc;
                font-size: 1rem;
                cursor: pointer;
                transition: 0.3s;
                font-weight: 500;
            }}
            .tab-btn:hover {{ background: rgba(0,200,255,0.05); color: #fff; }}
            .tab-btn.active {{
                background: linear-gradient(135deg, #00c8ff, #7a5af5);
                color: #fff;
                box-shadow: 0 4px 20px rgba(0, 200, 255, 0.2);
            }}
            .tab-content {{ display: none; }}
            .tab-content.active {{ display: block; animation: fadeUp 0.4s ease; }}
            @keyframes fadeUp {{ from {{ opacity: 0; transform: translateY(10px); }} to {{ opacity: 1; transform: translateY(0); }} }}
            
            .drop-zone {{ 
                border: 2px dashed rgba(0, 200, 255, 0.3); 
                border-radius: 30px; 
                padding: 50px 20px; 
                text-align: center; 
                cursor: pointer; 
                transition: 0.4s; 
                background: rgba(255,255,255,0.02); 
                margin: 20px 0;
            }}
            .drop-zone:hover, .drop-zone.dragover {{ 
                background: rgba(0,200,255,0.08); 
                border-color: #00c8ff; 
                box-shadow: 0 0 60px rgba(0, 200, 255, 0.1);
            }}
            .drop-zone .icon {{ font-size: 4rem; display: block; margin-bottom: 12px; }}
            .drop-zone p {{ font-size: 1.2rem; color: #b0b9cc; }}
            #fileInput {{ display: none; }}
            
            #progress-container {{ 
                display: none; 
                margin: 25px 0; 
                padding: 20px;
                background: rgba(255,255,255,0.03);
                border-radius: 20px;
                border: 1px solid rgba(0,200,255,0.1);
            }}
            #progress-text {{ display: flex; justify-content: space-between; font-size: 0.9rem; color: #b0b9cc; margin-bottom: 12px; }}
            #progress-bar-track {{
                width: 100%;
                height: 12px;
                background: #1a2338;
                border-radius: 30px;
                overflow: hidden;
                position: relative;
            }}
            #progress-bar-fill {{
                height: 100%;
                width: 0%;
                background: linear-gradient(90deg, #00c8ff, #7a5af5, #ff00ff);
                border-radius: 30px;
                transition: width 0.3s ease;
                box-shadow: 0 0 20px rgba(0, 200, 255, 0.3);
            }}
            #progress-percent {{ font-weight: bold; color: #00c8ff; }}
            
            .controls {{
                display: flex;
                gap: 15px;
                justify-content: center;
                margin-top: 15px;
            }}
            .btn {{
                padding: 12px 30px;
                border: none;
                border-radius: 40px;
                font-weight: 600;
                font-size: 1rem;
                cursor: pointer;
                transition: 0.3s;
                background: linear-gradient(135deg, #00c8ff, #7a5af5);
                color: #fff;
                box-shadow: 0 4px 20px rgba(0, 200, 255, 0.2);
            }}
            .btn:hover {{ transform: translateY(-3px); box-shadow: 0 8px 30px rgba(0, 200, 255, 0.4); }}
            .btn-stop {{
                background: linear-gradient(135deg, #ff4444, #cc0000);
                box-shadow: 0 4px 20px rgba(255, 68, 68, 0.2);
            }}
            .btn-stop:hover {{ box-shadow: 0 8px 30px rgba(255, 68, 68, 0.4); }}
            
            #results {{ display: none; margin-top: 25px; }}
            .results-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; }}
            .results-header h3 {{ color: #00e676; font-size: 1.3rem; }}
            .results-stats {{
                display: flex;
                gap: 15px;
                flex-wrap: wrap;
            }}
            .stat-box {{
                padding: 6px 16px;
                border-radius: 20px;
                background: rgba(255,255,255,0.03);
                border: 1px solid rgba(255,255,255,0.05);
                font-size: 0.85rem;
                color: #b0b9cc;
            }}
            .stat-box span {{ color: #fff; font-weight: 600; }}
            table {{ 
                width: 100%; 
                border-collapse: collapse; 
                background: rgba(15, 22, 37, 0.8); 
                border-radius: 20px; 
                overflow: hidden; 
                backdrop-filter: blur(10px);
            }}
            th {{ 
                background: rgba(26, 35, 56, 0.9); 
                padding: 16px; 
                text-align: center; 
                color: #b0b9cc; 
                font-weight: 500;
            }}
            td {{ 
                padding: 14px; 
                text-align: center; 
                border-bottom: 1px solid rgba(255,255,255,0.03); 
                color: #d0d8e5;
            }}
            tr:hover td {{ background: rgba(255,255,255,0.02); }}
            .address {{ color: #00c8ff; font-weight: 500; }}
            .confidence {{ padding: 4px 12px; border-radius: 20px; font-size: 0.8rem; display: inline-block; }}
            .confidence-high {{ background: rgba(0, 230, 118, 0.2); color: #00e676; border: 1px solid rgba(0, 230, 118, 0.3); }}
            .confidence-medium {{ background: rgba(255, 170, 0, 0.2); color: #ffaa00; border: 1px solid rgba(255, 170, 0, 0.3); }}
            .confidence-low {{ background: rgba(255, 68, 68, 0.2); color: #ff4444; border: 1px solid rgba(255, 68, 68, 0.3); }}
            
            #export-btn {{ 
                display: none; 
                margin: 25px auto; 
                padding: 14px 40px; 
                background: linear-gradient(135deg, #00c8ff, #7a5af5); 
                color: #fff; 
                border: none; 
                border-radius: 40px; 
                cursor: pointer; 
                font-weight: 600; 
                font-size: 1.1rem;
                box-shadow: 0 4px 20px rgba(0, 200, 255, 0.2);
                transition: 0.3s;
            }}
            #export-btn:hover {{ transform: translateY(-3px); box-shadow: 0 8px 30px rgba(0, 200, 255, 0.4); }}
            
            #hook-section {{
                display: none;
                margin-top: 25px;
                padding: 20px;
                background: rgba(15, 22, 37, 0.5);
                border-radius: 20px;
                border: 1px solid rgba(0,200,255,0.1);
            }}
            #hook-section .hook-header {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 15px;
            }}
            #hook-section .hook-header h3 {{ color: #7a5af5; font-size: 1.2rem; }}
            .hook-code-container {{
                background: #0a0a1a;
                padding: 15px;
                border-radius: 15px;
                overflow-x: auto;
                font-family: 'Courier New', monospace;
                font-size: 0.9rem;
                color: #00e676;
                border: 1px solid rgba(255,255,255,0.05);
                max-height: 400px;
                overflow-y: auto;
            }}
            .hook-code-container pre {{ margin: 0; white-space: pre-wrap; word-break: break-all; }}
            #copy-hook-btn {{
                margin-top: 10px;
                padding: 8px 20px;
                background: rgba(0,200,255,0.1);
                border: 1px solid rgba(0,200,255,0.2);
                border-radius: 20px;
                color: #00c8ff;
                cursor: pointer;
                transition: 0.3s;
            }}
            #copy-hook-btn:hover {{ background: rgba(0,200,255,0.2); }}
            
            #error-msg {{ color: #ff6b6b; text-align: center; margin-top: 16px; display: none; background: rgba(255, 107, 107, 0.1); padding: 12px; border-radius: 12px; border: 1px solid rgba(255, 107, 107, 0.2); }}
            .footer {{ text-align: center; margin-top: 20px; font-size: 0.8rem; color: #3d4a62; border-top: 1px solid rgba(255,255,255,0.04); padding-top: 15px; }}
            @media (max-width: 600px) {{ .container {{ padding: 15px; }} th, td {{ font-size: 0.75rem; padding: 8px; }} .header h1 {{ font-size: 2rem; }} }}
        </style>
    </head>
    <body>
        <div id="bg-canvas"></div>

        <div class="container">
            <div class="header">
                <h1>{welcome_message}</h1>
                <p id="header-description">{header_description}</p>
            </div>
            
            <div class="tabs">
                <button class="tab-btn active" data-tab="extract">📤 استخراج الأوفستات</button>
                <button class="tab-btn" data-tab="manual">🛠️ إضافة أوفستات يدوياً</button>
            </div>
            
            <div class="tab-content active" id="tab-extract">
                <div class="drop-zone" id="dropZone">
                    <span class="icon">📁</span>
                    <p id="drop-zone-text">{drop_zone_text}</p>
                    <input type="file" id="fileInput" accept=".so">
                </div>

                <div id="progress-container">
                    <div id="progress-text">
                        <span id="progress-label">⏳ جاري التحميل...</span>
                        <span id="progress-percent">0%</span>
                    </div>
                    <div id="progress-bar-track">
                        <div id="progress-bar-fill"></div>
                    </div>
                    <div class="controls">
                        <button class="btn" id="export-btn" style="display:none;">📥 تصدير كـ JSON</button>
                        <button class="btn btn-stop" id="stop-btn" style="display:none;">⏹ إيقاف</button>
                    </div>
                </div>

                <div id="error-msg"></div>

                <div id="results">
                    <div class="results-header">
                        <h3 id="analysis-complete-text">{analysis_complete}</h3>
                        <div class="results-stats">
                            <div class="stat-box">📊 المجموع: <span id="result-count">0</span></div>
                            <div class="stat-box">🔵 عالية: <span id="high-count">0</span></div>
                            <div class="stat-box">🟡 متوسطة: <span id="medium-count">0</span></div>
                            <div class="stat-box">🔴 منخفضة: <span id="low-count">0</span></div>
                        </div>
                    </div>
                    <div style="overflow-x:auto;">
                        <table>
                            <thead>
                                <tr>
                                    <th>#</th>
                                    <th>اسم الأوفست</th>
                                    <th>العنوان (Hex)</th>
                                    <th>النوع</th>
                                    <th>الوصف</th>
                                    <th>الثقة</th>
                                </tr>
                            </thead>
                            <tbody id="tableBody"></tbody>
                        </table>
                    </div>
                    <div class="controls" style="margin-top:15px;">
                        <button class="btn" id="generate-hook-btn" style="display:none;">🔗 توليد الهوك</button>
                        <button class="btn btn-outline" id="filter-high-btn" style="display:none;">🔵 عالية فقط</button>
                        <button class="btn btn-outline" id="reset-filter-btn" style="display:none;">🔄 عرض الكل</button>
                    </div>
                </div>

                <div id="hook-section">
                    <div class="hook-header">
                        <h3>🔗 كود الهوك المُولد</h3>
                        <button id="copy-hook-btn">📋 نسخ الكود</button>
                    </div>
                    <div class="hook-code-container">
                        <pre id="hook-code-display">// جاري توليد الهوك...</pre>
                    </div>
                </div>
            </div>
            
            <div class="tab-content" id="tab-manual">
                <div id="manual-section" style="padding:20px; background:rgba(15,22,37,0.5); border-radius:20px; border:1px solid rgba(0,200,255,0.1);">
                    <h3 style="color:#7a5af5; margin-bottom:15px;">🛠️ إضافة أوفستات يدوياً وتوليد هوك</h3>
                    <div class="form-group">
                        <input type="text" id="manual-lib-name" placeholder="اسم الـ LIB (مثال: libUE4.so)" style="flex:1; min-width:200px; padding:12px; border-radius:12px; border:1px solid rgba(255,255,255,0.1); background:rgba(255,255,255,0.02); color:#e8edf5; font-size:0.95rem;">
                    </div>
                    <div class="form-group" style="margin-top:10px;">
                        <textarea id="manual-offsets-input" placeholder="أدخل الأوفستات بصيغة JSON، مثال:
        [{{
          &quot;name&quot;: &quot;AntiCheat_Check&quot;,
          &quot;address&quot;: &quot;0x12345678&quot;,
          &quot;type&quot;: &quot;Integer&quot;,
          &quot;description&quot;: &quot;فحص الحماية&quot;,
          &quot;confidence&quot;: &quot;عالية&quot;
        }}]" rows="6" style="flex:1; min-width:200px; padding:12px; border-radius:12px; border:1px solid rgba(255,255,255,0.1); background:rgba(255,255,255,0.02); color:#e8edf5; font-size:0.95rem; resize:vertical;"></textarea>
                    </div>
                    <button class="btn" id="manual-generate-btn" style="margin-top:10px;">🔗 توليد الهوك</button>
                    <div id="manual-hook-output" style="margin-top:15px; display:none;">
                        <div class="hook-code-container">
                            <pre id="manual-hook-code-display">// جاري توليد الهوك...</pre>
                        </div>
                        <button id="copy-manual-hook-btn" style="margin-top:10px; padding:8px 20px; background:rgba(0,200,255,0.1); border:1px solid rgba(0,200,255,0.2); border-radius:20px; color:#00c8ff; cursor:pointer;">📋 نسخ الكود</button>
                    </div>
                </div>
            </div>

            <div class="footer">
                {footer_text}
            </div>
        </div>

        <script>
            function loadThreeJS() {{
                return new Promise((resolve, reject) => {{
                    const script = document.createElement('script');
                    script.src = 'https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js';
                    script.onload = () => resolve(window.THREE);
                    script.onerror = reject;
                    document.head.appendChild(script);
                }});
            }}

            document.addEventListener('DOMContentLoaded', async () => {{
                try {{
                    const THREE = await loadThreeJS();
                    init3D(THREE);
                }} catch (e) {{
                    console.log('3D background not loaded, continuing with flat background');
                }}
            }});

            function init3D(THREE) {{
                const canvas = document.getElementById('bg-canvas');
                const scene = new THREE.Scene();
                const camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);
                const renderer = new THREE.WebGLRenderer({{ 
                    canvas: canvas, 
                    alpha: true,
                    antialias: true 
                }});
                renderer.setSize(window.innerWidth, window.innerHeight);
                renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
                canvas.style.pointerEvents = 'none';

                const particlesGeometry = new THREE.BufferGeometry();
                const particlesCount = 1200;
                const posArray = new Float32Array(particlesCount * 3);
                for (let i = 0; i < particlesCount * 3; i++) {{
                    posArray[i] = (Math.random() - 0.5) * 40;
                }}
                particlesGeometry.setAttribute('position', new THREE.BufferAttribute(posArray, 3));
                
                const particlesMaterial = new THREE.PointsMaterial({{
                    size: 0.04,
                    color: 0x00c8ff,
                    transparent: true,
                    opacity: 0.7,
                    blending: THREE.AdditiveBlending,
                }});
                const particlesMesh = new THREE.Points(particlesGeometry, particlesMaterial);
                scene.add(particlesMesh);

                const linesGeometry = new THREE.BufferGeometry();
                const linesPositions = [];
                for (let i = 0; i < particlesCount; i++) {{
                    for (let j = i + 1; j < particlesCount; j++) {{
                        const dx = posArray[i*3] - posArray[j*3];
                        const dy = posArray[i*3+1] - posArray[j*3+1];
                        const dz = posArray[i*3+2] - posArray[j*3+2];
                        const dist = Math.sqrt(dx*dx + dy*dy + dz*dz);
                        if (dist < 1.2) {{
                            linesPositions.push(posArray[i*3], posArray[i*3+1], posArray[i*3+2]);
                            linesPositions.push(posArray[j*3], posArray[j*3+1], posArray[j*3+2]);
                        }}
                    }}
                }}
                linesGeometry.setAttribute('position', new THREE.Float32BufferAttribute(linesPositions, 3));
                const linesMaterial = new THREE.LineBasicMaterial({{
                    color: 0x7a5af5,
                    transparent: true,
                    opacity: 0.1,
                }});
                const linesMesh = new THREE.LineSegments(linesGeometry, linesMaterial);
                scene.add(linesMesh);

                camera.position.z = 12;

                function animate() {{
                    requestAnimationFrame(animate);
                    particlesMesh.rotation.x += 0.0003;
                    particlesMesh.rotation.y += 0.0008;
                    linesMesh.rotation.x += 0.0003;
                    linesMesh.rotation.y += 0.0008;
                    renderer.render(scene, camera);
                }}
                animate();

                window.addEventListener('resize', () => {{
                    camera.aspect = window.innerWidth / window.innerHeight;
                    camera.updateProjectionMatrix();
                    renderer.setSize(window.innerWidth, window.innerHeight);
                }});
            }}

            const tabBtns = document.querySelectorAll('.tab-btn');
            const tabContents = document.querySelectorAll('.tab-content');

            tabBtns.forEach(btn => {{
                btn.addEventListener('click', () => {{
                    tabBtns.forEach(b => b.classList.remove('active'));
                    tabContents.forEach(c => c.classList.remove('active'));
                    btn.classList.add('active');
                    document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
                }});
            }});

            const dropZone = document.getElementById('dropZone');
            const fileInput = document.getElementById('fileInput');
            const progressContainer = document.getElementById('progress-container');
            const progressFill = document.getElementById('progress-bar-fill');
            const progressLabel = document.getElementById('progress-label');
            const progressPercent = document.getElementById('progress-percent');
            const errorMsg = document.getElementById('error-msg');
            const resultsDiv = document.getElementById('results');
            const tableBody = document.getElementById('tableBody');
            const exportBtn = document.getElementById('export-btn');
            const stopBtn = document.getElementById('stop-btn');
            const resultCount = document.getElementById('result-count');
            const highCount = document.getElementById('high-count');
            const mediumCount = document.getElementById('medium-count');
            const lowCount = document.getElementById('low-count');
            const generateHookBtn = document.getElementById('generate-hook-btn');
            const hookSection = document.getElementById('hook-section');
            const hookCodeDisplay = document.getElementById('hook-code-display');
            const copyHookBtn = document.getElementById('copy-hook-btn');
            const filterHighBtn = document.getElementById('filter-high-btn');
            const resetFilterBtn = document.getElementById('reset-filter-btn');

            let isAnalyzing = false;
            let currentResults = [];
            let filteredResults = [];
            let isFiltered = false;

            dropZone.addEventListener('click', () => fileInput.click());
            dropZone.addEventListener('dragover', (e) => {{ e.preventDefault(); dropZone.classList.add('dragover'); }});
            dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
            dropZone.addEventListener('drop', (e) => {{
                e.preventDefault();
                dropZone.classList.remove('dragover');
                if (e.dataTransfer.files[0]) handleFile(e.dataTransfer.files[0]);
            }});
            fileInput.addEventListener('change', (e) => {{
                if (e.target.files[0]) handleFile(e.target.files[0]);
            }});

            stopBtn.addEventListener('click', async () => {{
                if (!isAnalyzing) return;
                try {{
                    const response = await fetch('/stop', {{ method: 'POST' }});
                    if (response.ok) {{
                        progressLabel.textContent = '⏹ تم إيقاف التحليل';
                        isAnalyzing = false;
                        stopBtn.style.display = 'none';
                    }}
                }} catch (e) {{
                    console.error('خطأ في الإيقاف:', e);
                }}
            }});

            filterHighBtn.addEventListener('click', () => {{
                filteredResults = currentResults.filter(r => r.confidence === 'عالية' || r.confidence === 'عالية جداً');
                displayResults(filteredResults);
                isFiltered = true;
                filterHighBtn.style.display = 'none';
                resetFilterBtn.style.display = 'inline-block';
            }});

            resetFilterBtn.addEventListener('click', () => {{
                displayResults(currentResults);
                isFiltered = false;
                resetFilterBtn.style.display = 'none';
                filterHighBtn.style.display = 'inline-block';
            }});

            async function handleFile(file) {{
                if (!file.name.endsWith('.so')) {{
                    showError('⚠️ يرجى رفع ملف .so فقط');
                    return;
                }}

                errorMsg.style.display = 'none';
                progressContainer.style.display = 'block';
                progressFill.style.width = '0%';
                progressLabel.textContent = '⏳ جاري رفع الملف...';
                progressPercent.textContent = '0%';
                stopBtn.style.display = 'inline-block';
                isAnalyzing = true;
                exportBtn.style.display = 'none';
                resultsDiv.style.display = 'none';
                generateHookBtn.style.display = 'none';
                hookSection.style.display = 'none';
                filterHighBtn.style.display = 'none';
                resetFilterBtn.style.display = 'none';
                isFiltered = false;

                const formData = new FormData();
                formData.append('file', file);

                try {{
                    const xhr = new XMLHttpRequest();
                    const promise = new Promise((resolve, reject) => {{
                        xhr.open('POST', '/analyze');
                        xhr.onload = () => {{
                            if (xhr.status === 200) {{
                                resolve(JSON.parse(xhr.responseText));
                            }} else {{
                                reject(new Error(xhr.responseText || 'خطأ في الخادم'));
                            }}
                        }};
                        xhr.onerror = () => reject(new Error('فشل الاتصال بالخادم'));
                        xhr.upload.onprogress = (e) => {{
                            if (e.lengthComputable) {{
                                const percent = Math.round((e.loaded / e.total) * 100);
                                progressFill.style.width = percent + '%';
                                progressPercent.textContent = percent + '%';
                                progressLabel.textContent = '📤 جاري رفع الملف...';
                            }}
                        }};
                        xhr.send(formData);
                    }});

                    const progressInterval = setInterval(() => {{
                        if (isAnalyzing) {{
                            const current = parseInt(progressFill.style.width);
                            if (current < 80) {{
                                const newVal = Math.min(current + 2, 80);
                                progressFill.style.width = newVal + '%';
                                progressPercent.textContent = newVal + '%';
                                progressLabel.textContent = '🧠 جاري التحليل التلقائي...';
                            }}
                        }}
                    }}, 200);

                    const results = await promise;
                    clearInterval(progressInterval);

                    if (isAnalyzing) {{
                        progressFill.style.width = '100%';
                        progressPercent.textContent = '100%';
                        progressLabel.textContent = '✅ تم الانتهاء!';
                        stopBtn.style.display = 'none';
                        isAnalyzing = false;
                        currentResults = results;
                        displayResults(results);
                        filterHighBtn.style.display = 'inline-block';
                    }}

                }} catch (error) {{
                    showError('❌ خطأ: ' + error.message);
                    progressContainer.style.display = 'none';
                    stopBtn.style.display = 'none';
                    isAnalyzing = false;
                }}
            }}

            function displayResults(results) {{
                tableBody.innerHTML = '';
                
                const total = results.length;
                const high = results.filter(r => r.confidence === 'عالية' || r.confidence === 'عالية جداً').length;
                const medium = results.filter(r => r.confidence === 'متوسطة').length;
                const low = results.filter(r => r.confidence === 'منخفضة' || r.confidence === 'منخفضة جداً').length;
                
                resultCount.textContent = total;
                highCount.textContent = high;
                mediumCount.textContent = medium;
                lowCount.textContent = low;

                if (results.length === 0) {{
                    tableBody.innerHTML = `<tr><td colspan="6" style="text-align:center; color:#ffaa00; padding:30px;">⚠️ لم يتم العثور على أوفستات، حاول رفع ملف مختلف</td></tr>`;
                }} else {{
                    results.forEach((item, index) => {{
                        const row = document.createElement('tr');
                        let confidenceClass = 'confidence-medium';
                        if (item.confidence === 'عالية' || item.confidence === 'عالية جداً') confidenceClass = 'confidence-high';
                        else if (item.confidence === 'منخفضة' || item.confidence === 'منخفضة جداً') confidenceClass = 'confidence-low';
                        
                        row.innerHTML = `
                            <td>${{index + 1}}</td>
                            <td><strong>${{item.name}}</strong></td>
                            <td class="address">${{item.address}}</td>
                            <td>${{item.type}}</td>
                            <td>${{item.description}}</td>
                            <td><span class="confidence ${{confidenceClass}}">${{item.confidence}}</span></td>
                        `;
                        tableBody.appendChild(row);
                    }});
                }}

                exportBtn.style.display = 'inline-block';
                exportBtn.onclick = () => exportResults(results);
                generateHookBtn.style.display = 'inline-block';
                generateHookBtn.onclick = () => generateHook(results);
                resultsDiv.style.display = 'block';
            }}

            function exportResults(results) {{
                const blob = new Blob([JSON.stringify(results, null, 2)], {{ type: 'application/json' }});
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = 'extracted_offsets.json';
                a.click();
                URL.revokeObjectURL(url);
            }}

            async function generateHook(offsets) {{
                if (!offsets || offsets.length === 0) {{
                    showError('⚠️ لا توجد أوفستات لتوليد الهوك');
                    return;
                }}

                try {{
                    const response = await fetch('/generate_hook', {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify({{
                            lib_name: 'extracted_lib',
                            offsets: offsets
                        }})
                    }});

                    if (!response.ok) {{
                        throw new Error('فشل توليد الهوك');
                    }}

                    const data = await response.json();
                    hookCodeDisplay.textContent = data.hook_code;
                    hookSection.style.display = 'block';
                    copyHookBtn.onclick = () => {{
                        navigator.clipboard.writeText(data.hook_code);
                        copyHookBtn.textContent = '✅ تم النسخ!';
                        setTimeout(() => copyHookBtn.textContent = '📋 نسخ الكود', 2000);
                    }};

                }} catch (error) {{
                    showError('❌ خطأ في توليد الهوك: ' + error.message);
                }}
            }}

            const manualLibName = document.getElementById('manual-lib-name');
            const manualOffsetsInput = document.getElementById('manual-offsets-input');
            const manualGenerateBtn = document.getElementById('manual-generate-btn');
            const manualHookOutput = document.getElementById('manual-hook-output');
            const manualHookCodeDisplay = document.getElementById('manual-hook-code-display');
            const copyManualHookBtn = document.getElementById('copy-manual-hook-btn');

            manualGenerateBtn.addEventListener('click', async () => {{
                const libName = manualLibName.value.trim();
                const offsetsJson = manualOffsetsInput.value.trim();

                if (!libName) {{
                    showError('⚠️ يرجى إدخال اسم الـ LIB');
                    return;
                }}

                if (!offsetsJson) {{
                    showError('⚠️ يرجى إدخال الأوفستات بصيغة JSON');
                    return;
                }}

                let offsets;
                try {{
                    offsets = JSON.parse(offsetsJson);
                    if (!Array.isArray(offsets) || offsets.length === 0) {{
                        throw new Error('يجب أن تكون الأوفستات مصفوفة غير فارغة');
                    }}
                }} catch (e) {{
                    showError('⚠️ صيغة JSON غير صحيحة: ' + e.message);
                    return;
                }}

                try {{
                    const response = await fetch('/generate_hook', {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify({{
                            lib_name: libName,
                            offsets: offsets
                        }})
                    }});

                    if (!response.ok) {{
                        throw new Error('فشل توليد الهوك');
                    }}

                    const data = await response.json();
                    manualHookCodeDisplay.textContent = data.hook_code;
                    manualHookOutput.style.display = 'block';
                    copyManualHookBtn.onclick = () => {{
                        navigator.clipboard.writeText(data.hook_code);
                        copyManualHookBtn.textContent = '✅ تم النسخ!';
                        setTimeout(() => copyManualHookBtn.textContent = '📋 نسخ الكود', 2000);
                    }};

                }} catch (error) {{
                    showError('❌ خطأ في توليد الهوك: ' + error.message);
                }}
            }});

            function showError(msg) {{
                errorMsg.textContent = msg;
                errorMsg.style.display = 'block';
                setTimeout(() => errorMsg.style.display = 'none', 6000);
            }}
        </script>
    </body>
    </html>
    """
    return render_template_string(html)

@app.route('/webhook', methods=['POST'])
def webhook():
    """معالجة تحديثات التيلجرام عبر Webhook"""
    update = request.get_json()
    
    if 'message' in update:
        message = update['message']
        chat_id = message['chat']['id']
        user_id = message['from']['id']
        text = message.get('text', '')
        
        # التحقق من الصلاحية
        if str(user_id) not in ADMIN_IDS and str(chat_id) not in ADMIN_IDS:
            send_telegram_message("⛔ أنت غير مصرح لك باستخدام هذا البوت.", chat_id)
            return jsonify({'status': 'ok'})
        
        # معالجة الأوامر
        if text.startswith('/'):
            handle_command(text, chat_id, user_id)
    
    return jsonify({'status': 'ok'})

def handle_command(text, chat_id, user_id):
    """معالجة الأوامر"""
    command = text.split(' ')[0].lower()
    args = text.split(' ')[1:] if len(text.split(' ')) > 1 else []
    
    if command == '/start':
        welcome = f"""
🎯 <b>مرحباً بك في لوحة تحكم الأداة!</b>

📋 <b>الأوامر المتاحة:</b>
/start - عرض هذه القائمة
/stats - عرض إحصائيات الزوار
/visitors - عرض آخر 10 زوار
/fingerprint <id> - عرض بصمة زائر معين
/broadcast <رسالة> - إرسال رسالة لجميع الزوار
/message <رسالة> - إرسال رسالة للمستخدمين
/messages - عرض الرسائل المعلقة
/approve <id> - الموافقة على رسالة
/reject <id> - رفض رسالة
/texts - عرض جميع النصوص
/settext <key> <value> - تغيير نص
/status - حالة السيرفر
/restart - إعادة تشغيل السيرفر

🛠️ <b>لوحة التحكم:</b>
يمكنك التحكم في جميع إعدادات السيرفر من هنا!
"""
        send_telegram_message(welcome, chat_id)
    
    elif command == '/stats':
        stats = get_visitor_stats()
        
        message = f"""
📊 <b>إحصائيات الزوار</b>

👥 <b>إجمالي الزيارات:</b> {stats['total']}
👤 <b>زوار فريدين:</b> {stats['unique']}
📅 <b>اليوم:</b> {stats['today']}
📆 <b>هذا الأسبوع:</b> {stats['week']}

📱 <b>أنواع الأجهزة:</b>
"""
        for device, count in stats['devices']:
            message += f"  • {device}: {count}\n"
        
        message += f"\n🌐 <b>المتصفحات:</b>\n"
        for browser, count in stats['browsers']:
            message += f"  • {browser}: {count}\n"
        
        message += f"\n💻 <b>أنظمة التشغيل:</b>\n"
        for os_name, count in stats['os']:
            message += f"  • {os_name}: {count}\n"
        
        message += f"\n📍 <b>أكثر الدول زيارة:</b>\n"
        for country, count in stats['countries']:
            message += f"  • {country}: {count}\n"
        
        send_telegram_message(message, chat_id)
    
    elif command == '/visitors':
        visitors = get_recent_visitors(10)
        
        if not visitors:
            send_telegram_message("📭 لا يوجد زوار حتى الآن.", chat_id)
            return
        
        message = "👥 <b>آخر 10 زوار:</b>\n\n"
        for i, visitor in enumerate(visitors, 1):
            message += f"<b>{i}.</b> 🆔 {visitor[1][:8]}... | {visitor[3]} | {visitor[6]} | {visitor[7]}\n"
            message += f"   📅 {visitor[9][:19]} | زيارات: {visitor[10]}\n"
            message += f"   🔍 /fingerprint {visitor[1]}\n\n"
        
        send_telegram_message(message, chat_id)
    
    elif command == '/fingerprint':
        if len(args) < 1:
            send_telegram_message("⚠️ استخدم: /fingerprint <البصمة>", chat_id)
            return
        
        fingerprint = args[0]
        visitor = get_visitor_by_fingerprint(fingerprint)
        
        if not visitor:
            send_telegram_message(f"❌ لا يوجد زائر بالبصمة: {fingerprint}", chat_id)
            return
        
        message = f"""
🔍 <b>معلومات الزائر:</b>

🆔 <b>البصمة:</b> <code>{visitor[1]}</code>
📡 <b>IP:</b> {visitor[2]}
👤 <b>الجهاز:</b> {visitor[4]}
🌐 <b>المتصفح:</b> {visitor[5]}
💻 <b>نظام التشغيل:</b> {visitor[6]}
📍 <b>الدولة:</b> {visitor[7]}
🏙️ <b>المدينة:</b> {visitor[8]}
📅 <b>أول زيارة:</b> {visitor[9][:19]}
📅 <b>آخر زيارة:</b> {visitor[10][:19]}
🔄 <b>عدد الزيارات:</b> {visitor[11]}

📌 <b>User Agent:</b> {visitor[3][:100]}...
"""
        send_telegram_message(message, chat_id)
    
    elif command == '/broadcast':
        if len(args) < 1:
            send_telegram_message("⚠️ استخدم: /broadcast <الرسالة>", chat_id)
            return
        
        content = ' '.join(args)
        add_message(content, 'admin', 'system_broadcast', 'pending')
        
        send_telegram_message(f"📨 تم إضافة رسالة البث: {content[:100]}...\n\n⏳ في انتظار الموافقة.", chat_id)
    
    elif command == '/message':
        if len(args) < 1:
            send_telegram_message("⚠️ استخدم: /message <الرسالة>", chat_id)
            return
        
        content = ' '.join(args)
        add_message(content, 'admin', 'system_message', 'pending')
        
        send_telegram_message(f"📨 تم إضافة الرسالة: {content[:100]}...\n\n⏳ في انتظار الموافقة.", chat_id)
    
    elif command == '/messages':
        pending = get_pending_messages()
        
        if not pending:
            send_telegram_message("📭 لا توجد رسائل معلقة.", chat_id)
            return
        
        message = "📨 <b>الرسائل المعلقة:</b>\n\n"
        for msg_id, content, user_ip, fingerprint, sent_at in pending:
            message += f"<b>#{msg_id}</b> | {sent_at[:19]}\n"
            message += f"📌 {content[:100]}{'...' if len(content) > 100 else ''}\n"
            message += f"🔍 /approve {msg_id} | /reject {msg_id}\n\n"
        
        send_telegram_message(message, chat_id)
    
    elif command == '/approve':
        if len(args) < 1:
            send_telegram_message("⚠️ استخدم: /approve <الرقم>", chat_id)
            return
        
        try:
            msg_id = int(args[0])
            update_message_status(msg_id, 'approved')
            send_telegram_message(f"✅ تم الموافقة على الرسالة #{msg_id}", chat_id)
        except Exception as e:
            send_telegram_message(f"❌ خطأ: {e}", chat_id)
    
    elif command == '/reject':
        if len(args) < 1:
            send_telegram_message("⚠️ استخدم: /reject <الرقم>", chat_id)
            return
        
        try:
            msg_id = int(args[0])
            update_message_status(msg_id, 'rejected')
            send_telegram_message(f"❌ تم رفض الرسالة #{msg_id}", chat_id)
        except Exception as e:
            send_telegram_message(f"❌ خطأ: {e}", chat_id)
    
    elif command == '/texts':
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('SELECT key, value FROM texts')
        results = c.fetchall()
        conn.close()
        
        message = "📝 <b>النصوص الحالية:</b>\n\n"
        for key, value in results:
            message += f"<b>{key}:</b> {value[:50]}{'...' if len(value) > 50 else ''}\n"
        
        send_telegram_message(message, chat_id)
    
    elif command == '/settext':
        if len(args) < 2:
            send_telegram_message("⚠️ استخدم: /settext <الاسم> <القيمة>", chat_id)
            return
        
        key = args[0]
        value = ' '.join(args[1:])
        set_text(key, value)
        send_telegram_message(f"✅ تم تحديث النص <b>{key}</b> بنجاح!", chat_id)
    
    elif command == '/status':
        bot_status = get_setting('bot_status')
        total_visitors = get_setting('total_visitors')
        unique_visitors = get_setting('unique_visitors')
        last_update = get_setting('last_update')
        
        message = f"""
🟢 <b>حالة السيرفر:</b>

🤖 <b>حالة البوت:</b> {'✅ نشط' if bot_status == 'active' else '❌ متوقف'}
👥 <b>إجمالي الزيارات:</b> {total_visitors or 0}
👤 <b>زوار فريدين:</b> {unique_visitors or 0}
📊 <b>آخر تحديث:</b> {last_update or datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

🛠️ <b>الخدمات:</b>
• 🔍 استخراج الأوفستات: نشط
• 🔗 توليد الهوك: نشط
• 📨 نظام الرسائل: نشط
"""
        send_telegram_message(message, chat_id)
    
    elif command == '/restart':
        send_telegram_message("🔄 جاري إعادة تشغيل السيرفر...", chat_id)
        os.system('systemctl restart flask_app')
    
    else:
        send_telegram_message("⚠️ أمر غير معروف. استخدم /start لعرض الأوامر المتاحة.", chat_id)

@app.route('/analyze', methods=['POST'])
def analyze():
    global stop_analysis
    stop_analysis = False
    
    if 'file' not in request.files:
        return jsonify({'error': 'لم يتم رفع ملف'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'لم يتم اختيار ملف'}), 400
    
    with tempfile.NamedTemporaryFile(delete=False, suffix='.so') as tmp:
        file.save(tmp.name)
        tmp_path = tmp.name
    
    try:
        results = analyze_so_file(tmp_path)
        return jsonify(results)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

@app.route('/generate_hook', methods=['POST'])
def generate_hook_endpoint():
    data = request.json
    lib_name = data.get('lib_name', 'unknown_lib')
    offsets = data.get('offsets', [])
    
    if not offsets:
        return jsonify({'error': 'لا توجد أوفستات لتوليد الهوك'}), 400
    
    hook_code = generate_hook(lib_name, offsets)
    return jsonify({'hook_code': hook_code})

@app.route('/stop', methods=['POST'])
def stop():
    global stop_analysis
    stop_analysis = True
    return jsonify({'status': 'stopped'})

@app.route('/get_text/<key>')
def get_text_endpoint(key):
    value = get_text(key)
    return jsonify({'key': key, 'value': value})

@app.route('/set_text', methods=['POST'])
def set_text_endpoint():
    data = request.json
    key = data.get('key')
    value = data.get('value')
    if key and value:
        set_text(key, value)
        return jsonify({'status': 'success'})
    return jsonify({'error': 'Missing key or value'}), 400

# ================================================================
# تشغيل التطبيق
# ================================================================

if __name__ == '__main__':
    print("✅ الخادم يعمل على http://localhost:5000")
    print("📊 صفحة الإحصائيات: http://localhost:5000/stats")
    print("🟢 البوت يعمل عبر Webhook")
    print("=" * 50)
    print("🚀 اكتمل التحميل! الأداة جاهزة للعمل.")
    print("🔔 ملاحظة: يجب عليك تعيين Webhook باستخدام set_webhook()")
    
    app.run(host='0.0.0.0', port=5000, debug=True)
