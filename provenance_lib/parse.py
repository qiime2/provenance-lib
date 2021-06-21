from __future__ import annotations
from typing import List, Dict

import yaml
import zipfile

from .archive_formats import FormatHandler, ProvNode, _ResultMetadata

# TODO: Move constructors into a separate module
# from yaml_constructors import (
#     metadata_constructor, citation_constructor, ref_constructor)


# TODO: The framework exposes many additional custom tags not yet handled
# here. Check qiime2/core/archive/provenance.py for everything
def citation_constructor(loader, node):
    value = loader.construct_scalar(node)
    return value


def ref_constructor(loader, node):
    value = loader.construct_scalar(node)
    environment, plugins, plugin_name = value.split(':')
    return plugin_name


def metadata_constructor(loader, node):
    value = loader.construct_scalar(node)
    return value


yaml.SafeLoader.add_constructor('!metadata', metadata_constructor)
yaml.SafeLoader.add_constructor('!cite', citation_constructor)
yaml.SafeLoader.add_constructor('!ref', ref_constructor)


class ProvDAG:
    """
    A single-rooted DAG of ProvNode objects, representing a single QIIME 2
    Archive.
    TODO: May also contain a non-hierarchical pool of unique ProvNodes?
    """
    _num_results: int
    _archv_contents: Dict[str, ProvNode]
    _archive_md: _ResultMetadata

    # TODO: Does this object even care about these version numbers?
    @property
    def archive_version(self):
        return self.handler.archive_version

    @property
    def framework_version(self):
        return self.handler.framework_version

    @property
    def root_uuid(self):
        return self._archive_md.uuid

    @property
    def root_node(self):
        return self.get_result(self.root_uuid)

    @property
    def archive_type(self):
        return self._archive_md.type

    @property
    def archive_format(self):
        return self._archive_md.format

    def get_result(self, uuid):
        return self._archv_contents[uuid]

    def _traverse_uuids_from_root(self):
        return self.root_node.traverse_uuids()

    def __str__(self):
        return repr(self._archive_md)

    def __repr__(self):
        # Traverse DAG, printing UUIDs
        # TODO: Improve this repr to remove id duplication
        r_str = self.__str__() + "\nContains Results:\n"
        uuid_yaml = yaml.dump(self._traverse_uuids_from_root())
        r_str += uuid_yaml
        return r_str

    def __init__(self, archive_fp: str):
        self._archive_md: None
        self._archv_contents: None
        self._num_results = 0

        with zipfile.ZipFile(archive_fp) as zf:
            self.handler = FormatHandler(zf)
            self._archive_md, (self._num_results, self._archv_contents) = \
                self.handler.parse(zf, archive_fp)


class UnionedDAG:
    """
    a many-rooted DAG of ProvNode objects, created from a Union of ProvDAGs
    """

    # TODO: Implement
    def __init__(self, dags: List[ProvDAG]):
        self.root_uuids = [dag.root_uuid for dag in dags]
        self.root_nodes = [dag.root_node for dag in dags]
