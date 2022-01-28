# flake8: noqa
# coding: utf-8
"""
Right now, the framework seems to require that UsageOutputNames is passed an
arg for every output name.  I've hacked a change that makes that more
permissive, just by injecting a filler variable name ('_').  The idea is that
if a user doesn't pass an arg for an output, they don't care about that output.

This also opens the door for replay to do its thing without having to ask the
SDK action about its output names.
"""


from qiime2.sdk import PluginManager
from qiime2.plugins import ArtifactAPIUsage
from qiime2 import Artifact

PluginManager()
use = ArtifactAPIUsage()


def factory():
    return Artifact.load("/home/chris/Downloads/demux.qza")


demux = use.init_artifact('my_artifact', factory)


use.action(
     use.UsageAction(plugin_id='dada2', action_id='denoise_single'),
     use.UsageInputs(demultiplexed_seqs=demux, trim_left=0, trunc_len=120),
     use.UsageOutputNames(representative_sequences='rep_seqs',
                          table='table', denoising_stats='stats')
   )
use.action(
     use.UsageAction(plugin_id='dada2', action_id='denoise_single'),
     use.UsageInputs(demultiplexed_seqs=demux, trim_left=0, trunc_len=120),
     use.UsageOutputNames(representative_sequences='rep_seqs',
                          table='table')
   )

print(use.render())
