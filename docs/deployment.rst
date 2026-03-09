Deployment
==========

Docker is the recommended way to deploy AITA in production.

Dockerfile
----------

.. code-block:: dockerfile

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
   RUN echo '[server]\nheadless = true\nport = 8501\nenableCORS = false\n\
   enableXsrfProtection = false\n\n[browser]\ngatherUsageStats = false' \
   > /root/.streamlit/config.toml

   EXPOSE 8501
   ENTRYPOINT ["streamlit", "run", "main.py", \
               "--server.port=8501", "--server.address=0.0.0.0"]

docker-compose.yml
------------------

.. code-block:: yaml

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

The volume mount ensures the SQLite database (interaction logs, feedback) and
config overrides persist across container rebuilds.

Build and Run
-------------

.. code-block:: bash

   # Build the image
   docker compose build

   # Start in background
   docker compose up -d

   # View logs
   docker compose logs -f

   # Rebuild after changes
   docker compose build --no-cache
   docker compose up -d

Custom Port
-----------

To expose on a different port (e.g., 30002):

.. code-block:: yaml

   services:
     aita:
       build: .
       ports:
         - "30002:8501"

Then set ``GOOGLE_REDIRECT_URI=http://your-server:30002`` in ``.env`` and
update the redirect URI in Google Cloud Console.

Data Persistence
----------------

The ``/app/data`` volume stores:

- ``aita.db`` — SQLite database with interaction logs, feedback, and feature requests
- ``config_overrides.json`` — Admin-modified course settings

Always mount this as a Docker volume to preserve data across rebuilds.

Updating aita-core
------------------

To update the core package inside Docker:

1. Update ``requirements.txt`` to the new version (e.g., ``aita-core>=0.4.0``)
2. Rebuild: ``docker compose build --no-cache``
3. Restart: ``docker compose up -d``

Cost Estimate
-------------

Using GPT-4o-mini (default), estimated cost is **under $20/semester** for a
class of 80 students with heavy usage. See
`OpenAI pricing <https://openai.com/api/pricing/>`_ for current rates.
