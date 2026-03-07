# aita-core

Shared core package for **AI Teaching Assistant (AITA)** chatbots. Provides the Streamlit UI, RAG pipeline, database logging, admin panel, and document ingestion utilities — parameterized by a `CourseConfig` so the same codebase serves multiple courses.

## Installation

```bash
pip install git+https://github.com/umnCETransportation/aita-core.git
```

## Usage

Each course repo provides a thin `config.py` and `main.py`:

### `config.py`

```python
import os
import glob
from dotenv import load_dotenv
from aita_core import CourseConfig

load_dotenv()

BASE_DIR = os.path.dirname(__file__)

_client_secret_matches = glob.glob(os.path.join(BASE_DIR, "client_secret*.json"))

CONFIG = CourseConfig(
    course_id="3102",
    course_name="CEGE 3102: AI Teaching Assistant",
    course_short_name="CEGE 3102 AITA",
    course_description=(
        "Welcome! This AI assistant helps you learn probability and statistics "
        "concepts for **CEGE 3102: Uncertainty and Decision Analysis**."
    ),
    system_prompt="You are an AI Teaching Assistant for CEGE 3102...",
    week_topics={1: ["Fundamentals of probability"], ...},
    topic_num_to_week={1: 1, 2: 1, ...},
    hw_num_to_week={1: 2, 2: 3, ...},
    lab_num_to_week={1: 1, 2: 2, ...},
    study_guide_to_week={"Quiz 1 ": 3, ...},
    example_prompts={1: ["What is a sample space?", ...], ...},
    base_dir=BASE_DIR,
    course_materials_dir=os.path.join(BASE_DIR, "course_materials"),
    faiss_db_dir=os.path.join(BASE_DIR, "faiss_db"),
    docs_dir=os.path.join(BASE_DIR, "docs"),
    backup_dir=os.path.join(BASE_DIR, "backup"),
    data_dir=os.getenv("AITA_DATA_DIR", os.path.join(BASE_DIR, "data")),
    admin_password=os.getenv("ADMIN_PASSWORD", "admin3102"),
    cookie_name="aita_3102_auth",
    cookie_key=os.getenv("GOOGLE_COOKIE_KEY", "aita3102secretkey"),
    redirect_uri=os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:30001"),
    google_client_secret_file=_client_secret_matches[0] if _client_secret_matches else "",
)
```

### `main.py`

```python
from config import CONFIG
from aita_core import run

run(CONFIG)
```

Run with: `streamlit run main.py`

### `add_document.py`

Each course keeps its own ingestion script using shared utilities:

```python
from aita_core.ingest import (
    get_week_for_filename, load_pdf, load_tex,
    chunk_documents, get_embeddings, build_faiss_index, save_index,
    collect_syllabus,
)
from config import CONFIG

def collect_handouts():
    # Course-specific directory layout
    ...

def main():
    all_docs = collect_handouts()
    all_docs += collect_syllabus(CONFIG.course_materials_dir)
    chunks = chunk_documents(all_docs, CONFIG.chunk_size, CONFIG.chunk_overlap)
    texts = [c["text"] for c in chunks]
    embeddings = get_embeddings(texts, CONFIG.embedding_model)
    index = build_faiss_index(embeddings)
    save_index(index, chunks, CONFIG.faiss_db_dir, CONFIG.docs_dir, CONFIG.backup_dir)

if __name__ == "__main__":
    main()
```

## Course repo structure

```
AITA_XXXX/
├── config.py              # CourseConfig with all course-specific data
├── main.py                # 3 lines: import config, import aita_core, run
├── add_document.py        # Course-specific document collection + shared pipeline
├── course_materials/      # PDFs, LaTeX source
├── faiss_db/              # Built vector index
├── .env                   # API keys (not committed)
├── docker-compose.yml     # Port mapping, volume mount
├── Dockerfile
└── requirements.txt       # aita-core as dependency
```
