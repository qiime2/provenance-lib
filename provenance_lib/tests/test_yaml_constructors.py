import unittest
import warnings
import yaml

from ..yaml_constructors import (
    citation_key_constructor, metadata_path_constructor, ref_constructor,
    set_constructor, color_constructor, no_provenance_constructor,
    )
yaml.SafeLoader.add_constructor('!color', color_constructor)
yaml.SafeLoader.add_constructor('!cite', citation_key_constructor)
yaml.SafeLoader.add_constructor('!metadata', metadata_path_constructor)
yaml.SafeLoader.add_constructor('!no-provenance', no_provenance_constructor)
yaml.SafeLoader.add_constructor('!ref', ref_constructor)
yaml.SafeLoader.add_constructor('!set', set_constructor)


class UnknownConstrTests(unittest.TestCase):
    """
    Makes explicit the current handling of unimplemented custom tags
    In future, we may want to deal with these more graciously (e.g. warn), but
    for now we're going to fail fast

    TODO: This isn't actually coupled to the behavior of safe_load in the code
    Though it's a nice idea, it's not functional as implemented
    """
    def test_unknown_tag(self):
        tag = r"!foo 'this is not an implemented tag'"
        with self.assertRaisesRegex(yaml.constructor.ConstructorError,
                                    'could not determine a constructor.*!foo'):
            yaml.safe_load(tag)


class CitationKeyConstrTests(unittest.TestCase):
    def test_citation_key_constructor(self):
        tag = r"!cite 'framework|qiime2:2020.6.0.dev0|0'"
        actual = yaml.safe_load(tag)
        self.assertEqual(actual, 'framework|qiime2:2020.6.0.dev0|0')


class ColorPrimitiveConstrTests(unittest.TestCase):
    # TODO: I have no idea what ColorPrimitives are. Is this constructor
    # reasonable?
    def test_citation_key_constructor(self):
        tag = r"!color '#57f289'"
        actual = yaml.safe_load(tag)
        self.assertEqual(actual, '#57f289')


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


class MetadataPathConstrTests(unittest.TestCase):
    def test_metadata_path_constructor(self):
        tag = r"!metadata 'metadata.tsv'"
        actual = yaml.safe_load(tag)
        self.assertEqual(actual, {'input_artifact_uuids': [],
                                  'relative_fp': 'metadata.tsv'})

    def test_metadata_path_constructor_Artifact_as_md(self):
        tag = r"!metadata '415409a4-stuff-e3eaba5301b4:feature_metadata.tsv'"
        actual = yaml.safe_load(tag)
        self.assertEqual(
            actual,
            {'input_artifact_uuids': ['415409a4-stuff-e3eaba5301b4'],
             'relative_fp': 'feature_metadata.tsv'}
             )

    def test_metadata_path_constructor_Artifacts_as_md(self):
        tag = (r"!metadata '415409a4-stuff-e3eaba5301b4,"
               r"12345-other-stuff-67890"
               r":feature_metadata.tsv'")
        actual = yaml.safe_load(tag)
        self.assertEqual(
            actual,
            {'input_artifact_uuids': ['415409a4-stuff-e3eaba5301b4',
                                      '12345-other-stuff-67890'],
             'relative_fp': 'feature_metadata.tsv'}
             )


class NoProvenanceConstrTests(unittest.TestCase):
    def test_no_provenance_constructor(self):
        tag = "!no-provenance '34b07e56-27a5-4f03-ae57-ff427b50aaa1'"
        with self.assertWarnsRegex(UserWarning,
                                   'Artifact 34b07e.*prior to provenance'):
            actual = yaml.safe_load(tag)
            self.assertEqual(actual, '34b07e56-27a5-4f03-ae57-ff427b50aaa1')

    def test_multiple_warnings_fire(self):
        tag_list = """
        - !no-provenance '34b07e56-27a5-4f03-ae57-ff427b50aaa1'
        - !no-provenance 'gerbil'
        """
        with warnings.catch_warnings(record=True) as w:
            # Just in case something else has modified the filter state
            warnings.simplefilter("default")
            yaml.safe_load(tag_list)
            # There should be exactly two warnings
            self.assertEqual(len(w), 2)

            # The first should be a Userwarnign containing these strings
            self.assertEqual(UserWarning, w[0].category)
            self.assertIn('Artifact 34b07e', str(w[0].message))
            self.assertIn('prior to provenance', str(w[0].message))

            # And the second should look similar
            self.assertEqual(UserWarning, w[1].category)
            self.assertIn('gerbil', str(w[1].message))
            self.assertIn('prior to provenance', str(w[0].message))


class SetRefConstrTests(unittest.TestCase):
    """
    Tests for the !set tag constructor.
    """
    def test_set_ref(self):
        flow_tag = r"!set ['foo', 'bar', 'baz']"
        flow = yaml.safe_load(flow_tag)
        self.assertEqual(flow, {'foo', 'bar', 'baz'})

        # NOTE: we don't expect duplicate values here (because dumped values
        # were a set), but it doesn't hurt to test the behavior
        block_tag = '!set\n- spam\n- egg\n- spam\n'
        block = yaml.safe_load(block_tag)
        self.assertEqual(block, {'spam', 'egg'})
