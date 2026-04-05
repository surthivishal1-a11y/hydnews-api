from flask import Flask, jsonify, request
from flask_cors import CORS
import threading
from datetime import datetime
import pg8000.native
import os

app = Flask(__name__)
CORS(app)
db_lock = threading.Lock()

def get_conn():
    return pg8000.native.Connection(
        user=os.getenv("PGUSER"),
        password=os.getenv("PGPASSWORD"),
        host=os.getenv("PGHOST"),
        port=int(os.getenv("PGPORT")),
        database=os.getenv("PGDATABASE"),
        ssl_context=True
    )

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
    conn.run("""INSERT INTO admin_users (username, password, name, role)
        VALUES ('vishal', 'hydnews2026', 'Vishal', 'admin')
        ON CONFLICT (username) DO NOTHING""")
    conn.close()

@app.route('/', methods=['GET'])
def health():
    setup_db()
    return jsonify({"status": "HydNews API Running", "version": "2.0"})

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    conn = get_conn()
    rows = conn.run("SELECT id, username, password, name, role, last_login FROM admin_users WHERE username=:u AND password=:p",
                    u=data.get('username'), p=data.get('password'))
    user = rows[0] if rows else None
    if user:
        conn.run("UPDATE admin_users SET last_login=:t WHERE username=:u",
                 t=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), u=data.get('username'))
    conn.close()
    if user:
        return jsonify({"success": True, "name": user[3], "role": user[4]})
    return jsonify({"success": False, "message": "Wrong credentials"})

@app.route('/updates/add', methods=['POST'])
def add_update():
    data = request.json
    with db_lock:
        conn = get_conn()
        try:
            conn.run("""INSERT INTO updates (university, title, url, category, status, detected_at)
                VALUES (:university, :title, :url, :category, 'pending', :detected_at)
                ON CONFLICT (title) DO NOTHING""",
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
    rows = conn.run("""SELECT id, university, title, url, category, detected_at
        FROM updates WHERE status='pending' ORDER BY detected_at DESC""")
    conn.close()
    return jsonify([{"id": r[0], "university": r[1], "title": r[2],
        "url": r[3], "category": r[4], "detected_at": r[5]} for r in rows])

@app.route('/updates/all', methods=['GET'])
def get_all():
    limit = int(request.args.get('limit', 200))
    status = request.args.get('status', None)
    conn = get_conn()
    if status:
        rows = conn.run("""SELECT id, university, title, url, category,
            status, detected_at, approved_at, approved_by
            FROM updates WHERE status=:s
            ORDER BY detected_at DESC LIMIT :l""", s=status, l=limit)
    else:
        rows = conn.run("""SELECT id, university, title, url, category,
            status, detected_at, approved_at, approved_by
            FROM updates ORDER BY detected_at DESC LIMIT :l""", l=limit)
    conn.close()
    return jsonify([{"id": r[0], "university": r[1], "title": r[2],
        "url": r[3], "category": r[4], "status": r[5],
        "detected_at": r[6], "approved_at": r[7],
        "approved_by": r[8]} for r in rows])

@app.route('/updates/approve', methods=['POST'])
def approve():
    data = request.json
    conn = get_conn()
    conn.run("""UPDATE updates SET status='approved', approved_at=:t,
        approved_by=:by, message=:m WHERE id=:id""",
        t=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        by=data.get('approved_by', 'admin'),
        m=data.get('message', ''),
        id=data.get('id'))
    conn.close()
    return jsonify({"success": True})

@app.route('/updates/approve_all', methods=['POST'])
def approve_all():
    data = request.json
    year = data.get('year', '2026')
    conn = get_conn()
    conn.run("""UPDATE updates SET status='approved', approved_at=:t, approved_by='auto'
        WHERE status='pending' AND detected_at >= :y""",
        t=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        y=year + '-01-01')
    conn.run("""DELETE FROM updates WHERE status='pending'
        AND (title LIKE '%2010%' OR title LIKE '%2011%'
        OR title LIKE '%2012%' OR title LIKE '%2013%'
        OR title LIKE '%2014%' OR title LIKE '%2015%')""")
    conn.close()
    return jsonify({"success": True})

@app.route('/updates/reject', methods=['POST'])
def reject():
    data = request.json
    conn = get_conn()
    conn.run("UPDATE updates SET status='rejected' WHERE id=:id", id=data.get('id'))
    conn.close()
    return jsonify({"success": True})

@app.route('/updates/stats', methods=['GET'])
def stats():
    conn = get_conn()
    pending = conn.run("SELECT COUNT(*) FROM updates WHERE status='pending'")[0][0]
    approved = conn.run("SELECT COUNT(*) FROM updates WHERE status='approved'")[0][0]
    rejected = conn.run("SELECT COUNT(*) FROM updates WHERE status='rejected'")[0][0]
    total = conn.run("SELECT COUNT(*) FROM updates")[0][0]
    students = conn.run("SELECT COUNT(*) FROM students WHERE is_active=1")[0][0]
    alumni = conn.run("SELECT COUNT(*) FROM students WHERE status='alumni'")[0][0]
    today = conn.run("SELECT COUNT(*) FROM updates WHERE detected_at >= :d",
                     d=datetime.now().strftime("%Y-%m-%d"))[0][0]
    conn.close()
    return jsonify({"pending": pending, "approved": approved,
        "rejected": rejected, "total": total,
        "students": students, "alumni": alumni, "today": today})

@app.route('/updates/by_category', methods=['GET'])
def by_category():
    conn = get_conn()
    rows = conn.run("SELECT category, COUNT(*) as count FROM updates GROUP BY category ORDER BY count DESC")
    conn.close()
    return jsonify([{"category": r[0], "count": r[1]} for r in rows])

@app.route('/updates/universities', methods=['GET'])
def get_universities():
    category = request.args.get('category', None)
    conn = get_conn()
    if category:
        rows = conn.run("""SELECT university, COUNT(*) as count
            FROM updates WHERE status='approved' AND category=:c
            GROUP BY university ORDER BY university""", c=category)
    else:
        rows = conn.run("""SELECT university, COUNT(*) as count
            FROM updates WHERE status='approved'
            GROUP BY university ORDER BY university""")
    conn.close()
    return jsonify([{"university": r[0], "count": r[1]} for r in rows])

@app.route('/students', methods=['GET'])
def get_students():
    university = request.args.get('university', None)
    course = request.args.get('course', None)
    year = request.args.get('year', None)
    conn = get_conn()
    query = """SELECT id, phone, name, university, course,
        current_year, current_semester, hall_ticket,
        regulation, has_backlog, status, registered_at
        FROM students WHERE is_active=1"""
    params = {}
    if university:
        query += " AND university=:university"
        params['university'] = university
    if course:
        query += " AND course=:course"
        params['course'] = course
    if year:
        query += " AND current_year=:year"
        params['year'] = year
    query += " ORDER BY registered_at DESC"
    rows = conn.run(query, **params)
    conn.close()
    return jsonify([{"id": r[0], "phone": r[1], "name": r[2],
        "university": r[3], "course": r[4], "current_year": r[5],
        "current_semester": r[6], "hall_ticket": r[7],
        "regulation": r[8], "has_backlog": r[9],
        "status": r[10], "registered_at": r[11]} for r in rows])

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
        conn.run("""INSERT INTO students
            (phone, name, university, course, current_year,
             current_semester, hall_ticket, regulation,
             total_years, registered_at, last_updated)
            VALUES (:phone, :name, :university, :course, :year,
             :semester, :hall_ticket, :regulation,
             :total_years, :registered_at, :last_updated)
            ON CONFLICT (phone) DO NOTHING""",
            phone=data.get('phone'),
            name=data.get('name'),
            university=data.get('university'),
            course=data.get('course'),
            year=data.get('year', 1),
            semester=data.get('semester', 1),
            hall_ticket=data.get('hall_ticket', ''),
            regulation=data.get('regulation', ''),
            total_years=total_years,
            registered_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            last_updated=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        success = True
    except Exception as e:
        print("Error:", e)
        success = False
    conn.close()
    return jsonify({"success": success})

@app.route('/students/update_progress', methods=['POST'])
def update_progress():
    data = request.json
    phone = data.get('phone')
    passed = data.get('passed', False)
    conn = get_conn()
    rows = conn.run("""SELECT current_year, current_semester,
        total_years, has_backlog, backlog_sems
        FROM students WHERE phone=:phone""", phone=phone)
    if not rows:
        conn.close()
        return jsonify({"success": False, "message": "Student not found"})
    current_year, current_sem, total_years, has_backlog, backlog_sems = rows[0]
    if passed:
        if current_sem == 1:
            new_sem = 2
            new_year = current_year
        else:
            new_sem = 1
            new_year = current_year + 1
        if new_year > total_years:
            conn.run("UPDATE students SET status='alumni', last_updated=:t WHERE phone=:phone",
                t=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), phone=phone)
            conn.close()
            return jsonify({"success": True, "status": "alumni",
                "message": "Degree completed! Congratulations!"})
        conn.run("""UPDATE students SET current_year=:y,
            current_semester=:s, last_updated=:t WHERE phone=:phone""",
            y=new_year, s=new_sem,
            t=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), phone=phone)
    else:
        backlog = backlog_sems or ""
        sem_key = "Y" + str(current_year) + "S" + str(current_sem)
        if sem_key not in backlog:
            backlog = backlog + "," + sem_key if backlog else sem_key
        conn.run("""UPDATE students SET has_backlog=1,
            backlog_sems=:b, last_updated=:t WHERE phone=:phone""",
            b=backlog, t=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), phone=phone)
    conn.close()
    return jsonify({"success": True})

@app.route('/students/stats', methods=['GET'])
def student_stats():
    conn = get_conn()
    by_university = conn.run("SELECT university, COUNT(*) FROM students WHERE is_active=1 GROUP BY university ORDER BY 2 DESC")
    by_course = conn.run("SELECT course, COUNT(*) FROM students WHERE is_active=1 GROUP BY course ORDER BY 2 DESC")
    by_year = conn.run("SELECT current_year, COUNT(*) FROM students WHERE is_active=1 GROUP BY current_year ORDER BY 1")
    total = conn.run("SELECT COUNT(*) FROM students WHERE is_active=1")[0][0]
    backlog = conn.run("SELECT COUNT(*) FROM students WHERE has_backlog=1")[0][0]
    alumni = conn.run("SELECT COUNT(*) FROM students WHERE status='alumni'")[0][0]
    conn.close()
    return jsonify({"total": total, "backlog": backlog, "alumni": alumni,
        "by_university": [{"university": r[0], "count": r[1]} for r in by_university],
        "by_course": [{"course": r[0], "count": r[1]} for r in by_course],
        "by_year": [{"year": r[0], "count": r[1]} for r in by_year]})

@app.route('/ads', methods=['GET'])
def get_ads():
    university = request.args.get('university', None)
    course = request.args.get('course', None)
    conn = get_conn()
    query = "SELECT id, advertiser_name, ad_text FROM ads WHERE is_active=1"
    params = {}
    if university:
        query += " AND (target_university=:university OR target_university='all')"
        params['university'] = university
    if course:
        query += " AND (target_course=:course OR target_course='all')"
        params['course'] = course
    rows = conn.run(query, **params)
    conn.close()
    return jsonify([{"id": r[0], "advertiser": r[1], "text": r[2]} for r in rows])

@app.route('/ads/add', methods=['POST'])
def add_ad():
    data = request.json
    conn = get_conn()
    conn.run("""INSERT INTO ads (advertiser_name, ad_text, target_university,
         target_course, is_active, created_at, expires_at)
         VALUES (:advertiser_name, :ad_text, :target_university,
         :target_course, 1, :created_at, :expires_at)""",
        advertiser_name=data.get('advertiser_name'),
        ad_text=data.get('ad_text'),
        target_university=data.get('target_university', 'all'),
        target_course=data.get('target_course', 'all'),
        created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        expires_at=data.get('expires_at', ''))
    conn.close()
    return jsonify({"success": True})

@app.route('/sent_log/add', methods=['POST'])
def add_sent_log():
    data = request.json
    conn = get_conn()
    conn.run("""INSERT INTO sent_log (update_id, student_phone, sent_at, status)
        VALUES (:update_id, :student_phone, :sent_at, :status)""",
        update_id=data.get('update_id'),
        student_phone=data.get('student_phone'),
        sent_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        status=data.get('status', 'sent'))
    conn.close()
    return jsonify({"success": True})

@app.route('/team/add', methods=['POST'])
def add_team():
    data = request.json
    conn = get_conn()
    try:
        conn.run("""INSERT INTO admin_users (username, password, name, role)
            VALUES (:username, :password, :name, :role)
            ON CONFLICT (username) DO NOTHING""",
            username=data.get('username'),
            password=data.get('password'),
            name=data.get('name'),
            role=data.get('role', 'editor'))
        success = True
    except:
        success = False
    conn.close()
    return jsonify({"success": success})

@app.route('/team', methods=['GET'])
def get_team():
    conn = get_conn()
    rows = conn.run("SELECT id, username, name, role, last_login FROM admin_users")
    conn.close()
    return jsonify([{"id": r[0], "username": r[1],
        "name": r[2], "role": r[3], "last_login": r[4]} for r in rows])

if __name__ == '__main__':
    setup_db()
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)