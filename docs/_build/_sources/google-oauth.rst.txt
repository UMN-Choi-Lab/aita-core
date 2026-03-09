Google OAuth Setup
==================

Google OAuth restricts login to ``@umn.edu`` accounts (or any Google Workspace
domain). If not configured, the app falls back to a simple student ID text input.

Setup Steps
-----------

1. Create a project in `Google Cloud Console <https://console.cloud.google.com/>`_

2. Enable the **Google+ API** (or People API)

3. Go to **APIs & Services** → **Credentials** → **Create Credentials** →
   **OAuth 2.0 Client ID**

4. Select **Web application** as the application type

5. Under **Authorized redirect URIs**, add your server URL:

   .. code-block:: text

      http://your-server:8501

   Include the port if you're not using standard HTTP/HTTPS ports.

6. Download the client secret JSON file and place it in your project root.
   The filename must start with ``client_secret`` and end with ``.json``:

   .. code-block:: text

      client_secret_943166...apps.googleusercontent.com.json

7. Set environment variables in ``.env``:

   .. code-block:: bash

      GOOGLE_COOKIE_KEY=a-random-secret-string-for-jwt
      GOOGLE_REDIRECT_URI=http://your-server:8501

How It Works
------------

The OAuth flow uses **PKCE** (Proof Key for Code Exchange) via
``google_auth_oauthlib``:

1. User clicks "Sign in with Google"
2. Redirected to Google's consent screen
3. Google redirects back with an authorization code
4. aita-core exchanges the code for user info (name, email)
5. Email domain is checked (must be ``@umn.edu``)
6. A JWT cookie is set for persistent login across sessions

The PKCE code verifier is stored in ``oauth_store.py`` at the module level,
which persists across Streamlit reruns (unlike ``st.session_state`` which is
per-session).

Domain Restriction
------------------

By default, only ``@umn.edu`` email addresses are accepted. To change this,
you would need to modify the domain check in ``aita_core/app.py``:

.. code-block:: python

   if not email.endswith("@umn.edu"):
       st.error("Please sign in with your @umn.edu account.")

Troubleshooting
---------------

**"Authentication failed: Bad Request"**
   The authorization code was likely used twice (Streamlit rerun). This is
   handled by the dedup guard in the OAuth flow. Clear cookies and try again.

**"invalid_grant: Bad Request"**
   The PKCE code verifier was lost between the redirect and the callback.
   This can happen if the Streamlit server restarted. Try signing in again.

**Redirect URI mismatch**
   The URI in Google Cloud Console must exactly match ``GOOGLE_REDIRECT_URI``
   in your ``.env``, including the protocol (http/https) and port number.

**Falls back to student ID login**
   All three must be present: client secret file, ``GOOGLE_COOKIE_KEY``, and
   ``GOOGLE_REDIRECT_URI``. Check that all are set correctly.
