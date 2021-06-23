def is_provnode_data(fp):
    """
    a filter predicate which returns metadata, action, citation,
    and VERSION fps with which we can construct a ProvNode
    """
    return 'provenance' in fp and 'artifacts' not in fp and (
        'metadata.yaml' in fp or
        'action.yaml' in fp or
        'citations.bib' in fp)
