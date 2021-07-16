def is_root_provnode_data(fp):
    """
    a filter predicate which returns metadata, action, citation,
    and VERSION fps with which we can construct a ProvNode
    """
    return 'provenance' in fp and 'artifacts' not in fp and (
        'metadata.yaml' in fp or
        'action.yaml' in fp or
        'citations.bib' in fp or
        'VERSION')


class ReallyEqualMixin(object):
    """
    Mixin for testing implementations of __eq__/__ne__.

    Based on this public domain code (also explains why the mixin is useful):
    https://ludios.org/testing-your-eq-ne-cmp/
    """

    def assertReallyEqual(self, a, b):
        # assertEqual first, because it will have a good message if the
        # assertion fails.
        self.assertEqual(a, b)
        self.assertEqual(b, a)
        self.assertTrue(a == b)
        self.assertTrue(b == a)
        self.assertFalse(a != b)
        self.assertFalse(b != a)

    def assertReallyNotEqual(self, a, b):
        # assertNotEqual first, because it will have a good message if the
        # assertion fails.
        self.assertNotEqual(a, b)
        self.assertNotEqual(b, a)
        self.assertFalse(a == b)
        self.assertFalse(b == a)
        self.assertTrue(a != b)
        self.assertTrue(b != a)
