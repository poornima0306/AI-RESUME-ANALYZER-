from PyPDF2 import PdfReader
from docx import Document
import os


# =========================
# EXTRACT RESUME TEXT
# =========================

def extract_resume_text(filepath):

    text = ""

    # PDF
    if filepath.endswith(".pdf"):

        reader = PdfReader(filepath)

        for page in reader.pages:
            extracted = page.extract_text()

            if extracted:
                text += extracted

    # DOCX
    elif filepath.endswith(".docx"):

        doc = Document(filepath)

        for para in doc.paragraphs:
            text += para.text

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