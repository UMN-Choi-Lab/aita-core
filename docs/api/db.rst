``aita_core.db`` — Database
===========================

SQLite database for interaction logs, student feedback, and feature requests.
The database auto-initializes tables on first connection.

Connection
----------

.. autofunction:: aita_core.db.get_conn

Interactions
------------

.. autofunction:: aita_core.db.log_interaction

.. autofunction:: aita_core.db.get_interactions

.. autofunction:: aita_core.db.count_interactions

.. autofunction:: aita_core.db.rate_interaction

Feedback
--------

.. autofunction:: aita_core.db.add_feedback

.. autofunction:: aita_core.db.get_feedback

Feature Requests
----------------

.. autofunction:: aita_core.db.add_feature_request

.. autofunction:: aita_core.db.get_feature_requests

.. autofunction:: aita_core.db.update_feature_request_status

Analytics
---------

.. autofunction:: aita_core.db.get_interaction_stats

Database Schema
---------------

.. code-block:: sql

   CREATE TABLE interactions (
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       timestamp TEXT NOT NULL,
       student_id TEXT NOT NULL,
       week INTEGER NOT NULL,
       question TEXT NOT NULL,
       response TEXT NOT NULL,
       sources TEXT,
       rating INTEGER
   );

   CREATE TABLE feedback (
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       timestamp TEXT NOT NULL,
       student_id TEXT NOT NULL,
       interaction_id INTEGER REFERENCES interactions(id),
       rating INTEGER,
       comment TEXT
   );

   CREATE TABLE feature_requests (
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       timestamp TEXT NOT NULL,
       student_id TEXT NOT NULL,
       title TEXT NOT NULL,
       description TEXT,
       status TEXT DEFAULT 'open'
   );
