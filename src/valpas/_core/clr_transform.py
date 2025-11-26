import pandas as pd
import numpy as np
from typing import Union
from scipy.stats import zscore
import warnings
warnings.filterwarnings('ignore')

def clr_transform(
    similarity_matrix: Union[pd.DataFrame, np.ndarray],
    method: str = 'harmonic',
    handle_diagonal: str = 'exclude',
    min_observations: int = 3,
    return_components: bool = False,
    verbose: bool = False
) -> Union[pd.DataFrame, dict]:
    """
    Transform similarity matrix using Z-scores based on harmonic mean of row and column Z-scores
    Following the CLR (Context Likelihood of Relatedness) method (Faith, et al. 2006)

    Args:
        similarity_matrix: Square similarity matrix (DataFrame or numpy array)
        method: Method for combining Z-scores ('harmonic', 'arithmetic', 'geometric')
        handle_diagonal: How to handle diagonal values ('exclude', 'include', 'zero')
        min_observations: Minimum number of observations needed to calculate Z-score
        return_components: Whether to return individual row/column Z-scores
        verbose: Whether to print out messages

    Returns:
        Transformed similarity matrix (DataFrame) or dict with components if return_components=True
    """

    # Convert to DataFrame if numpy array
    if isinstance(similarity_matrix, np.ndarray):
        n = similarity_matrix.shape[0]
        index_names = [f'Entity_{i}' for i in range(n)]
        similarity_df = pd.DataFrame(similarity_matrix, index=index_names, columns=index_names)
    else:
        similarity_df = similarity_matrix.copy()

    n_entities = len(similarity_df)

    # Validate input
    if similarity_df.shape[0] != similarity_df.shape[1]:
        raise ValueError("Similarity matrix must be square")

    if n_entities < min_observations:
        raise ValueError(f"Matrix too small. Need at least {min_observations} entities")

    # Initialize output matrices
    row_zscores = pd.DataFrame(
        np.zeros_like(similarity_df.values),
        index=similarity_df.index,
        columns=similarity_df.columns
    )

    col_zscores = pd.DataFrame(
        np.zeros_like(similarity_df.values),
        index=similarity_df.index,
        columns=similarity_df.columns
    )

    transformed_matrix = pd.DataFrame(
        np.zeros_like(similarity_df.values),
        index=similarity_df.index,
        columns=similarity_df.columns
    )

    # Calculate row-wise Z-scores
    if verbose:
        print("Calculating row-wise Z-scores...")

    for i, row_name in enumerate(similarity_df.index):
        row_similarities = similarity_df.iloc[i].values.copy()

        # Handle diagonal based on method
        if handle_diagonal == 'exclude':
            # Exclude diagonal value from Z-score calculation
            non_diagonal_mask = np.arange(len(row_similarities)) != i
            values_for_zscore = row_similarities[non_diagonal_mask]

            if len(values_for_zscore) >= min_observations:
                # Calculate Z-scores for non-diagonal values
                row_z = zscore(values_for_zscore, nan_policy='omit')

                # Map back to full array
                full_row_z = np.zeros(len(row_similarities))
                full_row_z[non_diagonal_mask] = row_z
                full_row_z[i] = 0  # Set diagonal to 0

                row_zscores.iloc[i] = full_row_z
            else:
                row_zscores.iloc[i] = 0

        elif handle_diagonal == 'zero':
            # Set diagonal to 0 before calculating Z-scores
            row_similarities[i] = 0
            if len(row_similarities) >= min_observations:
                row_zscores.iloc[i] = zscore(row_similarities, nan_policy='omit')
            else:
                row_zscores.iloc[i] = 0

        else:  # include diagonal
            if len(row_similarities) >= min_observations:
                row_zscores.iloc[i] = zscore(row_similarities, nan_policy='omit')
            else:
                row_zscores.iloc[i] = 0

    # Calculate column-wise Z-scores
    if verbose:
        print("Calculating column-wise Z-scores...")

    for j, col_name in enumerate(similarity_df.columns):
        col_similarities = similarity_df.iloc[:, j].values.copy()

        # Handle diagonal based on method
        if handle_diagonal == 'exclude':
            # Exclude diagonal value from Z-score calculation
            non_diagonal_mask = np.arange(len(col_similarities)) != j
            values_for_zscore = col_similarities[non_diagonal_mask]

            if len(values_for_zscore) >= min_observations:
                # Calculate Z-scores for non-diagonal values
                col_z = zscore(values_for_zscore, nan_policy='omit')

                # Map back to full array
                full_col_z = np.zeros(len(col_similarities))
                full_col_z[non_diagonal_mask] = col_z
                full_col_z[j] = 0  # Set diagonal to 0

                col_zscores.iloc[:, j] = full_col_z
            else:
                col_zscores.iloc[:, j] = 0

        elif handle_diagonal == 'zero':
            # Set diagonal to 0 before calculating Z-scores
            col_similarities[j] = 0
            if len(col_similarities) >= min_observations:
                col_zscores.iloc[:, j] = zscore(col_similarities, nan_policy='omit')
            else:
                col_zscores.iloc[:, j] = 0

        else:  # include diagonal
            if len(col_similarities) >= min_observations:
                col_zscores.iloc[:, j] = zscore(col_similarities, nan_policy='omit')
            else:
                col_zscores.iloc[:, j] = 0

    # Combine row and column Z-scores
    if verbose:
        print(f"Combining Z-scores using {method} mean...")

    for i in range(n_entities):
        for j in range(n_entities):
            row_z = row_zscores.iloc[i, j]
            col_z = col_zscores.iloc[i, j]

            # Handle NaN values
            if np.isnan(row_z) or np.isnan(col_z):
                transformed_matrix.iloc[i, j] = 0
                continue

            # Calculate combined Z-score based on method
            if method == 'harmonic':
                # Harmonic mean of absolute Z-scores, preserving sign
                abs_row_z = abs(row_z)
                abs_col_z = abs(col_z)

                if abs_row_z == 0 and abs_col_z == 0:
                    combined_z = 0
                elif abs_row_z == 0 or abs_col_z == 0:
                    combined_z = 0  # Harmonic mean is 0 if any component is 0
                else:
                    harmonic_mean = 2 * abs_row_z * abs_col_z / (abs_row_z + abs_col_z)
                    # Preserve sign based on average sign
                    sign = np.sign((row_z + col_z) / 2)
                    combined_z = sign * harmonic_mean

            elif method == 'arithmetic':
                combined_z = (row_z + col_z) / 2

            elif method == 'geometric':
                # Geometric mean of absolute values, preserving sign
                abs_row_z = abs(row_z)
                abs_col_z = abs(col_z)

                if abs_row_z == 0 or abs_col_z == 0:
                    combined_z = 0
                else:
                    geometric_mean = np.sqrt(abs_row_z * abs_col_z)
                    sign = np.sign((row_z + col_z) / 2)
                    combined_z = sign * geometric_mean

            else:
                raise ValueError("Method must be 'harmonic', 'arithmetic', or 'geometric'")

            transformed_matrix.iloc[i, j] = combined_z

    # Handle diagonal values in final matrix
    if handle_diagonal in ['exclude', 'zero']:
        np.fill_diagonal(transformed_matrix.values, 0)

    if return_components:
        return {
            'transformed_matrix': transformed_matrix,
            'row_zscores': row_zscores,
            'col_zscores': col_zscores,
            'original_matrix': similarity_df,
            'method': method,
            'handle_diagonal': handle_diagonal
        }

    return transformed_matrix
