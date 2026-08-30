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
    Model for predicting confidence from edge weights.
    Can be trained on known interactions and reused for future analyses.
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
        self.scaler = StandardScaler()
        self.is_fitted = False
        self.training_history = []
        self.feature_names = ['weight']

        self._initialize_model()

    def _initialize_model(self):
        """Initialize the base model"""
        if self.model_type == 'logistic':
            base_model = LogisticRegression(
                random_state=self.random_state,
                max_iter=1000
            )
        elif self.model_type == 'random_forest':
            base_model = RandomForestClassifier(
                n_estimators=100,
                random_state=self.random_state,
                max_depth=10
            )
        else:
            raise ValueError(f"Unknown model type: {self.model_type}")

        if self.calibrate:
            self.model = CalibratedClassifierCV(
                base_model,
                cv=5,
                method='isotonic'
            )
        else:
            self.model = base_model

    def fit(
        self,
        edges_df: pd.DataFrame,
        positive_interactions: List[Tuple[str, str]],
        negative_interactions: Optional[List[Tuple[str, str]]] = None,
        weight_col: str = 'weight',
        source_col: str = 'source',
        target_col: str = 'target',
        n_negative_samples: int = None,
        verbose: bool = True
    ) -> 'ConfidenceModel':
        """
        Train the confidence model on known positive (and optionally negative) interactions.

        Parameters
        ----------
        edges_df : pd.DataFrame
            DataFrame containing edges with weights
        positive_interactions : List[Tuple[str, str]]
            Known true positive interactions
        negative_interactions : List[Tuple[str, str]], optional
            Known true negative interactions. If None, samples from non-positive edges.
        weight_col : str
            Column name for edge weights
        source_col, target_col : str
            Column names for source and target nodes
        n_negative_samples : int, optional
            Number of negative samples to use. Defaults to len(positive_interactions)
        verbose : bool
            Print training progress

        Returns
        -------
        self : ConfidenceModel
            Fitted model
        """

        def normalize_pair(pair):
            """Ensure consistent ordering of node pairs"""
            return tuple(sorted([str(pair[0]), str(pair[1])]))

        # Create lookup sets
        positive_set = set(normalize_pair(p) for p in positive_interactions)

        if negative_interactions is not None:
            negative_set = set(normalize_pair(n) for n in negative_interactions)
        else:
            negative_set = set()

        # Build feature matrix and labels
        X_positive = []
        X_negative = []

        for _, row in edges_df.iterrows():
            pair = normalize_pair((row[source_col], row[target_col]))
            weight = row[weight_col]

            if pair in positive_set:
                X_positive.append([weight])
            elif negative_interactions is not None and pair in negative_set:
                X_negative.append([weight])
            elif negative_interactions is None and pair not in positive_set:
                X_negative.append([weight])

        if len(X_positive) == 0:
            raise ValueError("No positive interactions found in edges_df")

        if verbose:
            print(f"Found {len(X_positive)} positive edges in data")
            print(f"Found {len(X_negative)} candidate negative edges")

        # Sample negatives if needed
        if n_negative_samples is None:
            n_negative_samples = len(X_positive)

        if len(X_negative) > n_negative_samples:
            indices = np.random.choice(
                len(X_negative),
                n_negative_samples,
                replace=False
            )
            X_negative = [X_negative[i] for i in indices]

        # Combine into training data
        X = np.array(X_positive + X_negative)
        y = np.array([1] * len(X_positive) + [0] * len(X_negative))

        if verbose:
            print(f"Training on {len(X_positive)} positives, {len(X_negative)} negatives")

        # Scale features
        X_scaled = self.scaler.fit_transform(X)

        # Train model with cross-validation scoring
        cv_scores = cross_val_score(self.model, X_scaled, y, cv=5, scoring='roc_auc')

        if verbose:
            print(f"Cross-validation AUC: {cv_scores.mean():.3f} ± {cv_scores.std():.3f}")

        # Fit final model
        self.model.fit(X_scaled, y)
        self.is_fitted = True

        # Store training history
        self.training_history.append({
            'n_positive': len(X_positive),
            'n_negative': len(X_negative),
            'cv_auc_mean': cv_scores.mean(),
            'cv_auc_std': cv_scores.std()
        })

        return self

    def predict_confidence(
        self,
        edges_df: pd.DataFrame,
        weight_col: str = 'weight'
    ) -> np.ndarray:
        """
        Predict confidence scores for edges.

        Parameters
        ----------
        edges_df : pd.DataFrame
            DataFrame containing edges with weights
        weight_col : str
            Column name for edge weights

        Returns
        -------
        np.ndarray
            Confidence scores (probabilities) for each edge
        """
        if not self.is_fitted:
            raise RuntimeError("Model must be fitted before predicting. Call fit() first.")

        X = edges_df[[weight_col]].values
        X_scaled = self.scaler.transform(X)

        # Get probability of positive class
        confidence_scores = self.model.predict_proba(X_scaled)[:, 1]

        return confidence_scores

    def add_confidence_to_edges(
        self,
        edges_df: pd.DataFrame,
        weight_col: str = 'weight',
        confidence_col: str = 'model_confidence'
    ) -> pd.DataFrame:
        """
        Add confidence column to edges DataFrame.

        Parameters
        ----------
        edges_df : pd.DataFrame
            DataFrame containing edges
        weight_col : str
            Column name for edge weights
        confidence_col : str
            Name for the new confidence column

        Returns
        -------
        pd.DataFrame
            DataFrame with added confidence column
        """
        result_df = edges_df.copy()
        result_df[confidence_col] = self.predict_confidence(edges_df, weight_col)
        return result_df

    def save(self, filepath: str):
        """
        Save the trained model to disk.

        Parameters
        ----------
        filepath : str
            Path to save the model (recommend .pkl extension)
        """
        if not self.is_fitted:
            raise RuntimeError("Cannot save unfitted model")

        model_data = {
            'model': self.model,
            'scaler': self.scaler,
            'model_type': self.model_type,
            'calibrate': self.calibrate,
            'random_state': self.random_state,
            'feature_names': self.feature_names,
            'training_history': self.training_history,
            'is_fitted': self.is_fitted
        }

        with open(filepath, 'wb') as f:
            pickle.dump(model_data, f)

    @classmethod
    def load(cls, filepath: str) -> 'ConfidenceModel':
        """
        Load a trained model from disk.

        Parameters
        ----------
        filepath : str
            Path to the saved model

        Returns
        -------
        ConfidenceModel
            Loaded model ready for prediction
        """
        with open(filepath, 'rb') as f:
            model_data = pickle.load(f)

        # Create new instance without initializing model
        instance = cls.__new__(cls)
        instance.model = model_data['model']
        instance.scaler = model_data['scaler']
        instance.model_type = model_data['model_type']
        instance.calibrate = model_data['calibrate']
        instance.random_state = model_data['random_state']
        instance.feature_names = model_data['feature_names']
        instance.training_history = model_data['training_history']
        instance.is_fitted = model_data['is_fitted']

        return instance

    def get_training_summary(self) -> Dict:
        """Get summary of model training"""
        if not self.training_history:
            return {'status': 'not trained'}

        latest = self.training_history[-1]
        return {
            'status': 'trained',
            'model_type': self.model_type,
            'calibrated': self.calibrate,
            'n_training_runs': len(self.training_history),
            'latest_training': latest
        }

def generate_negative_interactions(
    positive_interactions: List[Tuple[str, str]],
    filter_interactions: List[Tuple[str,str]] = None,
    negative_ratio: float = 2.0,
    strategy: str = 'random_pairs'
) -> List[Tuple[str, str]]:
    """
    Generate negative interactions from positive interaction proteins

    Args:
        positive_interactions: List of positive interaction pairs
        filter_interactions: List of other interactions to filter from negatives
        negative_ratio: Ratio of negatives to positives to generate. If 0 then returns
                        all possible pairs
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

    filter_set = set()
    if filter_interactions:
        for p1, p2 in filter_interactions:
            pair = tuple(sorted([p1, p2]))
            filter_set.add(pair)

    # Generate negative interactions
    n_negatives_needed = int(len(positive_interactions) * negative_ratio)
    negative_interactions = []

    if strategy == 'random_pairs':
        # Generate all possible pairs and exclude positives
        all_possible_pairs = []
        for i in range(n_proteins):
            for j in range(i + 1, n_proteins):
                pair = tuple(sorted([proteins[i], proteins[j]]))
                if pair not in positive_set and pair not in filter_set:
                    all_possible_pairs.append(pair)

        # Randomly sample from possible negatives
        if len(all_possible_pairs) < n_negatives_needed:
            print(f"Warning: Only {len(all_possible_pairs)} possible negative pairs available, "
                  f"requested {n_negatives_needed}")
            negative_interactions = all_possible_pairs
        elif negative_ratio == 0:
            print('Using all possible pairs as negatives')
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

# helper function to use column 1 as protein_col1,
#                        column 2 as protein_col2,
#                        column 3 as weight
# As input from a result object (since we don't know
#    a priori what the column names are)
def calculate_edge_confidence_default(edges_df, positive_interactions, **kwargs):
    colnames=edges_df.columns
    kwargs['protein_col1'] = colnames[0]
    kwargs['protein_col2'] = colnames[1]
    kwargs['weight_col'] = colnames[2]
    return(calculate_edge_confidence(edges_df, positive_interactions, **kwargs))

def calculate_edge_confidence(
    edges_df: pd.DataFrame,
    positive_interactions: List[Tuple[str, str]],
    negative_interactions: List[Tuple[str, str]] = None,
    exclude_negative_interactions: List[Tuple[str, str]] = None,
    protein_col1: str = 'protein1',
    protein_col2: str = 'protein2',
    weight_col: str = 'weight',
    calculate_limit: int = 10000,
    return_all: bool = False,
    confidence_metric: str = 'ppv',
    additional_metrics: List[str] = None,
    min_threshold_samples: int = 1,
    min_counts: int = 3,
    negative_ratio: int = 0,
    normalize_pairs: bool = False,
    extrapolate_confidence: bool = False,
    verbose: bool = True,
    **kwargs
) -> pd.DataFrame:
    """
    Calculate confidence scores for edges based on positive/negative interaction lists

    Args:
        edges_df: DataFrame with protein pairs and weights
        positive_interactions: List of (protein1, protein2) tuples for known positives
        negative_interactions: List of (protein1, protein2) tuples for known negatives
        exclude_negative_interactions: List of (protein1, protein2) tuples to exclude from random negatives
        protein_col1: Column name for first protein
        protein_col2: Column name for second protein
        weight_col: Column name for edge weights
        calculate_limit: Only calculate confidence for the top N scoring edges
        return_all: For calculate_limit if True will return all edges (w and w/o confidence)
        confidence_metric: Primary metric ('ppv', 'precision', 'recall', 'f1', 'accuracy', 'enrichment')
        additional_metrics: List of additional metrics to calculate
        min_threshold_samples: Minimum samples needed above threshold for reliable confidence
        min_counts: Minimum number of matching values used in association calculation
        normalize_pairs: Whether to normalize protein pair order (A,B) = (B,A)
        extrapolate_confidence: Whether to assign predictions max confidence if they're before confidence scores
        verbose: Whether to print progress information

    Returns:
        DataFrame with added confidence scores and metrics
    """

    # first make sure that the edges are sorted by weight
    edges_df = edges_df.sort_values(by=weight_col, ascending=False)

    # filter for edges that have more than min_count comparisons
    size_og = len(edges_df)
    edges_df = edges_df[edges_df['counts']>min_counts]
    if verbose:
        print(f'Filtered {size_og} edges to {len(edges_df)} with min_counts {min_counts}')

    # convert interactions to strings for comparison - this is only necessary
    #    if the interactions are not strings (e.g. int) which happens with some
    #    identifier types and is difficult to track down.
    positive_interactions = [tuple(map(str, t)) for t in positive_interactions]
    if negative_interactions:
        negative_interactions = [tuple(map(str, t)) for t in negative_interactions]
    if exclude_negative_interactions:
        exclude_negative_interactions = [tuple(map(str, t)) for t in exclude_negative_interactions]

    # these edge lists can be really big (easily 10s of millions of edges)
    # making this function *very* slow. An easy fix is to just calculate for
    # the top weights and leave the rest as is.
    if calculate_limit:
        merge_after = False
        # This ASSUMES THE edge list is ordered descending by weight
        #      should check this!
        if len(edges_df) > calculate_limit:
            if verbose:
                print(f'Limiting confidence calculation to {calculate_limit} of {len(edges_df)} possible edges')
            calc_part_df = edges_df.iloc[:calculate_limit, :]
            leave_part_df = edges_df.iloc[calculate_limit:, :]
            edges_df = calc_part_df
            merge_after = True

    if additional_metrics is None:
        additional_metrics = []

    # Validate inputs
    required_cols = [protein_col1, protein_col2, weight_col]
    missing_cols = [col for col in required_cols if col not in edges_df.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")

    if len(positive_interactions) == 0:
        raise ValueError("Must provide at least one positive interaction")

    # Create a copy to avoid modifying original
    result_df = edges_df.copy()

    # Normalize interaction pairs if requested
    def normalize_pair(pair):
        if normalize_pairs:
            return tuple(sorted([pair[0], pair[1]]))
        return pair

    has_positives = positive_interactions is not None and len(positive_interactions) > 0
    has_negatives = negative_interactions is not None and len(negative_interactions) > 0

    # Generate negatives if only positives provided
    if has_positives and not has_negatives:
        if verbose:
            print(f"Generating negative interactions from positive set...")

        negative_interactions = generate_negative_interactions(
            positive_interactions,
            filter_interactions=exclude_negative_interactions,
            negative_ratio=negative_ratio,
            strategy='random_pairs'
        )
        has_negatives = True

        if verbose:
            print(f"Generated {len(negative_interactions)} negative interactions")

    # Create sets of known interactions for fast lookup
    positive_set = set([normalize_pair(interaction) for interaction in positive_interactions])
    negative_set = set([normalize_pair(interaction) for interaction in negative_interactions])

    if verbose:
        print(f"Processing {len(edges_df)} edges...")
        print(f"Positive interactions: {len(positive_set)}")
        print(f"Negative interactions: {len(negative_set)}")

        # Check for overlap
        overlap = positive_set.intersection(negative_set)
        if overlap:
            print(f"Warning: {len(overlap)} interactions appear in both positive and negative sets")

    # Create normalized pairs for edges
    edge_pairs = []
    for _, row in result_df.iterrows():
        pair = normalize_pair((row[protein_col1], row[protein_col2]))
        edge_pairs.append(pair)

    result_df['_normalized_pair'] = edge_pairs

    # Identify which edges are in positive/negative sets
    result_df['in_positive_set'] = result_df['_normalized_pair'].isin(positive_set)
    result_df['in_negative_set'] = result_df['_normalized_pair'].isin(negative_set)
    result_df['in_known_set'] = result_df['in_positive_set'] | result_df['in_negative_set']

    if verbose:
        n_edges_in_positive = result_df['in_positive_set'].sum()
        n_edges_in_negative = result_df['in_negative_set'].sum()
        n_edges_in_known = result_df['in_known_set'].sum()
        print(f"Edges found in positive set: {n_edges_in_positive}")
        print(f"Edges found in negative set: {n_edges_in_negative}")
        print(f"Total edges with known labels: {n_edges_in_known}")
        print(f"Edges without labels: {len(result_df) - n_edges_in_known}")

    # Calculate confidence scores for each edge
    confidence_scores = []
    metric_scores = {metric: [] for metric in additional_metrics}
    n_samples_above = []
    n_positives_above = []
    n_negatives_above = []

    weights = result_df[weight_col].values

    for i, threshold in enumerate(weights):
        # Find edges with weight >= current threshold
        above_threshold_mask = weights >= threshold
        edges_above = result_df[above_threshold_mask]

        # Count positives and negatives above threshold
        positives_above = edges_above['in_positive_set'].sum()
        negatives_above = edges_above['in_negative_set'].sum()
        total_known_above = positives_above + negatives_above

        n_samples_above.append(total_known_above)
        n_positives_above.append(positives_above)
        n_negatives_above.append(negatives_above)

        # Calculate primary confidence metric
        if total_known_above < min_threshold_samples:
            # Not enough samples for reliable confidence
            confidence = np.nan
        else:
            if confidence_metric in ['ppv', 'precision']:
                # Positive Predictive Value / Precision
                confidence = positives_above / total_known_above if total_known_above > 0 else 0.0

            elif confidence_metric == 'enrichment':
                # Enrichment over background rate
                background_rate = len(positive_set) / (len(positive_set) + len(negative_set))
                observed_rate = positives_above / total_known_above if total_known_above > 0 else 0.0
                confidence = observed_rate / background_rate if background_rate > 0 else 0.0

            elif confidence_metric == 'recall':
                # Recall (sensitivity)
                confidence = positives_above / len(positive_set) if len(positive_set) > 0 else 0.0

            elif confidence_metric == 'f1':
                # F1 score
                precision = positives_above / total_known_above if total_known_above > 0 else 0.0
                recall = positives_above / len(positive_set) if len(positive_set) > 0 else 0.0
                confidence = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

            elif confidence_metric == 'accuracy':
                # Accuracy
                total_possible = len(positive_set) + len(negative_set)
                true_positives = positives_above
                true_negatives = len(negative_set) - negatives_above
                confidence = (true_positives + true_negatives) / total_possible if total_possible > 0 else 0.0

            else:
                raise ValueError(f"Unknown confidence metric: {confidence_metric}")

        confidence_scores.append(confidence)

        # Calculate additional metrics
        for metric in additional_metrics:
            if total_known_above < min_threshold_samples:
                metric_scores[metric].append(np.nan)
                continue

            if metric == 'ppv' or metric == 'precision':
                score = positives_above / total_known_above if total_known_above > 0 else 0.0
            elif metric == 'recall' or metric == 'sensitivity':
                score = positives_above / len(positive_set) if len(positive_set) > 0 else 0.0
            elif metric == 'specificity':
                score = (len(negative_set) - negatives_above) / len(negative_set) if len(negative_set) > 0 else 0.0
            elif metric == 'f1':
                precision = positives_above / total_known_above if total_known_above > 0 else 0.0
                recall = positives_above / len(positive_set) if len(positive_set) > 0 else 0.0
                score = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
            elif metric == 'accuracy':
                total_possible = len(positive_set) + len(negative_set)
                true_positives = positives_above
                true_negatives = len(negative_set) - negatives_above
                score = (true_positives + true_negatives) / total_possible if total_possible > 0 else 0.0
            elif metric == 'enrichment':
                background_rate = len(positive_set) / (len(positive_set) + len(negative_set))
                observed_rate = positives_above / total_known_above if total_known_above > 0 else 0.0
                score = observed_rate / background_rate if background_rate > 0 else 0.0
            elif metric == 'lift':
                # Lift = (true positive rate) / (positive rate)
                tpr = positives_above / len(positive_set) if len(positive_set) > 0 else 0.0
                positive_rate = len(positive_set) / (len(positive_set) + len(negative_set))
                score = tpr / positive_rate if positive_rate > 0 else 0.0
            elif metric == 'odds_ratio':
                # Odds ratio
                tp = positives_above
                fp = negatives_above
                fn = len(positive_set) - positives_above
                tn = len(negative_set) - negatives_above

                if tp * tn == 0 or fp * fn == 0:
                    score = np.nan  # Undefined odds ratio
                else:
                    score = (tp * tn) / (fp * fn)
            else:
                raise ValueError(f"Unknown additional metric: {metric}")

            metric_scores[metric].append(score)

    # Add confidence and additional metrics to dataframe
    #result_df[f'confidence_{confidence_metric}'] = confidence_scores
    result_df['confidence'] = confidence_scores

    # we treat everything above the confidence line as having
    # maximum confidence - a reasonable, though debatable strategy
    if extrapolate_confidence:
        if verbose:
            print("Extrapolating maximum confidence to unassigned values")
        max_conf = max(result_df['confidence'].fillna(0))
        result_df['confidence'] = result_df['confidence'].fillna(max_conf)

    for metric in additional_metrics:
        result_df[f'{metric}_score'] = metric_scores[metric]

    # Add supporting information
    result_df['n_samples_above_threshold'] = n_samples_above
    result_df['n_positives_above_threshold'] = n_positives_above
    result_df['n_negatives_above_threshold'] = n_negatives_above

    # Clean up temporary columns
    result_df = result_df.drop(['_normalized_pair',], axis=1)

    if verbose:
        valid_confidences = ~np.isnan(confidence_scores)
        if np.any(valid_confidences):
            print(f"\nConfidence Statistics ({confidence_metric}):")
            print(f"  Valid confidence scores: {np.sum(valid_confidences)}")
            print(f"  Mean confidence: {np.nanmean(confidence_scores):.4f}")
            print(f"  Median confidence: {np.nanmedian(confidence_scores):.4f}")
            print(f"  Min confidence: {np.nanmin(confidence_scores):.4f}")
            print(f"  Max confidence: {np.nanmax(confidence_scores):.4f}")
        else:
            print("Warning: No valid confidence scores calculated")

    # this leaves all the extra columns in the second part as Nan-s,
    #      which might muck things up
    if calculate_limit and merge_after and return_all:
        result_df = pd.concat([result_df, leave_part_df], ignore_index=True)

    return result_df

def calculate_edge_confidence_with_model(
    edges_df: pd.DataFrame,
    model: ConfidenceModel = None,
    positive_interactions: List[Tuple] = None,
    weight_col: str = 'weight',
    source_col: str = 'source',
    target_col: str = 'target',
    train_new_model: bool = False,
    model_save_path: str = None,
    verbose: bool = True
) -> pd.DataFrame:
    """
    Calculate edge confidence using either a pre-trained model or by training a new one.

    Parameters
    ----------
    edges_df : pd.DataFrame
        Edge list with weights
    model : ConfidenceModel, optional
        Pre-trained model. If None and train_new_model=True, trains a new model.
    positive_interactions : List[Tuple], optional
        Known positive interactions (required if train_new_model=True)
    train_new_model : bool
        Whether to train a new model if none provided
    model_save_path : str, optional
        If provided, saves the trained model to this path
    verbose : bool
        Print progress information

    Returns
    -------
    pd.DataFrame
        Edges with confidence scores added
    """

    if model is not None and model.is_fitted:
        if verbose:
            print("Using pre-trained confidence model")
        return model.add_confidence_to_edges(
            edges_df,
            weight_col=weight_col
        )

    if train_new_model:
        if positive_interactions is None:
            raise ValueError(
                "positive_interactions required when train_new_model=True"
            )

        if verbose:
            print("Training new confidence model...")

        model = ConfidenceModel(model_type='logistic', calibrate=True)
        model.fit(
            edges_df,
            positive_interactions=positive_interactions,
            weight_col=weight_col,
            source_col=source_col,
            target_col=target_col,
            verbose=verbose
        )

        if model_save_path:
            model.save(model_save_path)
            if verbose:
                print(f"Model saved to {model_save_path}")

        return model.add_confidence_to_edges(edges_df, weight_col=weight_col)

    # Fall back to default calculation without model
    if verbose:
        print("No model provided, using default confidence calculation")

    return calculate_edge_confidence_default(
        edges_df,
        positive_interactions=positive_interactions,
        weight_col=weight_col
    )
