import torch
import torch.nn as nn
import torch.optim as optim
import pandas as pd
import numpy as np
from sklearn.linear_model import Ridge
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score, average_precision_score, precision_recall_curve, roc_curve
from sklearn.preprocessing import StandardScaler
from typing import List, Tuple, Dict, Union, Optional, Callable
import matplotlib.pyplot as plt
import seaborn as sns
from scipy.stats import pearsonr, spearmanr
import warnings
warnings.filterwarnings('ignore')

def weighted_correlation_matrix(
    data: np.ndarray,
    weights: np.ndarray,
    method: str = 'pearson'
) -> np.ndarray:
    """
    Calculate weighted correlation matrix between proteins

    Args:
        data: Array of shape (n_proteins, n_conditions)
        weights: Array of shape (n_conditions,) with weights for each condition
        method: 'pearson' or 'spearman'

    Returns:
        Weighted correlation matrix of shape (n_proteins, n_proteins)
    """
    n_proteins, n_conditions = data.shape

    if not weights is None:
        # Normalize weights
        weights = np.abs(weights)  # Ensure positive weights
        weights = weights / np.sum(weights)  # Normalize to sum to 1

        # Weight the data
        weighted_data = data * np.sqrt(weights).reshape(1, -1)
    else:
        # calculate unweighted correlation
        weighted_data = data

    if method == 'pearson':
        # Calculate weighted Pearson correlation
        correlation_matrix = np.corrcoef(weighted_data)
    elif method == 'spearman':
        # For Spearman, we need to rank the weighted data
        from scipy.stats import rankdata
        ranked_data = np.apply_along_axis(rankdata, axis=1, arr=weighted_data)
        correlation_matrix = np.corrcoef(ranked_data)
    else:
        raise ValueError("method must be 'pearson' or 'spearman'")

    # Handle NaN values
    correlation_matrix = np.nan_to_num(correlation_matrix, nan=0.0)

    return correlation_matrix

def extract_interaction_scores(
    correlation_matrix: np.ndarray,
    interactions: List[Tuple[int, int]],
    protein_to_idx: Dict[str, int] = None
) -> np.ndarray:
    """
    Extract correlation scores for specific protein interactions

    Args:
        correlation_matrix: Correlation matrix between proteins
        interactions: List of (protein1, protein2) tuples or (idx1, idx2) tuples
        protein_to_idx: Mapping from protein names to indices (if interactions use names)

    Returns:
        Array of correlation scores for the interactions
    """
    scores = []

    for interaction in interactions:
        if protein_to_idx is not None:
            # Convert protein names to indices
            idx1 = protein_to_idx.get(interaction[0], -1)
            idx2 = protein_to_idx.get(interaction[1], -1)

            if idx1 == -1 or idx2 == -1:
                continue  # Skip if protein not found
        else:
            idx1, idx2 = interaction

        # Get absolute correlation (strength of relationship)
        score = abs(correlation_matrix[idx1, idx2])
        scores.append(score)

    return np.array(scores)

def objective_function_auc(
    correlation_matrix: np.ndarray,
    positive_interactions: List[Tuple],
    negative_interactions: List[Tuple] = None,
    protein_to_idx: Dict[str, int] = None,
    n_random_negatives: int = None
) -> float:
    """
    Objective function based on AUC for distinguishing positive from negative interactions

    Args:
        correlation_matrix: Weighted correlation matrix
        positive_interactions: List of known positive interactions
        negative_interactions: List of known negative interactions
        protein_to_idx: Mapping from protein names to indices
        n_random_negatives: Number of random negative interactions to generate

    Returns:
        AUC score (to be maximized)
    """
    # Get scores for positive interactions
    positive_scores = extract_interaction_scores(
        correlation_matrix, positive_interactions, protein_to_idx
    )

    if len(positive_scores) == 0:
        return 0.0

    # Get scores for negative interactions
    if negative_interactions is not None:
        negative_scores = extract_interaction_scores(
            correlation_matrix, negative_interactions, protein_to_idx
        )
    else:
        # Generate random negative interactions
        n_proteins = correlation_matrix.shape[0]
        if n_random_negatives is None:
            n_random_negatives = len(positive_interactions) * 2

        # Sample random pairs that are not in positive interactions
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

        negative_scores = extract_interaction_scores(correlation_matrix, negative_pairs)

    if len(negative_scores) == 0:
        return 0.0

    # Create labels and scores for AUC calculation
    y_true = np.concatenate([np.ones(len(positive_scores)), np.zeros(len(negative_scores))])
    y_scores = np.concatenate([positive_scores, negative_scores])

    if len(np.unique(y_true)) < 2:
        return 0.0

    try:
        auc = roc_auc_score(y_true, y_scores)
        return auc
    except:
        return 0.0

class NeuralWeightLearner(nn.Module):
    """Neural network for learning condition weights"""

    def __init__(
        self,
        n_conditions: int,
        hidden_dims: List[int] = [64, 32],
        dropout_rate: float = 0.1,
        activation: str = 'relu'
    ):
        super().__init__()

        self.n_conditions = n_conditions

        # Build network
        layers = []
        prev_dim = n_conditions

        for hidden_dim in hidden_dims:
            layers.extend([
                nn.Linear(prev_dim, hidden_dim),
                nn.ReLU() if activation == 'relu' else nn.Tanh(),
                nn.Dropout(dropout_rate)
            ])
            prev_dim = hidden_dim

        # Output layer - weights for each condition
        layers.append(nn.Linear(prev_dim, n_conditions))
        layers.append(nn.Softmax(dim=-1))  # Ensure weights sum to 1

        self.network = nn.Sequential(*layers)

        # Initialize with uniform weights
        self.init_weights()

    def init_weights(self):
        """Initialize network to output uniform weights"""
        with torch.no_grad():
            # Set final layer to output uniform distribution
            final_layer = list(self.network.children())[-2]  # Before softmax
            final_layer.weight.fill_(0.0)
            final_layer.bias.fill_(0.0)

    def forward(self, x=None):
        """Forward pass - x can be None since we learn global weights"""
        if x is None:
            # Use a dummy input vector
            x = torch.ones(1, self.n_conditions)

        weights = self.network(x)
        return weights.squeeze()

def learn_correlation_weights(
    data: pd.DataFrame,
    interactions: List[Tuple[str, str]],
    learning_method: str = 'ridge',
    correlation_method: str = 'pearson',
    train_split: float = 0.7,
    random_state: int = 42,
    n_random_negatives: int = None,
    neural_config: Dict = None,
    ridge_config: Dict = None,
    max_iterations: int = 1000,
    verbose: bool = True
) -> Dict:
    """
    Learn optimal weights for weighted correlation to predict protein interactions

    Args:
        data: DataFrame with proteins as rows, conditions as columns
        interactions: List of (protein1, protein2) tuples representing known interactions
        learning_method: 'ridge' or 'neural'
        correlation_method: 'pearson' or 'spearman'
        train_split: Fraction of interactions to use for training
        random_state: Random seed
        n_random_negatives: Number of random negative interactions
        neural_config: Configuration for neural network
        ridge_config: Configuration for ridge regression
        max_iterations: Maximum training iterations
        verbose: Whether to print progress

    Returns:
        Dictionary with model, weights, matrices, and performance metrics
    """

    np.random.seed(random_state)
    torch.manual_seed(random_state)

    # for now fill all Nan with 0
    # FIXME: we need to be able to handle missing values better
    data = data.fillna(0)

    # Prepare data
    protein_names = data.index.tolist()
    condition_names = data.columns.tolist()
    protein_to_idx = {protein: idx for idx, protein in enumerate(protein_names)}
    data_array = data.values
    n_proteins, n_conditions = data_array.shape

    if verbose:
        print(f"Data shape: {data_array.shape}")
        print(f"Number of interactions: {len(interactions)}")

    # Filter interactions to only include proteins in our data
    valid_interactions = []
    for interaction in interactions:
        if interaction[0] in protein_to_idx and interaction[1] in protein_to_idx:
            valid_interactions.append(interaction)

    if verbose:
        print(f"Valid interactions in data: {len(valid_interactions)}")

    # Split interactions into train/validation
    train_interactions, val_interactions = train_test_split(
        valid_interactions,
        train_size=train_split,
        random_state=random_state
    )

    if verbose:
        print(f"Training interactions: {len(train_interactions)}")
        print(f"Validation interactions: {len(val_interactions)}")

    # Set default configurations
    if neural_config is None:
        neural_config = {
            'hidden_dims': [64, 32],
            'dropout_rate': 0.1,
            'learning_rate': 0.01,
            'weight_decay': 1e-4
        }

    if ridge_config is None:
        ridge_config = {
            'alpha': 1.0,
            'max_iter': max_iterations
        }

    if n_random_negatives is None:
        n_random_negatives = len(train_interactions) * 2

    # Training history
    training_history = {
        'iteration': [],
        'train_objective': [],
        'weights': []
    }

    # first evaluate using normal correlation
    starting_validation_metrics = validate_correlation_predictions(
        weighted_correlation_matrix(data, None),
        val_interactions,
        protein_to_idx,
        n_random_negatives=len(val_interactions) * 2
    )

    starting_train_metrics = validate_correlation_predictions(
        weighted_correlation_matrix(data, None),
        train_interactions,
        protein_to_idx,
        n_random_negatives=len(train_interactions) * 2
    )

    if learning_method == 'ridge':
        # Ridge regression approach
        if verbose:
            print("Training with Ridge Regression...")

        # Create features for ridge regression
        # For each interaction, create a feature vector based on condition weights
        X_train = []
        y_train = []

        # Positive interactions
        for interaction in train_interactions:
            idx1 = protein_to_idx[interaction[0]]
            idx2 = protein_to_idx[interaction[1]]

            # Feature: element-wise product of protein expressions
            feature = data_array[idx1] * data_array[idx2]
            X_train.append(feature)
            y_train.append(1.0)

        # Generate negative interactions
        positive_set = set()
        for interaction in train_interactions:
            idx1 = protein_to_idx[interaction[0]]
            idx2 = protein_to_idx[interaction[1]]
            positive_set.add((min(idx1, idx2), max(idx1, idx2)))

        negative_pairs = []
        attempts = 0
        while len(negative_pairs) < n_random_negatives and attempts < n_random_negatives * 10:
            i, j = np.random.choice(n_proteins, 2, replace=False)
            pair = (min(i, j), max(i, j))
            if pair not in positive_set:
                negative_pairs.append((i, j))
            attempts += 1

        # Negative interactions
        for i, j in negative_pairs:
            feature = data_array[i] * data_array[j]
            X_train.append(feature)
            y_train.append(0.0)

        X_train = np.array(X_train)
        y_train = np.array(y_train)

        # Standardize features
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)

        # Train ridge regression
        ridge_model = Ridge(alpha=ridge_config['alpha'], max_iter=ridge_config['max_iter'])
        ridge_model.fit(X_train_scaled, y_train)

        # Extract weights (use absolute values)
        learned_weights = np.abs(ridge_model.coef_)
        learned_weights = learned_weights / np.sum(learned_weights)  # Normalize

        model = {
            'ridge_model': ridge_model,
            'scaler': scaler,
            'type': 'ridge'
        }

        # Calculate training objective
        train_corr_matrix = weighted_correlation_matrix(data_array, learned_weights, correlation_method)
        train_objective = objective_function_auc(
            train_corr_matrix, train_interactions,
            protein_to_idx=protein_to_idx, n_random_negatives=n_random_negatives
        )

        training_history['iteration'] = [0]
        training_history['train_objective'] = [train_objective]
        training_history['weights'] = [learned_weights.copy()]

    elif learning_method == 'neural':
        # Neural network approach
        if verbose:
            print("Training with Neural Network...")

        model_nn = NeuralWeightLearner(
            n_conditions=n_conditions,
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

            # Get current weights
            weights = model_nn()
            weights_np = weights.detach().numpy()

            # Calculate weighted correlation matrix
            corr_matrix = weighted_correlation_matrix(data_array, weights_np, correlation_method)

            # Calculate objective
            objective = objective_function_auc(
                corr_matrix, train_interactions,
                protein_to_idx=protein_to_idx, n_random_negatives=n_random_negatives
            )

            # Convert to loss (negative objective since we want to maximize)
            loss = -torch.tensor(objective, requires_grad=True)

            # Backward pass
            loss.backward()
            optimizer.step()

            # Track best weights
            if objective > best_objective:
                best_objective = objective
                best_weights = weights_np.copy()

            # Store history
            if iteration % 50 == 0 or iteration == max_iterations - 1:
                training_history['iteration'].append(iteration)
                training_history['train_objective'].append(objective)
                training_history['weights'].append(weights_np.copy())

                if verbose and iteration % 200 == 0:
                    print(f"Iteration {iteration}: Objective = {objective:.4f}")

        learned_weights = best_weights
        model = {
            'neural_model': model_nn,
            'type': 'neural'
        }

    else:
        raise ValueError("learning_method must be 'ridge' or 'neural'")

    # Calculate final weighted correlation matrix
    final_correlation_matrix = weighted_correlation_matrix(data_array, learned_weights, correlation_method)

    # Create weighted correlation DataFrame
    weighted_corr_df = pd.DataFrame(
        final_correlation_matrix,
        index=protein_names,
        columns=protein_names
    )

    # Final validation
    validation_metrics = validate_correlation_predictions(
        final_correlation_matrix,
        val_interactions,
        protein_to_idx,
        n_random_negatives=len(val_interactions) * 2
    )

    # Training metrics
    training_metrics = validate_correlation_predictions(
        final_correlation_matrix,
        train_interactions,
        protein_to_idx,
        n_random_negatives=len(train_interactions) * 2
    )

    if verbose:
        print(f"\nUnweighted results:")
        print(f"Unweighted val AUC: {starting_validation_metrics['auc']:.4f}")
        print(f"Unweighted val AP: {starting_validation_metrics['average_precision']:.4f}")
        print(f"Unweighted train AUC: {starting_train_metrics['auc']:.4f}")
        print(f"Unweighted train AP: {starting_train_metrics['average_precision']:.4f}")
        print(f"\nFinal Results:")
        print(f"Training AUC: {training_metrics['auc']:.4f}")
        print(f"Validation AUC: {validation_metrics['auc']:.4f}")
        print(f"Training AP: {training_metrics['average_precision']:.4f}")
        print(f"Validation AP: {validation_metrics['average_precision']:.4f}")

    # Create weights DataFrame
    weights_df = pd.DataFrame({
        'condition': condition_names,
        'weight': learned_weights
    }).sort_values('weight', ascending=False)

    results = {
        'model': model,
        'learned_weights': learned_weights,
        'weights_dataframe': weights_df,
        'weighted_correlation_matrix': weighted_corr_df,
        'training_metrics': training_metrics,
        'validation_metrics': validation_metrics,
        'training_history': training_history,
        'train_interactions': train_interactions,
        'val_interactions': val_interactions,
        'config': {
            'learning_method': learning_method,
            'correlation_method': correlation_method,
            'train_split': train_split,
            'n_random_negatives': n_random_negatives,
            'neural_config': neural_config if learning_method == 'neural' else None,
            'ridge_config': ridge_config if learning_method == 'ridge' else None
        }
    }

    return results

def validate_correlation_predictions(
    correlation_matrix: np.ndarray,
    interactions: List[Tuple[str, str]],
    protein_to_idx: Dict[str, int],
    n_random_negatives: int = None
) -> Dict:
    """
    Validate correlation predictions against known interactions

    Args:
        correlation_matrix: Correlation matrix to evaluate
        interactions: Known interactions for validation
        protein_to_idx: Mapping from protein names to indices
        n_random_negatives: Number of random negatives to generate

    Returns:
        Dictionary with performance metrics
    """

    # Get positive scores
    positive_scores = extract_interaction_scores(correlation_matrix, interactions, protein_to_idx)

    if len(positive_scores) == 0:
        return {'auc': 0.0, 'average_precision': 0.0, 'n_positive': 0, 'n_negative': 0}

    # Generate negative interactions
    n_proteins = correlation_matrix.shape[0]
    if n_random_negatives is None:
        n_random_negatives = len(interactions) * 2

    positive_set = set()
    for interaction in interactions:
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

    negative_scores = extract_interaction_scores(correlation_matrix, negative_pairs)

    # Calculate metrics
    y_true = np.concatenate([np.ones(len(positive_scores)), np.zeros(len(negative_scores))])
    y_scores = np.concatenate([positive_scores, negative_scores])

    try:
        auc = roc_auc_score(y_true, y_scores)
        ap = average_precision_score(y_true, y_scores)

        # Additional metrics
        fpr, tpr, _ = roc_curve(y_true, y_scores)
        precision, recall, _ = precision_recall_curve(y_true, y_scores)

        metrics = {
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
        print(f"Error calculating metrics: {e}")
        metrics = {
            'auc': 0.0,
            'average_precision': 0.0,
            'n_positive': len(positive_scores),
            'n_negative': len(negative_scores)
        }

    return metrics
