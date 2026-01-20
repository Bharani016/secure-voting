
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

face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

# ----------------------------
# DATABASE SETUP
# ----------------------------
def init_db():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS voters (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        aadhaar_hash TEXT UNIQUE NOT NULL,
        mobile TEXT NOT NULL,
        has_voted INTEGER DEFAULT 0
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS votes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        voter_id INTEGER NOT NULL,
        candidate TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        FOREIGN KEY(voter_id) REFERENCES voters(id)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS admin (
        id INTEGER PRIMARY KEY,
        username TEXT NOT NULL,
        password_hash TEXT NOT NULL
    )''')
    c.execute("INSERT OR IGNORE INTO admin (id, username, password_hash) VALUES (1, 'admin', ?)",
              (hashlib.sha256('admin123'.encode()).hexdigest(),))
    conn.commit()
    conn.close()

# ----------------------------
# UTILS
# ----------------------------
def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def hash_aadhaar(aadhaar):
    return hashlib.sha256(aadhaar.encode()).hexdigest()

def generate_otp():
    return str(secrets.randbelow(1000000)).zfill(6)

def verify_face(face1_path, face2_path, threshold=0.45):
    if not (os.path.exists(face1_path) and os.path.exists(face2_path)):
        return False, 0.0
    img1 = cv2.imread(face1_path, cv2.IMREAD_GRAYSCALE)
    img2 = cv2.imread(face2_path, cv2.IMREAD_GRAYSCALE)
    if img1 is None or img2 is None:
        return False, 0.0
    hist1 = cv2.calcHist([img1], [0], None, [256], [0, 256])
    hist2 = cv2.calcHist([img2], [0], None, [256], [0, 256])
    score = cv2.compareHist(hist1, hist2, cv2.HISTCMP_CORREL)
    print(f"[DEBUG] Face similarity score: {score:.3f}")
    return score > threshold, score

def detect_and_save_face(image_path, frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, 1.3, 5)
    if len(faces) == 0:
        return False
    (x, y, w, h) = faces[0]
    face = gray[y:y+h, x:x+w]
    face = cv2.resize(face, (200, 200))
    face = cv2.GaussianBlur(face, (5, 5), 0)
    cv2.imwrite(image_path, face)
    return True

# ----------------------------
# ROUTES
# ----------------------------
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = get_db_connection()
        admin = conn.execute('SELECT * FROM admin WHERE username = ?', (username,)).fetchone()
        conn.close()
        if admin and admin['password_hash'] == hashlib.sha256(password.encode()).hexdigest():
            session['role'] = 'admin'
            session['otp'] = generate_otp()
            session['username'] = username
            flash(f"OTP for demo: {session['otp']} (not sent via SMS)", "info")
            return redirect(url_for('admin_otp'))
        else:
            flash("Invalid admin credentials", "error")
    return render_template('admin_login.html')

@app.route('/admin_otp', methods=['GET', 'POST'])
def admin_otp():
    if 'role' not in session or session.get('role') != 'admin':
        return redirect(url_for('index'))
    if request.method == 'POST':
        if request.form['otp'] == session.get('otp'):
            return redirect(url_for('admin_face_verify'))
        else:
            flash("Invalid OTP", "error")
    return render_template('otp.html', role='admin')

@app.route('/admin_face_verify', methods=['GET', 'POST'])
def admin_face_verify():
    if 'role' not in session or session.get('role') != 'admin':
        return redirect(url_for('index'))
    if request.method == 'POST':
        frame_data = request.json.get('frame')
        if not frame_data:  # ✅ CORRECTED
            return jsonify({"success": False, "msg": "No image data"})
        import base64
        header, encoded = frame_data.split(',', 1)
        binary = base64.b64decode(encoded)
        nparr = np.frombuffer(binary, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        face_path = os.path.join(FACE_DIR, 'admin_face.jpg')
        if not os.path.exists(face_path):
            if detect_and_save_face(face_path, frame):
                session['face_verified'] = True
                return jsonify({"success": True, "redirect": url_for('admin_dashboard')})
            else:
                return jsonify({"success": False, "msg": "No face detected"})
        else:
            temp_path = os.path.join(FACE_DIR, 'admin_temp.jpg')
            if detect_and_save_face(temp_path, frame):
                valid, score = verify_face(face_path, temp_path)
                os.remove(temp_path)
                if valid:
                    session['face_verified'] = True
                    return jsonify({"success": True, "redirect": url_for('admin_dashboard')})
                else:
                    return jsonify({"success": False, "msg": f"Face mismatch (score: {score:.2f})"})
            else:
                return jsonify({"success": False, "msg": "No face detected"})
    return render_template('face_verify.html', role='admin')

@app.route('/admin_dashboard')
def admin_dashboard():
    if not session.get('face_verified') or session.get('role') != 'admin':
        return redirect(url_for('index'))
    conn = get_db_connection()
    candidates = conn.execute('SELECT candidate, COUNT(*) as count FROM votes GROUP BY candidate').fetchall()
    total_votes = conn.execute('SELECT COUNT(*) as total FROM votes').fetchone()['total']
    voters_count = conn.execute('SELECT COUNT(*) as total FROM voters').fetchone()['total']
    conn.close()
    results = []
    for row in candidates:
        pct = (row['count'] / total_votes * 100) if total_votes > 0 else 0
        results.append({'candidate': row['candidate'], 'votes': row['count'], 'pct': round(pct, 1)})
    return render_template('admin_dashboard.html', results=results, total_votes=total_votes, voters_count=voters_count)

@app.route('/add_voter', methods=['GET', 'POST'])
def add_voter():
    if not session.get('face_verified') or session.get('role') != 'admin':
        return redirect(url_for('index'))
    if request.method == 'POST':
        aadhaar = request.form['aadhaar']
        mobile = request.form['mobile']
        aadhaar_hash = hash_aadhaar(aadhaar)
        try:
            conn = get_db_connection()
            conn.execute('INSERT INTO voters (aadhaar_hash, mobile) VALUES (?, ?)', (aadhaar_hash, mobile))
            conn.commit()
            conn.close()
            flash("Voter added successfully!", "success")
        except sqlite3.IntegrityError:
            flash("Aadhaar already registered!", "error")
    return render_template('add_voter.html')

@app.route('/user_login', methods=['GET', 'POST'])
def user_login():
    if request.method == 'POST':
        aadhaar = request.form['aadhaar']
        mobile = request.form['mobile']
        aadhaar_hash = hash_aadhaar(aadhaar)
        conn = get_db_connection()
        voter = conn.execute('SELECT * FROM voters WHERE aadhaar_hash = ? AND mobile = ?', 
                             (aadhaar_hash, mobile)).fetchone()
        conn.close()
        if voter:
            session['role'] = 'voter'
            session['voter_id'] = voter['id']
            session['aadhaar_hash'] = aadhaar_hash
            if voter['has_voted']:
                flash("You have already voted!", "error")
                return redirect(url_for('index'))
            session['otp'] = generate_otp()
            flash(f"OTP for demo: {session['otp']} (not sent via SMS)", "info")
            return redirect(url_for('user_otp'))
        else:
            flash("Invalid Aadhaar or mobile number", "error")
    return render_template('user_login.html')

@app.route('/user_otp', methods=['GET', 'POST'])
def user_otp():
    if 'role' not in session or session.get('role') != 'voter':
        return redirect(url_for('index'))
    if request.method == 'POST':
        if request.form['otp'] == session.get('otp'):
            return redirect(url_for('user_face_verify'))
        else:
            flash("Invalid OTP", "error")
    return render_template('otp.html', role='voter')

@app.route('/user_face_verify', methods=['GET', 'POST'])
def user_face_verify():
    if 'role' not in session or session.get('role') != 'voter':
        return redirect(url_for('index'))
    aadhaar_hash = session['aadhaar_hash']
    face_path = os.path.join(FACE_DIR, f"{aadhaar_hash}.jpg")
    if request.method == 'POST':
        frame_data = request.json.get('frame')
        if not frame_data:  # ✅ CORRECTED
            return jsonify({"success": False, "msg": "No image data"})
        import base64
        header, encoded = frame_data.split(',', 1)
        binary = base64.b64decode(encoded)
        nparr = np.frombuffer(binary, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if not os.path.exists(face_path):
            if detect_and_save_face(face_path, frame):
                session['face_verified'] = True
                return jsonify({"success": True, "redirect": url_for('vote')})
            else:
                return jsonify({"success": False, "msg": "No face detected"})
        else:
            temp_path = os.path.join(FACE_DIR, f"{aadhaar_hash}_temp.jpg")
            if detect_and_save_face(temp_path, frame):
                valid, score = verify_face(face_path, temp_path)
                os.remove(temp_path)
                if valid:
                    session['face_verified'] = True
                    return jsonify({"success": True, "redirect": url_for('vote')})
                else:
                    return jsonify({"success": False, "msg": f"Face mismatch (score: {score:.2f})"})
            else:
                return jsonify({"success": False, "msg": "No face detected"})
    return render_template('face_verify.html', role='voter')

@app.route('/vote', methods=['GET', 'POST'])
def vote():
    if not session.get('face_verified') or session.get('role') != 'voter':
        return redirect(url_for('index'))
    if request.method == 'POST':
        candidate = request.form['candidate']
        voter_id = session['voter_id']
        conn = get_db_connection()
        voter = conn.execute('SELECT has_voted FROM voters WHERE id = ?', (voter_id,)).fetchone()
        if voter and voter['has_voted'] == 0:
            conn.execute('INSERT INTO votes (voter_id, candidate, timestamp) VALUES (?, ?, ?)',
                         (voter_id, candidate, datetime.now().isoformat()))
            conn.execute('UPDATE voters SET has_voted = 1 WHERE id = ?', (voter_id,))
            conn.commit()
            flash("Vote cast successfully! Thank you.", "success")
            session.clear()
            return redirect(url_for('index'))
        else:
            flash("Already voted or invalid session", "error")
            return redirect(url_for('index'))
    candidates = ["Alice Johnson", "Raj Patel", "Maria Garcia", "Li Wei"]
    return render_template('vote.html', candidates=candidates)

@app.route('/logout', methods=['GET', 'POST'])
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/results')
def results():
    # Security: Only allow verified admins
    if not session.get('face_verified') or session.get('role') != 'admin':
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    
    # Get total voters and votes
    voters_count = conn.execute('SELECT COUNT(*) as total FROM voters').fetchone()['total']
    total_votes = conn.execute('SELECT COUNT(*) as total FROM votes').fetchone()['total']
    
    # Get candidate-wise results
    candidates = conn.execute('''
        SELECT candidate, COUNT(*) as count 
        FROM votes 
        GROUP BY candidate 
        ORDER BY count DESC
    ''').fetchall()
    
    # Prepare data for template
    results_list = []
    for row in candidates:
        pct = round((row['count'] / total_votes * 100), 1) if total_votes > 0 else 0
        results_list.append({
            'candidate': row['candidate'],
            'votes': row['count'],
            'pct': pct
        })
    
    conn.close()
    return render_template(
        'results.html',
        voters_count=voters_count,
        total_votes=total_votes,
        results=results_list
    )

if __name__ == '__main__':
    init_db()
    app.run(debug=True)