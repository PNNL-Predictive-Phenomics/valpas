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

__all__ = [
    'autoencoder',
    'confidence_evaluation',
    # 'valpas_core',
    # 'io',
    'AnnotationList',
    'AnalysisResults',
    'AssociationResult',
    'Omic',
    'OmicMeasurement',
    'SingleExperiment',
    'CrossExperiment'
    ]


from importlib import import_module as _import_module


# Resolve the existing public API only when requested. Importing a lightweight
# subpackage must not import analysis/training code or alter warning filters.
_LAZY_EXPORTS = {
    'autoencoder': ('._core.autoencoder', None),
    'confidence_evaluation': ('.confidence_evaluation', None),
    'AnnotationList': ('._core.classes.annotations', 'AnnotationList'),
    'AnalysisResults': ('._core.classes.results', 'AnalysisResults'),
    'AssociationResult': ('._core.classes.results', 'AssociationResult'),
    'Omic': ('._core.classes.omics', 'Omic'),
    'OmicMeasurement': ('._core.classes.omics', 'OmicMeasurement'),
    'SingleExperiment': ('._core.classes.experiments', 'SingleExperiment'),
    'CrossExperiment': ('._core.classes.experiments', 'CrossExperiment'),
}


def __getattr__(name):
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute = _LAZY_EXPORTS[name]
    module = _import_module(module_name, __name__)
    value = module if attribute is None else getattr(module, attribute)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(__all__))

from ._version import __version__
from ._version import __version_tuple__
