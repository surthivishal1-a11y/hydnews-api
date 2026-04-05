from flask import Flask, jsonify, request
from flask_cors import CORS
import threading
from datetime import datetime
import pg8000.native
import os

app = Flask(__name__)
CORS(app)
db_lock = threading.Lock()

# ---------------- DB CONNECTION ---------------- #

def get_conn():
    return pg8000.native.Connection(
        user=os.getenv("PGUSER"),
        password=os.getenv("PGPASSWORD"),
        host=os.getenv("PGHOST"),
        port=int(os.getenv("PGPORT")),
        database=os.getenv("PGDATABASE"),
        ssl_context=True
    )

# ---------------- DB SETUP ---------------- #

def setup_db():
    conn = get_conn()

    conn.run("""CREATE TABLE IF NOT EXISTS updates (
        id SERIAL PRIMARY KEY,
        university TEXT,
        title TEXT UNIQUE,
        url TEXT,
        category TEXT DEFAULT 'General',
        status TEXT DEFAULT 'pending',
        detected_at TEXT,
        approved_at TEXT,
        approved_by TEXT,
        message TEXT)""")

    conn.run("""CREATE TABLE IF NOT EXISTS students (
        id SERIAL PRIMARY KEY,
        phone TEXT UNIQUE,
        name TEXT,
        university TEXT,
        course TEXT,
        current_year INTEGER DEFAULT 1,
        current_semester INTEGER DEFAULT 1,
        hall_ticket TEXT,
        regulation TEXT,
        has_backlog INTEGER DEFAULT 0,
        backlog_sems TEXT,
        total_years INTEGER DEFAULT 3,
        status TEXT DEFAULT 'active',
        registered_at TEXT,
        last_updated TEXT,
        is_active INTEGER DEFAULT 1)""")

    conn.run("""CREATE TABLE IF NOT EXISTS admin_users (
        id SERIAL PRIMARY KEY,
        username TEXT UNIQUE,
        password TEXT,
        name TEXT,
        role TEXT DEFAULT 'editor',
        last_login TEXT)""")

    conn.run("""CREATE TABLE IF NOT EXISTS sent_log (
        id SERIAL PRIMARY KEY,
        update_id INTEGER,
        student_phone TEXT,
        sent_at TEXT,
        status TEXT DEFAULT 'sent')""")

    conn.run("""CREATE TABLE IF NOT EXISTS ads (
        id SERIAL PRIMARY KEY,
        advertiser_name TEXT,
        ad_text TEXT,
        target_university TEXT,
        target_course TEXT,
        is_active INTEGER DEFAULT 1,
        created_at TEXT,
        expires_at TEXT)""")

    # Default admin
    conn.run("""INSERT INTO admin_users (username, password, name, role)
        VALUES ('vishal', 'hydnews2026', 'Vishal', 'admin')
        ON CONFLICT (username) DO NOTHING""")

    conn.close()


# ---------------- HEALTH ---------------- #

@app.route('/', methods=['GET'])
def health():
    return jsonify({"status": "HydNews API Running", "version": "2.0"})


# ---------------- AUTH ---------------- #

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    conn = get_conn()

    rows = conn.run("""
        SELECT id, username, password, name, role 
        FROM admin_users 
        WHERE username=:u AND password=:p
    """, u=data.get('username'), p=data.get('password'))

    user = rows[0] if rows else None

    if user:
        conn.run("""
            UPDATE admin_users SET last_login=:t WHERE username=:u
        """, t=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), u=data.get('username'))

    conn.close()

    if user:
        return jsonify({"success": True, "name": user[3], "role": user[4]})

    return jsonify({"success": False, "message": "Wrong credentials"})


# ---------------- UPDATES ---------------- #

@app.route('/updates/add', methods=['POST'])
def add_update():
    data = request.json

    with db_lock:
        conn = get_conn()
        try:
            conn.run("""
                INSERT INTO updates (university, title, url, category, status, detected_at)
                VALUES (:university, :title, :url, :category, 'pending', :detected_at)
                ON CONFLICT (title) DO NOTHING
            """,
            university=data.get('university'),
            title=data.get('title'),
            url=data.get('url'),
            category=data.get('category', 'General'),
            detected_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

            success = True
        except Exception as e:
            print("DB Error:", e)
            success = False

        conn.close()

    return jsonify({"success": success})


@app.route('/updates/pending', methods=['GET'])
def get_pending():
    conn = get_conn()

    rows = conn.run("""
        SELECT id, university, title, url, category, detected_at
        FROM updates WHERE status='pending'
        ORDER BY detected_at DESC
    """)

    conn.close()

    return jsonify([{
        "id": r[0], "university": r[1], "title": r[2],
        "url": r[3], "category": r[4], "detected_at": r[5]
    } for r in rows])


@app.route('/updates/approve', methods=['POST'])
def approve():
    data = request.json
    conn = get_conn()

    conn.run("""
        UPDATE updates SET status='approved', approved_at=:t,
        approved_by=:by, message=:m WHERE id=:id
    """,
    t=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    by=data.get('approved_by', 'admin'),
    m=data.get('message', ''),
    id=data.get('id'))

    conn.close()

    return jsonify({"success": True})


# ---------------- STUDENTS ---------------- #

@app.route('/students/add', methods=['POST'])
def add_student():
    data = request.json

    course = data.get('course', '').lower()
    if 'b.tech' in course or 'be' in course:
        total_years = 4
    elif 'mba' in course or 'm.tech' in course:
        total_years = 2
    else:
        total_years = 3

    conn = get_conn()

    try:
        conn.run("""
            INSERT INTO students
            (phone, name, university, course, current_year,
             current_semester, total_years, registered_at, last_updated)
            VALUES (:phone, :name, :university, :course, :year,
             :semester, :total_years, :registered_at, :last_updated)
            ON CONFLICT (phone) DO NOTHING
        """,
        phone=data.get('phone'),
        name=data.get('name'),
        university=data.get('university'),
        course=data.get('course'),
        year=data.get('year', 1),
        semester=data.get('semester', 1),
        total_years=total_years,
        registered_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        last_updated=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        success = True

    except Exception as e:
        print("Error:", e)
        success = False

    conn.close()

    return jsonify({"success": success})


# ---------------- MAIN ---------------- #

if __name__ == '__main__':
    print("Starting HydNews API...")
    setup_db()
    app.run(host='0.0.0.0', port=5000)