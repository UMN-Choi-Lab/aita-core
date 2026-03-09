aita-core
=========

**Shared core package for AI Teaching Assistant (AITA) chatbots.**

aita-core provides a complete, course-agnostic framework for building AI teaching
assistant chatbots. It includes a Streamlit chat UI, RAG (Retrieval-Augmented
Generation) pipeline, document ingestion, interaction logging, and an admin
dashboard — all parameterized by a single ``CourseConfig`` object.

Key design principle: **the chatbot never gives direct answers.** It guides
students through Socratic questioning, hints, and conceptual explanations.

.. code-block:: python

   from config import CONFIG
   from aita_core import run

   run(CONFIG)

Features
--------

- **Pedagogical guardrails** — Never gives direct answers; uses Socratic questioning
- **Week-aware responses** — Won't discuss topics not yet covered in class
- **RAG pipeline** — Retrieves relevant course materials to ground responses
- **Source citations** — References specific handouts, slides, and homework with PDF downloads
- **Admin dashboard** — View interaction logs, student feedback, and manage course settings
- **Google OAuth** — Restrict access to ``@umn.edu`` accounts (optional)
- **Wikibook ingestion** — Automatically fetch and index online textbook chapters
- **Mobile-friendly** — Responsive UI works on phones and tablets

.. toctree::
   :maxdepth: 2
   :caption: User Guide

   getting-started
   configuration
   deployment
   google-oauth

.. toctree::
   :maxdepth: 2
   :caption: Architecture

   architecture
   modules

.. toctree::
   :maxdepth: 1
   :caption: API Reference

   api/config
   api/app
   api/rag
   api/ingest
   api/db
   api/admin
   api/utils
