from flask import Flask, jsonify, request
import sqlite3
import threading
from datetime import datetime

app = Flask(_name_)
db_lock = threading.Lock()

def setup_db():
    conn = sqlite3.connect("hydnews.db")
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS updates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        university TEXT, title TEXT UNIQUE, url TEXT,
        status TEXT DEFAULT 'pending',
        detected_at TEXT, approved_at TEXT, approved_by TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS students (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        phone TEXT UNIQUE, name TEXT, university TEXT,
        course TEXT, year TEXT, registered_at TEXT,
        is_active INTEGER DEFAULT 1)""")
    c.execute("""CREATE TABLE IF NOT EXISTS admin_users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE, password TEXT,
        name TEXT, role TEXT DEFAULT 'editor')""")
    c.execute("""INSERT OR IGNORE INTO admin_users
        (username, password, name, role)
        VALUES ('vishal', 'hydnews2026', 'Vishal', 'admin')""")
    conn.commit()
    conn.close()

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    conn = sqlite3.connect("hydnews.db")
    c = conn.cursor()
    c.execute("SELECT * FROM admin_users WHERE username=? AND password=?",
              (data.get('username'), data.get('password')))
    user = c.fetchone()
    conn.close()
    if user:
        return jsonify({"success": True, "name": user[3], "role": user[4]})
    return jsonify({"success": False})

@app.route('/updates/add', methods=['POST'])
def add_update():
    data = request.json
    with db_lock:
        conn = sqlite3.connect("hydnews.db")
        c = conn.cursor()
        try:
            c.execute("""INSERT OR IGNORE INTO updates
                (university, title, url, status, detected_at)
                VALUES (?, ?, ?, 'pending', ?)""",
                (data.get('university'), data.get('title'),
                 data.get('url'), datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()
            inserted = c.rowcount
        except:
            inserted = 0
        conn.close()
    return jsonify({"success": inserted > 0})

@app.route('/updates/pending', methods=['GET'])
def get_pending():
    conn = sqlite3.connect("hydnews.db")
    c = conn.cursor()
    c.execute("""SELECT id, university, title, url, detected_at
        FROM updates WHERE status='pending'
        ORDER BY detected_at DESC""")
    rows = c.fetchall()
    conn.close()
    return jsonify([{"id": r[0], "university": r[1],
        "title": r[2], "url": r[3], "detected_at": r[4]} for r in rows])

@app.route('/updates/all', methods=['GET'])
def get_all():
    conn = sqlite3.connect("hydnews.db")
    c = conn.cursor()
    c.execute("""SELECT id, university, title, url, status,
        detected_at, approved_at, approved_by
        FROM updates ORDER BY detected_at DESC LIMIT 200""")
    rows = c.fetchall()
    conn.close()
    return jsonify([{"id": r[0], "university": r[1], "title": r[2],
        "url": r[3], "status": r[4], "detected_at": r[5],
        "approved_at": r[6], "approved_by": r[7]} for r in rows])

@app.route('/updates/approve', methods=['POST'])
def approve():
    data = request.json
    conn = sqlite3.connect("hydnews.db")
    c = conn.cursor()
    c.execute("""UPDATE updates SET status='approved',
        approved_at=?, approved_by=? WHERE id=?""",
        (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
         data.get('approved_by', 'admin'), data.get('id')))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/updates/reject', methods=['POST'])
def reject():
    data = request.json
    conn = sqlite3.connect("hydnews.db")
    c = conn.cursor()
    c.execute("UPDATE updates SET status='rejected' WHERE id=?",
              (data.get('id'),))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/updates/stats', methods=['GET'])
def stats():
    conn = sqlite3.connect("hydnews.db")
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM updates WHERE status='pending'")
    pending = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM updates WHERE status='approved'")
    approved = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM updates WHERE status='rejected'")
    rejected = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM students WHERE is_active=1")
    students = c.fetchone()[0]
    conn.close()
    return jsonify({"pending": pending, "approved": approved,
        "rejected": rejected, "students": students})

@app.route('/students', methods=['GET'])
def get_students():
    conn = sqlite3.connect("hydnews.db")
    c = conn.cursor()
    c.execute("""SELECT id, phone, name, university, course, year, registered_at
        FROM students WHERE is_active=1 ORDER BY registered_at DESC""")
    rows = c.fetchall()
    conn.close()
    return jsonify([{"id": r[0], "phone": r[1], "name": r[2],
        "university": r[3], "course": r[4],
        "year": r[5], "registered_at": r[6]} for r in rows])

@app.route('/students/add', methods=['POST'])
def add_student():
    data = request.json
    conn = sqlite3.connect("hydnews.db")
    c = conn.cursor()
    try:
        c.execute("""INSERT OR IGNORE INTO students
            (phone, name, university, course, year, registered_at)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (data.get('phone'), data.get('name'),
             data.get('university'), data.get('course'),
             data.get('year'), datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        success = c.rowcount > 0
    except:
        success = False
    conn.close()
    return jsonify({"success": success})

@app.route('/', methods=['GET'])
def health():
    setup_db()
    return jsonify({"status": "HydNews API Running"})

if _name_ == '_main_':
    setup_db()
    app.run(host='0.0.0.0', port=5000)