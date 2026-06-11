from flask import Flask, render_template, request, redirect, url_for, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin, login_user,
    login_required, logout_user, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from flask_mail import Mail, Message
from flask import session
import os
import uuid
from dotenv import load_dotenv
from datetime import datetime
import plotly.graph_objects as go
import plotly.express as px


from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

from resume_utils import (
    extract_resume_text,
    job_fit_score,
    generate_suggestions,
    generate_ai_tips,
    generate_interview_questions
)
from datetime import datetime

# ================= ENV =================
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
print("KEY =", GEMINI_API_KEY)
print("GEMINI KEY FOUND:", bool(GEMINI_API_KEY))

client = None
try:
    from google import genai
    if GEMINI_API_KEY:
        client = genai.Client(api_key=GEMINI_API_KEY)

    print("CLIENT:", client)

except Exception as e:
    print("Gemini init failed:", e)

# ================= APP =================
app = Flask(__name__)
app.config["SECRET_KEY"] = "mysecretkey"

# ================= MAIL =================
app.config["MAIL_SERVER"] = "smtp.gmail.com"
app.config["MAIL_PORT"] = 587
app.config["MAIL_USE_TLS"] = True
app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME")
app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD")

mail = Mail(app)

# ================= DB =================
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL or "sqlite:///users.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)



# ================= LOGIN =================
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# ================= UPLOAD =================
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# ================= GEMINI SAFE =================
client = None
try:
    from google import genai
    if GEMINI_API_KEY:
        client = genai.Client(api_key=GEMINI_API_KEY)
except Exception as e:
    print("Gemini init failed:", e)

# ================= MODELS =================
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True)
    username = db.Column(db.String(120), unique=True)
    password = db.Column(db.String(200))
    is_admin = db.Column(db.Boolean, default=False)


class Report(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    resume_name = db.Column(db.String(200))
    role = db.Column(db.String(100))
    final_score = db.Column(db.Integer)
    user_id = db.Column(db.Integer)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# ================= HOME =================
@app.route("/")
def landing():
    return render_template("landing.html")

@app.route("/dashboard")
@login_required
def home():

    return render_template(
        "index.html",
        username=current_user.username
    )
# ================= REGISTER =================
@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        existing_user = User.query.filter_by(
            username=request.form["username"]
        ).first()

        if existing_user:
            return "Username already exists ❌"

        existing_email = User.query.filter_by(
            email=request.form["email"]
        ).first()

        if existing_email:
            return "Email already registered ❌"

        user = User(
            username=request.form["username"],
            email=request.form["email"],
            password=generate_password_hash(request.form["password"])
        )

        db.session.add(user)
        db.session.commit()

        return redirect(url_for("login"))

    return render_template("register.html")

# ================= LOGIN =================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = User.query.filter_by(username=request.form["username"]).first()

        if user and check_password_hash(user.password, request.form["password"]):
            login_user(user)
            
            session["chat_history"] = []
            return redirect(url_for("home"))

        return "Invalid login ❌"

    return render_template("login.html")

# ================= LOGOUT =================
@app.route("/logout")
@login_required
def logout():

    session.pop("chat_history", None)

    logout_user()

    return redirect(url_for("login"))

# ================= PROFILE =================
@app.route("/profile")
@login_required
def profile():
    reports = Report.query.filter_by(user_id=current_user.id).all()

    total = len(reports)
    avg = int(sum(r.final_score for r in reports) / total) if total else 0
    best = max([r.final_score for r in reports], default=0)

    return render_template(
        "profile.html",
        username=current_user.username,
        total_reports=total,
        avg_score=avg,
        best_score=best
    )

# ================= HISTORY =================
@app.route("/history")
@login_required
def history():

    reports = Report.query.filter_by(
        user_id=current_user.id
    ).all()

    return render_template(
        "history.html",
        reports=reports
    )

# ================= ADMIN =================
@app.route("/admin")
@login_required
def admin():
    if not current_user.is_admin:
        return "Access Denied"

    users = User.query.all()
    reports = Report.query.all()

    return render_template("admin.html", users=users, reports=reports)

# ================= CHATBOT =================

@app.route("/chatbot", methods=["GET", "POST"])
@login_required
def chatbot():

    current_date = datetime.now().strftime("%d %B %Y")
    current_time = datetime.now().strftime("%I:%M %p")

    reply = ""
    user_message = ""

    if request.method == "POST":

        user_message = request.form.get("message", "").strip()

        if "chat_history" not in session:
            session["chat_history"] = []

        history = session["chat_history"]

        history.append({
            "role": "user",
            "message": user_message
        })

        print("SESSION KEYS =", session.keys())

        resume_text = session.get("resume_text", "")
        print("RESUME TEXT =", resume_text)

        conversation = ""

        for msg in history:
            conversation += f"{msg['role']}: {msg['message']}\n"

        prompt = f"""
You are a friendly AI assistant similar to ChatGPT.

User Resume:
{resume_text}

Current Date: {current_date}
Current Time: {current_time}

Rules:
- Answer any topic the user asks.
- Have natural conversations.
- Be friendly and helpful.
- Talk like a real human friend.
- Remember previous conversation.
- Use resume information when asked.
- If user asks about skills, projects, education, experience, certifications or resume details, answer from the resume above.
- If user asks normal questions, answer normally.
- Do not say you cannot see the resume when resume information is available.
- Keep answers clear and concise.
- If user asks about resume, use User Resume information.
- If resume does not contain the answer, say it is not available in the resume.
- Never ignore resume information when asked about skills, education, projects or experience.
- Use plain text.
- Avoid markdown symbols like **, ##, *, ``` .
- Use short paragraphs.
- Format replies cleanly.
- Do not use bullet points unless necessary.
- Keep replies clean and readable.

Conversation:
{conversation}

Assistant:
"""

        if client:

            try:

                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt
                )

                reply = response.text.strip()

                history.append({
                    "role": "assistant",
                    "message": reply
                })

                session["chat_history"] = history
                session.modified = True

            except Exception as e:

                error_text = str(e)

                if "429" in error_text:

                    if resume_text:

                        reply = f"""
Gemini quota reached.

I can still access the uploaded resume.

Resume contains:
{resume_text[:500]}
"""

                    else:
                        reply = "⚠️ Daily AI limit reached. Please try again later."

                elif "503" in error_text:
                    reply = "⚠️ AI service is currently unavailable. Please try again later."

                else:
                    reply = "⚠️ Something went wrong. Please try again later."

                print("CHATBOT ERROR:", e)

        else:
            reply = "⚠️ AI service not available."

    return render_template(
        "chatbot.html",
        reply=reply,
        user_message=user_message,
        history=session.get("chat_history", [])
    )
# ================= TEMPLATES PAGE =================
@app.route("/templates")
@login_required
def templates():
    return render_template("templates.html")

# ================= DELETE REPORTS =================
@app.route("/delete_reports")
@login_required
def delete_reports():
    Report.query.filter_by(user_id=current_user.id).delete()
    db.session.commit()
    return redirect(url_for("home"))

# ================= UPLOAD =================
@app.route("/upload", methods=["POST"])
@login_required
def upload():

    file = request.files["resume"]
    if not file or file.filename == "":
        return "Please upload a resume first ❌"
    role = request.form["role"]
    job_desc = request.form["job_description"]

    # SAFE FILENAME
    filename = str(uuid.uuid4()) + "_" + file.filename
    path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(path)

    resume_text = extract_resume_text(path)
    print("FILE PATH =", path)
    print("RESUME LENGTH =", len(resume_text))
    print("UPLOAD RESUME =", resume_text[:300])

    session["resume_text"] = resume_text

    print("SESSION SAVED =", session.get("resume_text", "")[:300])

    print(session.keys())

    session.modified = True
    print("AFTER SAVE SESSION =", session.keys())
    ai_score = job_fit_score(resume_text, job_desc)

    skills_map = {
        "python_developer": ["python", "flask", "django"],
        "web_developer": ["html", "css", "javascript"],
        "data_scientist": ["python", "pandas", "numpy"]
    }

    role_skills = skills_map.get(role, [])

    found = [s for s in role_skills if s.lower() in resume_text.lower()]
    missing = [s for s in role_skills if s not in found]
    
    skill_scores = {}

    for skill in role_skills:

        if skill.lower() in resume_text.lower():
           skill_scores[skill] = 100
        else:
           skill_scores[skill] = 0
    final_score = int(ai_score)

    status = (
        "Excellent 🚀" if final_score >= 80 else
        "Good 👍" if final_score >= 50 else
        "Needs Improvement ⚠"
    )

    suggestions = generate_suggestions(resume_text, job_desc, missing)
    ai_tips = generate_ai_tips(final_score, missing)
    interview_questions = generate_interview_questions(resume_text)
# GRAPH FIXED
    fig = go.Figure(data=[
        go.Bar(
            name="Found Skills",
            x=["Skills"],
            y=[len(found)]
        ),
        go.Bar(
            name="Missing Skills",
            x=["Skills"],
            y=[len(missing)]
        )
    ])

    fig.update_layout(
        title="Resume Skills Analysis",
        barmode="group",
        height=350,
        width=700,
        template="plotly_white",
        margin=dict(l=20, r=20, t=50, b=20)
    )

    chart_div = fig.to_html(full_html=False)

    # PDndF
    pdf_name = filename + "_report.pdf"
    pdf_path = os.path.join(app.config["UPLOAD_FOLDER"], pdf_name)

    c = canvas.Canvas(pdf_path, pagesize=letter)
    c.drawString(100, 750, "AI Resume Report")
    c.drawString(100, 720, f"Score: {final_score}%")
    c.drawString(100, 700, f"Status: {status}")
    c.save()

    # SAVE DB
    report = Report(
        resume_name=filename,
        role=role,
        final_score=final_score,
        user_id=current_user.id
    )

    db.session.add(report)
    db.session.commit()

    return render_template(
        "result.html",
        final_score=final_score,
        found_skills=found,
        missing_skills=missing,
        suggestions=suggestions,
        ai_tips=ai_tips,
        chart_div=chart_div,
        pdf_filename=pdf_name,
        resume_filename=filename,
        ats_status=status,
        skill_scores=skill_scores,
        interview_questions=interview_questions
    )

# ================= PREVIEW =================
@app.route("/preview/<filename>")
@login_required
def preview(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

# ================= DOWNLOAD =================
@app.route("/download/<filename>")
@login_required
def download(filename):
    return send_from_directory(
        app.config["UPLOAD_FOLDER"],
        filename,
        as_attachment=True
    )

# ================= INTERVIEW =================
@app.route("/interview", methods=["POST"])
@login_required
def interview():
    role = request.form["role"]
    resume_text = request.form["resume_text"]

    prompt = f"Generate interview questions for {role} based on: {resume_text}"

    if client:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt  
        )
        questions = response.text
    else:
        questions = "AI not available"

    return render_template("interview.html", questions=questions)

# ================= RUN =================
if __name__ == "__main__":
    with app.app_context():
        db.create_all()

    app.run(host="0.0.0.0", port=10000)