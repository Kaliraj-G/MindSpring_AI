import os, re, json, sqlite3
from functools import wraps
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
import requests

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "change-this-local-secret-key")
DB = os.path.join(os.path.dirname(__file__), "mindspring.db")
API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/free")

def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    with db() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        con.execute("""CREATE TABLE IF NOT EXISTS notes(
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            topic TEXT NOT NULL, mode TEXT NOT NULL, content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        con.execute("""CREATE TABLE IF NOT EXISTS tests(
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            subject TEXT, topic TEXT, difficulty TEXT, questions_json TEXT NOT NULL,
            answers_json TEXT, score INTEGER, total INTEGER, analysis TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        con.execute("""CREATE TABLE IF NOT EXISTS chats(
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            role TEXT NOT NULL, content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")

init_db()

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper

def ai(messages, max_tokens=2200, temperature=0.4):
    if not API_KEY:
        raise RuntimeError("OpenRouter API key is missing. Add it to .env and restart.")
    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json", "X-Title": "MindSpring AI"},
        json={"model": MODEL, "messages": messages, "temperature": temperature, "max_tokens": max_tokens},
        timeout=90
    )
    if response.status_code >= 400:
        try: msg = response.json().get("error", {}).get("message", response.text)
        except Exception: msg = response.text
        raise RuntimeError(f"AI provider error ({response.status_code}): {msg}")
    return response.json()["choices"][0]["message"]["content"].strip()

def current_user():
    with db() as con:
        return con.execute("SELECT id, username FROM users WHERE id=?", (session["user_id"],)).fetchone()

@app.route("/")
def index():
    return redirect(url_for("dashboard") if session.get("user_id") else url_for("login"))

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if len(username) < 3 or len(password) < 6:
            flash("Use a username with at least 3 characters and password with at least 6 characters.")
        else:
            try:
                with db() as con:
                    con.execute("INSERT INTO users(username,password_hash) VALUES(?,?)",
                                (username, generate_password_hash(password)))
                flash("Account created. Please sign in.")
                return redirect(url_for("login"))
            except sqlite3.IntegrityError:
                flash("That username is already taken.")
    return render_template("auth.html", mode="register")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        with db() as con:
            user = con.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            return redirect(url_for("dashboard"))
        flash("Incorrect username or password.")
    return render_template("auth.html", mode="login")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required
def dashboard():
    with db() as con:
        notes = con.execute("SELECT COUNT(*) n FROM notes WHERE user_id=?", (session["user_id"],)).fetchone()["n"]
        tests = con.execute("SELECT COUNT(*) n FROM tests WHERE user_id=?", (session["user_id"],)).fetchone()["n"]
        recent = con.execute("SELECT id,subject,topic,score,total,created_at FROM tests WHERE user_id=? ORDER BY id DESC LIMIT 5", (session["user_id"],)).fetchall()
    return render_template("dashboard.html", username=session["username"], notes=notes, tests=tests, recent=recent)

@app.route("/api/notes", methods=["POST"])
@login_required
def create_notes():
    data = request.get_json() or {}
    topic = (data.get("topic") or "").strip()
    mode = data.get("mode", "Simple Notes")
    if not topic: return jsonify(error="Enter a topic first."), 400
    instructions = {
        "Simple Notes": "Explain in beginner-friendly simple English, with short paragraphs and easy examples.",
        "Detailed Notes": "Give thorough, structured explanations, definitions, key concepts, examples and applications.",
        "Exam Preparation": "Create exam-ready notes with definitions, headings, important points, likely short-answer questions and a concise conclusion.",
        "Quick Revision": "Create a compact revision sheet with key terms, formulas or facts where relevant, and brief examples."
    }.get(mode, "Explain clearly and accurately.")
    try:
        content = ai([
            {"role":"system","content":"""You are MindSpring AI, an accurate academic tutor. Output clean plain text, not Markdown. Do not use #, **, __, backticks, hashtags, emojis, decorative symbols, ads or promotional text. Use clear heading lines, numbered lists, short paragraphs and examples. Do not invent facts. Follow the requested study style."""},
            {"role":"user","content":f"Create {mode} for this topic: {topic}. {instructions} Use suitable sections only."}
        ])
        with db() as con:
            cur = con.execute("INSERT INTO notes(user_id,topic,mode,content) VALUES(?,?,?,?)",
                              (session["user_id"], topic, mode, content))
            note_id = cur.lastrowid
        return jsonify(id=note_id, topic=topic, mode=mode, content=content)
    except Exception as e: return jsonify(error=str(e)), 502

@app.route("/api/tests/generate", methods=["POST"])
@login_required
def generate_test():
    data = request.get_json() or {}
    subject = (data.get("subject") or "").strip()
    topic = (data.get("topic") or "").strip()
    difficulty = data.get("difficulty", "Medium")
    try: count = max(3, min(15, int(data.get("count", 5))))
    except: count = 5
    if not subject or not topic: return jsonify(error="Enter both subject and topic."), 400
    prompt = f"""Create exactly {count} multiple-choice questions for subject {subject}, topic {topic}, difficulty {difficulty}.
Return ONLY valid JSON, no Markdown fences, in this exact shape:
{{"questions":[{{"question":"...","options":["A. ...","B. ...","C. ...","D. ..."],"correct":0,"explanation":"...","concept":"specific concept tested"}}]}}
correct must be an integer 0,1,2,3. Each question must have four distinct plausible options. Cover different sub-concepts. Do not reveal correct answers in the question text."""
    try:
        raw = ai([{"role":"system","content":"You create accurate educational multiple-choice tests. Return strict JSON only."},
                  {"role":"user","content":prompt}], max_tokens=3500, temperature=0.3)
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.I)
        obj = json.loads(raw)
        questions = obj.get("questions", [])
        if len(questions) < 3: raise ValueError("AI returned too few questions. Please generate again.")
        questions = questions[:count]
        for q in questions:
            if len(q.get("options", [])) != 4 or q.get("correct") not in [0,1,2,3]:
                raise ValueError("AI returned an invalid question format. Please generate again.")
        with db() as con:
            cur = con.execute("INSERT INTO tests(user_id,subject,topic,difficulty,questions_json) VALUES(?,?,?,?,?)",
                              (session["user_id"], subject, topic, difficulty, json.dumps(questions)))
            test_id = cur.lastrowid
        # Never send correct answers to browser before submission
        public = [{"question":q["question"],"options":q["options"],"concept":q.get("concept","")} for q in questions]
        return jsonify(test_id=test_id, questions=public)
    except Exception as e: return jsonify(error=str(e)), 502

@app.route("/api/tests/<int:test_id>/submit", methods=["POST"])
@login_required
def submit_test(test_id):
    data = request.get_json() or {}
    answers = data.get("answers", [])
    with db() as con:
        test = con.execute("SELECT * FROM tests WHERE id=? AND user_id=?", (test_id,session["user_id"])).fetchone()
        if not test: return jsonify(error="Test not found."), 404
        qs = json.loads(test["questions_json"])
        if len(answers) != len(qs): return jsonify(error="Please answer every question before submitting."), 400
        details=[]; score=0; concept_stats={}
        for i,(q,a) in enumerate(zip(qs,answers)):
            try: selected=int(a)
            except: selected=-1
            correct=selected == q["correct"]
            score += int(correct)
            concept=q.get("concept","General")
            stat=concept_stats.setdefault(concept,{"correct":0,"total":0})
            stat["total"]+=1
            stat["correct"]+=int(correct)
            details.append({"question":q["question"],"selected":selected,"correct":q["correct"],
                            "is_correct":correct,"explanation":q.get("explanation",""),"concept":concept})
        weak=[{"concept":k,"correct":v["correct"],"total":v["total"],
               "percentage":round(v["correct"]/v["total"]*100)} for k,v in concept_stats.items() if v["correct"]<v["total"]]
        analysis = {"score":score,"total":len(qs),"percentage":round(score/len(qs)*100),
                    "strengths":[k for k,v in concept_stats.items() if v["correct"]==v["total"]],
                    "weak_areas":weak,"recommendation":"Revise the weak concepts and try another test." if weak else "Excellent work. Try a harder test to deepen your understanding."}
        con.execute("UPDATE tests SET answers_json=?,score=?,total=?,analysis=? WHERE id=?",
                    (json.dumps(answers),score,len(qs),json.dumps(analysis),test_id))
    return jsonify(analysis=analysis, details=details)

@app.route("/api/tests/history")
@login_required
def test_history():
    with db() as con:
        rows=con.execute("SELECT id,subject,topic,difficulty,score,total,analysis,created_at FROM tests WHERE user_id=? AND score IS NOT NULL ORDER BY id DESC",
                         (session["user_id"],)).fetchall()
    return jsonify(tests=[dict(r) for r in rows])

@app.route("/api/teacher", methods=["POST"])
@login_required
def teacher():
    data=request.get_json() or {}
    message=(data.get("message") or "").strip()
    if not message: return jsonify(error="Type or speak your question."),400
    with db() as con:
        history=con.execute("SELECT role,content FROM chats WHERE user_id=? ORDER BY id DESC LIMIT 8",
                            (session["user_id"],)).fetchall()
    messages=[{"role":"system","content":"You are the friendly MindSpring AI voice teacher. Teach any school or college subject conversationally in clear simple language. Answer follow-up questions using context. Ask one helpful checking question when appropriate. Do not use Markdown decoration."}]
    for row in reversed(history): messages.append({"role":row["role"],"content":row["content"]})
    messages.append({"role":"user","content":message})
    try:
        answer=ai(messages,max_tokens=1200)
        with db() as con:
            con.execute("INSERT INTO chats(user_id,role,content) VALUES(?,?,?)",(session["user_id"],"user",message))
            con.execute("INSERT INTO chats(user_id,role,content) VALUES(?,?,?)",(session["user_id"],"assistant",answer))
        return jsonify(answer=answer)
    except Exception as e: return jsonify(error=str(e)),502

@app.route("/notes")
@login_required
def notes_page():
    with db() as con:
        rows=con.execute("SELECT id,topic,mode,created_at FROM notes WHERE user_id=? ORDER BY id DESC",(session["user_id"],)).fetchall()
    return render_template("notes.html", notes=rows)

@app.route("/api/notes/<int:note_id>")
@login_required
def get_note(note_id):
    with db() as con:
        row=con.execute("SELECT * FROM notes WHERE id=? AND user_id=?",(note_id,session["user_id"])).fetchone()
    if not row:return jsonify(error="Note not found."),404
    return jsonify(dict(row))

@app.route("/tests")
@login_required
def tests_page(): return render_template("tests.html")

@app.route("/teacher")
@login_required
def teacher_page(): return render_template("teacher.html")

@app.route("/history")
@login_required
def history_page(): return render_template("history.html")

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
