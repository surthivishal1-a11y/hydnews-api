from flask import Flask, jsonify, request
import threading
from datetime import datetime
import os

app = Flask(__name__)
db_lock = threading.Lock()

DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://postgres:IlQWGghtCaBGVflkKoCyDCBnhIERySuf@postgres.railway.internal:5432/railway')

def get_conn():
    import psycopg2
    return psycopg2.connect(DATABASE_URL)

def setup_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS updates (
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
    c.execute("""CREATE TABLE IF NOT EXISTS students (
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
    c.execute("""CREATE TABLE IF NOT EXISTS admin_users (
        id SERIAL PRIMARY KEY,
        username TEXT UNIQUE,
        password TEXT,
        name TEXT,
        role TEXT DEFAULT 'editor',
        last_login TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS sent_log (
        id SERIAL PRIMARY KEY,
        update_id INTEGER,
        student_phone TEXT,
        sent_at TEXT,
        status TEXT DEFAULT 'sent')""")
    c.execute("""CREATE TABLE IF NOT EXISTS ads (
        id SERIAL PRIMARY KEY,
        advertiser_name TEXT,
        ad_text TEXT,
        target_university TEXT,
        target_course TEXT,
        is_active INTEGER DEFAULT 1,
        created_at TEXT,
        expires_at TEXT)""")
    c.execute("""INSERT INTO admin_users
        (username, password, name, role)
        VALUES ('vishal', 'hydnews2026', 'Vishal', 'admin')
        ON CONFLICT (username) DO NOTHING""")
    conn.commit()
    conn.close()

@app.route('/', methods=['GET'])
def health():
    setup_db()
    return jsonify({"status": "HydNews API Running", "version": "2.0"})

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM admin_users WHERE username=%s AND password=%s",
              (data.get('username'), data.get('password')))
    user = c.fetchone()
    if user:
        c.execute("UPDATE admin_users SET last_login=%s WHERE username=%s",
                  (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), data.get('username')))
        conn.commit()
    conn.close()
    if user:
        return jsonify({"success": True, "name": user[3], "role": user[4]})
    return jsonify({"success": False, "message": "Wrong credentials"})

@app.route('/updates/add', methods=['POST'])
def add_update():
    data = request.json
    with db_lock:
        conn = get_conn()
        c = conn.cursor()
        try:
            c.execute("""INSERT INTO updates
                (university, title, url, category, status, detected_at)
                VALUES (%s, %s, %s, %s, 'pending', %s)
                ON CONFLICT (title) DO NOTHING""",
                (data.get('university'), data.get('title'),
                 data.get('url'), data.get('category', 'General'),
                 datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()
            inserted = c.rowcount
        except Exception as e:
            conn.rollback()
            inserted = 0
            print("DB Error:", e)
        conn.close()
    return jsonify({"success": inserted > 0})

@app.route('/updates/pending', methods=['GET'])
def get_pending():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""SELECT id, university, title, url, category, detected_at
        FROM updates WHERE status='pending'
        ORDER BY detected_at DESC""")
    rows = c.fetchall()
    conn.close()
    return jsonify([{"id": r[0], "university": r[1], "title": r[2],
        "url": r[3], "category": r[4], "detected_at": r[5]} for r in rows])

@app.route('/updates/all', methods=['GET'])
def get_all():
    limit = request.args.get('limit', 200)
    status = request.args.get('status', None)
    conn = get_conn()
    c = conn.cursor()
    if status:
        c.execute("""SELECT id, university, title, url, category,
            status, detected_at, approved_at, approved_by
            FROM updates WHERE status=%s
            ORDER BY detected_at DESC LIMIT %s""", (status, limit))
    else:
        c.execute("""SELECT id, university, title, url, category,
            status, detected_at, approved_at, approved_by
            FROM updates ORDER BY detected_at DESC LIMIT %s""", (limit,))
    rows = c.fetchall()
    conn.close()
    return jsonify([{"id": r[0], "university": r[1], "title": r[2],
        "url": r[3], "category": r[4], "status": r[5],
        "detected_at": r[6], "approved_at": r[7],
        "approved_by": r[8]} for r in rows])

@app.route('/updates/approve', methods=['POST'])
def approve():
    data = request.json
    conn = get_conn()
    c = conn.cursor()
    c.execute("""UPDATE updates SET status='approved',
        approved_at=%s, approved_by=%s, message=%s WHERE id=%s""",
        (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
         data.get('approved_by', 'admin'),
         data.get('message', ''), data.get('id')))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/updates/approve_all', methods=['POST'])
def approve_all():
    data = request.json
    year = data.get('year', '2026')
    conn = get_conn()
    c = conn.cursor()
    c.execute("""UPDATE updates SET status='approved',
        approved_at=%s, approved_by='auto'
        WHERE status='pending'
        AND detected_at >= %s""",
        (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
         year + '-01-01'))
    approved = c.rowcount
    c.execute("""DELETE FROM updates
        WHERE status='pending'
        AND (title LIKE '%2010%' OR title LIKE '%2011%'
        OR title LIKE '%2012%' OR title LIKE '%2013%'
        OR title LIKE '%2014%' OR title LIKE '%2015%')""")
    deleted = c.rowcount
    conn.commit()
    conn.close()
    return jsonify({"success": True, "approved": approved, "deleted": deleted})

@app.route('/updates/reject', methods=['POST'])
def reject():
    data = request.json
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE updates SET status='rejected' WHERE id=%s", (data.get('id'),))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/updates/stats', methods=['GET'])
def stats():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM updates WHERE status='pending'")
    pending = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM updates WHERE status='approved'")
    approved = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM updates WHERE status='rejected'")
    rejected = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM updates")
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM students WHERE is_active=1")
    students = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM students WHERE status='alumni'")
    alumni = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM updates WHERE detected_at >= CURRENT_DATE::text")
    today = c.fetchone()[0]
    conn.close()
    return jsonify({"pending": pending, "approved": approved,
        "rejected": rejected, "total": total,
        "students": students, "alumni": alumni, "today": today})

@app.route('/updates/by_category', methods=['GET'])
def by_category():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""SELECT category, COUNT(*) as count
        FROM updates GROUP BY category ORDER BY count DESC""")
    rows = c.fetchall()
    conn.close()
    return jsonify([{"category": r[0], "count": r[1]} for r in rows])

@app.route('/students', methods=['GET'])
def get_students():
    university = request.args.get('university', None)
    course = request.args.get('course', None)
    year = request.args.get('year', None)
    conn = get_conn()
    c = conn.cursor()
    query = """SELECT id, phone, name, university, course,
        current_year, current_semester, hall_ticket,
        regulation, has_backlog, status, registered_at
        FROM students WHERE is_active=1"""
    params = []
    if university:
        query += " AND university=%s"
        params.append(university)
    if course:
        query += " AND course=%s"
        params.append(course)
    if year:
        query += " AND current_year=%s"
        params.append(year)
    query += " ORDER BY registered_at DESC"
    c.execute(query, params)
    rows = c.fetchall()
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
    c = conn.cursor()
    try:
        c.execute("""INSERT INTO students
            (phone, name, university, course, current_year,
             current_semester, hall_ticket, regulation,
             total_years, registered_at, last_updated)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (phone) DO NOTHING""",
            (data.get('phone'), data.get('name'),
             data.get('university'), data.get('course'),
             data.get('year', 1), data.get('semester', 1),
             data.get('hall_ticket', ''), data.get('regulation', ''),
             total_years,
             datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
             datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        success = c.rowcount > 0
    except Exception as e:
        conn.rollback()
        success = False
    conn.close()
    return jsonify({"success": success})

@app.route('/students/update_progress', methods=['POST'])
def update_progress():
    data = request.json
    phone = data.get('phone')
    passed = data.get('passed', False)
    conn = get_conn()
    c = conn.cursor()
    c.execute("""SELECT current_year, current_semester,
        total_years, has_backlog, backlog_sems
        FROM students WHERE phone=%s""", (phone,))
    student = c.fetchone()
    if not student:
        conn.close()
        return jsonify({"success": False, "message": "Student not found"})
    current_year, current_sem, total_years, has_backlog, backlog_sems = student
    if passed:
        if current_sem == 1:
            new_sem = 2
            new_year = current_year
        else:
            new_sem = 1
            new_year = current_year + 1
        if new_year > total_years:
            c.execute("""UPDATE students SET status='alumni',
                last_updated=%s WHERE phone=%s""",
                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), phone))
            conn.commit()
            conn.close()
            return jsonify({"success": True, "status": "alumni",
                "message": "Degree completed! Congratulations!"})
        c.execute("""UPDATE students SET current_year=%s,
            current_semester=%s, last_updated=%s WHERE phone=%s""",
            (new_year, new_sem,
             datetime.now().strftime("%Y-%m-%d %H:%M:%S"), phone))
    else:
        backlog = backlog_sems or ""
        sem_key = "Y" + str(current_year) + "S" + str(current_sem)
        if sem_key not in backlog:
            backlog = backlog + "," + sem_key if backlog else sem_key
        c.execute("""UPDATE students SET has_backlog=1,
            backlog_sems=%s, last_updated=%s WHERE phone=%s""",
            (backlog, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), phone))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/students/stats', methods=['GET'])
def student_stats():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""SELECT university, COUNT(*) FROM students
        WHERE is_active=1 GROUP BY university ORDER BY 2 DESC""")
    by_university = c.fetchall()
    c.execute("""SELECT course, COUNT(*) FROM students
        WHERE is_active=1 GROUP BY course ORDER BY 2 DESC""")
    by_course = c.fetchall()
    c.execute("""SELECT current_year, COUNT(*) FROM students
        WHERE is_active=1 GROUP BY current_year ORDER BY 1""")
    by_year = c.fetchall()
    c.execute("SELECT COUNT(*) FROM students WHERE is_active=1")
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM students WHERE has_backlog=1")
    backlog = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM students WHERE status='alumni'")
    alumni = c.fetchone()[0]
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
    c = conn.cursor()
    query = "SELECT id, advertiser_name, ad_text FROM ads WHERE is_active=1"
    params = []
    if university:
        query += " AND (target_university=%s OR target_university='all')"
        params.append(university)
    if course:
        query += " AND (target_course=%s OR target_course='all')"
        params.append(course)
    c.execute(query, params)
    rows = c.fetchall()
    conn.close()
    return jsonify([{"id": r[0], "advertiser": r[1], "text": r[2]} for r in rows])

@app.route('/ads/add', methods=['POST'])
def add_ad():
    data = request.json
    conn = get_conn()
    c = conn.cursor()
    c.execute("""INSERT INTO ads
        (advertiser_name, ad_text, target_university,
         target_course, is_active, created_at, expires_at)
        VALUES (%s, %s, %s, %s, 1, %s, %s)""",
        (data.get('advertiser_name'), data.get('ad_text'),
         data.get('target_university', 'all'),
         data.get('target_course', 'all'),
         datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
         data.get('expires_at', '')))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/sent_log/add', methods=['POST'])
def add_sent_log():
    data = request.json
    conn = get_conn()
    c = conn.cursor()
    c.execute("""INSERT INTO sent_log
        (update_id, student_phone, sent_at, status)
        VALUES (%s, %s, %s, %s)""",
        (data.get('update_id'), data.get('student_phone'),
         datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
         data.get('status', 'sent')))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/team/add', methods=['POST'])
def add_team():
    data = request.json
    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute("""INSERT INTO admin_users
            (username, password, name, role)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (username) DO NOTHING""",
            (data.get('username'), data.get('password'),
             data.get('name'), data.get('role', 'editor')))
        conn.commit()
        success = c.rowcount > 0
    except:
        conn.rollback()
        success = False
    conn.close()
    return jsonify({"success": success})

@app.route('/team', methods=['GET'])
def get_team():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, username, name, role, last_login FROM admin_users")
    rows = c.fetchall()
    conn.close()
    return jsonify([{"id": r[0], "username": r[1],
        "name": r[2], "role": r[3], "last_login": r[4]} for r in rows])

if __name__ == '__main__':
    setup_db()
    app.run(host='0.0.0.0', port=5000)