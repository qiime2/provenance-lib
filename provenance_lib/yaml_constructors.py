from typing import List, Union

# NoProvenance = collections.namedtuple('NoProvenance', ['uuid'])
# MetadataPath = collections.namedtuple('MetadataPath', ['path'])
# ColorPrimitive = collections.namedtuple('ColorPrimitive', ['hex'])
# LiteralString = collections.namedtuple('LiteralString', ['string'])


def citation_key_constructor(loader, node) -> str:
    """
    A constructor for !cite yaml tags, returning a bibtex key as a str.
    All we need for now is a key string we can match in citations.bib,
    so _we're not parsing these into component substrings_.

    If that need arises in future, these are spec'ed in provenance.py as:

    <domain>|<package>:<version>|<optional_identifier>|<index>

    and frequently look like this (note no identifier):

    framework|qiime2:2020.6.0.dev0|0
    """
    value = loader.construct_scalar(node)
    return value


def metadata_path_constructor(loader, node):
    """
    A constructor for !metadata yaml tags, this docstring still TODO
    """
    # TODO: NEXT - do we need more from this than a simple str? If so, what?
    # TODO: NEXT - test this
    value = loader.construct_scalar(node)
    return value


def ref_constructor(loader, node) -> Union[str, List[str]]:
    """
    A constructor for !ref yaml tags. These tags describe yaml values that
    reference other namespaces within the document, using colons to separate
    namespaces. For example:

    !ref 'environment:plugins:sample-classifier'

    At present, ForwardRef tags are only used in the framework to 'link' the
    plugin name to the plugin version and other details in the 'execution'
    namespace of action.yaml

    This constructor explicitly handles this type of !ref by extracting and
    returning the plugin name to simplify parsing, while supporting the return
    of a generic list of 'keys' (e.g. ['environment', 'framework', 'version'])
    in the event ForwardRef is used more broadly in future.
    """
    value = loader.construct_scalar(node)
    keys = value.split(':')
    if keys[0:2] == ['environment', 'plugins']:
        plugin_name = keys[2]
        return plugin_name
    else:
        return keys
