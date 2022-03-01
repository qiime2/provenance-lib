# coding: utf-8
# flake8: noqa
from provenance_lib.parse import ProvDAG
from provenance_lib.replay import write_citations
write_citations(
    ProvDAG(
        "/home/chris/src/provenance_py/provenance_lib/tests/data/v5_uu_emperor.qzv"
    ),
    "./playtesting/cite_emperor.bib",
)
