"""
utility to bin continous variables and estimate mutual information based
on B-Spline binning.

See also:
- Daub CO, Steuer R, Selbig J, Kloska S. Estimating mutual information using B-spline functions--an improved similarity measure for analysing gene expression data. BMC Bioinformatics. 2004 Aug 31;5:118. doi: 10.1186/1471-2105-5-118. PMID: 15339346; PMCID: PMC516800.
"""

from scipy.interpolate import BSpline
import numpy as np

def bspline_bin(
        data: np.ndarray,
        bins: int=10,
        order: int=1
        ) -> np.ndarray:
    """
    
    """
    degree = order - 1
    n_knots = bins + order
    knots = range(0, n_knots, 1)
    bspline_min = knots[order] - 1
    bspline_max = knots[n_knots - order]

    data_t = _transform_data(
        data=data,
        bspline_min=bspline_min,
        bspline_max=bspline_max
        )

    design_matrix = BSpline.design_matrix(data_t, knots, degree).toarray()

    return design_matrix


def _transform_data(
        data: np.ndarray,
        bspline_min: int,
        bspline_max: int
        ) -> np.ndarray:
    """
    
    """
    x_transformed = (
        (data - min(data))
        * (bspline_max - bspline_min)
        / (max(data) - min(data))
        + bspline_min
    )

    return x_transformed


def mutual_information(
        x: np.ndarray,
        y: np.ndarray,
        bins: int=10,
        spline_order: int=1,
        min_def: int=0
    ) -> float:
    """
    
    """

    xy_defined = np.where(~np.isnan(x) & ~np.isnan(y))
    x_defined_vals = x[xy_defined]
    y_defined_vals = y[xy_defined]

    if(len(xy_defined)/len(x) < min_def):
        mi = np.nan
    else:
        x_bin_associations = bspline_bin(
            data=x_defined_vals,
            bins=bins,
            order=spline_order
        )
        y_bin_associations = bspline_bin(
            data=y_defined_vals,
            bins=bins,
            order=spline_order
        )
        p_x = np.sum(x_bin_associations, axis=0) / len(x_defined_vals)
        p_y = np.sum(y_bin_associations, axis=0) / len(y_defined_vals)
        p_x_y = (
            np.matmul(
                np.transpose(x_bin_associations),
                y_bin_associations
                ) / len(x)
            ).flatten('F')
        
        h_x = -np.nansum(p_x * np.log2(p_x))
        h_y = -np.nansum(p_y * np.log2(p_y))
        h_x_y = -np.nansum(p_x_y * np.log2(p_x_y))

        mi = h_x + h_y - h_x_y

    return mi
