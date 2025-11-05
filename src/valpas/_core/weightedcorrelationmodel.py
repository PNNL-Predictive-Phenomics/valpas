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

class WeightedCorrelationCalculator:
    """Calculate weighted correlations """

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

    def __init__(self, correlation_method: str = 'pearson', correlation_missing_handling: str = 'pairwise'):
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
            'removed_proteins': removed_proteins,
            'original_data_shape': data.shape,
            'processed_data_shape': processed_data.shape,
            'config': {
                'learning_method': learning_method,
                'correlation_method': self.correlation_method,
                'correlation_missing_handling': self.correlation_missing_handling,
                'train_split': train_split,
                'n_random_negatives': n_random_negatives,
                'neural_config': neural_config if learning_method == 'neural' else None,
                'ridge_config': ridge_config if learning_method == 'ridge' else None,
                'empirical_method': empirical_method if learning_method == 'empirical' else None
            }
        }

# Main function wrapper for easy use
def learn_correlation_weights(data: pd.DataFrame, interactions: List[Tuple[str, str]],
                            learning_method: str = 'ridge', **kwargs) -> Dict:
    """
    Main function to learn correlation weights

    Args:
        data: DataFrame with proteins as rows, conditions as columns
        interactions: List of (protein1, protein2) known interactions
        learning_method: 'ridge', 'neural', or 'empirical'
        **kwargs: Additional parameters

    Returns:
        Dictionary with complete results
    """
    learner = CorrelationWeightLearner(
        correlation_method=kwargs.get('correlation_method', 'pearson'),
        correlation_missing_handling=kwargs.get('correlation_missing_handling', 'pairwise')
    )

    return learner.learn_weights(
        data=data,
        interactions=interactions,
        learning_method=learning_method,
        # **kwargs
    )
