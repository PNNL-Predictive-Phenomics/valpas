from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from valpas._core.classes.results import (
        AnalysisResults,
        AssociationResult,
    )
    from valpas._core.classes.omics import (
        Omic,
        OmicMeasurement,
    )
    from valpas._core.classes.experiments import (
        Experiment,
        CrossExperiment,
        SingleExperiment,
    )