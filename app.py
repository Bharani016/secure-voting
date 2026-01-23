import base64
import os
import cv2
import hashlib
import secrets
import sqlite3
import numpy as np
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify

# ----------------------------
# CONFIG
# ----------------------------
app = Flask(__name__)
app.secret_key = 'your-super-secret-key-change-in-prod'
DATABASE = 'database.db'
FACE_DIR = 'faces'

os.makedirs(FACE_DIR, exist_ok=True)
os.makedirs("temp", exist_ok=True)

face_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
)

# ----------------------------
# IMAGE UTILS
# ----------------------------
def save_base64_image(base64_str, path):
    header, encoded = base64_str.split(",", 1)
    img_bytes = base64.b64decode(encoded)
    img_array = np.frombuffer(img_bytes, dtype=np.uint8)
    img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
    cv2.imwrite(path, img)

def detect_and_save_face(path, frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, 1.2, 6, minSize=(80, 80))
    if len(faces) == 0:
        return False

    faces = sorted(faces, key=lambda x: x[2]*x[3], reverse=True)
    x, y, w, h = faces[0]

    face = gray[y:y+h, x:x+w]
    face = cv2.resize(face, (200, 200))
    cv2.imwrite(path, face)
    return True

def verify_face(face1_path, face2_path, threshold=0.65):
    if not (os.path.exists(face1_path) and os.path.exists(face2_path)):
        return False, 0.0

    img1 = cv2.imread(face1_path, cv2.IMREAD_GRAYSCALE)
    img2 = cv2.imread(face2_path, cv2.IMREAD_GRAYSCALE)
    if img1 is None or img2 is None:
        return False, 0.0

    img1 = cv2.equalizeHist(cv2.resize(img1, (200, 200)))
    img2 = cv2.equalizeHist(cv2.resize(img2, (200, 200)))

    score = cv2.matchTemplate(img1, img2, cv2.TM_CCOEFF_NORMED)[0][0]
    print(f"[DEBUG] Haar face similarity score: {score:.3f}")
    return score >= threshold, score

# ----------------------------
# DATABASE
# ----------------------------
def init_db():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS voters (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        aadhaar_hash TEXT UNIQUE,
        mobile TEXT,
        has_voted INTEGER DEFAULT 0
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS votes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        voter_id INTEGER,
        candidate TEXT,
        timestamp TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS admin (
        id INTEGER PRIMARY KEY,
        username TEXT,
        password_hash TEXT
    )''')
    c.execute(
        "INSERT OR IGNORE INTO admin VALUES (1,'admin',?)",
        (hashlib.sha256("admin123".encode()).hexdigest(),)
    )
    conn.commit()
    conn.close()

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def generate_otp():
    return str(secrets.randbelow(1000000)).zfill(6)

def hash_aadhaar(a):
    return hashlib.sha256(a.encode()).hexdigest()

# ----------------------------
# ROUTES
# ----------------------------
@app.route('/')
def index():
    return render_template("index.html")

# -------- ADMIN FLOW --------
@app.route('/admin_login', methods=['GET','POST'])
def admin_login():
    if request.method == 'POST':
        user = request.form['username']
        pwd = request.form['password']
        conn = get_db()
        admin = conn.execute(
            "SELECT * FROM admin WHERE username=?",
            (user,)
        ).fetchone()
        conn.close()
        if admin and admin['password_hash'] == hashlib.sha256(pwd.encode()).hexdigest():
            session.clear()
            session['role'] = 'admin'
            session['otp'] = generate_otp()
            flash(f"OTP: {session['otp']}", "info")
            return redirect(url_for('admin_otp'))
        flash("Invalid credentials", "error")
    return render_template("admin_login.html")

@app.route('/admin_otp', methods=['GET','POST'])
def admin_otp():
    if session.get('role') != 'admin':
        return redirect('/')
    if request.method == 'POST':
        if request.form['otp'] == session['otp']:
            return redirect(url_for('admin_face'))
        flash("Invalid OTP", "error")
    return render_template("otp.html", role="admin")

@app.route('/admin_face')
def admin_face():
    if session.get('role') != 'admin':
        return redirect('/')
    return render_template("face_verify.html", role="admin")

@app.route('/admin_face_verify', methods=['POST'])
def admin_face_verify():
    frame = request.json.get("frame")
    if not frame:
        return jsonify(success=False, msg="No frame received")

    temp_img = "temp/admin_live.jpg"
    save_base64_image(frame, temp_img)

    img = cv2.imread(temp_img)
    if img is None:
        return jsonify(success=False, msg="Image decode failed")

    # ONLY DETECT FACE
    if not detect_and_save_face(temp_img, img):
        return jsonify(success=False, msg="Face not detected")

    # ✅ ALLOW DIRECTLY
    session['face_verified'] = True
    return jsonify(success=True, redirect="/admin_dashboard")


@app.route('/admin_dashboard')
def admin_dashboard():
    if not session.get('face_verified'):
        return redirect('/')
    return render_template("admin_dashboard.html")

# -------- USER FLOW --------
@app.route('/user_login', methods=['GET','POST'])
def user_login():
    if request.method == 'POST':
        aadhaar = hash_aadhaar(request.form['aadhaar'])
        mobile = request.form['mobile']
        conn = get_db()
        voter = conn.execute(
            "SELECT * FROM voters WHERE aadhaar_hash=? AND mobile=?",
            (aadhaar, mobile)
        ).fetchone()
        conn.close()
        if voter:
            session.clear()
            session['role'] = 'voter'
            session['voter_id'] = voter['id']
            session['otp'] = generate_otp()
            flash(f"OTP: {session['otp']}", "info")
            return redirect(url_for('user_otp'))
        flash("Invalid details", "error")
    return render_template("user_login.html")

@app.route('/user_otp', methods=['GET','POST'])
def user_otp():
    if session.get('role') != 'voter':
        return redirect('/')
    if request.method == 'POST':
        if request.form['otp'] == session['otp']:
            return redirect(url_for('user_face'))
        flash("Invalid OTP", "error")
    return render_template("otp.html", role="voter")

@app.route('/user_face')
def user_face():
    if session.get('role') != 'voter':
        return redirect('/')
    return render_template("face_verify.html", role="voter")

@app.route('/user_face_verify', methods=['POST'])
def user_face_verify():
    frame = request.json.get("frame")
    if not frame:
        return jsonify(success=False, msg="No frame received")

    temp_img = "temp/user_live.jpg"
    save_base64_image(frame, temp_img)

    img = cv2.imread(temp_img)
    if img is None:
        return jsonify(success=False, msg="Image decode failed")

    # ONLY DETECT FACE
    if not detect_and_save_face(temp_img, img):
        return jsonify(success=False, msg="Face not detected")

    # ✅ ALLOW DIRECTLY
    session['face_verified'] = True
    return jsonify(success=True, redirect="/vote")

@app.route('/results')
def results():
    if session.get('role') != 'admin' or not session.get('face_verified'):
        flash("Admin verification required", "error")
        return redirect(url_for('admin_login'))

    conn = get_db()

    voters_count = conn.execute(
        'SELECT COUNT(*) as total FROM voters'
    ).fetchone()['total']

    total_votes = conn.execute(
        'SELECT COUNT(*) as total FROM votes'
    ).fetchone()['total']

    candidates = conn.execute('''
        SELECT candidate, COUNT(*) as count
        FROM votes
        GROUP BY candidate
        ORDER BY count DESC
    ''').fetchall()

    conn.close()

    results_list = []
    for row in candidates:
        pct = round((row['count'] / total_votes * 100), 1) if total_votes else 0
        results_list.append({
            'candidate': row['candidate'],
            'votes': row['count'],
            'pct': pct
        })

    return render_template(
        'results.html',
        voters_count=voters_count,
        total_votes=total_votes,
        results=results_list
    )

@app.route('/add_voter', methods=['GET', 'POST'])
def add_voter():
    if session.get('role') != 'admin' or not session.get('face_verified'):
        flash("Admin verification required", "error")
        return redirect(url_for('admin_login'))

    if request.method == 'POST':
        aadhaar = request.form['aadhaar']
        mobile = request.form['mobile']
        aadhaar_hash = hash_aadhaar(aadhaar)

        try:
            conn = get_db()
            conn.execute(
                'INSERT INTO voters (aadhaar_hash, mobile) VALUES (?, ?)',
                (aadhaar_hash, mobile)
            )
            conn.commit()
            conn.close()

            flash("Voter added successfully!", "success")
            return redirect(url_for('add_voter'))

        except sqlite3.IntegrityError:
            flash("Aadhaar already registered!", "error")

    return render_template('add_voter.html')

@app.route('/vote', methods=['GET', 'POST'])
def vote():
    if not session.get('face_verified') or session.get('role') != 'voter':
        return redirect(url_for('index'))

    if request.method == 'POST':
        candidate = request.form['candidate']
        voter_id = session['voter_id']

        conn = get_db_connection()
        voter = conn.execute(
            'SELECT has_voted FROM voters WHERE id = ?', (voter_id,)
        ).fetchone()

        if voter and voter['has_voted'] == 0:
            conn.execute(
                'INSERT INTO votes (voter_id, candidate, timestamp) VALUES (?, ?, ?)',
                (voter_id, candidate, datetime.now().isoformat())
            )
            conn.execute(
                'UPDATE voters SET has_voted = 1 WHERE id = ?', (voter_id,)
            )
            conn.commit()
            conn.close()

            session.clear()
            flash("Vote cast successfully!", "success")
            return redirect(url_for('index'))

        flash("Already voted", "error")
        return redirect(url_for('index'))

    candidates = ["Bharani", "Jai Akash", "Fayas", "Dhanush"]
    return render_template('vote.html', candidates=candidates)


@app.route('/logout', methods=['GET', 'POST'])
def logout_user():
    session.clear()
    return redirect(url_for('index'))


# ----------------------------
if __name__ == "__main__":
    init_db()
    app.run(debug=True)
