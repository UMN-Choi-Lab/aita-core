``aita_core.rag`` — RAG Pipeline
=================================

The RAG (Retrieval-Augmented Generation) pipeline handles the complete flow
from user query to LLM response.

Pipeline Functions
------------------

.. autofunction:: aita_core.rag.chat

.. autofunction:: aita_core.rag.retrieve

.. autofunction:: aita_core.rag.build_messages

.. autofunction:: aita_core.rag.build_system_prompt

Homework Injection
------------------

.. autofunction:: aita_core.rag._inject_current_hw

When a student asks about "homework", "hw", or "assignment", the system checks
if the current week's homework is already in the retrieved chunks. If not, it
scans the full chunk index and injects the first matching chunk at the top of
the context. This ensures the LLM always has the relevant homework content when
answering homework-related questions.

Week-Aware System Prompt
-------------------------

The system prompt is dynamically built based on the current week:

.. autodata:: aita_core.rag.FUTURE_TOPIC_INSTRUCTION

The prompt includes:

- Current week number
- Current homework assignment name
- List of topics covered so far
- List of topics not yet covered
- Instructions to redirect questions about future topics

Internal Functions
------------------

.. autofunction:: aita_core.rag._get_client

.. autofunction:: aita_core.rag._load_index
