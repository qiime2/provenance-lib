import numpy as np
import biom
from qiime2 import Artifact

empty_table = biom.Table(np.array([]), [], [])
empty_table = Artifact.import_data('FeatureTable[Frequency]', empty_table)
empty_table.save('table')
