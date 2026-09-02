"""
Tests for PEP 563 (from __future__ import annotations) compatibility.

When user code has `from __future__ import annotations`, all annotations
are stored as strings at parse time.  The get_signature helper must use
eval_str=True so that registry lookups keyed on type objects still work.
"""
from __future__ import annotations

import unittest

from depi.services import ServiceCollection


class Config:
    def __init__(self):
        self.value = "test"


class ServiceWithStringAnnotations:
    """Constructor annotations are strings due to the module-level future import."""

    def __init__(self, config: Config):
        self.config = config


class TestPep563StringAnnotations(unittest.TestCase):
    def test_register_and_resolve_with_string_annotations(self):
        """A class whose __init__ uses string annotations registers and resolves."""
        collection = ServiceCollection()
        collection.add_singleton(Config)
        collection.add_singleton(ServiceWithStringAnnotations)
        provider = collection.build_provider()

        svc = provider.resolve(ServiceWithStringAnnotations)

        self.assertIsInstance(svc, ServiceWithStringAnnotations)
        self.assertIsInstance(svc.config, Config)
        self.assertEqual(svc.config.value, "test")

    def test_unresolvable_forward_ref_raises_name_error(self):
        """A genuinely unresolvable forward ref surfaces as a NameError, not silent skip."""
        from depi.services import get_signature

        class _BadAnnotations:
            def __init__(self, x: NonExistentType):  # noqa: F821
                pass

        # get_signature with eval_str=True must propagate NameError for unknown names
        with self.assertRaises(NameError):
            get_signature(_BadAnnotations)


if __name__ == "__main__":
    unittest.main()
