import torch
import torch.nn as nn
import torch.optim as optim
import pandas as pd
import numpy as np
from sklearn.linear_model import Ridge
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score, average_precision_score, precision_recall_curve, roc_curve
from sklearn.preprocessing import StandardScaler
#from sklearn.impute import SimpleImputer, KNNImputer, IterativeImputer // IterativeImputer is experimental
from sklearn.impute import SimpleImputer, KNNImputer
from typing import List, Tuple, Dict, Union, Optional, Callable
import matplotlib.pyplot as plt
import seaborn as sns
from scipy.stats import pearsonr, spearmanr
from scipy.optimize import minimize
import warnings
warnings.filterwarnings('ignore')

class MissingDataAnalyzer:
    """Analyze and handle missing data patterns in proteomics datasets"""

    @staticmethod
    def analyze_patterns(data: pd.DataFrame) -> Dict:
        """Analyze missing data patterns"""
        total_cells = data.size
        total_missing = data.isnull().sum().sum()
        missing_percentage = (total_missing / total_cells) * 100

        # Missing by row (proteins)
        missing_by_protein = data.isnull().sum(axis=1)
        proteins_with_missing = (missing_by_protein > 0).sum()

        # Missing by column (conditions)
        missing_by_condition = data.isnull().sum(axis=0)
        conditions_with_missing = (missing_by_condition > 0).sum()

        # Determine missing pattern
        if total_missing == 0:
            pattern = "complete"
        elif proteins_with_missing / len(data) > 0.5:
            pattern = "widespread_across_proteins"
        elif conditions_with_missing / len(data.columns) > 0.5:
            pattern = "widespread_across_conditions"
        else:
            pattern = "scattered"

        return {
            'total_missing': total_missing,
            'total_cells': total_cells,
            'missing_percentage': missing_percentage,
            'proteins_with_missing': proteins_with_missing,
            'conditions_with_missing': conditions_with_missing,
            'missing_by_protein': missing_by_protein,
            'missing_by_condition': missing_by_condition,
            'missing_pattern': pattern,
            'max_missing_per_protein': missing_by_protein.max(),
            'max_missing_per_condition': missing_by_condition.max()
        }

    @staticmethod
    def handle_missing_values(data: pd.DataFrame, strategy: str = 'median', **kwargs) -> Tuple[pd.DataFrame, Dict]:
        """Handle missing values using specified strategy"""
        missing_info = MissingDataAnalyzer.analyze_patterns(data)

        if missing_info['total_missing'] == 0:
            return data.copy(), missing_info

        processed_data = data.copy()

        if strategy == 'drop':
            row_threshold = kwargs.get('row_threshold', 0.5)
            col_threshold = kwargs.get('col_threshold', 0.8)

            # Drop columns with too many missing values
            cols_to_drop = []
            for col in processed_data.columns:
                missing_frac = processed_data[col].isnull().sum() / len(processed_data)
                if missing_frac > col_threshold:
                    cols_to_drop.append(col)

            if cols_to_drop:
                processed_data = processed_data.drop(columns=cols_to_drop)

            # Drop rows with too many missing values
            rows_to_drop = []
            for idx in processed_data.index:
                missing_frac = processed_data.loc[idx].isnull().sum() / len(processed_data.columns)
                if missing_frac > row_threshold:
                    rows_to_drop.append(idx)

            if rows_to_drop:
                processed_data = processed_data.drop(index=rows_to_drop)

            processed_data = processed_data.dropna()

        elif strategy == 'mean':
            imputer = SimpleImputer(strategy='mean')
            processed_data.iloc[:, :] = imputer.fit_transform(processed_data)

        elif strategy == 'median':
            imputer = SimpleImputer(strategy='median')
            processed_data.iloc[:, :] = imputer.fit_transform(processed_data)

        elif strategy == 'min':
            global_min = processed_data.min().min()
            fill_value = kwargs.get('fill_value', global_min * 0.1)
            processed_data = processed_data.fillna(fill_value)

        elif strategy == 'knn':
            n_neighbors = kwargs.get('n_neighbors', 5)
            imputer = KNNImputer(n_neighbors=n_neighbors)
            processed_data.iloc[:, :] = imputer.fit_transform(processed_data)

        elif strategy == 'iterative':
            raise ValueError(f"Strategy 'iterative' currently not supported")
            #max_iter = kwargs.get('max_iter', 10)
            #random_state = kwargs.get('random_state', 42)
            #imputer = IterativeImputer(max_iter=max_iter, random_state=random_state)
            #processed_data.iloc[:, :] = imputer.fit_transform(processed_data)

        elif strategy == 'protein_specific':
            for protein in processed_data.index:
                protein_data = processed_data.loc[protein]
                if protein_data.isnull().any():
                    fill_value = protein_data.median()
                    if pd.isna(fill_value):
                        fill_value = processed_data.median(axis=1).median()
                    processed_data.loc[protein] = protein_data.fillna(fill_value)

        elif strategy == 'condition_specific':
            for condition in processed_data.columns:
                condition_data = processed_data[condition]
                if condition_data.isnull().any():
                    fill_value = condition_data.median()
                    if pd.isna(fill_value):
                        fill_value = processed_data.median(axis=0).median()
                    processed_data[condition] = condition_data.fillna(fill_value)

        else:
            raise ValueError(f"Unknown strategy: {strategy}")

        final_missing_info = MissingDataAnalyzer.analyze_patterns(processed_data)
        missing_info['after_processing'] = final_missing_info
        missing_info['strategy_used'] = strategy

        return processed_data, missing_info

class WeightedCorrelationCalculator:
    """Calculate weighted correlations with missing value support"""

    @staticmethod
    # given a set of weights that are all 1 this method returns 'correlation'
    #     values very close to 1 and not much else. Why?
    def calculate_matrix(data: np.ndarray, weights: np.ndarray,
                        method: str = 'pearson', missing_handling: str = 'pairwise') -> np.ndarray:
        """Calculate weighted correlation matrix"""
        def m(x, w):
            """Weighted Mean"""
            return np.sum(x * w) / np.sum(w)

        def cov(x, y, w):
            """Weighted Covariance"""
            return np.sum(w * (x - m(x, w)) * (y - m(y, w))) / np.sum(w)

        def wcorr(x, y, w):
            """Weighted Correlation"""
            return cov(x, y, w) / np.sqrt(cov(x, x, w) * cov(y, y, w))

        n_proteins, n_conditions = data.shape

        # this step is not necessary?
        #weights = np.abs(weights) / np.sum(np.abs(weights))  # Normalize weights

        if missing_handling == 'listwise':
            # Remove proteins with any missing values
            complete_mask = ~np.isnan(data).any(axis=1)
            if not complete_mask.any():
                return np.eye(n_proteins)

            complete_data = data[complete_mask]
            weighted_data = complete_data * np.sqrt(weights).reshape(1, -1)

            if method == 'pearson':
                correlation_matrix_complete = np.corrcoef(weighted_data)
            elif method == 'spearman':
                from scipy.stats import rankdata
                ranked_data = np.apply_along_axis(rankdata, axis=1, arr=weighted_data)
                correlation_matrix_complete = np.corrcoef(ranked_data)

            # Expand back to full size
            correlation_matrix = np.eye(n_proteins)
            complete_indices = np.where(complete_mask)[0]
            for i, idx_i in enumerate(complete_indices):
                for j, idx_j in enumerate(complete_indices):
                    correlation_matrix[idx_i, idx_j] = correlation_matrix_complete[i, j]

        else:  # pairwise
            correlation_matrix = np.zeros((n_proteins, n_proteins))

            for i in range(n_proteins):
                for j in range(i, n_proteins):
                    if i == j:
                        correlation_matrix[i, j] = 1.0
                    else:
                        data_i, data_j = data[i], data[j]
                        valid_mask = ~(np.isnan(data_i) | np.isnan(data_j))

                        if valid_mask.sum() < 2:
                            correlation_matrix[i, j] = correlation_matrix[j, i] = 0.0
                            continue

                        valid_data_i = data_i[valid_mask]
                        valid_data_j = data_j[valid_mask]

                        #valid_weights = weights[valid_mask] / np.sum(weights[valid_mask])
                        valid_weights = weights[valid_mask]

                        weighted_i = valid_data_i * np.sqrt(valid_weights)
                        weighted_j = valid_data_j * np.sqrt(valid_weights)
                        #if i < 8 and j < 8:
                        #    print(max(valid_data_i))
                        #    print(max(valid_data_j))
                        #    print(np.corrcoef(valid_data_i, valid_data_j)[0, 1])

                        if method == 'pearson':
                            if np.std(valid_data_i) == 0 or np.std(valid_data_j) == 0:
                                corr = 0.0
                            else:
                                corr = np.corrcoef(weighted_i, weighted_j)[0, 1]
                                #corr = wcorr(valid_data_i, valid_data_j, valid_weights)
                                #corr = np.corrcoef(valid_data_i, valid_data_j)[0,1]

                        elif method == 'spearman':
                            corr, _ = spearmanr(weighted_i, weighted_j)
                            if np.isnan(corr):
                                corr = 0.0

                        correlation_matrix[i, j] = correlation_matrix[j, i] = corr

        return np.nan_to_num(correlation_matrix, nan=0.0)

class InteractionScorer:
    """Score protein interactions using correlation matrices"""

    @staticmethod
    def extract_scores(correlation_matrix: np.ndarray, interactions: List[Tuple],
                      protein_to_idx: Dict[str, int] = None,
                      removed_proteins: set = None) -> np.ndarray:
        """Extract correlation scores for protein interactions"""
        scores = []

        for interaction in interactions:
            if protein_to_idx is not None:
                if (removed_proteins and
                    (interaction[0] in removed_proteins or interaction[1] in removed_proteins)):
                    continue

                idx1 = protein_to_idx.get(interaction[0], -1)
                idx2 = protein_to_idx.get(interaction[1], -1)

                if idx1 == -1 or idx2 == -1:
                    continue
            else:
                idx1, idx2 = interaction

            if (idx1 >= correlation_matrix.shape[0] or idx2 >= correlation_matrix.shape[0] or
                idx1 < 0 or idx2 < 0):
                continue

            score = abs(correlation_matrix[idx1, idx2])
            if not (np.isnan(score) or np.isinf(score)):
                scores.append(score)

        return np.array(scores)

class ObjectiveFunction:
    """Objective functions for weight optimization"""

    @staticmethod
    def auc_objective(correlation_matrix: np.ndarray, positive_interactions: List[Tuple],
                     protein_to_idx: Dict[str, int] = None, n_random_negatives: int = None,
                     removed_proteins: set = None) -> float:
        """AUC-based objective function"""
        positive_scores = InteractionScorer.extract_scores(
            correlation_matrix, positive_interactions, protein_to_idx, removed_proteins
        )

        if len(positive_scores) == 0:
            return 0.0

        # Generate negative interactions
        n_proteins = correlation_matrix.shape[0]
        if n_random_negatives is None:
            n_random_negatives = len(positive_interactions) * 2

        positive_set = set()
        for interaction in positive_interactions:
            if protein_to_idx is not None:
                idx1 = protein_to_idx.get(interaction[0], -1)
                idx2 = protein_to_idx.get(interaction[1], -1)
                if idx1 != -1 and idx2 != -1:
                    positive_set.add((min(idx1, idx2), max(idx1, idx2)))
            else:
                positive_set.add((min(interaction[0], interaction[1]), max(interaction[0], interaction[1])))

        negative_pairs = []
        attempts = 0
        while len(negative_pairs) < n_random_negatives and attempts < n_random_negatives * 10:
            i, j = np.random.choice(n_proteins, 2, replace=False)
            pair = (min(i, j), max(i, j))
            if pair not in positive_set:
                negative_pairs.append((i, j))
            attempts += 1

        negative_scores = InteractionScorer.extract_scores(correlation_matrix, negative_pairs)

        if len(negative_scores) == 0:
            return 0.0

        y_true = np.concatenate([np.ones(len(positive_scores)), np.zeros(len(negative_scores))])
        y_scores = np.concatenate([positive_scores, negative_scores])

        if len(np.unique(y_true)) < 2:
            return 0.0

        try:
            return roc_auc_score(y_true, y_scores)
        except:
            return 0.0

class NeuralWeightLearner(nn.Module):
    """Neural network for learning condition weights"""

    def __init__(self, n_conditions: int, hidden_dims: List[int] = [64, 32],
                 dropout_rate: float = 0.1, activation: str = 'relu'):
        super().__init__()

        self.n_conditions = n_conditions

        if activation == 'relu':
            self.activation = nn.ReLU()
        elif activation == 'tanh':
            self.activation = nn.Tanh()
        elif activation == 'elu':
            self.activation = nn.ELU()

        layers = []
        prev_dim = n_conditions

        for hidden_dim in hidden_dims:
            layers.extend([
                nn.Linear(prev_dim, hidden_dim),
                self.activation,
                nn.Dropout(dropout_rate)
            ])
            prev_dim = hidden_dim

        layers.append(nn.Linear(prev_dim, n_conditions))
        layers.append(nn.Softmax(dim=-1))

        self.network = nn.Sequential(*layers)
        self.init_weights()

    def init_weights(self):
        """Initialize to output uniform weights"""
        with torch.no_grad():
            final_layer = list(self.network.children())[-2]
            final_layer.weight.fill_(0.0)
            final_layer.bias.fill_(0.0)

    def forward(self, x=None):
        if x is None:
            x = torch.ones(1, self.n_conditions)
        weights = self.network(x)
        return weights.squeeze()

class RidgeWeightLearner:
    """Ridge regression approach for learning weights"""

    def __init__(self, alpha: float = 1.0, max_iter: int = 1000):
        self.alpha = alpha
        self.max_iter = max_iter
        self.model = None
        self.scaler =None

    def fit(self, data_array: np.ndarray, train_interactions: List[Tuple],
            protein_to_idx: Dict[str, int], n_random_negatives: int):
        """Train ridge regression model"""
        X_train, y_train = [], []

        # Positive interactions
        for interaction in train_interactions:
            idx1 = protein_to_idx[interaction[0]]
            idx2 = protein_to_idx[interaction[1]]

            expr1, expr2 = data_array[idx1], data_array[idx2]
            valid_mask = ~(np.isnan(expr1) | np.isnan(expr2))

            if valid_mask.sum() >= 2:
                feature = np.zeros(data_array.shape[1])
                feature[valid_mask] = expr1[valid_mask] * expr2[valid_mask]
                if valid_mask.sum() < data_array.shape[1]:
                    feature[~valid_mask] = np.mean(feature[valid_mask])

                X_train.append(feature)
                y_train.append(1.0)

        # Negative interactions
        n_proteins = data_array.shape[0]
        positive_set = set()
        for interaction in train_interactions:
            idx1, idx2 = protein_to_idx[interaction[0]], protein_to_idx[interaction[1]]
            positive_set.add((min(idx1, idx2), max(idx1, idx2)))

        negative_count = 0
        attempts = 0
        while negative_count < n_random_negatives and attempts < n_random_negatives * 10:
            i, j = np.random.choice(n_proteins, 2, replace=False)
            pair = (min(i, j), max(i, j))
            if pair not in positive_set:
                expr1, expr2 = data_array[i], data_array[j]
                valid_mask = ~(np.isnan(expr1) | np.isnan(expr2))

                if valid_mask.sum() >= 2:
                    feature = np.zeros(data_array.shape[1])
                    feature[valid_mask] = expr1[valid_mask] * expr2[valid_mask]
                    if valid_mask.sum() < data_array.shape[1]:
                        feature[~valid_mask] = np.mean(feature[valid_mask])

                    X_train.append(feature)
                    y_train.append(0.0)
                    negative_count += 1
            attempts += 1

        if len(X_train) == 0:
            raise ValueError("No valid training samples")

        X_train = np.array(X_train)
        y_train = np.array(y_train)

        self.scaler = StandardScaler()
        X_train_scaled = self.scaler.fit_transform(X_train)

        self.model = Ridge(alpha=self.alpha, max_iter=self.max_iter)
        self.model.fit(X_train_scaled, y_train)

        learned_weights = np.abs(self.model.coef_)
        return learned_weights / np.sum(learned_weights)

class EmpiricalWeightLearner:
    """Empirical methods for learning weights"""

    @staticmethod
    def variance_weighting(data: np.ndarray) -> np.ndarray:
        """Weight by inverse variance"""
        variances = np.nanvar(data, axis=0)
        weights = 1.0 / (variances + 1e-8)  # Add small constant to avoid division by zero
        return weights / np.sum(weights)

    @staticmethod
    def information_weighting(data: np.ndarray) -> np.ndarray:
        """Weight by information content (entropy-based)"""
        weights = []
        for col in range(data.shape[1]):
            col_data = data[:, col]
            col_data = col_data[~np.isnan(col_data)]

            if len(col_data) == 0:
                weights.append(0.0)
                continue

            # Discretize data for entropy calculation
            hist, _ = np.histogram(col_data, bins=10)
            hist = hist + 1e-8  # Avoid log(0)
            probs = hist / np.sum(hist)
            entropy = -np.sum(probs * np.log2(probs))
            weights.append(entropy)

        weights = np.array(weights)
        return weights / np.sum(weights)

    @staticmethod
    def correlation_weighting(data: np.ndarray, interactions: List[Tuple],
                             protein_to_idx: Dict[str, int]) -> np.ndarray:
        """Weight by correlation with known interactions"""
        n_conditions = data.shape[1]
        weights = np.zeros(n_conditions)

        for condition_idx in range(n_conditions):
            condition_correlations = []

            for interaction in interactions:
                idx1 = protein_to_idx.get(interaction[0], -1)
                idx2 = protein_to_idx.get(interaction[1], -1)

                if idx1 != -1 and idx2 != -1:
                    val1, val2 = data[idx1, condition_idx], data[idx2, condition_idx]
                    if not (np.isnan(val1) or np.isnan(val2)):
                        # Needs to be something like:
                        # condition_correlations.append(abs(1-(val1-val2)))
                        condition_correlations.append(abs(val1 - val2))  # Inverse of difference

            if condition_correlations:
                #weights[condition_idx] = 1.0 / (np.mean(condition_correlations) + 1e-8)
                # this ends up being very small weights - why is that needed? It's not.
                weights[condition_idx] = (np.mean(condition_correlations) + 1e-8)

        #print(weights / max(weights))

        # testing this - this should be just correlation
        # yep... it's totally not. Bad bad code. Bad.
        # weights = np.ones(n_conditions)
        # return weights
        return weights / max(weights)
        # this division makes the weights even smaller. Again no reason to do that? This isn't the main problem though.
        #Original code: return weights / np.sum(weights) if np.sum(weights) > 0 else np.ones(n_conditions) / n_conditions

    @staticmethod
    def optimization_based(data: np.ndarray, interactions: List[Tuple],
                          protein_to_idx: Dict[str, int], method: str = 'L-BFGS-B') -> np.ndarray:
        """Direct optimization of objective function"""
        n_conditions = data.shape[1]

        def objective(weights):
            weights = np.abs(weights)
            weights = weights / np.sum(weights)

            correlation_matrix = WeightedCorrelationCalculator.calculate_matrix(
                data, weights, method='pearson', missing_handling='pairwise'
            )

            return -ObjectiveFunction.auc_objective(
                correlation_matrix, interactions, protein_to_idx
            )

        # Initial guess - uniform weights
        initial_weights = np.ones(n_conditions) / n_conditions

        # Optimize
        print(initial_weights)
        result = minimize(objective, initial_weights, method=method,
                         bounds=[(0, 1) for _ in range(n_conditions)])
        print(result.x)
        print(result.x/np.sum(result.x))

        if result.success:
            weights = np.abs(result.x)
            return weights / np.sum(weights)
        else:
            return initial_weights

class PerformanceValidator:
    """Validate correlation predictions"""

    @staticmethod
    def calculate_metrics(correlation_matrix: np.ndarray, interactions: List[Tuple],
                         protein_to_idx: Dict[str, int], removed_proteins: set = None,
                         n_random_negatives: int = None) -> Dict:
        """Calculate comprehensive performance metrics"""
        positive_scores = InteractionScorer.extract_scores(
            correlation_matrix, interactions, protein_to_idx, removed_proteins
        )

        if len(positive_scores) == 0:
            return {'auc': 0.0, 'average_precision': 0.0, 'n_positive': 0, 'n_negative': 0}

        # Generate negative interactions
        n_proteins = correlation_matrix.shape[0]
        if n_random_negatives is None:
            n_random_negatives = len(interactions) * 2

        positive_set = set()
        for interaction in interactions:
            if protein_to_idx is not None:
                idx1 = protein_to_idx.get(interaction[0], -1)
                idx2 = protein_to_idx.get(interaction[1], -1)
                if idx1 != -1 and idx2 != -1:
                    positive_set.add((min(idx1, idx2), max(idx1, idx2)))

        negative_pairs = []
        attempts = 0
        while len(negative_pairs) < n_random_negatives and attempts < n_random_negatives * 10:
            i, j = np.random.choice(n_proteins, 2, replace=False)
            pair = (min(i, j), max(i, j))
            if pair not in positive_set:
                negative_pairs.append((i, j))
            attempts += 1

        negative_scores = InteractionScorer.extract_scores(correlation_matrix, negative_pairs)

        if len(negative_scores) == 0:
            return {'auc': 0.0, 'average_precision': 0.0, 'n_positive': len(positive_scores), 'n_negative': 0}

        y_true = np.concatenate([np.ones(len(positive_scores)), np.zeros(len(negative_scores))])
        y_scores = np.concatenate([positive_scores, negative_scores])

        try:
            auc = roc_auc_score(y_true, y_scores)
            ap = average_precision_score(y_true, y_scores)

            fpr, tpr, _ = roc_curve(y_true, y_scores)
            precision, recall, _ = precision_recall_curve(y_true, y_scores)

            return {
                'auc': auc,
                'average_precision': ap,
                'n_positive': len(positive_scores),
                'n_negative': len(negative_scores),
                'positive_scores_mean': np.mean(positive_scores),
                'negative_scores_mean': np.mean(negative_scores),
                'positive_scores_std': np.std(positive_scores),
                'negative_scores_std': np.std(negative_scores),
                'fpr': fpr,
                'tpr': tpr,
                'precision': precision,
                'recall': recall
            }
        except Exception as e:
            return {'auc': 0.0, 'average_precision': 0.0, 'n_positive': len(positive_scores), 'n_negative': len(negative_scores)}

class CorrelationWeightLearner:
    """Main class for learning correlation weights"""

    def __init__(self, missing_strategy: str = 'median', missing_params: Dict = None,
                 correlation_method: str = 'pearson', correlation_missing_handling: str = 'pairwise'):
        self.missing_strategy = missing_strategy
        self.missing_params = missing_params or {}
        self.correlation_method = correlation_method
        self.correlation_missing_handling = correlation_missing_handling

    def learn_weights(self, data: pd.DataFrame, interactions: List[Tuple[str, str]],
                     learning_method: str = 'ridge', train_split: float = 0.7,
                     random_state: int = 42, n_random_negatives: int = None,
                     neural_config: Dict = None, ridge_config: Dict = None,
                     empirical_method: str = 'correlation', max_iterations: int = 50,
                     verbose: bool = True) -> Dict:
        """
        Learn optimal weights for weighted correlation

        Args:
            data: DataFrame with proteins as rows, conditions as columns
            interactions: List of (protein1, protein2) known interactions
            learning_method: 'ridge', 'neural', or 'empirical'
            train_split: Fraction for training
            random_state: Random seed
            n_random_negatives: Number of random negative interactions
            neural_config: Neural network configuration
            ridge_config: Ridge regression configuration
            empirical_method: Empirical method ('variance', 'information', 'correlation', 'optimization')
            max_iterations: Maximum iterations for neural training
            verbose: Print progress

        Returns:
            Dictionary with results
        """
        np.random.seed(random_state)
        torch.manual_seed(random_state)

        if verbose:
            print("=== Correlation Weight Learning ===")
            print(f"Original data shape: {data.shape}")
            print(f"Learning method: {learning_method}")

        # Handle missing values
        # NOTE: seems to introduce very large values into the matrix,
        #       which messes with correlation (and maybe other results?)
        processed_data, missing_info = MissingDataAnalyzer.handle_missing_values(
            data, strategy=self.missing_strategy, **self.missing_params
        )

        # does this fix it?
        processed_data = data

        if verbose:
            print(f"Processed data shape: {processed_data.shape}")

        # Setup data structures
        protein_names = processed_data.index.tolist()
        condition_names = processed_data.columns.tolist()
        protein_to_idx = {protein: idx for idx, protein in enumerate(protein_names)}
        data_array = processed_data.values

        # Track removed proteins
        original_proteins = set(data.index)
        remaining_proteins = set(processed_data.index)
        removed_proteins = original_proteins - remaining_proteins

        # Filter valid interactions
        valid_interactions = [
            interaction for interaction in interactions
            if interaction[0] in protein_to_idx and interaction[1] in protein_to_idx
        ]

        if len(valid_interactions) < 10:
            raise ValueError(f"Too few valid interactions: {len(valid_interactions)}")

        # Split interactions
        train_interactions, val_interactions = train_test_split(
            valid_interactions, train_size=train_split, random_state=random_state
        )

        if verbose:
            print(f"Training interactions: {len(train_interactions)}")
            print(f"Validation interactions: {len(val_interactions)}")

        # Set defaults
        if neural_config is None:
            neural_config = {'hidden_dims': [64, 32], 'dropout_rate': 0.1,
                           'learning_rate': 0.01, 'weight_decay': 1e-4}
        if ridge_config is None:
            ridge_config = {'alpha': 1.0, 'max_iter': 1000}
        if n_random_negatives is None:
            n_random_negatives = len(train_interactions) * 2

        # Learn weights based on method
        training_history = {'iteration': [], 'train_objective': [], 'weights': []}

        if learning_method == 'ridge':
            if verbose:
                print("Training Ridge Regression...")

            ridge_learner = RidgeWeightLearner(**ridge_config)
            learned_weights = ridge_learner.fit(
                data_array, train_interactions, protein_to_idx, n_random_negatives
            )

            model = {'ridge_learner': ridge_learner, 'type': 'ridge'}

            # Calculate objective
            correlation_matrix = WeightedCorrelationCalculator.calculate_matrix(
                data_array, learned_weights, self.correlation_method, self.correlation_missing_handling
            )
            train_objective = ObjectiveFunction.auc_objective(
                correlation_matrix, train_interactions, protein_to_idx, n_random_negatives, removed_proteins
            )

            training_history = {
                'iteration': [0],
                'train_objective': [train_objective],
                'weights': [learned_weights.copy()]
            }

        elif learning_method == 'neural':
            if verbose:
                print("Training Neural Network...")

            model_nn = NeuralWeightLearner(
                n_conditions=len(condition_names),
                hidden_dims=neural_config['hidden_dims'],
                dropout_rate=neural_config['dropout_rate']
            )

            optimizer = optim.Adam(
                model_nn.parameters(),
                lr=neural_config['learning_rate'],
                weight_decay=neural_config['weight_decay']
            )

            best_weights = None
            best_objective = -1.0

            for iteration in range(max_iterations):
                optimizer.zero_grad()

                weights = model_nn()
                weights_np = weights.detach().numpy()

                correlation_matrix = WeightedCorrelationCalculator.calculate_matrix(
                    data_array, weights_np, self.correlation_method, self.correlation_missing_handling
                )

                objective = ObjectiveFunction.auc_objective(
                    correlation_matrix, train_interactions, protein_to_idx, n_random_negatives, removed_proteins
                )

                loss = -torch.tensor(objective, requires_grad=True)
                loss.backward()
                optimizer.step()

                if objective > best_objective:
                    print(f'better... {objective}>{best_objective}')
                    best_objective = objective
                    best_weights = weights_np.copy()

                print(best_weights)

                if iteration % 50 == 0 or iteration == max_iterations - 1:
                    training_history['iteration'].append(iteration)
                    training_history['train_objective'].append(objective)
                    training_history['weights'].append(weights_np.copy())

                    if verbose and iteration % 50 == 0:
                        print(f"Iteration {iteration}: Objective = {objective:.4f}")

            learned_weights = best_weights
            print(best_weights)
            model = {'neural_model': model_nn, 'type': 'neural'}

        elif learning_method == 'empirical':
            if verbose:
                print(f"Using Empirical Method: {empirical_method}")

            if empirical_method == 'variance':
                learned_weights = EmpiricalWeightLearner.variance_weighting(data_array)
            elif empirical_method == 'information':
                learned_weights = EmpiricalWeightLearner.information_weighting(data_array)
            elif empirical_method == 'correlation':
                learned_weights = EmpiricalWeightLearner.correlation_weighting(
                    data_array, train_interactions, protein_to_idx
                )
            elif empirical_method == 'optimization':
                if verbose:
                    print("Empirical optimization")
                learned_weights = EmpiricalWeightLearner.optimization_based(
                    data_array, train_interactions, protein_to_idx
                )
            else:
                raise ValueError(f"Unknown empirical method: {empirical_method}")

            model = {'type': 'empirical', 'method': empirical_method}

            # Calculate objective
            correlation_matrix = WeightedCorrelationCalculator.calculate_matrix(
                data_array, learned_weights, self.correlation_method, self.correlation_missing_handling
            )
            train_objective = ObjectiveFunction.auc_objective(
                correlation_matrix, train_interactions, protein_to_idx, n_random_negatives, removed_proteins
            )

            training_history = {
                'iteration': [0],
                'train_objective': [train_objective],
                'weights': [learned_weights.copy()]
            }

        else:
            raise ValueError("learning_method must be 'ridge', 'neural', or 'empirical'")

        # Calculate final correlation matrix
        final_correlation_matrix = WeightedCorrelationCalculator.calculate_matrix(
            data_array, learned_weights, self.correlation_method, self.correlation_missing_handling
        )

        weighted_corr_df = pd.DataFrame(
            final_correlation_matrix,
            index=protein_names,
            columns=protein_names
        )

        # Performance validation
        training_metrics = PerformanceValidator.calculate_metrics(
            final_correlation_matrix, train_interactions, protein_to_idx, removed_proteins
        )

        validation_metrics = PerformanceValidator.calculate_metrics(
            final_correlation_matrix, val_interactions, protein_to_idx, removed_proteins
        )

        if verbose:
            print(f"\nResults:")
            print(f"Training AUC: {training_metrics['auc']:.4f}")
            print(f"Validation AUC: {validation_metrics['auc']:.4f}")
            print(f"Training AP: {training_metrics['average_precision']:.4f}")
            print(f"Validation AP: {validation_metrics['average_precision']:.4f}")

        # Create results
        weights_df = pd.DataFrame({
            'condition': condition_names,
            'weight': learned_weights
        }).sort_values('weight', ascending=False)

        return {
            'model': model,
            'learned_weights': learned_weights,
            'weights_dataframe': weights_df,
            'weighted_correlation_matrix': weighted_corr_df,
            'training_metrics': training_metrics,
            'validation_metrics': validation_metrics,
            'training_history': training_history,
            'train_interactions': train_interactions,
            'val_interactions': val_interactions,
            'missing_data_info': missing_info,
            'removed_proteins': removed_proteins,
            'original_data_shape': data.shape,
            'processed_data_shape': processed_data.shape,
            'config': {
                'learning_method': learning_method,
                'correlation_method': self.correlation_method,
                'correlation_missing_handling': self.correlation_missing_handling,
                'missing_strategy': self.missing_strategy,
                'missing_params': self.missing_params,
                'train_split': train_split,
                'n_random_negatives': n_random_negatives,
                'neural_config': neural_config if learning_method == 'neural' else None,
                'ridge_config': ridge_config if learning_method == 'ridge' else None,
                'empirical_method': empirical_method if learning_method == 'empirical' else None
            }
        }

# Main function wrapper for easy use
def learn_correlation_weights(data: pd.DataFrame, interactions: List[Tuple[str, str]],
                            learning_method: str = 'ridge', missing_strategy: str = 'median',
                            **kwargs) -> Dict:
    """
    Main function to learn correlation weights

    Args:
        data: DataFrame with proteins as rows, conditions as columns
        interactions: List of (protein1, protein2) known interactions
        learning_method: 'ridge', 'neural', or 'empirical'
        missing_strategy: Strategy for handling missing values
        **kwargs: Additional parameters

    Returns:
        Dictionary with complete results
    """
    learner = CorrelationWeightLearner(
        missing_strategy=missing_strategy,
        missing_params=kwargs.get('missing_params', {}),
        correlation_method=kwargs.get('correlation_method', 'pearson'),
        correlation_missing_handling=kwargs.get('correlation_missing_handling', 'pairwise')
    )

    return learner.learn_weights(
        data=data,
        interactions=interactions,
        learning_method=learning_method,
        # **kwargs
    )

class ResultsVisualizer:
    """Visualize results from correlation weight learning"""

    @staticmethod
    def plot_comprehensive_results(results: Dict, figsize: Tuple[int, int] = (20, 16)) -> plt.Figure:
        """Create comprehensive visualization of results"""
        fig = plt.figure(figsize=figsize)

        # 1. Learned weights
        ax1 = plt.subplot(4, 4, 1)
        weights_df = results['weights_dataframe']
        bars = ax1.bar(range(min(20, len(weights_df))), weights_df['weight'].head(20))
        ax1.set_xlabel('Condition Index')
        ax1.set_ylabel('Weight')
        ax1.set_title('Top 20 Learned Weights')
        ax1.grid(True, alpha=0.3)

        # 2. Weight distribution
        ax2 = plt.subplot(4, 4, 2)
        ax2.hist(weights_df['weight'], bins=20, alpha=0.7, edgecolor='black')
        ax2.axvline(np.mean(weights_df['weight']), color='red', linestyle='--',
                    label=f'Mean: {np.mean(weights_df["weight"]):.4f}')
        ax2.set_xlabel('Weight Value')
        ax2.set_ylabel('Frequency')
        ax2.set_title('Weight Distribution')
        ax2.legend()
        ax2.grid(True, alpha=0.3)

        # 3. Training progress
        ax3 = plt.subplot(4, 4, 3)
        history = results['training_history']
        if len(history['iteration']) > 1:
            ax3.plot(history['iteration'], history['train_objective'], 'b-', linewidth=2)
            ax3.set_xlabel('Iteration')
            ax3.set_ylabel('Training Objective (AUC)')
            ax3.set_title('Training Progress')
            ax3.grid(True, alpha=0.3)
        else:
            ax3.text(0.5, 0.5, f'Single iteration\n({results["config"]["learning_method"].title()})',
                    ha='center', va='center', transform=ax3.transAxes)
            ax3.set_title('Training Progress')

        # 4. Performance comparison
        ax4 = plt.subplot(4, 4, 4)
        train_metrics = results['training_metrics']
        val_metrics = results['validation_metrics']

        x = np.arange(2)
        width = 0.35

        bars1 = ax4.bar(x - width/2, [train_metrics['auc'], val_metrics['auc']],
                       width, label='AUC', alpha=0.7)
        bars2 = ax4.bar(x + width/2, [train_metrics['average_precision'], val_metrics['average_precision']],
                       width, label='Average Precision', alpha=0.7)

        ax4.set_ylabel('Score')
        ax4.set_title('Performance Metrics')
        ax4.set_xticks(x)
        ax4.set_xticklabels(['Training', 'Validation'])
        ax4.legend()
        ax4.grid(True, alpha=0.3)

        # Add value labels
        for bars in [bars1, bars2]:
            for bar in bars:
                height = bar.get_height()
                ax4.text(bar.get_x() + bar.get_width()/2., height + 0.01,
                        f'{height:.3f}', ha='center', va='bottom', fontsize=8)

        # 5. ROC curves
        ax5 = plt.subplot(4, 4, 5)
        if 'fpr' in train_metrics and 'tpr' in train_metrics:
            ax5.plot(train_metrics['fpr'], train_metrics['tpr'],
                    label=f'Training (AUC = {train_metrics["auc"]:.3f})', linewidth=2)
        if 'fpr' in val_metrics and 'tpr' in val_metrics:
            ax5.plot(val_metrics['fpr'], val_metrics['tpr'],
                    label=f'Validation (AUC = {val_metrics["auc"]:.3f})', linewidth=2)
        ax5.plot([0, 1], [0, 1], 'k--', alpha=0.5)
        ax5.set_xlabel('False Positive Rate')
        ax5.set_ylabel('True Positive Rate')
        ax5.set_title('ROC Curves')
        ax5.legend()
        ax5.grid(True, alpha=0.3)

        # 6. Correlation matrix heatmap
        ax6 = plt.subplot(4, 4, 6)
        corr_matrix = results['weighted_correlation_matrix']
        if len(corr_matrix) > 50:
            subset_indices = np.random.choice(len(corr_matrix), 50, replace=False)
            plot_matrix = corr_matrix.iloc[subset_indices, subset_indices]
            title_suffix = " (50 random)"
        else:
            plot_matrix = corr_matrix
            title_suffix = ""

        sns.heatmap(plot_matrix, cmap='RdBu_r', center=0, square=True,
                   cbar_kws={'label': 'Correlation'}, ax=ax6)
        ax6.set_title(f'Weighted Correlation Matrix{title_suffix}')

        # 7. Score distributions
        ax7 = plt.subplot(4, 4, 7)
        pos_mean = train_metrics.get('positive_scores_mean', 0)
        neg_mean = train_metrics.get('negative_scores_mean', 0)

        if pos_mean > 0 and neg_mean > 0:
            # Create sample distributions for visualization
            pos_scores = np.random.normal(pos_mean, train_metrics.get('positive_scores_std', 0.1), 100)
            neg_scores = np.random.normal(neg_mean, train_metrics.get('negative_scores_std', 0.1), 100)

            ax7.hist(pos_scores, bins=20, alpha=0.7, label='Positive Interactions', density=True)
            ax7.hist(neg_scores, bins=20, alpha=0.7, label='Random Pairs', density=True)
            ax7.set_xlabel('Correlation Score')
            ax7.set_ylabel('Density')
            ax7.set_title('Score Distributions')
            ax7.legend()
            ax7.grid(True, alpha=0.3)
        else:
            ax7.text(0.5, 0.5, 'Score distributions\nnot available',
                    ha='center', va='center', transform=ax7.transAxes)
            ax7.set_title('Score Distributions')

        # 8. Top weighted conditions
        ax8 = plt.subplot(4, 4, 8)
        top_conditions = weights_df.head(10)
        bars = ax8.barh(range(len(top_conditions)), top_conditions['weight'])
        ax8.set_yticks(range(len(top_conditions)))
        ax8.set_yticklabels(top_conditions['condition'], fontsize=8)
        ax8.set_xlabel('Weight')
        ax8.set_title('Top 10 Weighted Conditions')
        ax8.grid(True, alpha=0.3, axis='x')

        # 9. Missing data analysis
        ax9 = plt.subplot(4, 4, 9)
        missing_info = results['missing_data_info']

        if 'after_processing' in missing_info:
            categories = ['Before', 'After']
            values = [missing_info['missing_percentage'],
                     missing_info['after_processing']['missing_percentage']]
            colors = ['red', 'green']

            bars = ax9.bar(categories, values, color=colors, alpha=0.7)
            ax9.set_ylabel('Missing Percentage (%)')
            ax9.set_title('Missing Data Handling')

            for bar, val in zip(bars, values):
                ax9.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.1,
                        f'{val:.2f}%', ha='center', va='bottom')
        else:
            ax9.text(0.5, 0.5, 'No missing data\nprocessing needed',
                    ha='center', va='center', transform=ax9.transAxes)
            ax9.set_title('Missing Data Status')

        # 10. Data shape changes
        ax10 = plt.subplot(4, 4, 10)
        original_shape = results['original_data_shape']
        processed_shape = results['processed_data_shape']

        categories = ['Proteins', 'Conditions']
        original_vals = [original_shape[0], original_shape[1]]
        processed_vals = [processed_shape[0], processed_shape[1]]

        x = np.arange(len(categories))
        width = 0.35

        ax10.bar(x - width/2, original_vals, width, label='Original', alpha=0.7, color='lightcoral')
        ax10.bar(x + width/2, processed_vals, width, label='Processed', alpha=0.7, color='lightgreen')

        ax10.set_ylabel('Count')
        ax10.set_title('Data Shape Changes')
        ax10.set_xticks(x)
        ax10.set_xticklabels(categories)
        ax10.legend()

        # 11-12. Configuration and summary
        ax11 = plt.subplot(4, 4, (11, 12))
        ax11.axis('off')

        config = results['config']
        summary_text = f"""
Configuration:
• Learning Method: {config['learning_method'].title()}
• Correlation Method: {config['correlation_method'].title()}
• Missing Strategy: {config['missing_strategy'].title()}
• Train Split: {config['train_split']:.1%}

Data Processing:
• Original Shape: {original_shape}
• Processed Shape: {processed_shape}
• Removed Proteins: {len(results['removed_proteins'])}
• Missing Handling: {config['correlation_missing_handling']}

Performance:
• Training AUC: {train_metrics['auc']:.4f}
• Validation AUC: {val_metrics['auc']:.4f}
• Training AP: {train_metrics['average_precision']:.4f}
• Validation AP: {val_metrics['average_precision']:.4f}

Interactions:
• Training: {len(results['train_interactions'])}
• Validation: {len(results['val_interactions'])}
• Positive Training: {train_metrics['n_positive']}
• Negative Training: {train_metrics['n_negative']}
        """

        ax11.text(0.05, 0.95, summary_text, transform=ax11.transAxes,
                 fontsize=9, verticalalignment='top',
                 bbox=dict(boxstyle='round', facecolor='lightgray', alpha=0.8))

        # 13-16. Method-specific visualizations
        if config['learning_method'] == 'neural' and len(history['weights']) > 1:
            # Weight evolution
            ax13 = plt.subplot(4, 4, 13)
            weight_evolution = np.array(history['weights'])

            # Plot evolution of top 5 weights
            top_5_indices = np.argsort(weight_evolution[-1])[-5:]
            for idx in top_5_indices:
                ax13.plot(history['iteration'], weight_evolution[:, idx],
                         label=f'Cond {idx}', alpha=0.7)

            ax13.set_xlabel('Iteration')
            ax13.set_ylabel('Weight Value')
            ax13.set_title('Weight Evolution (Top 5)')
            ax13.legend(fontsize=8)
            ax13.grid(True, alpha=0.3)

        elif config['learning_method'] == 'empirical':
            # Empirical method comparison
            ax13 = plt.subplot(4, 4, 13)
            method = config.get('empirical_method', 'unknown')
            ax13.text(0.5, 0.5, f'Empirical Method:\n{method.title()}',
                     ha='center', va='center', transform=ax13.transAxes,
                     fontsize=12, bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.8))
            ax13.set_title('Learning Method')

        # Weight statistics
        ax14 = plt.subplot(4, 4, 14)
        weight_stats = {
            'Max': weights_df['weight'].max(),
            'Min': weights_df['weight'].min(),
            'Mean': weights_df['weight'].mean(),
            'Std': weights_df['weight'].std(),
            'Median': weights_df['weight'].median()
        }

        stats_names = list(weight_stats.keys())
        stats_values = list(weight_stats.values())

        bars = ax14.bar(stats_names, stats_values, alpha=0.7)
        ax14.set_ylabel('Weight Value')
        ax14.set_title('Weight Statistics')
        ax14.grid(True, alpha=0.3)

        # Add value labels
        for bar, val in zip(bars, stats_values):
            ax14.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(stats_values) * 0.01,
                     f'{val:.4f}', ha='center', va='bottom', fontsize=8)

        # Condition importance ranking
        ax15 = plt.subplot(4, 4, 15)
        top_10_weights = weights_df.head(10)['weight'].values
        positions = np.arange(len(top_10_weights))

        ax15.plot(positions, top_10_weights, 'bo-', linewidth=2, markersize=6)
        ax15.set_xlabel('Rank')
        ax15.set_ylabel('Weight Value')
        ax15.set_title('Weight Importance Ranking')
        ax15.grid(True, alpha=0.3)

        # Final summary
        ax16 = plt.subplot(4, 4, 16)
        ax16.axis('off')

        top_condition = weights_df.iloc[0]
        final_summary = f"""
Top Weighted Condition:
{top_condition['condition']}
Weight: {top_condition['weight']:.4f}

Model Quality:
Validation AUC: {val_metrics['auc']:.4f}
{'Excellent' if val_metrics['auc'] > 0.8 else 'Good' if val_metrics['auc'] > 0.7 else 'Fair' if val_metrics['auc'] > 0.6 else 'Poor'}

Weight Concentration:
Top 10%: {weights_df.head(len(weights_df)//10)['weight'].sum():.2%}
Top 25%: {weights_df.head(len(weights_df)//4)['weight'].sum():.2%}

Data Efficiency:
{processed_shape[0]/original_shape[0]*100:.1f}% proteins retained
{processed_shape[1]/original_shape[1]*100:.1f}% conditions retained
        """

        ax16.text(0.05, 0.95, final_summary, transform=ax16.transAxes,
                 fontsize=9, verticalalignment='top',
                 bbox=dict(boxstyle='round', facecolor='lightgreen', alpha=0.8))

        plt.tight_layout()
        return fig

# Example usage and testing
if __name__ == "__main__":
    # Create sample data with missing values and structure
    np.random.seed(42)
    n_proteins, n_conditions = 100, 20

    protein_names = [f'Protein_{i:03d}' for i in range(n_proteins)]
    condition_names = [f'Condition_{i:02d}' for i in range(n_conditions)]

    # Generate structured data
    data_matrix = np.random.randn(n_proteins, n_conditions)

    # Add correlation structure to specific conditions
    for informative_cond in [0, 5, 10, 15]:
        for i in range(0, n_proteins, 10):
            end_idx = min(i + 5, n_proteins)
            base_value = np.random.randn()
            for j in range(i, end_idx):
                data_matrix[j, informative_cond] = base_value + 0.3 * np.random.randn()

    # Add missing values
    missing_mask = np.random.random((n_proteins, n_conditions)) < 0.08
    data_matrix[missing_mask] = np.nan

    # Create DataFrame
    proteomics_df = pd.DataFrame(data_matrix, index=protein_names, columns=condition_names)

    # Create sample interactions
    sample_interactions = []
    for i in range(0, n_proteins, 10):
        group_proteins = protein_names[i:min(i+5, n_proteins)]
        for j in range(len(group_proteins)):
            for k in range(j+1, len(group_proteins)):
                sample_interactions.append((group_proteins[j], group_proteins[k]))

    # Add random interactions
    for _ in range(30):
        p1, p2 = np.random.choice(protein_names, 2, replace=False)
        sample_interactions.append((p1, p2))

    print(f"Created test dataset:")
    print(f"Shape: {proteomics_df.shape}")
    print(f"Missing values: {proteomics_df.isnull().sum().sum()}")
    print(f"Interactions: {len(sample_interactions)}")

    # Test all methods
    methods = [
        ('ridge', {}),
        ('neural', {'max_iterations': 300}),
        ('empirical', {'empirical_method': 'variance'}),
        ('empirical', {'empirical_method': 'optimization'})
    ]

    for method, params in methods:
        print(f"\n=== Testing {method.upper()} Method ===")
        if method == 'empirical':
            print(f"Empirical strategy: {params.get('empirical_method', 'variance')}")

        try:
            results = learn_correlation_weights(
                data=proteomics_df,
                interactions=sample_interactions,
                learning_method=method,
                missing_strategy='knn',
                verbose=True,
                **params
            )

            print(f"\nTop 5 conditions:")
            print(results['weights_dataframe'].head())

            # Create visualization
            fig = ResultsVisualizer.plot_comprehensive_results(results)
            method_name = method
            if method == 'empirical':
                method_name += f" ({params.get('empirical_method', 'variance')})"
            plt.suptitle(f'Correlation Weight Learning Results - {method_name.title()}', fontsize=16)
            plt.show()

        except Exception as e:
            print(f"Error with {method}: {e}")

    print("\nAll tests completed!")
