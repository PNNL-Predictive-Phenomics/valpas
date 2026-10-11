"""Tests for converting association matrices into sorted pair lists."""

import numpy as np
import pandas as pd

from valpas._core.processing import beautify_series


def test_beautify_series_drops_missing_pairs():
    """Pairs masked as NaN (diagonal, lower triangle) are not written out.

    pandas >= 3 no longer drops NaN in ``DataFrame.stack()``, which used to
    add self-pairs with empty values to sorted association lists.
    """
    rng = np.random.default_rng(0)
    data = pd.DataFrame(
        rng.uniform(1.0, 10.0, size=(8, 6)),
        columns=[f"P{i}" for i in range(6)],
    )
    values = data.corr()
    values.index.name = values.columns.name = "proteomics"
    masked = values.where(np.triu(np.ones(values.shape, dtype=bool), k=1))

    pairs = beautify_series(masked, value="pearson")

    # 6 features -> 6 * 5 / 2 unique pairs
    assert len(pairs) == 15
    assert not pairs["pearson"].isna().any()
    assert (pairs["proteomics_1"] != pairs["proteomics_2"]).all()
