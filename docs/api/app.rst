``aita_core.app`` — Streamlit Application
==========================================

The main Streamlit application with login, chat, and page routing.

Entry Point
-----------

.. autofunction:: aita_core.app.main

Pages
-----

.. autofunction:: aita_core.app.login_page

.. autofunction:: aita_core.app.chat_page

Authentication Helpers
----------------------

.. autofunction:: aita_core.app.resolve_file_path

The app uses JWT cookies for persistent authentication across browser sessions.
When Google OAuth is enabled, the login page shows a "Sign in with Google"
button that initiates the PKCE OAuth flow. When disabled, it falls back to a
simple student ID text input.

Chat Page Features
------------------

- **Multi-turn conversation** with full chat history
- **Source citations** with expandable section showing referenced materials
- **PDF downloads** for local course documents
- **Clickable links** for web-based sources (e.g., Wikibook chapters)
- **Example prompt buttons** shown when chat is empty (configurable per week)
- **Week selector** in sidebar for testing week-aware behavior

Sidebar Widgets
---------------

- **Current Week slider** — controls which week the assistant treats as current
- **Topics covered / not yet covered** — expandable lists
- **Feedback form** — students can submit positive/negative feedback
- **Feature request form** — students can suggest improvements
- **Admin Panel** button — navigates to the admin dashboard
- **Sign Out** button — clears session and auth cookie
