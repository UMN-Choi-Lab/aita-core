Configuration
=============

All course-specific settings are defined in a single ``CourseConfig`` dataclass.
This is the only thing you need to customize per course — the rest of aita-core
is fully generic.

Field Reference
---------------

Course Identity
^^^^^^^^^^^^^^^

.. list-table::
   :widths: 25 15 60
   :header-rows: 1

   * - Field
     - Type
     - Description
   * - ``course_id``
     - ``str``
     - Short identifier (e.g., ``"3102"``). Used in log messages.
   * - ``course_name``
     - ``str``
     - Full display name (e.g., ``"CEGE 3102: AI Teaching Assistant"``). Shown as page title.
   * - ``course_short_name``
     - ``str``
     - Sidebar title (e.g., ``"CEGE 3102 AITA"``).
   * - ``course_description``
     - ``str``
     - Markdown text shown on the login page below the title.
   * - ``system_prompt``
     - ``str``
     - The LLM system prompt. This is the primary mechanism for pedagogical guardrails.

Week & Topic Mappings
^^^^^^^^^^^^^^^^^^^^^

These fields control **week-aware** behavior: the chatbot won't discuss topics
from future weeks, and content is filtered during RAG retrieval.

.. list-table::
   :widths: 25 15 60
   :header-rows: 1

   * - Field
     - Type
     - Description
   * - ``week_topics``
     - ``dict[int, list[str]]``
     - Maps week number (1-15) to list of topic names covered that week.
       Used to build the system prompt's topic awareness.
   * - ``topic_num_to_week``
     - ``dict[int, int]``
     - Maps the number prefix in slide/handout filenames (e.g., ``3`` from
       ``"3 Topic Name.pdf"``) to the week that topic is first covered.
   * - ``hw_num_to_week``
     - ``dict[int, int]``
     - Maps homework number to the week it's assigned. Used for week-filtering
       during retrieval and for the "current homework" injection feature.
   * - ``lab_num_to_week``
     - ``dict[int, int]``
     - Maps lab number to the week it belongs to.
   * - ``study_guide_to_week``
     - ``dict[str, int]``
     - Maps study guide / quiz names to week. Matched by filename prefix.
   * - ``example_prompts``
     - ``dict[int, list[str]]``
     - Example prompts shown as clickable buttons when chat is empty,
       organized by week. 4 prompts per week works well.

Textbook (Optional)
^^^^^^^^^^^^^^^^^^^

.. list-table::
   :widths: 25 15 60
   :header-rows: 1

   * - Field
     - Type
     - Description
   * - ``textbook_url``
     - ``str``
     - Base URL for a Wikibook (e.g.,
       ``"https://en.wikibooks.org/wiki/Fundamentals_of_Transportation"``).
       Leave empty to skip textbook ingestion.
   * - ``textbook_chapter_to_week``
     - ``dict[str, int]``
     - Maps chapter URL slugs to week numbers (e.g.,
       ``{"Trip_Generation": 2, "Route_Choice": 4}``).

Paths
^^^^^

.. list-table::
   :widths: 25 15 60
   :header-rows: 1

   * - Field
     - Type
     - Description
   * - ``base_dir``
     - ``str``
     - Root directory of the course project.
   * - ``course_materials_dir``
     - ``str``
     - Directory containing course PDFs and LaTeX files.
   * - ``faiss_db_dir``
     - ``str``
     - Where the FAISS vector index is stored.
   * - ``docs_dir``
     - ``str``
     - Where document records (``doc.jsonl``) are saved.
   * - ``backup_dir``
     - ``str``
     - Timestamped backups of previous FAISS indices.
   * - ``data_dir``
     - ``str``
     - Where the SQLite database is stored. In Docker, this is
       typically a mounted volume (e.g., ``/app/data``).

Authentication
^^^^^^^^^^^^^^

.. list-table::
   :widths: 25 15 60
   :header-rows: 1

   * - Field
     - Type
     - Description
   * - ``admin_password``
     - ``str``
     - Password for the admin dashboard.
   * - ``cookie_name``
     - ``str``
     - Name of the JWT auth cookie (e.g., ``"aita_3102_auth"``).
   * - ``cookie_key``
     - ``str``
     - Secret key for signing JWT cookies. Set via ``GOOGLE_COOKIE_KEY`` env var.
   * - ``redirect_uri``
     - ``str``
     - OAuth redirect URI (must match Google Cloud Console config).
   * - ``google_client_secret_file``
     - ``str``
     - Path to the Google OAuth client secret JSON file. Leave empty to
       disable Google Auth (falls back to student ID login).

LLM & Embedding Settings
^^^^^^^^^^^^^^^^^^^^^^^^^

.. list-table::
   :widths: 25 15 15 45
   :header-rows: 1

   * - Field
     - Type
     - Default
     - Description
   * - ``llm_model``
     - ``str``
     - ``"gpt-4o-mini"``
     - OpenAI model used for chat completions.
   * - ``llm_temperature``
     - ``float``
     - ``0``
     - LLM temperature. 0 gives deterministic, factual responses.
   * - ``embedding_model``
     - ``str``
     - ``"text-embedding-3-large"``
     - OpenAI model for generating embeddings.
   * - ``embedding_dimensions``
     - ``int``
     - ``3072``
     - Embedding vector dimensions.
   * - ``chunk_size``
     - ``int``
     - ``2048``
     - Characters per text chunk during ingestion.
   * - ``chunk_overlap``
     - ``int``
     - ``256``
     - Overlap between consecutive chunks.
   * - ``retrieval_k``
     - ``int``
     - ``5``
     - Number of chunks to retrieve per query.

Config Overrides (Admin Panel)
------------------------------

Settings can be modified at runtime through the **Course Settings** tab in the
admin dashboard. Changes are saved to ``config_overrides.json`` in the
``data_dir`` and automatically loaded on startup.

Fields that can be edited at runtime:

- Course identity (name, description, system prompt)
- LLM settings (model, temperature, retrieval_k)
- Week schedule and topic mappings
- Example prompts
- Textbook URL and chapter mappings

.. note::

   Changes to ``embedding_model``, ``chunk_size``, and ``chunk_overlap``
   require re-running the document ingestion pipeline to take effect.

Computed Properties
-------------------

``CourseConfig`` provides several computed properties:

- ``google_auth_enabled`` — ``True`` if a Google client secret file is set.
- ``week_to_hw`` — Inverse of ``hw_num_to_week``: maps week to ``"HWN"`` string.
- ``get_topics_covered(week)`` — Returns list of topics covered up to the given week.
- ``get_topics_not_covered(week)`` — Returns list of topics not yet covered.
