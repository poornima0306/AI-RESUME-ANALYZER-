from flask import Flask, render_template, request, redirect, url_for, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from resume_utils import extract_resume_text, job_fit_score, generate_suggestions
from flask_mail import Mail, Message

import os
import re
import plotly.graph_objects as go
import plotly.express as px
import google.generativeai as genai

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

from resume_utils import extract_resume_text, job_fit_score, generate_suggestions,generate_ai_tips

app = Flask(__name__)
app.config['SECRET_KEY'] = 'mysecretkey'
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.environ.get("MAIL_USERNAME")
app.config['MAIL_PASSWORD'] = os.environ.get("MAIL_PASSWORD")
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

model = genai.GenerativeModel("gemini-1.5-flash")

# ================= DATABASE (FIXED ORDER) =================
db_url = os.environ.get("DATABASE_URL")

if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url or 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
mail = Mail(app)
db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


# ================= USER MODEL =================

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True)
    username = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(200))
    is_admin = db.Column(db.Boolean, default=False)
    profile_pic = db.Column(db.String(200))
# ================= REPORT MODEL =================

class Report(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    resume_name = db.Column(db.String(200))
    role = db.Column(db.String(100))
    final_score = db.Column(db.Integer)

    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# ================= HOME =================

@app.route('/')
@login_required
def home():

    reports = Report.query.filter_by(user_id=current_user.id).all()

    scores = [r.final_score for r in reports]
    names = [r.resume_name for r in reports]

    chart = None

    if reports:
        fig = px.line(
            x=names,
            y=scores,
            markers=True,
            title="Resume Score History"
        )

        chart = fig.to_html(full_html=False)

    return render_template(
        "index.html",
        username=current_user.username,
        chart=chart
    )


# ================= REGISTER =================

@app.route('/register', methods=['GET', 'POST'])
def register():

    if request.method == 'POST':
        email = request.form['email']
        username = request.form['username']
        password = generate_password_hash(request.form['password'])

        user = User(username=username, email=email, password=password)

        db.session.add(user)
        db.session.commit()

        return redirect(url_for('login'))

    return render_template('register.html')


# ================= LOGIN =================

@app.route('/login', methods=['GET', 'POST'])
def login():

    if request.method == 'POST':

        user = User.query.filter_by(
            username=request.form['username']
        ).first()

        if user and check_password_hash(
                user.password,
                request.form['password']
        ):

            login_user(user)

            return redirect(url_for('home'))

    return render_template('login.html')


@app.route('/admin')
@login_required
def admin():

    if not current_user.is_admin:
        return "Access Denied"

    users = User.query.order_by(User.id.desc()).all()
    reports = Report.query.all()

    return render_template('admin.html', users=users, reports=reports)

# ================= CHATBOT =================

@app.route('/chatbot_page')
@login_required
def chatbot_page():
    return render_template('chatbot.html')


@app.route('/chatbot', methods=["GET", "POST"])
@login_required
def chatbot():
     reply = ""

     if request.method == "POST":
        user_message = request.form['message']

        response = model.generation_content(user_message)
    
        "reply": reponse.text
    
    return render_template(
        "chatbot.html",
        reply=reply
    )

# ================= LOGOUT =================

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


# ================= PROFILE =================

@app.route('/profile')
@login_required
def profile():

    reports = Report.query.filter_by(
        user_id=current_user.id
    ).all()

    total_reports = len(reports)

    avg_score = 0

    if total_reports > 0:
        avg_score = int(
            sum(r.final_score for r in reports)
            / total_reports
        )

    best_score = 0

    if reports:
        best_score = max(
            r.final_score for r in reports
        )

    return render_template(
        'profile.html',
        username=current_user.username,
        total_reports=total_reports,
        avg_score=avg_score,
        best_score=best_score
    )

@app.route('/templates')
@login_required
def templates():
    return render_template('templates.html')

# ================= DELETE REPORTS =================

@app.route('/delete_reports')
@login_required
def delete_reports():

    Report.query.filter_by(
        user_id=current_user.id
    ).delete()

    db.session.commit()

    return redirect(url_for('home'))


# ================= UPLOAD =================

@app.route('/upload', methods=['POST'])
@login_required
def upload():

    file = request.files['resume']
    allowed_extensions = ['pdf', 'docx', 'png', 'jpg', 'jpeg']

    file_extension = file.filename.split('.')[-1].lower()

    if file_extension not in allowed_extensions:

       return "Only PDF, DOCX, and image files are allowed!"
    role = request.form['role']
    job_desc = request.form['job_description']

    filepath = os.path.join(
        app.config['UPLOAD_FOLDER'],
        file.filename
    )

    file.save(filepath)

    resume_text = extract_resume_text(filepath)

    ai_score = job_fit_score(resume_text, job_desc)

    skills = {
        "python_developer": ["python", "flask", "django"],
        "web_developer": ["html", "css", "javascript"],
        "data_scientist": ["python", "pandas", "numpy"]
    }

    role_skills = skills.get(role, [])

    found_skills = [
        s for s in role_skills
        if s.lower() in resume_text.lower()
    ]

    missing_skills = [
        s for s in role_skills
        if s not in found_skills
    ]
    skill_scores = {}

    for skill in role_skills:

        if skill.lower() in resume_text.lower():

           skill_scores[skill] = 100

        else:

           skill_scores[skill] = 20

    final_score = int(ai_score)
    if final_score >= 80:

        ats_status = "Excellent Resume 🚀"

    elif final_score >= 50:

        ats_status = "Good Resume 👍"

    else:

        ats_status = "Needs Improvement ⚠"

    suggestions = generate_suggestions(
        resume_text,
        job_desc,
        missing_skills
    )
    ai_tips = generate_ai_tips(
       final_score,
       missing_skills
    )

    msg = Message(

        "AI Resume Report",

        sender=app.config['MAIL_USERNAME'],

        recipients=[current_user.email]

    )

    msg.body = f"""

    Hello {current_user.username},

    Resume Score: {final_score}%

    ATS Status: {ats_status}

    """

    mail.send(msg)

    # ===== GRAPH =====

    fig = go.Figure(data=[
        go.Bar(
            name='Found Skills',
            x=['Skills'],
            y=[len(found_skills)]
        ),

        go.Bar(
            name='Missing Skills',
            x=['Skills'],
            y=[len(missing_skills)]
        )
    ])

    fig.update_layout(barmode='group')

    chart_div = fig.to_html(full_html=False)

    # ===== PDF =====

    pdf_filename = file.filename + "_report.pdf"

    pdf_path = os.path.join(
        app.config['UPLOAD_FOLDER'],
        pdf_filename
    )

    c = canvas.Canvas(pdf_path, pagesize=letter)

    c.drawString(100, 750, "AI Resume Report")
    c.drawString(100, 720, f"Resume: {file.filename}")
    c.drawString(100, 690, f"Role: {role}")
    c.drawString(100, 660, f"Final Score: {final_score}%")

    c.save()

    # ===== SAVE REPORT =====

    report = Report(
        resume_name=file.filename,
        role=role,
        final_score=final_score,
        user_id=current_user.id
    )

    db.session.add(report)
    db.session.commit()

    return render_template(
        'result.html',
        final_score=final_score,
        found_skills=found_skills,
        missing_skills=missing_skills,
        suggestions=suggestions,
        ai_tips=ai_tips,
        chart_div=chart_div,
        pdf_filename=pdf_filename,
        resume_filename=file.filename,
        ats_status=ats_status,
        skill_scores=skill_scores,
        interview_questions=interview_questions,
        resume_improvements=resume_improvements
    )


@app.route('/preview/<filename>')
@login_required
def preview(filename):

    return send_from_directory(
        app.config['UPLOAD_FOLDER'],
        filename
    )

@app.route("/interview", methods=["POST"])

def interview():

    role = request.form["role"]

    resume_text = request.form["resume_text"]

    prompt = f"""
    Generate interview questions for {role}

    based on this resume:

    {resume_text}
    """

    response = model.generate_content(prompt)

    questions = response.text

    return render_template(
        "interview.html",
        questions=questions
    )
    
# ================= DOWNLOAD =================

@app.route('/download/<filename>')
@login_required
def download(filename):
    return send_from_directory(
        app.config['UPLOAD_FOLDER'],
        filename,
        as_attachment=True
    )

# ================= RUN =================

if __name__ == '__main__':

    with app.app_context(): 
        db.create_all() 

    app.run(host="0.0.0.0", port=10000)