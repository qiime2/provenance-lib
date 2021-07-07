import unittest
import yaml

from ..yaml_constructors import (
    citation_key_constructor, metadata_path_constructor, ref_constructor)
yaml.SafeLoader.add_constructor('!cite', citation_key_constructor)
yaml.SafeLoader.add_constructor('!metadata', metadata_path_constructor)
yaml.SafeLoader.add_constructor('!ref', ref_constructor)


class CitationKeyConstrTests(unittest.TestCase):
    def test_citation_key_constructor(self):
        tag = r"!cite 'framework|qiime2:2020.6.0.dev0|0'"
        actual = yaml.safe_load(tag)
        print(actual)
        self.assertEqual(actual, 'framework|qiime2:2020.6.0.dev0|0')


class MetadataPathConstrTests(unittest.TestCase):
    pass


class ForwardRefConstrTests(unittest.TestCase):
    def test_action_plugin_ref(self):
        tag = r"plugin: !ref 'environment:plugins:diversity'"
        actual = yaml.safe_load(tag)
        self.assertEqual(actual, {'plugin': 'diversity'})

    def test_generic_ref(self):
        tag = r"plugin: !ref 'environment:framework:version'"
        actual = yaml.safe_load(tag)
        exp = {'plugin': ['environment', 'framework', 'version']}
        self.assertEqual(exp, actual)


class NoProvenanceConstrTests(unittest.TestCase):
    pass


class ColorPrimitiveConstrTests(unittest.TestCase):
    pass
