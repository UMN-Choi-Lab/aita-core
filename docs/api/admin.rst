``aita_core.admin`` — Admin Dashboard
======================================

Password-protected admin dashboard for viewing interaction logs, student
feedback, feature requests, and editing course settings.

Entry Point
-----------

.. autofunction:: aita_core.admin.admin_page

.. autofunction:: aita_core.admin.admin_dashboard

Authentication
--------------

.. autofunction:: aita_core.admin.check_admin_auth

.. autofunction:: aita_core.admin.admin_login

Course Settings
---------------

.. autofunction:: aita_core.admin.admin_settings

The Course Settings tab provides a form to edit all ``CourseConfig`` fields
at runtime. Changes are saved to ``config_overrides.json`` in the data
directory and take effect immediately (except embedding/chunk settings which
require re-ingestion).

Editable settings are organized into sections:

- **Course Identity** — name, short name, description
- **System Prompt** — the full LLM system prompt
- **LLM Settings** — model, temperature, retrieval_k, chunk size, embedding model
- **Textbook** — URL and chapter-to-week mapping
- **Week Schedule** — topics per week (JSON editor)
- **Content Mappings** — HW/topic/lab/study guide to week (JSON editors)
- **Example Prompts** — clickable prompts per week (JSON editor)

Dashboard Tabs
--------------

**Interaction History**
   Browse all student-chatbot interactions. Filter by student ID.
   Each entry shows the question, response, sources, and rating.

**Feedback**
   View student feedback with linked Q&A context. Shows positive/negative
   ratings and comments.

**Feature Requests**
   Manage student feature requests. Update status:
   ``open`` → ``in_progress`` → ``done`` / ``wontfix``.

**Course Settings**
   Edit course configuration at runtime. See above.
