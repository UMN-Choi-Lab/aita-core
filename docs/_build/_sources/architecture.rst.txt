Architecture
============

Overview
--------

AITA follows a three-layer architecture:

.. code-block:: text

   ┌─────────────────────────────────────────────────────┐
   │                   Frontend (Streamlit)               │
   │  ┌──────────┐  ┌──────────────┐  ┌───────────────┐  │
   │  │  Login /  │  │  Chat UI     │  │  Admin Panel  │  │
   │  │  Google   │  │  (multi-turn │  │  (settings,   │  │
   │  │  Auth     │  │   dialogue)  │  │   analytics)  │  │
   │  └──────────┘  └──────────────┘  └───────────────┘  │
   └────────────────────────┬────────────────────────────┘
                            │
   ┌────────────────────────▼────────────────────────────┐
   │                 RAG Pipeline                         │
   │  1. Embed user query (OpenAI)                       │
   │  2. Retrieve top-k chunks from FAISS (week-filtered)│
   │  3. Inject current homework if relevant             │
   │  4. Build prompt with system instructions + context  │
   │  5. Generate response (OpenAI)                      │
   └────────────────────────┬────────────────────────────┘
                            │
   ┌────────────────────────▼────────────────────────────┐
   │                    Data Layer                        │
   │  ┌─────────────┐  ┌────────────┐  ┌──────────────┐  │
   │  │ FAISS Index  │  │ SQLite DB  │  │ Course Docs  │  │
   │  │ (embeddings) │  │ (logs,     │  │ (PDFs, .tex) │  │
   │  │              │  │  feedback)  │  │              │  │
   │  └─────────────┘  └────────────┘  └──────────────┘  │
   └─────────────────────────────────────────────────────┘

Request Flow
------------

When a student asks a question, here's what happens:

1. **Query embedding** — The user's question is embedded using OpenAI's
   ``text-embedding-3-large`` model.

2. **Retrieval** — The embedding is used to search the FAISS index for the
   top-k most similar document chunks. Chunks are filtered by ``max_week``
   so only content from topics already covered is returned.

3. **Homework injection** — If the query mentions "homework", "hw", or
   "assignment", the system checks whether the current week's homework is in
   the retrieved results. If not, it's injected as the first chunk.

4. **Prompt construction** — A system prompt is built with:

   - The course-specific pedagogical instructions
   - Week-awareness: current week, covered topics, future topics
   - The retrieved course material chunks

5. **LLM generation** — The complete message list (system prompt + chat
   history + user query) is sent to the LLM.

6. **Logging** — The interaction (question, response, sources, week) is saved
   to the SQLite database.

Week-Aware Filtering
--------------------

Every document chunk has a ``max_week`` metadata field set during ingestion.
This is determined by matching the filename against the mappings in
``CourseConfig``:

- ``topic_num_to_week`` — for handouts and slides (by number prefix)
- ``hw_num_to_week`` — for homework files
- ``lab_num_to_week`` — for lab files
- ``study_guide_to_week`` — for study guides and quizzes
- ``textbook_chapter_to_week`` — for wikibook chapters

During retrieval, chunks with ``max_week > current_week`` are excluded. This
prevents the chatbot from discussing future topics.

The system prompt also lists covered and uncovered topics, instructing the LLM
to redirect questions about future material.

Document Ingestion Pipeline
---------------------------

The ingestion pipeline (``run_ingestion``) processes course materials into
a searchable FAISS index:

1. **Collection** — Collector functions scan the course materials directory
   and load documents (PDFs via PDFMiner, LaTeX files, or web pages).

2. **Chunking** — Each document is split into overlapping chunks
   (default: 2048 chars with 256 char overlap). Source metadata is prepended
   to each chunk.

3. **Embedding** — Chunks are embedded in batches using the OpenAI API.

4. **Indexing** — Embeddings are stored in a FAISS ``IndexFlatIP`` (inner
   product / cosine similarity) index. Chunk metadata is saved alongside
   in a pickle file.

5. **Backup** — If a previous index exists, it's backed up with a timestamp.

Module Dependency Graph
-----------------------

.. code-block:: text

   __init__.py
       └── config.py      (CourseConfig, set_config, get_config)
       └── app.py          (Streamlit UI)
               ├── config.py
               ├── rag.py         (RAG pipeline)
               │       ├── config.py
               │       └── [OpenAI API, FAISS]
               ├── db.py          (SQLite logging)
               │       └── config.py
               ├── admin.py       (Admin dashboard)
               │       ├── config.py
               │       └── db.py
               └── oauth_store.py (PKCE state)

   ingest.py  (standalone, called from add_document.py)
       ├── config.py
       ├── utils.py
       └── [OpenAI API, FAISS, PDFMiner]
