Module Overview
===============

aita-core is organized into the following modules:

.. list-table::
   :widths: 20 80
   :header-rows: 1

   * - Module
     - Description
   * - :doc:`api/config`
     - ``CourseConfig`` dataclass and global config management. All course-specific
       settings are defined here. Supports runtime overrides via JSON.
   * - :doc:`api/app`
     - Streamlit application entry point. Contains the login page (Google OAuth
       or student ID), chat page (multi-turn conversation with source citations),
       and page routing.
   * - :doc:`api/rag`
     - RAG (Retrieval-Augmented Generation) pipeline. Handles query embedding,
       FAISS retrieval with week filtering, homework injection, prompt
       construction, and LLM response generation.
   * - :doc:`api/ingest`
     - Document ingestion pipeline. Reads PDFs, LaTeX, and web pages; chunks
       text; generates embeddings; and builds the FAISS index. Supports
       custom collectors for non-standard directory layouts.
   * - :doc:`api/db`
     - SQLite database for interaction logs, student feedback, and feature
       requests. Auto-initializes tables on first use.
   * - :doc:`api/admin`
     - Admin dashboard with interaction history, feedback viewer, feature
       request management, and course settings editor.
   * - :doc:`api/utils`
     - Helper utilities for JSONL serialization.

Additionally, ``oauth_store.py`` provides module-level storage for the OAuth
PKCE code verifier (needed to persist across Streamlit reruns).
