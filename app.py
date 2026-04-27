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

@app.route('/updates/get/<int:update_id>', methods=['GET'])
def get_update(update_id):
    conn = get_conn()
    rows = conn.run("""SELECT id, university, title, url, category,
        status, detected_at, approved_at, approved_by
        FROM updates WHERE id=:id""", id=update_id)
    conn.close()
    if not rows:
        return jsonify({"error": "Not found"}), 404
    r = rows[0]
    return jsonify({"id": r[0], "university": r[1], "title": r[2],
        "url": r[3], "category": r[4], "status": r[5],
        "detected_at": r[6], "approved_at": r[7], "approved_by": r[8]})

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

@app.route('/updates/by-university', methods=['GET'])
def get_by_university():
    university = request.args.get('university', '')
    limit = int(request.args.get('limit', 200))
    category = request.args.get('category', None)
    conn = get_conn()
    if category:
        rows = conn.run("""SELECT id, university, title, url, category,
            status, detected_at, approved_at, approved_by
            FROM updates WHERE status='approved' 
            AND university=:u AND category=:c
            ORDER BY detected_at DESC LIMIT :l""",
            u=university, c=category, l=limit)
    else:
        rows = conn.run("""SELECT id, university, title, url, category,
            status, detected_at, approved_at, approved_by
            FROM updates WHERE status='approved' 
            AND university=:u
            ORDER BY detected_at DESC LIMIT :l""",
            u=university, l=limit)
    conn.close()
    return jsonify([{"id": r[0], "university": r[1], "title": r[2],
        "url": r[3], "category": r[4], "status": r[5],
        "detected_at": r[6], "approved_at": r[7],
        "approved_by": r[8]} for r in rows])

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

@app.route('/updates/fix_university', methods=['POST'])
def fix_university():
    conn = get_conn()
    conn.run("""UPDATE updates SET university='General Updates'
        WHERE university='Manabadi Today'""")
    conn.close()
    return jsonify({"success": True})

if __name__ == '__main__':
    setup_db()
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
@app.route('/news/setup', methods=['POST'])
def setup_news():
    conn = get_conn()
    conn.run("""CREATE TABLE IF NOT EXISTS news (
        id SERIAL PRIMARY KEY,
        slug TEXT UNIQUE,
        title_english TEXT,
        title_telugu TEXT,
        title_hindi TEXT,
        content_english TEXT,
        content_telugu TEXT,
        content_hindi TEXT,
        source_url TEXT UNIQUE,
        category TEXT DEFAULT 'General',
        image_url TEXT,
        published_at TIMESTAMP DEFAULT NOW()
    )""")
    conn.close()
    return jsonify({'success': True})

@app.route('/news/all', methods=['GET'])
def get_all_news():
    limit = int(request.args.get('limit', 20))
    conn = get_conn()
    rows = conn.run("""SELECT id, slug, title_english, title_telugu, title_hindi, category, image_url, published_at FROM news ORDER BY published_at DESC LIMIT :l""", l=limit)
    conn.close()
    return jsonify([{'id':r[0],'slug':r[1],'title_english':r[2],'title_telugu':r[3],'title_hindi':r[4],'category':r[5],'image_url':r[6],'published_at':str(r[7])} for r in rows])

@app.route('/news/get/<slug>', methods=['GET'])
def get_news_by_slug(slug):
    conn = get_conn()
    rows = conn.run("""SELECT * FROM news WHERE slug=:s""", s=slug)
    conn.close()
    if not rows:
        return jsonify({'error': 'Not found'}), 404
    r = rows[0]
    return jsonify({'id':r[0],'slug':r[1],'title_english':r[2],'title_telugu':r[3],'title_hindi':r[4],'content_english':r[5],'content_telugu':r[6],'content_hindi':r[7],'source_url':r[8],'category':r[9],'image_url':r[10],'published_at':str(r[11])})

@app.route('/news/add', methods=['POST'])
def add_news():
    data = request.json
    conn = get_conn()
    try:
        conn.run("""INSERT INTO news (slug, title_english, title_telugu, title_hindi, content_english, content_telugu, content_hindi, source_url, category, image_url) VALUES (:slug, :te, :tt, :th, :ce, :ct, :ch, :url, :cat, :img) ON CONFLICT (source_url) DO NOTHING""",
            slug=data['slug'], te=data['title_english'], tt=data.get('title_telugu',''), th=data.get('title_hindi',''),
            ce=data['content_english'], ct=data.get('content_telugu',''), ch=data.get('content_hindi',''),
            url=data['source_url'], cat=data.get('category','General'), img=data.get('image_url',''))
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 500

@app.route('/results/check', methods=['POST'])
def check_result():
    import requests as req
    data = request.json
    hall_ticket = data.get('hall_ticket', '')

    year = data.get('year', '1')
    category = data.get('category', 'G')
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
            'Referer': 'https://tgbienew.cgg.gov.in/tgbieResultsLiveNew2026.do',
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        form_data = {
            'actionpart': 'showResult',
            'property(pass_year)': '2026',
            'year': year,
            'category': category,
            'property(month)': 'M',
            'hallticket_no': hall_ticket
        }
        res = req.post('https://tgbienew.cgg.gov.in/tgbieResultsLiveNew2026.do', data=form_data, headers=headers, timeout=15)
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(res.text, 'html.parser')
        result_text = soup.get_text()
        return jsonify({'success': True, 'html': res.text[:50000], 'result_text': result_text[:3000]})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/news/alter', methods=['POST'])
def alter_news_table():
    conn = get_conn()
    try:
        conn.run("""ALTER TABLE news ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'pending'""")
        conn.run("""ALTER TABLE news ADD COLUMN IF NOT EXISTS accuracy_score INTEGER DEFAULT 0""")
        conn.run("""ALTER TABLE news ADD COLUMN IF NOT EXISTS accuracy_issues TEXT DEFAULT ''""")
        conn.run("""ALTER TABLE news ADD COLUMN IF NOT EXISTS approved_at TIMESTAMP""")
        conn.close()
        return jsonify({'success': True, 'message': 'Columns added'})
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)})

@app.route('/news/pending', methods=['GET'])
def get_pending_news():
    conn = get_conn()
    rows = conn.run("""SELECT id, slug, title_english, title_telugu, title_hindi, category, image_url, published_at, accuracy_score, accuracy_issues FROM news WHERE status='pending' ORDER BY published_at DESC""")
    conn.close()
    return jsonify([{'id':r[0],'slug':r[1],'title_english':r[2],'title_telugu':r[3],'title_hindi':r[4],'category':r[5],'image_url':r[6],'published_at':str(r[7]),'accuracy_score':r[8],'accuracy_issues':r[9]} for r in rows])

@app.route('/news/approve/<int:news_id>', methods=['POST'])
def approve_news(news_id):
    conn = get_conn()
    conn.run("""UPDATE news SET status='published', approved_at=NOW() WHERE id=:id""", id=news_id)
    conn.close()
    return jsonify({'success': True})

@app.route('/news/reject/<int:news_id>', methods=['POST'])
def reject_news(news_id):
    conn = get_conn()
    conn.run("""DELETE FROM news WHERE id=:id""", id=news_id)
    conn.close()
    return jsonify({'success': True})

@app.route('/news/published', methods=['GET'])
def get_published_news():
    limit = int(request.args.get('limit', 20))
    category = request.args.get('category', None)
    conn = get_conn()
    if category:
        rows = conn.run("""SELECT id, slug, title_english, title_telugu, title_hindi, category, image_url, published_at, accuracy_score FROM news WHERE status='published' AND category=:c ORDER BY published_at DESC LIMIT :l""", c=category, l=limit)
    else:
        rows = conn.run("""SELECT id, slug, title_english, title_telugu, title_hindi, category, image_url, published_at, accuracy_score FROM news WHERE status='published' ORDER BY published_at DESC LIMIT :l""", l=limit)
    conn.close()
    return jsonify([{'id':r[0],'slug':r[1],'title_english':r[2],'title_telugu':r[3],'title_hindi':r[4],'category':r[5],'image_url':r[6],'published_at':str(r[7]),'accuracy_score':r[8]} for r in rows])

@app.route('/ou/register', methods=['POST'])
def ou_register():
    try:
        data = request.json
        name = data.get('name')
        whatsapp = data.get('whatsapp')
        course = data.get('course')
        year = data.get('year')
        semester = data.get('semester')
        admission_year = data.get('admission_year')
        hall_ticket = data.get('hall_ticket', '')
        college_name = data.get('college_name', '')
        language = data.get('language', 'english')
        total_years = data.get('total_years', 3)

        if not all([name, whatsapp, course, year, semester, admission_year]):
            return jsonify({'error': 'Missing required fields'}), 400

        import psycopg2
        ou_conn = psycopg2.connect("postgresql://postgres:MWJnIiZQjLZfMONQuEQPMGSBFkNOpKeB@postgres.railway.internal:5432/railway")
        ou_cur = ou_conn.cursor()

        ou_cur.execute("SELECT id FROM ou_students WHERE whatsapp=%s", (whatsapp,))
        if ou_cur.fetchone():
            ou_cur.close()
            ou_conn.close()
            return jsonify({'error': 'WhatsApp number already registered'}), 400

        ou_cur.execute("""
            INSERT INTO ou_students 
            (name, whatsapp, college_name, course, current_year, current_semester, 
             admission_year, total_years, hall_ticket, language)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (name, whatsapp, college_name if college_name else None, course, year, semester,
              admission_year, total_years, hall_ticket or None, language))

        student_id = ou_cur.fetchone()[0]
        ou_conn.commit()
        ou_cur.close()
        ou_conn.close()

        return jsonify({'success': True, 'student_id': student_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/ou/notifications/pending', methods=['GET'])
def ou_pending_notifications():
    try:
        import psycopg2
        conn = psycopg2.connect("postgresql://postgres:MWJnIiZQjLZfMONQuEQPMGSBFkNOpKeB@postgres.railway.internal:5432/railway")
        cur = conn.cursor()
        cur.execute("""
            SELECT id, title, url, category, detected_at 
            FROM ou_notifications 
            WHERE approval_status='pending' 
            ORDER BY detected_at DESC 
            LIMIT 50
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify([{
            'id': r[0], 'title': r[1], 'url': r[2],
            'category': r[3], 'detected_at': str(r[4])
        } for r in rows])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/ou/notifications/approve/<int:notif_id>', methods=['POST'])
def ou_approve_notification(notif_id):
    try:
        import psycopg2
        conn = psycopg2.connect("postgresql://postgres:MWJnIiZQjLZfMONQuEQPMGSBFkNOpKeB@postgres.railway.internal:5432/railway")
        cur = conn.cursor()
        cur.execute("""
            UPDATE ou_notifications 
            SET approval_status='approved', approved_at=NOW()
            WHERE id=%s
            RETURNING title, url, category
        """, (notif_id,))
        row = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({'success': True, 'title': row[0]})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/ou/notifications/reject/<int:notif_id>', methods=['POST'])
def ou_reject_notification(notif_id):
    try:
        import psycopg2
        conn = psycopg2.connect("postgresql://postgres:MWJnIiZQjLZfMONQuEQPMGSBFkNOpKeB@postgres.railway.internal:5432/railway")
        cur = conn.cursor()
        cur.execute("UPDATE ou_notifications SET approval_status='rejected' WHERE id=%s", (notif_id,))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/ou/students/all', methods=['GET'])
def ou_all_students():
    try:
        import psycopg2
        conn = psycopg2.connect("postgresql://postgres:MWJnIiZQjLZfMONQuEQPMGSBFkNOpKeB@postgres.railway.internal:5432/railway")
        cur = conn.cursor()
        cur.execute("""
            SELECT id, name, whatsapp, college_name, course, 
            current_year, current_semester, hall_ticket, status, registered_at
            FROM ou_students ORDER BY registered_at DESC
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify([{
            'id': r[0], 'name': r[1], 'whatsapp': r[2],
            'college': r[3], 'course': r[4], 'year': r[5],
            'semester': r[6], 'hall_ticket': r[7],
            'status': r[8], 'registered_at': str(r[9])
        } for r in rows])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/ou/alerts/history', methods=['GET'])
def ou_alerts_history():
    try:
        import psycopg2
        conn = psycopg2.connect("postgresql://postgres:MWJnIiZQjLZfMONQuEQPMGSBFkNOpKeB@postgres.railway.internal:5432/railway")
        cur = conn.cursor()
        cur.execute("""
            SELECT a.id, s.name, s.whatsapp, s.course, 
            a.type, a.whatsapp_status, a.sent_at
            FROM ou_alerts_sent a
            JOIN ou_students s ON a.student_id = s.id
            ORDER BY a.sent_at DESC LIMIT 100
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify([{
            'id': r[0], 'name': r[1], 'whatsapp': r[2],
            'course': r[3], 'type': r[4],
            'status': r[5], 'sent_at': str(r[6])
        } for r in rows])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/ou/dashboard', methods=['GET'])
def ou_dashboard():
    try:
        import psycopg2
        conn = psycopg2.connect("postgresql://postgres:MWJnIiZQjLZfMONQuEQPMGSBFkNOpKeB@postgres.railway.internal:5432/railway")
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM ou_students WHERE status='active'")
        students = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM ou_notifications WHERE approval_status='pending'")
        pending = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM ou_notifications")
        total_notifs = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM ou_alerts_sent WHERE sent_at::date = CURRENT_DATE")
        alerts_today = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM ou_notifications WHERE category='Results'")
        results = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM ou_notifications WHERE category='Time Tables'")
        timetables = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM ou_notifications WHERE category='Notifications'")
        notifications = cur.fetchone()[0]
        cur.close()
        conn.close()
        return jsonify({
            'students': students,
            'pending_approvals': pending,
            'total_notifications': total_notifs,
            'alerts_today': alerts_today,
            'results': results,
            'timetables': timetables,
            'notifications': notifications
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/ou/scraper/logs', methods=['GET'])
def ou_scraper_logs():
    try:
        import psycopg2
        conn = psycopg2.connect("postgresql://postgres:MWJnIiZQjLZfMONQuEQPMGSBFkNOpKeB@postgres.railway.internal:5432/railway")
        cur = conn.cursor()
        cur.execute("""
            SELECT title, category, detected_at, approval_status
            FROM ou_notifications
            ORDER BY detected_at DESC
            LIMIT 20
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        logs = []
        for r in rows:
            if r[3] == 'pending':
                emoji = '🔔'
            elif r[3] == 'approved':
                emoji = '✅'
            else:
                emoji = '❌'
            logs.append({
                'message': f"{emoji} [{r[1]}] {r[0][:60]}",
                'time': str(r[2]),
                'status': r[3],
                'category': r[1]
            })
        return jsonify({
            'logs': logs,
            'scraper_status': 'running',
            'last_updated': str(rows[0][2]) if rows else ''
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/ou/result/check', methods=['POST'])
def ou_result_check():
    try:
        import requests as req
        from bs4 import BeautifulSoup
        import urllib3
        urllib3.disable_warnings()
        
        data = request.json
        hall_ticket = data.get('hall_ticket', '').strip()
        
        if len(hall_ticket) != 12:
            return jsonify({'error': 'Invalid hall ticket'}), 400

        # Check cache first
        import psycopg2
        conn = psycopg2.connect("postgresql://postgres:MWJnIiZQjLZfMONQuEQPMGSBFkNOpKeB@postgres.railway.internal:5432/railway")
        cur = conn.cursor()
        cur.execute("SELECT result_data FROM ou_results WHERE hall_ticket=%s ORDER BY detected_at DESC LIMIT 1", (hall_ticket,))
        cached = cur.fetchone()
        if cached:
            import json
            return jsonify(json.loads(cached[0]))

        # Get all result pages
        res = req.get("https://www.osmania.ac.in/examination-results.php",
            headers={"User-Agent": "Mozilla/5.0"}, timeout=15, verify=False)
        soup = BeautifulSoup(res.text, "html.parser")
        
        pages = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "res07" in href:
                if not href.startswith("http"):
                    href = "https://www.osmania.ac.in/" + href.lstrip("/")
                pages.append(href)

        # Check each page
        for page in pages:
            try:
                res2 = req.post(page,
                    data={"htno": hall_ticket, "mbstatus": "SEARCH"},
                    headers={"User-Agent": "Mozilla/5.0"},
                    timeout=10, verify=False)
                soup2 = BeautifulSoup(res2.text, "html.parser")
                text = soup2.get_text()
                
                if hall_ticket not in text or "Is Not Found" in text:
                    continue

                # Parse result
                name = course = ""
                subjects = []
                status = ""

                for row in soup2.find_all("tr"):
                    cells = [td.get_text(strip=True) for td in row.find_all(["td","th"])]
                    if not cells: continue
                    if "Name" in cells and len(cells) > 1:
                        idx = cells.index("Name")
                        if idx+1 < len(cells): name = cells[idx+1]
                    if "Course" in cells and len(cells) > 1:
                        idx = cells.index("Course")
                        if idx+1 < len(cells): course = cells[idx+1]
                    if len(cells) == 4 and cells[0].isdigit():
                        subjects.append({"code": cells[0], "name": cells[1], "credits": cells[2], "grade": cells[3]})
                    if "PROMOTED" in " ".join(cells):
                        status = "PROMOTED"
                    if "FAILED" in " ".join(cells):
                        status = "FAILED"

                if name:
                    result = {
                        "found": True,
                        "hall_ticket": hall_ticket,
                        "name": name,
                        "course": course,
                        "subjects": subjects,
                        "status": status,
                        "result_page": page
                    }
                    # Save to cache
                    import json
                    cur.execute("""
                        INSERT INTO ou_results (hall_ticket, result_data, result_status)
                        VALUES (%s, %s, %s)
                        ON CONFLICT DO NOTHING
                    """, (hall_ticket, json.dumps(result), status))
                    conn.commit()
                    cur.close()
                    conn.close()
                    return jsonify(result)
            except:
                continue

        cur.close()
        conn.close()
        return jsonify({"found": False})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/ou/register/quick', methods=['POST'])
def ou_register_quick():
    try:
        import psycopg2
        data = request.json
        whatsapp = data.get('whatsapp', '').strip()
        hall_ticket = data.get('hall_ticket', '').strip()
        name = data.get('name', '').strip()
        course = data.get('course', '').strip()

        if not whatsapp or len(whatsapp) < 10:
            return jsonify({'error': 'Invalid WhatsApp number'}), 400

        conn = psycopg2.connect("postgresql://postgres:MWJnIiZQjLZfMONQuEQPMGSBFkNOpKeB@postgres.railway.internal:5432/railway")
        cur = conn.cursor()

        cur.execute("SELECT id FROM ou_students WHERE whatsapp=%s", (whatsapp,))
        if cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'success': True, 'message': 'Already registered'})

        cur.execute("""
            INSERT INTO ou_students (name, whatsapp, course, hall_ticket, university, current_year, current_semester, admission_year, total_years, language, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (name or 'OU Student', whatsapp, course or 'Unknown', hall_ticket or None, 'Osmania University', 1, 1, 2025, 3, 'english', 'active'))

        conn.commit()
        cur.close()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
