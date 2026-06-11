from PyPDF2 import PdfReader
from docx import Document
import os


# =========================
# EXTRACT RESUME TEXT
# =========================

def extract_resume_text(filepath):

    text = ""

    if filepath.endswith(".pdf"):

        reader = PdfReader(filepath)

        print("TOTAL PAGES =", len(reader.pages))

        for i, page in enumerate(reader.pages):

            extracted = page.extract_text()

            print("PAGE", i+1, "TEXT =", extracted)

            if extracted:
                text += extracted

    return text.lower()


# =========================
# AI SCORE
# =========================

def job_fit_score(resume_text, job_description):

    resume_words = set(resume_text.lower().split())
    jd_words = set(job_description.lower().split())

    common_words = resume_words.intersection(jd_words)

    if len(jd_words) == 0:
        return 0

    score = int((len(common_words) / len(jd_words)) * 100)

    # LIMIT SCORE
    if score > 100:
        score = 100

    return score


# =========================
# SUGGESTIONS
# =========================

def generate_suggestions(resume, jd, missing_skills):

    suggestions = []

    if missing_skills:

        for skill in missing_skills:

            suggestions.append(
                f"Add {skill} skill to improve your ATS score."
            )

    else:

        suggestions.append(
            "Excellent resume! Your skills match the role well."
        )

    return suggestions
def generate_ai_tips(score, missing_skills):

    tips = []

    # LOW SCORE

    if score < 40:

        tips.append(
            "Your resume needs major improvements."
        )

        tips.append(
            "Add more projects and technical skills."
        )

    # MEDIUM SCORE

    elif score < 70:

        tips.append(
            "Your resume is good but can be improved."
        )

        tips.append(
            "Add certifications and achievements."
        )

    # HIGH SCORE

    else:

        tips.append(
            "Excellent resume for this role."
        )

        tips.append(
            "Try applying for top companies."
        )

    # MISSING SKILLS

    if missing_skills:

        tips.append(
            "Focus on these missing skills: "
            + ", ".join(missing_skills)
        )

    # COMMON TIPS

    tips.append(
        "Add GitHub and LinkedIn links."
    )

    tips.append(
        "Use ATS-friendly resume format."
    )

    return tips

def generate_interview_questions(resume_text):

    questions = []

    if "python" in resume_text:
        questions.append("Explain a Python project you have worked on.")

    if "machine learning" in resume_text or "ml" in resume_text:
        questions.append("What Machine Learning models have you used?")

    if "computer vision" in resume_text:
        questions.append("Explain a Computer Vision project.")

    if "wordpress" in resume_text:
        questions.append("What are the advantages of WordPress?")

    if "intern" in resume_text:
        questions.append("What did you learn during your internship?")

    questions.append("Tell me about yourself.")
    questions.append("Why should we hire you?")
    questions.append("What are your strengths?")

    return questions