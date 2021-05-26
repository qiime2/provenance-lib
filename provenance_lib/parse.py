import codecs
import pathlib
import re
from typing import List, Dict

import bibtexparser as bp
import yaml
import zipfile

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


class _Action:
    """ Provenance data for a single QIIME 2 Result from action.yaml """
    _action_details = None

    @property
    def action_id(self):
        """ the UUID assigned to this Action (not its Results) """
        return self._execution_details['uuid']

    @property
    def action_type(self):
        """ the type of Action represented (e.g. Method, Pipeline, etc. ) """
        return self._action_details['type']

    @property
    def action(self):
        """ the action executed by this Action """
        return self._action_details['action']

    @property
    def plugin(self):
        """ the plugin which executed this Action """
        return self._action_details['plugin']

    @property
    def inputs(self):
        """
        a list of single-item dicts containing the types and UUIDs of this
        action's inputs
        """
        return self._action_details['inputs']

    def __init__(self, zf: zipfile, fp: str):
        self._action_dict = yaml.safe_load(zf.read(fp))
        self._action_details = self._action_dict['action']
        self._execution_details = self._action_dict['execution']
        self._env_details = self._action_dict['environment']

    def __repr__(self):
        return (f"_Action(action_id={self.action_id}, type={self.action_type},"
                f" plugin={self.plugin}, action={self.action})")


class _ResultMetadata:
    """ Basic metadata about a single QIIME 2 Result from metadata.yaml """

    def __init__(self, zf: zipfile, md_fp: str):
        _md_dict = yaml.safe_load(zf.read(md_fp))
        self.uuid = _md_dict['uuid']
        self.type = _md_dict['type']
        self.format = _md_dict['format']

    def __repr__(self):
        return (f"_ResultMetadata(UUID: {self.uuid}, "
                f"Semantic Type: {self.type}, Format: {self.format})")


class _Citations:
    """
    citations for a single QIIME 2 Result, as a dict of dicts where each
    inner dictionary represents one citation keyed on the citation's bibtex ID
    """
    # TODO: What does the framework do with when 0 citations are registered?
    # Do we get an empty citations.bib? no citations.bib?
    # impossible because framework always cited?
    def __init__(self, zf: zipfile, fp: str):
        bib_db = bp.loads(zf.read(fp))
        self._citations = {entry['ID']: entry for entry in bib_db.entries}

    def __repr__(self):
        keys = [entry for entry in self._citations.keys()]
        return (f"Citations({keys})")


class ProvNode:
    """ One node of a provenance DAG, describing one QIIME 2 Result """
    _parents = None
    _origin_archives = []

    # NOTE: ProvNodes capture their "origin_archive" in a list when
    # initialized, and ProvNode.parents expects that origin_archive to be at
    # index 0. Union (and similar operations) should not interfere with this
    # convention.

    @property
    def parents(self):
        """ The list of ProvNodes used as inputs in creating this ProvNode """
        # NOTE: We must delay gathering parentage data until the Archive is
        # fully populated (or risk KeyError). Caching this lazily allows us to
        # delay until the first call (likely the first DAG traversal)
        if not self._parents:
            try:
                parent_dicts = [parent for parent in self._action.inputs]
                parent_uuids = [
                    list(uuid.values())[0] for uuid in parent_dicts]
                self._parents = [
                    self._origin_archives[0]._archive_contents[uuid]
                    for uuid in parent_uuids]
            except KeyError:
                pass
        return self._parents

    @property
    def uuid(self):
        return self._result_md.uuid

    @property
    def sem_type(self):
        return self._result_md.type

    @property
    def format(self):
        return self._result_md.format

    def __init__(self, origin_archive, zf: zipfile,
                 fps_for_this_result: List[pathlib.Path]):
        self._origin_archives.append(origin_archive)
        # TODO: Does VERSION effect what other things get read in?
        for fp in fps_for_this_result:
            # TODO: Should we be reading these zipfiles once here,
            # and then passing them to the constructors below?
            if fp.name == 'metadata.yaml':
                self._result_md = _ResultMetadata(zf, str(fp))
            elif fp.name == 'action.yaml':
                self._action = _Action(zf, str(fp))
            elif fp.name == 'citations.bib':
                self._citations = _Citations(zf, str(fp))

    def __repr__(self):
        return f'ProvNode({self.uuid}, {self.sem_type}, fmt={self.format})'

    def __str__(self):
        return f'ProvNode({self.uuid})'

    def __eq__(self, other):
        # TODO: Should this offer more robust validation?
        return self.uuid == other.uuid

    # TODO: Should this live in ProvDAG?
    def traverse_uuids(self):
        """ depth-first traversal of this ProvNode's ancestors """
        local_parents = dict()
        if not self.parents:
            local_parents = {self.uuid: None}
        else:
            sub_dag = dict()
            for parent in self.parents:
                sub_dag.update(parent.traverse_uuids())
            local_parents[self.uuid] = sub_dag
        return local_parents


class Archive:
    """
    Lightly-processed contents of a single QIIME 2 Archive, an Archive
    contains a non-hierarchical pool of unique ProvNodes
    """

    # TODO: Can we assume all Q2 archives contain only unique Results?
    # If not, Archive should filter duplicates.

    # TODO: Read and check VERSION # first
    # TODO: add property for archive version?
    # TODO: UUID class with basic validation?
    # NOTE: static type declarations like this break testing unless the class
    # is forward declared (ProvNode must be above Archive or NameError).
    _number_of_results: int
    _archive_contents: Dict[str, ProvNode]
    _archive_md: _ResultMetadata

    @property
    def root_uuid(self):
        return self._archive_md.uuid

    @property
    def archive_type(self):
        return self._archive_md.type

    @property
    def archive_format(self):
        return self._archive_md.format

    def get_result(self, uuid):
        return self._archive_contents[uuid]

    def __str__(self):
        return f"Archive(Root: {self.root_uuid})"

    def __repr__(self):
        r_str = (f"Archive(Root: {self.root_uuid}, Semantic Type: "
                 f"{self.archive_type}, Format: {self.archive_format})\n"
                 "Contains Results:\n")
        for uuid in self._archive_contents.keys():
            r_str += str(uuid)
            r_str += "\n"
        return r_str

    def __init__(self, archive_fp: str):
        self._archive_md: None
        self._archive_contents: None
        self._number_of_results = 0

        with zipfile.ZipFile(archive_fp) as zf:
            self._get_version_info(zf)
            self._get_root_metadata(zf, archive_fp)
            self._populate_archive(zf)

    def _get_version_info(self, zf: zipfile):
        """Parse Archive VERSION file"""
        # This very permissive RE allows 1 to 2-digit integer archive versions,
        # and any framework version string containing 1 or more non-newline
        # characters. The final `$` catches VERSION files with too many lines.
        # _VERSION_MATCHER = r"QIIME 2\narchive: [0-9]{1,2}\nframework: .+$"

        # This stricter version should match all framework versions to date,
        # handling both old semver and newer yyyy.mm?.patch strings,
        # and .dev variants. It blows a deprecation warning when decoding the
        # RE for later pretty-printing, but seems to work properly.
        # TODO: Test the RE directly
        _VERSION_MATCHER = (
            r"QIIME 2\n"
            r"archive: [0-9]{1,2}\n"
            r"framework: "
            r"(?:20[0-9]{2}|2)\.(?:[0-9]{1,2}|0)\.[0-9](?:\.dev[0-9]?)?$")
        _REPR_VERSION_MATCHER = codecs.decode(
            _VERSION_MATCHER, 'unicode-escape')

        # TODO: This copypasta should be factored out.
        # All files in zf start with root uuid, so we can grab it from any file
        version_fp = pathlib.Path(zf.namelist()[0]).parts[0] + '/VERSION'
        try:
            with zf.open(version_fp) as vfp:
                _read = str(vfp.read(), 'utf-8')
        except KeyError:
            raise ValueError(
                "Malformed Archive: VERSION file misplaced or nonexistent")

        if not re.match(_VERSION_MATCHER, _read):
            raise ValueError(
                "Malformed Archive: VERSION file out of spec\n\n"
                f"Should match this RE:\n{_REPR_VERSION_MATCHER}\n\n"
                f"Actually looks like:\n{_read}\n")

        _, self._archive_version, self._framework_version =\
            [line.strip() for line in _read.split(sep="\n") if line]

    def _get_root_metadata(self, zf: zipfile, archive_fp: str):
        """ Get archive metadata including root uuid """
        # All files in zf start with root uuid, so we can grab it from any file
        root_md_fp = pathlib.Path(zf.namelist()[0]).parts[0] + '/metadata.yaml'
        try:
            self._archive_md = _ResultMetadata(zf, root_md_fp)
        except KeyError:
            raise ValueError("Malformed Archive: "
                             "no top-level metadata.yaml file")

    def _populate_archive(self, zf: zipfile):
        """
        Populates an _Archive with all relevant provenance data
        Takes an Archive (as a zipfile) as input.

        By convention, the filepaths within these Archives begin with:
        <archive_root_uuid>/provenance/...
        archive-root provenance files live directly inside 'provenance'
        e.g: <archive_root_uuid>/provenance/metadata.yaml
        non-root provenance files live inside 'artifacts/<uuid>'
        e.g: <archive_root_uuid>/provenance/artifacts/<uuid>/metadata.yaml
        """
        self._archive_contents = {}

        filenames = ['metadata.yaml', 'action/action.yaml', 'citations.bib']
        prov_data_fps = [
            pathlib.Path(fp) for fp in zf.namelist()
            if 'provenance' in fp
            # and any of the filenames above show up in the filepath
            and any(map(lambda x: x in fp, filenames))
        ]

        # make a provnode for each UUID
        for fp in prov_data_fps:
            # if no 'artifacts' -> this is provenance for the archive root
            if 'artifacts' not in fp.parts:
                uuid = fp.parts[0]
                prefix = pathlib.Path(uuid) / 'provenance'
            else:
                uuid = self._get_nonroot_uuid(fp)
                prefix = pathlib.Path(*fp.parts[0:4])

            if uuid not in self._archive_contents:
                fps_for_this_result = [prefix / name for name in filenames]
                self._number_of_results += 1
                self._archive_contents[uuid] = ProvNode(self, zf,
                                                        fps_for_this_result)

    def _get_nonroot_uuid(self, fp: pathlib.Path):
        """
        For non-root provenance files, get the Result's uuid from the path
        (avoiding the root Result's UUID which is in all paths)
        """
        if fp.name == 'action.yaml':
            uuid = fp.parts[-3]
        else:
            uuid = fp.parts[-2]
        return uuid


class ProvDAG:
    """
    a single-rooted DAG of ProvNode objects.
    """

    def __init__(self, archive: Archive):
        self.root_uuid = archive.root_uuid
        self.root = archive.get_result(self.root_uuid)

    def __repr__(self):
        # Traverse DAG, printing UUIDs
        # TODO: Improve this repr to remove duplication?
        uuid_yaml = yaml.dump(self.traverse_uuids_from_root())
        return f"Root:\n{uuid_yaml}"

    def __str__(self):
        return f"ProvDAG(Root: {self.root_uuid})"

    def traverse_uuids_from_root(self):
        return self.root.traverse_uuids()


class UnionedDAG:
    """
    a many-rooted DAG of ProvNode objects, created from a Union of ProvDAGs
    """

    # TODO: Implement
    def __init__(self, dags: List[ProvDAG]):
        self.root_uuids = [dag.root_uuid for dag in dags]
        self.root_nodes = [dag.root for dag in dags]
