Getting Started
===============

This guide walks you through setting up an AITA chatbot for your course.

Prerequisites
-------------

- Python 3.11+
- Docker (for deployment)
- An `OpenAI API key <https://platform.openai.com/api-keys>`_
- (Optional) Google Cloud OAuth credentials for university login

Using the Template (Recommended)
---------------------------------

The fastest way to get started is the
`aita-template <https://github.com/UMN-Choi-Lab/aita-template>`_ repository:

1. Go to `UMN-Choi-Lab/aita-template <https://github.com/UMN-Choi-Lab/aita-template>`_
2. Click **"Use this template"** → **"Create a new repository"**
3. Clone your new repo, then follow the README inside

The template includes ``config.py``, ``main.py``, ``add_document.py``,
``Dockerfile``, and ``docker-compose.yml`` with ``TODO`` markers for your
course-specific data. If you use the template, skip to :ref:`step3-env`.

Manual Setup
------------

Step 1: Create Your Course Repository
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

   mkdir AITA_XXXX
   cd AITA_XXXX
   git init

Step 2: Install aita-core
^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

   pip install aita-core

Or add to ``requirements.txt``:

.. code-block:: text

   aita-core>=0.4.0

.. _step3-env:

Step 3: Set Up Environment Variables
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Create a ``.env`` file:

.. code-block:: bash

   OPENAI_API_KEY=sk-your-openai-api-key
   ADMIN_PASSWORD=your-admin-password
   GOOGLE_COOKIE_KEY=your-random-secret-string
   GOOGLE_REDIRECT_URI=http://your-server:8501
   AITA_DATA_DIR=/app/data

.. list-table::
   :widths: 25 75
   :header-rows: 1

   * - Variable
     - Description
   * - ``OPENAI_API_KEY``
     - Your OpenAI API key for embeddings and chat
   * - ``ADMIN_PASSWORD``
     - Password for the admin dashboard
   * - ``GOOGLE_COOKIE_KEY``
     - Random secret for JWT auth cookies
   * - ``GOOGLE_REDIRECT_URI``
     - Your server URL for OAuth callback
   * - ``AITA_DATA_DIR``
     - Directory for SQLite database (default: ``./data``)

Step 4: Add Course Materials
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Create a ``course_materials/`` directory with the standard layout:

.. code-block:: text

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

.. warning::

   Do **NOT** include homework solutions — the chatbot could retrieve and leak
   them to students.

Step 5: Create ``config.py``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

This file defines everything specific to your course. See :doc:`configuration`
for the full reference.

.. code-block:: python

   import os, sys, glob
   from dotenv import load_dotenv
   from aita_core import CourseConfig

   load_dotenv()
   BASE_DIR = os.path.dirname(__file__)

   # Detect Google OAuth credentials
   _client_secrets = glob.glob(os.path.join(BASE_DIR, "client_secret*.json"))
   _cookie_key = os.getenv("GOOGLE_COOKIE_KEY")
   _redirect_uri = os.getenv("GOOGLE_REDIRECT_URI")
   _google_secret = _client_secrets[0] if (_client_secrets and _cookie_key and _redirect_uri) else ""

   SYSTEM_PROMPT = """\
   You are an AI Teaching Assistant for YOUR COURSE at the University of Minnesota.

   YOUR CORE PRINCIPLE: You must NEVER give direct answers to homework or exam problems.
   Instead, guide students through Socratic questioning, hints, and conceptual explanations.
   """

   CONFIG = CourseConfig(
       course_id="XXXX",
       course_name="CEGE XXXX: AI Teaching Assistant",
       course_short_name="CEGE XXXX AITA",
       course_description="Welcome! This AI assistant helps you learn ...",
       system_prompt=SYSTEM_PROMPT,
       week_topics={
           1: ["Topic A", "Topic B"],
           2: ["Topic C"],
           # ... all 15 weeks
       },
       topic_num_to_week={1: 1, 2: 2},
       hw_num_to_week={1: 2, 2: 3},
       lab_num_to_week={1: 2},
       study_guide_to_week={},
       example_prompts={
           1: ["What topics does this course cover?",
               "Help me with this week's homework"],
       },
       base_dir=BASE_DIR,
       course_materials_dir=os.path.join(BASE_DIR, "course_materials"),
       faiss_db_dir=os.path.join(BASE_DIR, "faiss_db"),
       docs_dir=os.path.join(BASE_DIR, "docs"),
       backup_dir=os.path.join(BASE_DIR, "backup"),
       data_dir=os.getenv("AITA_DATA_DIR", os.path.join(BASE_DIR, "data")),
       admin_password=os.getenv("ADMIN_PASSWORD", ""),
       cookie_name="aita_XXXX_auth",
       cookie_key=_cookie_key or "",
       redirect_uri=_redirect_uri or "http://localhost:8501",
       google_client_secret_file=_google_secret,
   )

Step 6: Create ``main.py``
^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   from config import CONFIG
   from aita_core import run

   run(CONFIG)

Step 7: Create ``add_document.py``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

For the standard directory layout:

.. code-block:: python

   from config import CONFIG
   from aita_core.ingest import run_ingestion

   if __name__ == "__main__":
       run_ingestion(CONFIG)

For non-standard layouts, pass custom collectors:

.. code-block:: python

   from config import CONFIG
   from aita_core.ingest import run_ingestion, load_pdf

   def my_collect_handouts(config):
       docs = []
       # Your custom logic to find PDFs
       # Return list of {"text": ..., "metadata": {...}}
       return docs

   if __name__ == "__main__":
       run_ingestion(CONFIG, collectors=[
           ("handouts", my_collect_handouts),
       ])

Step 8: Build the Vector Store
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

   python add_document.py

This reads your course materials, generates embeddings via OpenAI, and saves a
FAISS index to ``faiss_db/``.

Step 9: Test Locally
^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

   streamlit run main.py

Open http://localhost:8501 and test with sample questions.

Step 10: Deploy
^^^^^^^^^^^^^^^

See :doc:`deployment` for Docker deployment instructions.

Recommended ``.gitignore``
^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: text

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
