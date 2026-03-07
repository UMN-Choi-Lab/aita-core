# aita-core

[![PyPI version](https://badge.fury.io/py/aita-core.svg)](https://pypi.org/project/aita-core/)

Shared core package for **AI Teaching Assistant (AITA)** chatbots. Provides the Streamlit UI, RAG pipeline, database logging, admin panel, and document ingestion utilities — parameterized by a `CourseConfig` so the same codebase serves multiple courses.

## How It Works

AITA is an AI chatbot that helps students learn course material. It uses **Retrieval-Augmented Generation (RAG)** — your course documents (slides, handouts, homework) are indexed into a vector database, and when a student asks a question, the system retrieves relevant content and generates a pedagogically appropriate response using an LLM.

Key design principle: **the chatbot never gives direct answers**. It guides students through Socratic questioning, hints, and conceptual explanations.

## Step-by-Step Setup Guide

### Prerequisites

- Python 3.11+
- Docker (for deployment)
- An [OpenAI API key](https://platform.openai.com/api-keys)
- (Optional) Google Cloud OAuth credentials for UMN login

### Step 1: Create Your Course Repository

Create a new directory for your course:

```bash
mkdir AITA_XXXX
cd AITA_XXXX
git init
```

### Step 2: Install aita-core

```bash
pip install aita-core
```

Or add to `requirements.txt`:

```
aita-core>=0.1.0
```

### Step 3: Set Up Environment Variables

Create a `.env` file (never commit this):

```bash
OPENAI_API_KEY=sk-your-openai-api-key
ADMIN_PASSWORD=your-admin-password
GOOGLE_COOKIE_KEY=your-random-secret-string
GOOGLE_REDIRECT_URI=http://your-server:8501
AITA_DATA_DIR=/app/data
```

Create a `.env.example` for reference (safe to commit):

```bash
OPENAI_API_KEY=your-openai-api-key-here
ADMIN_PASSWORD=your-admin-password-here
GOOGLE_COOKIE_KEY=your-cookie-secret-here
GOOGLE_REDIRECT_URI=http://localhost:8501
AITA_DATA_DIR=/app/data
```

### Step 4: Add Your Course Materials

Create a `course_materials/` directory and organize your files:

```
course_materials/
├── Handouts/
│   └── Handouts/
│       ├── 1 Topic Name.pdf
│       ├── 2 Topic Name.pdf
│       └── ...
├── Homework handouts/
│   └── Homework handouts/
│       ├── HW1.pdf
│       ├── HW2.pdf
│       └── ...
├── Slides/
│   └── Slides/
│       ├── 1 Topic Name/
│       │   ├── content.tex    (or Notes.pdf)
│       │   └── Handout.pdf
│       └── ...
└── syllabus/
    └── Syllabus.pdf (or Syllabus.tex)
```

**Important:** Do NOT include homework solutions — the chatbot could leak them to students.

### Step 5: Create `config.py`

This is where you define everything specific to your course. Copy the template below and fill in your course details:

```python
import os
import sys
import glob
from dotenv import load_dotenv
from aita_core import CourseConfig

load_dotenv()

BASE_DIR = os.path.dirname(__file__)
_client_secret_matches = glob.glob(os.path.join(BASE_DIR, "client_secret*.json"))

# Google Auth requires all three: client_secret file + GOOGLE_COOKIE_KEY + GOOGLE_REDIRECT_URI
_google_cookie_key = os.getenv("GOOGLE_COOKIE_KEY")
_google_redirect_uri = os.getenv("GOOGLE_REDIRECT_URI")
if _client_secret_matches and _google_cookie_key and _google_redirect_uri:
    _google_client_secret = _client_secret_matches[0]
else:
    _google_client_secret = ""
    if _client_secret_matches:
        print("[WARN] Google OAuth: client_secret found but GOOGLE_COOKIE_KEY or "
              "GOOGLE_REDIRECT_URI not set. Falling back to student ID login.",
              file=sys.stderr)

SYSTEM_PROMPT = """\
You are an AI Teaching Assistant for COURSE_NAME \
at the University of Minnesota, taught by Prof. YOUR NAME.

YOUR CORE PRINCIPLE: You must NEVER give direct answers to homework or exam problems. \
Instead, you should:
- Ask Socratic questions to guide students toward understanding
- Provide hints and point students to relevant concepts or course materials
- Explain underlying principles without solving the specific problem
- Encourage students to attempt the problem first and share their reasoning
- When students share their work, help them identify errors conceptually

When responding:
- Cite source material when referencing course content
- Be encouraging, patient, and supportive
- Keep responses focused and concise
- If the question is not related to the course, politely redirect
- Use LaTeX for math: $inline$ and $$display$$
- IMPORTANT: Never use \\[ \\] or \\( \\) for LaTeX. Always use $...$ and $$...$$

You will be provided with relevant context from course materials to ground your responses.\
"""

CONFIG = CourseConfig(
    # --- Course identity ---
    course_id="XXXX",
    course_name="CEGE XXXX: AI Teaching Assistant",
    course_short_name="CEGE XXXX AITA",
    course_description=(
        "Welcome! This AI assistant helps you learn concepts for "
        "**CEGE XXXX: Your Course Title**."
    ),
    system_prompt=SYSTEM_PROMPT,

    # --- Week-to-topic mapping ---
    # What topics are covered each week? Used to prevent the chatbot
    # from discussing future topics before they're taught.
    week_topics={
        1:  ["Topic A"],
        2:  ["Topic B", "Topic C"],
        3:  ["Topic D"],
        # ... add all 15 weeks
        15: ["Final exam review"],
    },

    # --- Document-to-week mapping ---
    # Maps the number prefix in filenames (e.g., "3 Topic Name.pdf" -> topic 3)
    # to the week that topic is first covered.
    topic_num_to_week={
        1: 1, 2: 2, 3: 3,
        # ... one entry per handout/slide topic folder
    },

    # Maps homework number to the week it's assigned.
    hw_num_to_week={
        1: 2, 2: 3, 3: 4,
        # ... one entry per homework
    },

    # Maps lab number to week.
    lab_num_to_week={
        1: 1, 2: 2, 3: 3,
        # ... one entry per lab
    },

    # Maps study guide / quiz names to week. Leave empty if not applicable.
    study_guide_to_week={},

    # --- Example prompts ---
    # Shown as clickable buttons when chat is empty. 4 per week works well.
    example_prompts={
        1: [
            "What topics does this course cover?",
            "What are the prerequisites?",
            "How is grading structured?",
            "Help me with this week's homework",
        ],
        # ... add for each week
    },

    # --- Paths ---
    base_dir=BASE_DIR,
    course_materials_dir=os.path.join(BASE_DIR, "course_materials"),
    faiss_db_dir=os.path.join(BASE_DIR, "faiss_db"),
    docs_dir=os.path.join(BASE_DIR, "docs"),
    backup_dir=os.path.join(BASE_DIR, "backup"),
    data_dir=os.getenv("AITA_DATA_DIR", os.path.join(BASE_DIR, "data")),

    # --- Auth ---
    admin_password=os.getenv("ADMIN_PASSWORD", ""),
    cookie_name="aita_XXXX_auth",
    cookie_key=_google_cookie_key or "",
    redirect_uri=_google_redirect_uri or "http://localhost:8501",
    google_client_secret_file=_google_client_secret,
)
```

### Step 6: Create `main.py`

```python
from config import CONFIG
from aita_core import run

run(CONFIG)
```

### Step 7: Create `add_document.py`

This script ingests your course materials into the vector database. Adapt the `collect_*` functions to match your directory layout:

```python
import os
from aita_core.ingest import (
    get_week_for_filename, load_pdf, load_tex,
    chunk_documents, get_embeddings, build_faiss_index, save_index,
    collect_syllabus,
)
from config import CONFIG


def _week_for(filename):
    return get_week_for_filename(
        filename, CONFIG.topic_num_to_week, CONFIG.hw_num_to_week,
        CONFIG.lab_num_to_week, CONFIG.study_guide_to_week,
    )


def collect_handouts():
    docs = []
    handouts_dir = os.path.join(CONFIG.course_materials_dir, "Handouts", "Handouts")
    if not os.path.isdir(handouts_dir):
        print(f"  Warning: {handouts_dir} not found")
        return docs
    for filename in sorted(os.listdir(handouts_dir)):
        if not filename.endswith(".pdf"):
            continue
        file_path = os.path.join(handouts_dir, filename)
        label = f"Handout: {filename}"
        week = _week_for(filename)
        print(f"  Loading {label} (week {week})")
        docs.extend(load_pdf(file_path, label, max_week=week))
    return docs


def collect_homework_questions():
    docs = []
    hw_dir = os.path.join(CONFIG.course_materials_dir, "Homework handouts", "Homework handouts")
    if not os.path.isdir(hw_dir):
        print(f"  Warning: {hw_dir} not found")
        return docs
    for filename in sorted(os.listdir(hw_dir)):
        if not filename.endswith(".pdf"):
            continue
        if "solution" in filename.lower():
            print(f"  Skipping (solution): {filename}")
            continue
        file_path = os.path.join(hw_dir, filename)
        label = f"Homework: {filename}"
        week = _week_for(filename)
        print(f"  Loading {label} (week {week})")
        docs.extend(load_pdf(file_path, label, max_week=week))
    return docs


def collect_slide_content():
    docs = []
    slides_dir = os.path.join(CONFIG.course_materials_dir, "Slides", "Slides")
    if not os.path.isdir(slides_dir):
        print(f"  Warning: {slides_dir} not found")
        return docs
    for topic_name in sorted(os.listdir(slides_dir)):
        topic_path = os.path.join(slides_dir, topic_name)
        if not os.path.isdir(topic_path):
            continue
        label = f"Slides: {topic_name}"
        week = _week_for(topic_name)
        content_tex = os.path.join(topic_path, "content.tex")
        if os.path.exists(content_tex):
            print(f"  Loading {label} (LaTeX, week {week})")
            docs.extend(load_tex(content_tex, label, max_week=week))
        else:
            notes_pdf = os.path.join(topic_path, "Notes.pdf")
            if os.path.exists(notes_pdf):
                print(f"  Loading {label} (PDF, week {week})")
                docs.extend(load_pdf(notes_pdf, label, max_week=week))
    return docs


def main():
    print("=" * 60)
    print("AITA Document Ingestion Pipeline")
    print("=" * 60)

    print("\n[1/4] Collecting lecture handouts...")
    all_docs = collect_handouts()

    print("\n[2/4] Collecting homework questions...")
    all_docs += collect_homework_questions()

    print("\n[3/4] Collecting slide content...")
    all_docs += collect_slide_content()

    print("\n[4/4] Collecting syllabus...")
    all_docs += collect_syllabus(CONFIG.course_materials_dir)

    if not all_docs:
        print("\nNo documents found. Check course_materials directory.")
        return

    print(f"\nTotal documents loaded: {len(all_docs)}")

    chunks = chunk_documents(all_docs, CONFIG.chunk_size, CONFIG.chunk_overlap)
    print(f"Total chunks after splitting: {len(chunks)}")

    print(f"\nGenerating embeddings with {CONFIG.embedding_model}...")
    texts = [c["text"] for c in chunks]
    embeddings = get_embeddings(texts, CONFIG.embedding_model)

    print("\nBuilding FAISS index...")
    index = build_faiss_index(embeddings)
    save_index(index, chunks, CONFIG.faiss_db_dir, CONFIG.docs_dir, CONFIG.backup_dir)

    print("\nDone! Vector store is ready.")


if __name__ == "__main__":
    main()
```

### Step 8: Build the Vector Store

```bash
python add_document.py
```

This reads your course materials, generates embeddings via OpenAI, and saves a FAISS index to `faiss_db/`.

### Step 9: Test Locally

```bash
streamlit run main.py
```

Open http://localhost:8501 in your browser and test with sample questions.

### Step 10: Deploy with Docker

Create a `Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY config.py main.py ./
COPY client_secret*.json* ./
COPY faiss_db/ ./faiss_db/
COPY course_materials/ ./course_materials/

RUN mkdir -p /app/data
RUN mkdir -p /root/.streamlit
RUN echo '[server]\nheadless = true\nport = 8501\nenableCORS = false\nenableXsrfProtection = false\n\n[browser]\ngatherUsageStats = false' > /root/.streamlit/config.toml

EXPOSE 8501
ENTRYPOINT ["streamlit", "run", "main.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

Create a `docker-compose.yml`:

```yaml
services:
  aita:
    build: .
    ports:
      - "8501:8501"
    env_file:
      - .env
    volumes:
      - /path/to/persistent/data:/app/data
    restart: unless-stopped
```

Build and run:

```bash
docker compose build
docker compose up -d
```

Your chatbot is now live at `http://your-server:8501`.

### Step 11: Set Up `.gitignore`

```
.env
.venv/
__pycache__/
*.py[cod]
*.egg-info/
faiss_db/
backup/
docs/
course_materials/
client_secret*.json
.DS_Store
.vscode/
.idea/
.streamlit/secrets.toml
```

### Step 12: (Optional) Google OAuth

To restrict login to `@umn.edu` accounts:

1. Create a project in [Google Cloud Console](https://console.cloud.google.com/)
2. Enable the **Google+ API** (or People API)
3. Create OAuth 2.0 credentials (Web application)
4. Add your redirect URI (e.g., `http://your-server:8501`)
5. Download the client secret JSON and place it in your project root as `client_secret_*.json`
6. Set `GOOGLE_COOKIE_KEY` and `GOOGLE_REDIRECT_URI` in your `.env`

If any of these are missing, the app automatically falls back to student ID login.

## Features

- **Pedagogical guardrails** — Never gives direct answers; uses Socratic questioning
- **Week-aware responses** — Won't discuss topics not yet covered in class
- **Source citations** — References specific handouts, slides, and homework
- **PDF downloads** — Students can download referenced course materials
- **Admin dashboard** — View interaction logs, student feedback, and feature requests
- **Google OAuth** — Restrict access to `@umn.edu` accounts (optional)
- **Mobile-friendly** — Responsive UI works on phones and tablets

## Cost

Using GPT-4o-mini (default), estimated cost is **under $20/semester** for a class of 80 students with heavy usage. See [OpenAI pricing](https://openai.com/api/pricing/) for current rates.

## Course Repo Structure

```
AITA_XXXX/
├── config.py              # CourseConfig with all course-specific data
├── main.py                # 3 lines: import config, import aita_core, run
├── add_document.py        # Course-specific document collection + shared pipeline
├── course_materials/      # PDFs, LaTeX source (not committed)
├── faiss_db/              # Built vector index (not committed)
├── .env                   # API keys (not committed)
├── .env.example           # Template for .env (safe to commit)
├── .gitignore
├── docker-compose.yml
├── Dockerfile
└── requirements.txt       # just: aita-core>=0.1.0
```
