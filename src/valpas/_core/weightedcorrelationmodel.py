"""
Weighted Correlation Model for VaLPAS

This module provides methods for learning optimal condition weights
for correlation-based association analysis. Supports both empirical
methods and neural network-based learning.
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Optional, Union
from sklearn.metrics import roc_auc_score, average_precision_score
from scipy.stats import pearsonr, spearmanr
from scipy.optimize import minimize
import warnings

# Optional torch import for neural network method
try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    warnings.warn("PyTorch not available. Neural network learning method will be disabled.")


class AnalysisResults:
    """
    Container for weighted correlation analysis results.
    """

    def __init__(
        self,
        correlation_matrix: pd.DataFrame,
        weights: Dict[str, float],
        training_history: Dict,
        metadata: Dict,
        training_metrics: Dict = None,
        validation_metrics: Dict = None
    ):
        self.correlation_matrix = correlation_matrix
        self.weights = weights
        self.training_history = training_history
        self.metadata = metadata
        self.training_metrics = training_metrics or {}
        self.validation_metrics = validation_metrics or {}
        self.analysis_type = "Weighted Correlation"

    def get_performance_assessment(self) -> str:
        """Assess overall model performance."""
        auc = self.validation_metrics.get('auc', self.training_metrics.get('auc', 0))
        if auc >= 0.9:
            return "Excellent"
        elif auc >= 0.8:
            return "Good"
        elif auc >= 0.7:
            return "Fair"
        elif auc >= 0.6:
            return "Poor"
        else:
            return "Very Poor"

    def get_top_conditions(self, n: int = 10) -> List[Tuple[str, float]]:
        """Get the top n most important conditions by weight."""
        sorted_weights = sorted(self.weights.items(), key=lambda x: x[1], reverse=True)
        return sorted_weights[:n]

    def get_bottom_conditions(self, n: int = 10) -> List[Tuple[str, float]]:
        """Get the bottom n least important conditions by weight."""
        sorted_weights = sorted(self.weights.items(), key=lambda x: x[1])
        return sorted_weights[:n]

    def to_edge_list(self, threshold: float = 0.0) -> pd.DataFrame:
        """Convert correlation matrix to edge list."""
        edges = []
        proteins = self.correlation_matrix.index.tolist()

        for i, p1 in enumerate(proteins):
            for j, p2 in enumerate(proteins):
                if i < j:  # Upper triangle only
                    weight = self.correlation_matrix.iloc[i, j]
                    if abs(weight) >= threshold:
                        edges.append({
                            'source': p1,
                            'target': p2,
                            'weight': weight
                        })

        return pd.DataFrame(edges)

    def summary(self) -> str:
        """Generate a text summary of the results."""
        lines = []
        lines.append("=" * 60)
        lines.append("WEIGHTED CORRELATION ANALYSIS RESULTS")
        lines.append("=" * 60)
        lines.append("")

        # Metadata
        lines.append("ANALYSIS METADATA:")
        for key, value in self.metadata.items():
            lines.append(f"  {key}: {value}")
        lines.append("")

        # Performance Section
        lines.append("PERFORMANCE METRICS:")
        lines.append(f"  Training AUC: {self.training_metrics.get('auc', 0):.4f}")
        lines.append(f"  Validation AUC: {self.validation_metrics.get('auc', 0):.4f}")
        lines.append(f"  Training AP: {self.training_metrics.get('average_precision', 0):.4f}")
        lines.append(f"  Validation AP: {self.validation_metrics.get('average_precision', 0):.4f}")
        lines.append(f"  Performance Assessment: {self.get_performance_assessment()}")
        lines.append("")

        # Top conditions
        lines.append("TOP 10 CONDITIONS BY WEIGHT:")
        for name, weight in self.get_top_conditions(10):
            lines.append(f"  {name}: {weight:.4f}")
        lines.append("")

        lines.append("=" * 60)

        return "\n".join(lines)

    def __repr__(self):
        return (f"AnalysisResults(type={self.analysis_type}, "
                f"n_proteins={len(self.correlation_matrix)}, "
                f"n_conditions={len(self.weights)})")


class WeightedCorrelationCalculator:
    """
    Calculator for weighted correlation matrices with proper missing data handling.
    """

    @staticmethod
    def calculate_matrix(
        data: np.ndarray,
        weights: np.ndarray,
        method: str = 'pearson',
        missing_handling: str = 'pairwise'
    ) -> np.ndarray:
        """
        Calculate weighted correlation matrix.

        Parameters
        ----------
        data : np.ndarray
            Data matrix (n_features x n_conditions)
        weights : np.ndarray
            Condition weights (n_conditions,)
        method : str
            Correlation method ('pearson' or 'spearman')
        missing_handling : str
            How to handle missing values ('pairwise', 'complete', 'impute')

        Returns
        -------
        np.ndarray
            Correlation matrix (n_features x n_features)
        """
        n_features, n_conditions = data.shape

        # Ensure weights are numpy array and normalized
        weights = np.asarray(weights, dtype=np.float64)
        weights = weights / weights.sum()

        # Handle missing values based on strategy
        if missing_handling == 'complete':
            # Use only complete cases (conditions with no missing values)
            valid_mask = ~np.any(np.isnan(data), axis=0)
            if valid_mask.sum() < 2:
                warnings.warn("Too few complete cases, falling back to pairwise")
                missing_handling = 'pairwise'
            else:
                data = data[:, valid_mask].copy()
                weights = weights[valid_mask]
                weights = weights / weights.sum()
                n_conditions = data.shape[1]

        elif missing_handling == 'impute':
            # Impute with weighted mean per feature
            data = data.copy()
            for i in range(n_features):
                mask = np.isnan(data[i])
                if mask.any() and (~mask).any():
                    valid_weights = weights[~mask]
                    valid_data = data[i, ~mask]
                    weighted_mean = np.average(valid_data, weights=valid_weights)
                    data[i, mask] = weighted_mean

        # Convert to ranks for Spearman
        if method == 'spearman':
            data = data.copy()
            for i in range(n_features):
                valid_mask = ~np.isnan(data[i])
                if valid_mask.sum() > 0:
                    ranks = np.zeros_like(data[i])
                    ranks[valid_mask] = np.argsort(np.argsort(data[i, valid_mask])).astype(float)
                    ranks[~valid_mask] = np.nan
                    data[i] = ranks

        # Calculate correlation matrix
        correlation_matrix = np.zeros((n_features, n_features))

        if missing_handling == 'pairwise':
            for i in range(n_features):
                correlation_matrix[i, i] = 1.0
                for j in range(i + 1, n_features):
                    corr = WeightedCorrelationCalculator._pairwise_weighted_correlation(
                        data[i], data[j], weights
                    )
                    correlation_matrix[i, j] = corr
                    correlation_matrix[j, i] = corr
        else:
            # Complete or imputed - no missing values at this point
            for i in range(n_features):
                correlation_matrix[i, i] = 1.0
                for j in range(i + 1, n_features):
                    corr = WeightedCorrelationCalculator._weighted_correlation(
                        data[i], data[j], weights
                    )
                    correlation_matrix[i, j] = corr
                    correlation_matrix[j, i] = corr

        return correlation_matrix

    @staticmethod
    def _weighted_correlation(
        x: np.ndarray,
        y: np.ndarray,
        w: np.ndarray
    ) -> float:
        """Calculate weighted Pearson correlation (no missing values)."""
        # Weighted means
        mean_x = np.average(x, weights=w)
        mean_y = np.average(y, weights=w)

        # Centered values
        dx = x - mean_x
        dy = y - mean_y

        # Weighted covariance and standard deviations
        cov_xy = np.average(dx * dy, weights=w)
        var_x = np.average(dx**2, weights=w)
        var_y = np.average(dy**2, weights=w)

        std_x = np.sqrt(var_x)
        std_y = np.sqrt(var_y)

        if std_x < 1e-10 or std_y < 1e-10:
            return 0.0

        corr = cov_xy / (std_x * std_y)
        return np.clip(corr, -1.0, 1.0)

    @staticmethod
    def _pairwise_weighted_correlation(
        x: np.ndarray,
        y: np.ndarray,
        w: np.ndarray
    ) -> float:
        """Calculate weighted Pearson correlation with pairwise deletion."""
        # Find valid pairs
        valid_mask = ~(np.isnan(x) | np.isnan(y))

        if valid_mask.sum() < 2:
            return 0.0

        x_valid = x[valid_mask]
        y_valid = y[valid_mask]
        w_valid = w[valid_mask]

        # Renormalize weights
        w_valid = w_valid / w_valid.sum()

        return WeightedCorrelationCalculator._weighted_correlation(x_valid, y_valid, w_valid)


class EmpiricalWeightLearner:
    """
    Empirical methods for learning condition weights.
    """

    @staticmethod
    def variance_weighting(
        data: np.ndarray,
        min_weight: float = 0.01
    ) -> np.ndarray:
        """
        Weight conditions by variance (higher variance = more informative).

        Parameters
        ----------
        data : np.ndarray
            Data matrix (n_features x n_conditions)
        min_weight : float
            Minimum weight to assign

        Returns
        -------
        np.ndarray
            Condition weights
        """
        # Calculate variance across features for each condition
        variances = np.nanvar(data, axis=0)

        # Handle zero/nan variances
        variances = np.nan_to_num(variances, nan=0.0)
        variances = np.maximum(variances, min_weight)

        # Normalize
        weights = variances / variances.sum()

        return weights

    @staticmethod
    def information_weighting(
        data: np.ndarray,
        n_bins: int = 10,
        min_weight: float = 0.01
    ) -> np.ndarray:
        """
        Weight conditions by information content (entropy).

        Parameters
        ----------
        data : np.ndarray
            Data matrix (n_features x n_conditions)
        n_bins : int
            Number of bins for entropy calculation
        min_weight : float
            Minimum weight to assign

        Returns
        -------
        np.ndarray
            Condition weights
        """
        n_features, n_conditions = data.shape
        entropies = np.zeros(n_conditions)

        for j in range(n_conditions):
            col = data[:, j]
            col = col[~np.isnan(col)]

            if len(col) < n_bins:
                entropies[j] = min_weight
                continue

            # Discretize and calculate entropy
            hist, _ = np.histogram(col, bins=n_bins)
            hist = hist / hist.sum()
            hist = hist[hist > 0]
            entropies[j] = -np.sum(hist * np.log2(hist))

        # Higher entropy = more information
        entropies = np.maximum(entropies, min_weight)
        weights = entropies / entropies.sum()

        return weights

    @staticmethod
    def correlation_weighting(
        data: np.ndarray,
        positive_pairs: List[Tuple[int, int]],
        min_weight: float = 0.01
    ) -> np.ndarray:
        """
        Weight conditions by how well they discriminate positive interactions.

        Parameters
        ----------
        data : np.ndarray
            Data matrix (n_features x n_conditions)
        positive_pairs : List[Tuple[int, int]]
            List of (i, j) index pairs for positive interactions
        min_weight : float
            Minimum weight to assign

        Returns
        -------
        np.ndarray
            Condition weights
        """
        n_features, n_conditions = data.shape

        if len(positive_pairs) == 0:
            return np.ones(n_conditions) / n_conditions

        # For each condition, calculate how similar positive pairs are
        condition_scores = np.zeros(n_conditions)

        for j in range(n_conditions):
            col = data[:, j]

            similarities = []
            for i1, i2 in positive_pairs:
                if not (np.isnan(col[i1]) or np.isnan(col[i2])):
                    # Use inverse absolute difference (smaller diff = more similar)
                    diff = abs(col[i1] - col[i2])
                    # Normalize by standard deviation of column
                    col_std = np.nanstd(col)
                    if col_std > 0:
                        normalized_diff = diff / col_std
                        sim = 1.0 / (1.0 + normalized_diff)
                    else:
                        sim = 0.5
                    similarities.append(sim)

            if similarities:
                condition_scores[j] = np.mean(similarities)
            else:
                condition_scores[j] = min_weight

        condition_scores = np.maximum(condition_scores, min_weight)
        weights = condition_scores / condition_scores.sum()

        return weights

    @staticmethod
    def optimization_based(
        data: np.ndarray,
        positive_pairs: List[Tuple[int, int]],
        negative_pairs: List[Tuple[int, int]],
        correlation_method: str = 'pearson',
        missing_handling: str = 'pairwise',
        n_iterations: int = 100,
        verbose: bool = False
    ) -> np.ndarray:
        """
        Learn weights through scipy optimization.

        Parameters
        ----------
        data : np.ndarray
            Data matrix (n_features x n_conditions)
        positive_pairs : List[Tuple[int, int]]
            Known positive interaction pairs
        negative_pairs : List[Tuple[int, int]]
            Known/sampled negative interaction pairs
        correlation_method : str
            'pearson' or 'spearman'
        missing_handling : str
            Missing value handling strategy
        n_iterations : int
            Maximum optimization iterations
        verbose : bool
            Print optimization progress

        Returns
        -------
        np.ndarray
            Learned condition weights
        """
        n_features, n_conditions = data.shape

        def objective(weights):
            """Negative AUC objective function."""
            weights = np.abs(weights)
            weights = weights / weights.sum()

            corr_matrix = WeightedCorrelationCalculator.calculate_matrix(
                data, weights, correlation_method, missing_handling
            )

            pos_scores = [corr_matrix[i, j] for i, j in positive_pairs]
            neg_scores = [corr_matrix[i, j] for i, j in negative_pairs]

            y_true = [1] * len(pos_scores) + [0] * len(neg_scores)
            y_scores = pos_scores + neg_scores

            try:
                auc = roc_auc_score(y_true, y_scores)
                return -auc  # Minimize negative AUC
            except Exception:
                return 0.0

        # Initial weights (uniform)
        x0 = np.ones(n_conditions) / n_conditions

        # Optimize
        result = minimize(
            objective,
            x0,
            method='L-BFGS-B',
            bounds=[(0.001, 1.0)] * n_conditions,
            options={'maxiter': n_iterations, 'disp': verbose}
        )

        weights = np.abs(result.x)
        weights = weights / weights.sum()

        return weights


# ============================================================================
# Neural Network Components (only if PyTorch available)
# ============================================================================

if TORCH_AVAILABLE:

    class DifferentiableWeightedCorrelation(nn.Module):
        """
        Differentiable weighted correlation calculation for gradient-based learning.
        """

        def __init__(self, correlation_method: str = 'pearson'):
            super().__init__()
            self.correlation_method = correlation_method

        def forward(
            self,
            data: torch.Tensor,
            weights: torch.Tensor
        ) -> torch.Tensor:
            """
            Calculate weighted correlation matrix using PyTorch operations.

            Parameters
            ----------
            data : torch.Tensor
                Shape (n_proteins, n_conditions)
            weights : torch.Tensor
                Shape (n_conditions,) - weights for each condition

            Returns
            -------
            torch.Tensor
                Correlation matrix of shape (n_proteins, n_proteins)
            """
            n_proteins, n_conditions = data.shape

            # Normalize weights to sum to 1
            weights_normalized = weights / weights.sum()

            # Calculate weighted means
            # weighted_data shape: (n_proteins, n_conditions)
            weighted_sum = (data * weights_normalized.unsqueeze(0)).sum(dim=1, keepdim=True)
            weighted_means = weighted_sum  # Already the weighted mean

            # Center the data
            centered_data = data - weighted_means

            # Apply sqrt weights for weighted covariance
            sqrt_weights = torch.sqrt(weights_normalized).unsqueeze(0)
            weighted_centered = centered_data * sqrt_weights

            # Calculate covariance matrix: (n_proteins, n_proteins)
            cov_matrix = torch.mm(weighted_centered, weighted_centered.t())

            # Compute standard deviations
            variances = torch.diag(cov_matrix)
            std_devs = torch.sqrt(torch.clamp(variances, min=1e-8))

            # Outer product of std devs
            std_matrix = torch.outer(std_devs, std_devs)
            std_matrix = torch.clamp(std_matrix, min=1e-8)

            # Correlation matrix
            corr_matrix = cov_matrix / std_matrix

            # Clamp to valid correlation range
            corr_matrix = torch.clamp(corr_matrix, -1.0, 1.0)

            return corr_matrix


    class DifferentiableAUCLoss(nn.Module):
        """
        Differentiable approximation of AUC loss using pairwise ranking.
        """

        def __init__(self, margin: float = 0.1, temperature: float = 1.0):
            super().__init__()
            self.margin = margin
            self.temperature = temperature

        def forward(
            self,
            correlation_matrix: torch.Tensor,
            positive_pairs: List[Tuple[int, int]],
            negative_pairs: List[Tuple[int, int]]
        ) -> torch.Tensor:
            """
            Calculate differentiable AUC approximation loss.

            Uses a pairwise ranking loss that approximates AUC optimization.
            """
            if len(positive_pairs) == 0 or len(negative_pairs) == 0:
                return torch.tensor(0.0, requires_grad=True)

            # Extract positive scores
            pos_indices = torch.tensor(positive_pairs, dtype=torch.long)
            pos_scores = correlation_matrix[pos_indices[:, 0], pos_indices[:, 1]]

            # Extract negative scores
            neg_indices = torch.tensor(negative_pairs, dtype=torch.long)
            neg_scores = correlation_matrix[neg_indices[:, 0], neg_indices[:, 1]]

            # Efficient pairwise ranking loss using broadcasting
            # pos_scores: (n_pos,), neg_scores: (n_neg,)
            # We want: loss += softplus((neg + margin - pos) / temp) for all pairs

            # Expand for broadcasting: (n_pos, 1) - (1, n_neg) -> (n_pos, n_neg)
            pos_expanded = pos_scores.unsqueeze(1)  # (n_pos, 1)
            neg_expanded = neg_scores.unsqueeze(0)  # (1, n_neg)

            # Difference matrix
            diff = (neg_expanded + self.margin - pos_expanded) / self.temperature

            # Softplus for smooth hinge loss
            pairwise_loss = torch.nn.functional.softplus(diff)

            # Average over all pairs
            loss = pairwise_loss.mean()

            return loss


    class NeuralWeightLearner(nn.Module):
        """
        Neural network for learning condition weights.
        """

        def __init__(
            self,
            n_conditions: int,
            hidden_dims: List[int] = [64, 32],
            dropout_rate: float = 0.1,
            activation: str = 'relu',
            init_weights: Optional[np.ndarray] = None
        ):
            super().__init__()

            self.n_conditions = n_conditions

            # Build network layers
            layers = []
            input_dim = n_conditions

            for hidden_dim in hidden_dims:
                layers.append(nn.Linear(input_dim, hidden_dim))
                if activation == 'relu':
                    layers.append(nn.ReLU())
                elif activation == 'leaky_relu':
                    layers.append(nn.LeakyReLU(0.1))
                elif activation == 'elu':
                    layers.append(nn.ELU())
                elif activation == 'tanh':
                    layers.append(nn.Tanh())
                layers.append(nn.Dropout(dropout_rate))
                input_dim = hidden_dim

            # Output layer
            layers.append(nn.Linear(input_dim, n_conditions))
            layers.append(nn.Softplus())  # Ensure positive weights

            self.network = nn.Sequential(*layers)

            # Learnable input (condition embeddings)
            if init_weights is not None:
                self.condition_embedding = nn.Parameter(
                    torch.tensor(init_weights, dtype=torch.float32)
                )
            else:
                self.condition_embedding = nn.Parameter(
                    torch.ones(n_conditions, dtype=torch.float32)
                )

        def forward(self) -> torch.Tensor:
            """Generate condition weights."""
            raw_weights = self.network(self.condition_embedding)
            # Normalize to sum to 1
            weights = raw_weights / raw_weights.sum()
            return weights


def _prepare_interaction_pairs(
    interactions: List[Tuple[str, str]],
    protein_names: List[str],
    verbose: bool = True
) -> List[Tuple[int, int]]:
    """
    Convert string interaction pairs to index pairs.

    Parameters
    ----------
    interactions : List[Tuple[str, str]]
        Interaction pairs as protein names
    protein_names : List[str]
        List of protein names (index order)
    verbose : bool
        Print status messages

    Returns
    -------
    List[Tuple[int, int]]
        Interaction pairs as indices
    """
    protein_to_idx = {name: idx for idx, name in enumerate(protein_names)}

    pairs = []
    missing_count = 0

    for p1, p2 in interactions:
        idx1 = protein_to_idx.get(str(p1), -1)
        idx2 = protein_to_idx.get(str(p2), -1)

        if idx1 == -1 or idx2 == -1:
            missing_count += 1
            continue

        if idx1 != idx2:
            # Ensure consistent ordering
            pairs.append((min(idx1, idx2), max(idx1, idx2)))

    # Remove duplicates
    pairs = list(set(pairs))

    if verbose and missing_count > 0:
        print(f"Warning: {missing_count} interactions had proteins not found in data")

    return pairs


def _sample_negative_pairs(
    n_proteins: int,
    positive_pairs: List[Tuple[int, int]],
    n_negatives: int,
    random_state: int = 42
) -> List[Tuple[int, int]]:
    """
    Sample random negative pairs (pairs not in positive set).

    Parameters
    ----------
    n_proteins : int
        Number of proteins
    positive_pairs : List[Tuple[int, int]]
        Known positive pairs to exclude
    n_negatives : int
        Number of negative samples to generate
    random_state : int
        Random seed

    Returns
    -------
    List[Tuple[int, int]]
        Sampled negative pairs
    """
    rng = np.random.RandomState(random_state)
    positive_set = set(positive_pairs)

    negative_pairs = []
    max_attempts = n_negatives * 20
    attempts = 0

    while len(negative_pairs) < n_negatives and attempts < max_attempts:
        i, j = rng.choice(n_proteins, 2, replace=False)
        pair = (min(i, j), max(i, j))

        if pair not in positive_set and pair not in negative_pairs:
            negative_pairs.append(pair)

        attempts += 1

    return negative_pairs


def _evaluate_weights(
    data: np.ndarray,
    weights: np.ndarray,
    positive_pairs: List[Tuple[int, int]],
    negative_pairs: List[Tuple[int, int]],
    correlation_method: str = 'pearson',
    missing_handling: str = 'pairwise'
) -> Dict:
    """
    Evaluate weight performance using AUC and average precision.

    Parameters
    ----------
    data : np.ndarray
        Data matrix
    weights : np.ndarray
        Condition weights
    positive_pairs : List[Tuple[int, int]]
        Positive interaction pairs
    negative_pairs : List[Tuple[int, int]]
        Negative interaction pairs
    correlation_method : str
        Correlation method
    missing_handling : str
        Missing value handling

    Returns
    -------
    Dict
        Evaluation metrics
    """
    # Calculate correlation matrix
    corr_matrix = WeightedCorrelationCalculator.calculate_matrix(
        data, weights, correlation_method, missing_handling
    )

    # Extract scores
    pos_scores = [corr_matrix[i, j] for i, j in positive_pairs]
    neg_scores = [corr_matrix[i, j] for i, j in negative_pairs]

    y_true = [1] * len(pos_scores) + [0] * len(neg_scores)
    y_scores = pos_scores + neg_scores

    metrics = {}

    try:
        metrics['auc'] = roc_auc_score(y_true, y_scores)
    except Exception:
        metrics['auc'] = 0.5

    try:
        metrics['average_precision'] = average_precision_score(y_true, y_scores)
    except Exception:
        metrics['average_precision'] = 0.0

    metrics['mean_positive_score'] = np.mean(pos_scores) if pos_scores else 0.0
    metrics['mean_negative_score'] = np.mean(neg_scores) if neg_scores else 0.0
    metrics['score_separation'] = metrics['mean_positive_score'] - metrics['mean_negative_score']

    return metrics


def learn_correlation_weights_neural(
    data: np.ndarray,
    positive_pairs: List[Tuple[int, int]],
    negative_pairs: List[Tuple[int, int]],
    condition_names: List[str],
    correlation_method: str = 'pearson',
    max_iterations: int = 500,
    learning_rate: float = 0.01,
    weight_decay: float = 1e-4,
    hidden_dims: List[int] = [64, 32],
    dropout_rate: float = 0.1,
    patience: int = 50,
    min_delta: float = 1e-4,
    init_weights: Optional[np.ndarray] = None,
    verbose: bool = True
) -> Dict:
    """
    Learn condition weights using neural network with proper gradient flow.

    Parameters
    ----------
    data : np.ndarray
        Data matrix of shape (n_proteins, n_conditions)
    positive_pairs : List[Tuple[int, int]]
        Known positive interactions as index pairs
    negative_pairs : List[Tuple[int, int]]
        Negative interactions as index pairs
    condition_names : List[str]
        Names of conditions (columns)
    correlation_method : str
        'pearson' or 'spearman'
    max_iterations : int
        Maximum training iterations
    learning_rate : float
        Learning rate for optimizer
    weight_decay : float
        L2 regularization strength
    hidden_dims : List[int]
        Hidden layer dimensions for neural network
    dropout_rate : float
        Dropout rate
    patience : int
        Early stopping patience
    min_delta : float
        Minimum improvement for early stopping
    init_weights : np.ndarray, optional
        Initial weights (e.g., from empirical method)
    verbose : bool
        Print training progress

    Returns
    -------
    Dict
        Results including learned weights, training history, and model
    """
    if not TORCH_AVAILABLE:
        raise RuntimeError("PyTorch is required for neural network learning method")

    n_proteins, n_conditions = data.shape

    if verbose:
        print(f"Neural network training:")
        print(f"  Data shape: {data.shape}")
        print(f"  Positive pairs: {len(positive_pairs)}")
        print(f"  Negative pairs: {len(negative_pairs)}")

    # Handle missing values for neural network (impute with mean)
    data_imputed = data.copy()
    for i in range(n_proteins):
        mask = np.isnan(data_imputed[i])
        if mask.any() and (~mask).any():
            data_imputed[i, mask] = np.nanmean(data_imputed[i])
        elif mask.all():
            data_imputed[i, :] = 0.0

    # Convert data to tensor
    data_tensor = torch.tensor(data_imputed, dtype=torch.float32)

    # Initialize models
    weight_learner = NeuralWeightLearner(
        n_conditions=n_conditions,
        hidden_dims=hidden_dims,
        dropout_rate=dropout_rate,
        init_weights=init_weights
    )

    corr_calculator = DifferentiableWeightedCorrelation(correlation_method)
    loss_fn = DifferentiableAUCLoss(margin=0.1, temperature=1.0)

    optimizer = optim.Adam(
        weight_learner.parameters(),
        lr=learning_rate,
        weight_decay=weight_decay
    )

    scheduler = optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode='min', factor=0.5, patience=20, verbose=False
    )

    # Training history
    training_history = {
        'iteration': [],
        'loss': [],
        'auc': [],
        'weights': []
    }

    best_loss = float('inf')
    best_weights = None
    best_auc = 0.0
    patience_counter = 0

    for iteration in range(max_iterations):
        weight_learner.train()
        optimizer.zero_grad()

        # Forward pass
        weights = weight_learner()
        corr_matrix = corr_calculator(data_tensor, weights)
        loss = loss_fn(corr_matrix, positive_pairs, negative_pairs)

        # Backward pass
        loss.backward()

        # Gradient clipping
        torch.nn.utils.clip_grad_norm_(weight_learner.parameters(), max_norm=1.0)

        optimizer.step()
        scheduler.step(loss)

        # Calculate actual AUC for monitoring
        weight_learner.eval()
        with torch.no_grad():
            weights_np = weights.detach().numpy()
            corr_np = corr_matrix.detach().numpy()

            pos_scores = [corr_np[i, j] for i, j in positive_pairs]
            neg_scores = [corr_np[i, j] for i, j in negative_pairs]

            y_true = [1] * len(pos_scores) + [0] * len(neg_scores)
            y_scores = pos_scores + neg_scores

            try:
                auc = roc_auc_score(y_true, y_scores)
            except Exception:
                auc = 0.5

        # Record history
        if iteration % 10 == 0:
            training_history['iteration'].append(iteration)
            training_history['loss'].append(loss.item())
            training_history['auc'].append(auc)
            training_history['weights'].append(weights_np.copy())

        # Early stopping check (using AUC, higher is better)
        current_loss = -auc  # Convert to loss (lower is better)
        if current_loss < best_loss - min_delta:
            best_loss = current_loss
            best_weights = weights_np.copy()
            best_auc = auc
            patience_counter = 0
        else:
            patience_counter += 1

        if patience_counter >= patience:
            if verbose:
                print(f"  Early stopping at iteration {iteration}")
            break

        if verbose and iteration % 50 == 0:
            print(f"  Iteration {iteration}: Loss = {loss.item():.4f}, AUC = {auc:.4f}")

    if verbose:
        print(f"  Training complete. Best AUC: {best_auc:.4f}")

    return {
        'weights': best_weights,
        'training_history': training_history,
        'best_auc': best_auc,
        'model': weight_learner,
        'type': 'neural'
    }


def learn_correlation_weights(
    data: pd.DataFrame,
    interactions: List[Tuple[str, str]],
    learning_method: str = 'empirical',
    empirical_method: str = 'variance',
    correlation_method: str = 'pearson',
    missing_strategy: str = 'pairwise',
    max_iterations: int = 500,
    n_random_negatives: int = None,
    validation_split: float = 0.2,
    random_state: int = 42,
    neural_config: Dict = None,
    verbose: bool = True
) -> AnalysisResults:
    """
    Main entry point for learning correlation weights.

    Parameters
    ----------
    data : pd.DataFrame
        Data with proteins as rows, conditions as columns
    interactions : List[Tuple[str, str]]
        Known positive interactions as protein name pairs
    learning_method : str
        'empirical' or 'neural'
    empirical_method : str
        If learning_method='empirical': 'variance', 'information',
        'correlation', or 'optimization'
    correlation_method : str
        'pearson' or 'spearman'
    missing_strategy : str
        'pairwise', 'complete', or 'impute'
    max_iterations : int
        Maximum iterations for optimization methods
    n_random_negatives : int, optional
        Number of random negative samples (default: 2x positives)
    validation_split : float
        Fraction of interactions for validation
    random_state : int
        Random seed for reproducibility
    neural_config : Dict, optional
        Configuration for neural network method
    verbose : bool
        Print progress

    Returns
    -------
    AnalysisResults
        Results containing correlation matrix, weights, and training history
    """
    # Default neural config
    if neural_config is None:
        neural_config = {
            'hidden_dims': [64, 32],
            'dropout_rate': 0.1,
            'learning_rate': 0.01,
            'weight_decay': 1e-4,
            'patience': 50
        }

    # Extract data
    data_array = data.values.astype(np.float64)
    protein_names = data.index.tolist()
    condition_names = data.columns.tolist()
    n_proteins, n_conditions = data_array.shape

    if verbose:
        print(f"Weighted Correlation Learning")
        print(f"  Data shape: {data_array.shape}")
        print(f"  Number of interactions: {len(interactions)}")
        print(f"  Learning method: {learning_method}")
        if learning_method == 'empirical':
            print(f"  Empirical method: {empirical_method}")

    # Convert interactions to index pairs
    positive_pairs = _prepare_interaction_pairs(interactions, protein_names, verbose)

    if len(positive_pairs) == 0:
        raise ValueError("No valid positive interactions found in data")

    if verbose:
        print(f"  Valid positive pairs: {len(positive_pairs)}")

    # Split into training and validation
    rng = np.random.RandomState(random_state)
    n_val = max(1, int(len(positive_pairs) * validation_split))
    val_indices = rng.choice(len(positive_pairs), n_val, replace=False)
    train_indices = [i for i in range(len(positive_pairs)) if i not in val_indices]

    train_positive_pairs = [positive_pairs[i] for i in train_indices]
    val_positive_pairs = [positive_pairs[i] for i in val_indices]

    # Generate negative pairs
    if n_random_negatives is None:
        n_random_negatives = len(positive_pairs) * 2

    negative_pairs = _sample_negative_pairs(
        n_proteins, positive_pairs, n_random_negatives, random_state
    )

    # Split negatives
    n_val_neg = max(1, int(len(negative_pairs) * validation_split))
    val_neg_indices = rng.choice(len(negative_pairs), n_val_neg, replace=False)
    train_neg_indices = [i for i in range(len(negative_pairs)) if i not in val_neg_indices]

    train_negative_pairs = [negative_pairs[i] for i in train_neg_indices]
    val_negative_pairs = [negative_pairs[i] for i in val_neg_indices]

    if verbose:
        print(f"  Training: {len(train_positive_pairs)} pos, {len(train_negative_pairs)} neg")
        print(f"  Validation: {len(val_positive_pairs)} pos, {len(val_negative_pairs)} neg")

    # Learn weights
    training_history = {}
    model_info = {}

    if learning_method == 'neural':
        if not TORCH_AVAILABLE:
            warnings.warn("PyTorch not available, falling back to empirical optimization")
            learning_method = 'empirical'
            empirical_method = 'optimization'

    if learning_method == 'neural':
        # Initialize with empirical weights for better starting point
        init_weights = EmpiricalWeightLearner.variance_weighting(data_array)

        results = learn_correlation_weights_neural(
            data=data_array,
            positive_pairs=train_positive_pairs,
            negative_pairs=train_negative_pairs,
            condition_names=condition_names,
            correlation_method=correlation_method,
            max_iterations=max_iterations,
            learning_rate=neural_config['learning_rate'],
            weight_decay=neural_config['weight_decay'],
            hidden_dims=neural_config['hidden_dims'],
            dropout_rate=neural_config['dropout_rate'],
            patience=neural_config.get('patience', 50),
            init_weights=init_weights,
            verbose=verbose
        )
        learned_weights = results['weights']
        training_history = results['training_history']
        model_info = {'type': 'neural', 'model': results['model']}

    elif learning_method == 'empirical':
        if verbose:
            print(f"  Computing {empirical_method} weights...")

        if empirical_method == 'variance':
            learned_weights = EmpiricalWeightLearner.variance_weighting(data_array)
        elif empirical_method == 'information':
            learned_weights = EmpiricalWeightLearner.information_weighting(data_array)
        elif empirical_method == 'correlation':
            learned_weights = EmpiricalWeightLearner.correlation_weighting(
                data_array, train_positive_pairs
            )
        elif empirical_method == 'optimization':
            learned_weights = EmpiricalWeightLearner.optimization_based(
                data_array, train_positive_pairs, train_negative_pairs,
                correlation_method, missing_strategy, max_iterations, verbose
            )
        else:
            raise ValueError(f"Unknown empirical method: {empirical_method}")

        training_history = {'method': empirical_method}
        model_info = {'type': 'empirical', 'method': empirical_method}
    else:
        raise ValueError(f"Unknown learning method: {learning_method}")

    # Evaluate on training set
    training_metrics = _evaluate_weights(
        data_array, learned_weights, train_positive_pairs, train_negative_pairs,
        correlation_method, missing_strategy
    )

    # Evaluate on validation set
    validation_metrics = _evaluate_weights(
        data_array, learned_weights, val_positive_pairs, val_negative_pairs,
        correlation_method, missing_strategy
    )

    if verbose:
        print(f"  Training AUC: {training_metrics['auc']:.4f}")
        print(f"  Validation AUC: {validation_metrics['auc']:.4f}")

    # Calculate final correlation matrix with learned weights
    correlation_matrix = WeightedCorrelationCalculator.calculate_matrix(
        data_array, learned_weights, correlation_method, missing_strategy
    )

    # Convert to DataFrame
    correlation_df = pd.DataFrame(
        correlation_matrix,
        index=protein_names,
        columns=protein_names
    )

    # Create results object
    results = AnalysisResults(
        correlation_matrix=correlation_df,
        weights=dict(zip(condition_names, learned_weights)),
        training_history=training_history,
        metadata={
            'learning_method': learning_method,
            'empirical_method': empirical_method if learning_method == 'empirical' else None,
            'correlation_method': correlation_method,
            'missing_strategy': missing_strategy,
            'n_proteins': n_proteins,
            'n_conditions': n_conditions,
            'n_interactions': len(interactions),
            'n_train_positive': len(train_positive_pairs),
            'n_train_negative': len(train_negative_pairs),
            'random_state': random_state
        },
        training_metrics=training_metrics,
        validation_metrics=validation_metrics
    )

    return results


# Convenience alias for backwards compatibility
WeightedCorrelationModel = learn_correlation_weights
