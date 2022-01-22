# coding: utf-8
from qiime2.sdk import PluginManager
from qiime2 import Artifact
from q2cli.core.usage import CLIUsage

PluginManager()
use = CLIUsage()

def factory():
    return qiime2.Artifact.load("/home/chris/Downloads/demux.qza")

demux = use.init_artifact('my_artifact', factory)

use.action(
     use.UsageAction(plugin_id='dada2', action_id='denoise_single'),
     use.UsageInputs(demultiplexed_seqs=demux, trim_left=0, trunc_len=120),
     use.UsageOutputNames(representative_sequences='rep_seqs_0',
                          table='table_0', denoising_stats='stats_0')
   )

print(use.render())
use.action(
     use.UsageAction(plugin_id='dada2', action_id='denoise_single'),
     use.UsageInputs(demultiplexed_seqs=demux, trim_left=0, trunc_len=120),
     use.UsageOutputNames(representative_sequences='rep_seqs_1',
                          table='table_1')
   )
print(use.render())
"""
Renders the following:
qiime dada2 denoise-single \
  --i-demultiplexed-seqs my-artifact.qza \
  --p-trim-left 0 \
  --p-trunc-len 120 \
  --o-representative-sequences rep-seqs.qza \
  --o-table table.qza \
  --o-denoising-stats stats.qza
qiime dada2 denoise-single \
  --i-demultiplexed-seqs my-artifact.qza \
  --p-trim-left 0 \
  --p-trunc-len 120 \
  --o-representative-sequences rep-seqs-1.qza \
  --o-table table-1.qza

The second will fail. We're going to need to write a filler 
"""
