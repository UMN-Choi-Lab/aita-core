``aita_core.ingest`` — Document Ingestion
==========================================

The ingestion module processes course materials into a searchable FAISS
vector index.

Pipeline Runner
---------------

.. autofunction:: aita_core.ingest.run_ingestion

Default Collectors
------------------

These collectors work with the standard directory layout:

.. autofunction:: aita_core.ingest.collect_handouts

.. autofunction:: aita_core.ingest.collect_homework

.. autofunction:: aita_core.ingest.collect_slides

.. autofunction:: aita_core.ingest.collect_syllabus

.. autofunction:: aita_core.ingest.collect_wikibook

Document Loaders
----------------

.. autofunction:: aita_core.ingest.load_pdf

.. autofunction:: aita_core.ingest.load_tex

.. autofunction:: aita_core.ingest.load_wikibook_page

.. autofunction:: aita_core.ingest.clean_pdf_text

Text Chunking
-------------

.. autofunction:: aita_core.ingest.chunk_documents

.. autofunction:: aita_core.ingest.chunk_text

Embedding & Indexing
--------------------

.. autofunction:: aita_core.ingest.get_embeddings

.. autofunction:: aita_core.ingest.build_faiss_index

.. autofunction:: aita_core.ingest.save_index

Week Assignment
---------------

.. autofunction:: aita_core.ingest.get_week_for_filename

Custom Collectors
-----------------

If your course materials don't follow the standard directory layout, write
custom collector functions and pass them to ``run_ingestion()``:

.. code-block:: python

   def my_collect_handouts(config):
       \"\"\"Collect handout PDFs from a custom location.\"\"\"
       docs = []
       handout_dir = os.path.join(config.course_materials_dir, "my_handouts")
       for pdf in sorted(os.listdir(handout_dir)):
           if not pdf.endswith(".pdf"):
               continue
           path = os.path.join(handout_dir, pdf)
           week = get_week_for_filename(
               pdf, config.topic_num_to_week, config.hw_num_to_week,
               config.lab_num_to_week, config.study_guide_to_week,
           )
           docs.extend(load_pdf(path, f"Handout: {pdf}", max_week=week))
       return docs

   run_ingestion(CONFIG, collectors=[
       ("handouts", my_collect_handouts),
       ("syllabus", collect_syllabus),
   ])

Each collector function receives the ``CourseConfig`` and returns a list of
document dicts with the structure:

.. code-block:: python

   {
       "text": "The full text content...",
       "metadata": {
           "source": "/path/to/file.pdf",      # or URL
           "source_label": "Handout: Topic.pdf", # display label
           "max_week": 3,                        # week availability
       }
   }
