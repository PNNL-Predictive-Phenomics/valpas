import pandas as pd
import numpy as np
from typing import List, Tuple, Dict, Optional, Union, Any
from sklearn.metrics import precision_score, recall_score, f1_score, accuracy_score
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.preprocessing import StandardScaler
from sklearn.calibration import CalibratedClassifierCV
import pickle
import warnings
warnings.filterwarnings('ignore')

class ConfidenceModel:
    """
    Simple model for predicting confidence from edge weights
    """

    def __init__(
        self,
        model_type: str = 'logistic',
        calibrate: bool = True,
        random_state: int = 42
    ):
        self.model_type = model_type
        self.calibrate = calibrate
        self.random_state = random_state
        self.model = None
        self.scaler = None
        self.training_history = []
        self.feature_names = ['weight']

        self._initialize_model()

    def _initialize_model(self):
        """Initialize the base model"""
        if self.model_type == 'logistic':
            base_model = LogisticRegression(random_state=self.random_state)
        elif self.model_type == 'random_forest':
            base_model = RandomForestClassifier(
                n_estimators=100,
                random_state=self.random_state,
                max_depth=10
            )
        else:
            raise ValueError(f"Unknown model type: {self.model_type}")

        # Use calibrated classifier for better probability estimates
        if self.calibrate:
            self.model = CalibratedClassifierCV(base_model, cv=3)
        else:
            self.model = base_model

        self.scaler = StandardScaler()

    def _prepare_features(self, weights: np.ndarray) -> np.ndarray:
        """Prepare features from weights"""
        # For now, just use weight as primary feature
        # Could be extended to include weight transformations, statistics, etc.
        features = np.column_stack([
            weights,                           # Raw weight
            np.log(weights + 1e-8),           # Log weight
            weights ** 2,                      # Squared weight
            np.sqrt(weights),                  # Square root weight
            (weights > np.median(weights)).astype(int)  # Above median indicator
        ])

        self.feature_names = ['weight', 'log_weight', 'weight_squared', 'sqrt_weight', 'above_median']
        return features

    def fit(self, weights: np.ndarray, labels: np.ndarray, update_existing: bool = False):
        """
        Fit the model to weight-label data

        Args:
            weights: Array of edge weights
            labels: Binary labels (1 for positive, 0 for negative)
            update_existing: Whether to update existing model or train from scratch
        """
        X = self._prepare_features(weights)

        if update_existing and hasattr(self, 'model') and self.model is not None:
            # For updating, we'll retrain on combined data
            # In practice, you might want more sophisticated incremental learning
            print("Note: Retraining model with combined data (incremental learning not implemented)")

        # Fit scaler
        if not update_existing or self.scaler is None:
            X_scaled = self.scaler.fit_transform(X)
        else:
            X_scaled = self.scaler.transform(X)

        # Fit model
        self.model.fit(X_scaled, labels)

        # Store training info
        training_info = {
            'n_samples': len(weights),
            'n_positive': np.sum(labels),
            'n_negative': np.sum(labels == 0),
            'weight_range': [np.min(weights), np.max(weights)],
            'positive_rate': np.mean(labels)
        }

        # Cross-validation score
        cv_scores = cross_val_score(self.model, X_scaled, labels, cv=3, scoring='roc_auc')
        training_info['cv_auc_mean'] = np.mean(cv_scores)
        training_info['cv_auc_std'] = np.std(cv_scores)

        self.training_history.append(training_info)

        return training_info

    def predict_confidence(self, weights: np.ndarray) -> np.ndarray:
        """Predict confidence scores for given weights"""
        if self.model is None:
            raise ValueError("Model has not been trained yet")

        X = self._prepare_features(weights)
        X_scaled = self.scaler.transform(X)

        # Get probability of positive class
        confidence_scores = self.model.predict_proba(X_scaled)[:, 1]
        return confidence_scores

    def get_feature_importance(self) -> Dict[str, float]:
        """Get feature importance (if supported by model)"""
        if self.model is None:
            return {}

        # For calibrated classifiers, get base estimator
        base_model = self.model.base_estimator if hasattr(self.model, 'base_estimator') else self.model

        if hasattr(base_model, 'feature_importances_'):
            importance = base_model.feature_importances_
        elif hasattr(base_model, 'coef_'):
            importance = np.abs(base_model.coef_[0])
        else:
            return {}

        return dict(zip(self.feature_names, importance))

    def save_model(self, filepath: str):
        """Save model to file"""
        model_data = {
            'model': self.model,
            'scaler': self.scaler,
            'model_type': self.model_type,
            'calibrate': self.calibrate,
            'training_history': self.training_history,
            'feature_names': self.feature_names
        }

        with open(filepath, 'wb') as f:
            pickle.dump(model_data, f)

    @classmethod
    def load_model(cls, filepath: str):
        """Load model from file"""
        with open(filepath, 'rb') as f:
            model_data = pickle.load(f)

        instance = cls(
            model_type=model_data['model_type'],
            calibrate=model_data['calibrate']
        )

        instance.model = model_data['model']
        instance.scaler = model_data['scaler']
        instance.training_history = model_data['training_history']
        instance.feature_names = model_data['feature_names']

        return instance

def generate_negative_interactions(
    positive_interactions: List[Tuple[str, str]],
    negative_ratio: float = 2.0,
    strategy: str = 'random_pairs'
) -> List[Tuple[str, str]]:
    """
    Generate negative interactions from positive interaction proteins

    Args:
        positive_interactions: List of positive interaction pairs
        negative_ratio: Ratio of negatives to positives to generate
        strategy: Strategy for generating negatives ('random_pairs', 'non_interacting')

    Returns:
        List of negative interaction pairs
    """

    # Get all unique proteins from positive interactions
    proteins = set()
    for p1, p2 in positive_interactions:
        proteins.add(p1)
        proteins.add(p2)

    proteins = list(proteins)
    n_proteins = len(proteins)

    if n_proteins < 2:
        raise ValueError("Need at least 2 proteins to generate negative interactions")

    # Create set of positive pairs for exclusion
    positive_set = set()
    for p1, p2 in positive_interactions:
        pair = tuple(sorted([p1, p2]))
        positive_set.add(pair)

    # Generate negative interactions
    n_negatives_needed = int(len(positive_interactions) * negative_ratio)
    negative_interactions = []

    if strategy == 'random_pairs':
        # Generate all possible pairs and exclude positives
        all_possible_pairs = []
        for i in range(n_proteins):
            for j in range(i + 1, n_proteins):
                pair = tuple(sorted([proteins[i], proteins[j]]))
                if pair not in positive_set:
                    all_possible_pairs.append(pair)

        # Randomly sample from possible negatives
        if len(all_possible_pairs) < n_negatives_needed:
            print(f"Warning: Only {len(all_possible_pairs)} possible negative pairs available, "
                  f"requested {n_negatives_needed}")
            negative_interactions = all_possible_pairs
        else:
            negative_interactions = list(np.random.choice(
                len(all_possible_pairs),
                size=n_negatives_needed,
                replace=False
            ))
            negative_interactions = [all_possible_pairs[i] for i in negative_interactions]

    elif strategy == 'non_interacting':
        # More sophisticated strategy could go here
        # For now, fall back to random pairs
        return generate_negative_interactions(positive_interactions, negative_ratio, 'random_pairs')

    return negative_interactions

def calculate_edge_confidence(
    edges_df: pd.DataFrame,
    positive_interactions: Optional[List[Tuple[str, str]]] = None,
    negative_interactions: Optional[List[Tuple[str, str]]] = None,
    input_model: Optional[ConfidenceModel] = None,
    generate_model: bool = True,
    model_type: str = 'logistic',
    protein_col1: str = 'protein1',
    protein_col2: str = 'protein2',
    weight_col: str = 'weight',
    confidence_metric: str = 'ppv',
    additional_metrics: List[str] = None,
    min_threshold_samples: int = 10,
    negative_ratio: float = 2.0,
    normalize_pairs: bool = True,
    verbose: bool = True
) -> Tuple[pd.DataFrame, Optional[ConfidenceModel]]:
    """
    Enhanced edge confidence calculation with model learning and application

    Args:
        edges_df: DataFrame with protein pairs and weights
        positive_interactions: List of known positive interactions
        negative_interactions: List of known negative interactions (optional)
        input_model: Pre-trained confidence model (optional)
        generate_model: Whether to generate/train a model
        model_type: Type of model to train ('logistic', 'random_forest')
        protein_col1: Column name for first protein
        protein_col2: Column name for second protein
        weight_col: Column name for edge weights
        confidence_metric: Primary metric for threshold-based confidence
        additional_metrics: Additional metrics to calculate
        min_threshold_samples: Minimum samples for threshold-based confidence
        negative_ratio: Ratio of negatives to positives when auto-generating
        normalize_pairs: Whether to normalize protein pair order
        verbose: Whether to print progress

    Returns:
        Tuple of (DataFrame with confidence scores, trained/updated model)
    """

    if additional_metrics is None:
        additional_metrics = []

    # Validate inputs
    required_cols = [protein_col1, protein_col2, weight_col]
    missing_cols = [col for col in required_cols if col not in edges_df.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")

    result_df = edges_df.copy()
    model = input_model

    # Determine operation mode
    has_positives = positive_interactions is not None and len(positive_interactions) > 0
    has_negatives = negative_interactions is not None and len(negative_interactions) > 0
    has_model = input_model is not None

    if verbose:
        print(f"Operation mode analysis:")
        print(f"  Has positives: {has_positives}")
        print(f"  Has negatives: {has_negatives}")
        print(f"  Has input model: {has_model}")
        print(f"  Generate model: {generate_model}")

    # Generate negatives if only positives provided
    if has_positives and not has_negatives:
        if verbose:
            print(f"Generating negative interactions from positive set...")

        negative_interactions = generate_negative_interactions(
            positive_interactions,
            negative_ratio=negative_ratio,
            strategy='random_pairs'
        )
        has_negatives = True

        if verbose:
            print(f"Generated {len(negative_interactions)} negative interactions")

    # Model operations
    if has_positives and has_negatives and generate_model:
        # Train or update model

        # Normalize pairs for consistency
        def normalize_pair(pair):
            return tuple(sorted([pair[0], pair[1]])) if normalize_pairs else pair

        positive_set = set([normalize_pair(pair) for pair in positive_interactions])
        negative_set = set([normalize_pair(pair) for pair in negative_interactions])

        # Create edge pair mapping
        edge_pairs = []
        for _, row in result_df.iterrows():
            pair = normalize_pair((row[protein_col1], row[protein_col2]))
            edge_pairs.append(pair)

        result_df['_normalized_pair'] = edge_pairs

        # Find edges that are in training sets
        result_df['in_positive_set'] = result_df['_normalized_pair'].isin(positive_set)
        result_df['in_negative_set'] = result_df['_normalized_pair'].isin(negative_set)
        result_df['in_training_set'] = result_df['in_positive_set'] | result_df['in_negative_set']

        # Extract training data
        training_edges = result_df[result_df['in_training_set']]

        if len(training_edges) == 0:
            if verbose:
                print("Warning: No training edges found in edge data")
            training_weights = []
            training_labels = []
        else:
            training_weights = training_edges[weight_col].values
            training_labels = training_edges['in_positive_set'].astype(int).values

        if verbose:
            print(f"Training data: {len(training_weights)} edges")
            print(f"  Positives: {np.sum(training_labels)}")
            print(f"  Negatives: {np.sum(training_labels == 0)}")

        # Train or update model
        if len(training_weights) > 0:
            if not has_model:
                # Train new model
                if verbose:
                    print(f"Training new {model_type} model...")

                model = ConfidenceModel(model_type=model_type)
                training_info = model.fit(training_weights, training_labels)

                if verbose:
                    print(f"Model training completed:")
                    print(f"  CV AUC: {training_info['cv_auc_mean']:.4f} ± {training_info['cv_auc_std']:.4f}")
                    print(f"  Positive rate: {training_info['positive_rate']:.4f}")

            else:
                # Update existing model
                if verbose:
                    print("Updating existing model with new data...")

                training_info = model.fit(training_weights, training_labels, update_existing=True)

                if verbose:
                    print(f"Model update completed:")
                    print(f"  CV AUC: {training_info['cv_auc_mean']:.4f} ± {training_info['cv_auc_std']:.4f}")

        # Clean up temporary columns
        result_df = result_df.drop(['_normalized_pair', 'in_positive_set',
                                  'in_negative_set', 'in_training_set'], axis=1)

    # Apply model to predict confidence scores
    if model is not None:
        if verbose:
            print("Applying model to predict confidence scores...")

        model_confidence_scores = model.predict_confidence(result_df[weight_col].values)
        result_df['confidence_model'] = model_confidence_scores

        if verbose:
            print(f"Model confidence statistics:")
            print(f"  Mean: {np.mean(model_confidence_scores):.4f}")
            print(f"  Std: {np.std(model_confidence_scores):.4f}")
            print(f"  Range: [{np.min(model_confidence_scores):.4f}, {np.max(model_confidence_scores):.4f}]")

        # Get feature importance if available
        feature_importance = model.get_feature_importance()
        if feature_importance and verbose:
            print("Feature importance:")
            for feature, importance in feature_importance.items():
                print(f"  {feature}: {importance:.4f}")

    # Calculate threshold-based confidence if we have training data
    if has_positives and has_negatives:
        if verbose:
            print("Calculating threshold-based confidence...")

        # Use the original function for threshold-based confidence
        threshold_result = calculate_edge_confidence(
            edges_df=result_df.drop(columns=['confidence_model'] if 'confidence_model' in result_df.columns else []),
            positive_interactions=positive_interactions,
            negative_interactions=negative_interactions,
            protein_col1=protein_col1,
            protein_col2=protein_col2,
            weight_col=weight_col,
            confidence_metric=confidence_metric,
            additional_metrics=additional_metrics,
            min_threshold_samples=min_threshold_samples,
            normalize_pairs=normalize_pairs,
            verbose=False  # Avoid double output
        )

        # Merge threshold-based results
        threshold_cols = [col for col in threshold_result.columns if col not in result_df.columns]
        for col in threshold_cols:
            result_df[col] = threshold_result[col]

    return result_df, model
