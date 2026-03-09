``aita_core.config`` — Configuration
=====================================

The configuration module defines the ``CourseConfig`` dataclass and provides
global config management via ``set_config()`` / ``get_config()``.

.. automodule:: aita_core.config
   :members:
   :undoc-members:
   :show-inheritance:

Constants
---------

.. py:data:: INT_KEY_DICT_FIELDS
   :type: frozenset

   Set of field names whose dict keys are integers (need conversion when
   serializing to/from JSON).

.. py:data:: EDITABLE_FIELDS
   :type: list[str]

   List of ``CourseConfig`` field names that can be edited via the admin panel
   and saved as JSON overrides.
