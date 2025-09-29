"""
VaLPAS (Variation-Leveraged Phenomic Assoccioation Study) is a toolkit
with the ultimate purpose to iluminate the biological dark matter by
providing a systemic framework to predict protein functionality from
phenomics. VaLPAS uses phenotypic variation between organisms as well as
various modes of omics-data (e.g. Proteomics, Metabolomics,
Transcriptomics, etc.) collected under differing environmental
conditions. The toolkit generates associations between the different
datatypes that then can be leveraged to postulate hypothesis of protein
functionality for proteins of previously unknown function.
"""

from ._core.classes.omics import (
    Omic,
    OmicMeasurement,
    )
from ._core.classes.results import (
    AssociationResult,
)
from ._core.classes.experiments import (
    SingleExperiment,
    CrossExperiment,
)
from ._core import autoencoder

__all__ = [
    'utils',
    'visualization',
    'io',
    'confidence_evaluation'
    'autoencoder',
    'AssociationResult',
    'Omic',
    'OmicMeasurement',
    'SingleExperiment',
    'CrossExperiment',
    ]
