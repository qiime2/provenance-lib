qiime tools import \
  --type 'EMPSingleEndSequences' \
  --input-path <your data here> \
  --output-path emp-single-end-sequences-0.qza
# Replay attempts to represent metadata inputs accurately, but metadata .tsv
# files are merged automatically by some interfaces, rendering distinctions
# between file inputs invisible in provenance. We output the recorded
# metadata to disk to enable visual inspection.
# The following command may have received additional metadata .tsv files. To
# confirm you have covered your metadata needs adequately, review the
# original metadata, saved at 'recorded_metadata/demux_emp_single_0/'
qiime demux emp-single \
  --i-seqs emp-single-end-sequences-0.qza \
  --m-barcodes-file barcodes-0.tsv \
  --m-barcodes-column <column_name> \
  --p-no-rev-comp-barcodes \
  --p-no-rev-comp-mapping-barcodes \
  --o-per-sample-sequences per-sample-sequences-0.qza
qiime dada2 denoise-single \
  --i-demultiplexed-seqs per-sample-sequences-0.qza \
  --p-trunc-len 120 \
  --p-trim-left 0 \
  --p-max-ee 2.0 \
  --p-trunc-q 2 \
  --p-chimera-method consensus \
  --p-min-fold-parent-over-abundance 1.0 \
  --p-n-threads 1 \
  --p-n-reads-learn 1000000 \
  --p-hashed-feature-ids \
  --o-representative-sequences representative-sequences-0.qza \
  --o-table table-0.qza
qiime phylogeny align-to-tree-mafft-fasttree \
  --i-sequences representative-sequences-0.qza \
  --p-n-threads 1 \
  --p-mask-max-gap-frequency 1.0 \
  --p-mask-min-conservation 0.4 \
  --o-rooted-tree rooted-tree-0.qza
# The following command may have received additional metadata .tsv files. To
# confirm you have covered your metadata needs adequately, review the
# original metadata, saved at
# 'recorded_metadata/diversity_core_metrics_phylogenetic_0/'
qiime diversity core-metrics-phylogenetic \
  --i-table table-0.qza \
  --i-phylogeny rooted-tree-0.qza \
  --p-sampling-depth 1109 \
  --m-metadata-file metadata-0.tsv \
  # TODO: The following parameter name was not found in your current
  # QIIME 2 environment. This may occur when the plugin version you have
  # installed does not match the version used in the original analysis.
  # Please see the docs and correct the parameter name before running.
  --?-n-jobs 1 \
  --o-unweighted-unifrac-emperor unweighted-unifrac-emperor-0.qzv