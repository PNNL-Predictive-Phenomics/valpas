import torch
import torch.nn as nn
import torch.nn.functional as F
import pandas as pd
import numpy as np
import os

from torch.utils.data import Dataset, DataLoader
from sklearn.preprocessing import StandardScaler, RobustScaler
from sklearn.metrics.pairwise import cosine_similarity
import matplotlib.pyplot as plt
import seaborn as sns
from typing import Optional, Tuple, Dict, List, Union, Any
import warnings
import base64
from io import BytesIO
import json
from datetime import datetime

from .classes.analysisresults import AnalysisResults

warnings.filterwarnings('ignore')

class ProteomicsDataset(Dataset):
    """Dataset class for proteomics data with masking support"""

    def __init__(
        self,
        data: pd.DataFrame,
        scaler: Optional[Union[StandardScaler, RobustScaler]] = None,
        mask_probability: float = 0.15,
        scaling_method: str = 'standard'
    ):
        """
        Initialize proteomics dataset

        Args:
            data: DataFrame with proteins as rows, samples as columns
            scaler: Pre-fitted scaler, if None will fit new one
            mask_probability: Probability of masking each value during training
            scaling_method: 'standard', 'robust', or 'none'
        """
        self.original_data = data.copy()
        self.protein_names = data.index.tolist()
        self.sample_names = data.columns.tolist()
        self.mask_probability = mask_probability

        # Handle missing values
        if data.isnull().any().any():
            print(f"Warning: Found {data.isnull().sum().sum()} missing values, filling with median")
            data = data.fillna(data.median())

        # Scaling
        if scaling_method == 'none':
            self.scaler = None
            self.scaled_data = data.values
        else:
            if scaler is None:
                if scaling_method == 'standard':
                    self.scaler = StandardScaler()
                elif scaling_method == 'robust':
                    self.scaler = RobustScaler()
                else:
                    raise ValueError("scaling_method must be 'standard', 'robust', or 'none'")

                # Fit scaler on flattened data
                flat_data = data.values.flatten().reshape(-1, 1)
                self.scaler.fit(flat_data)
            else:
                self.scaler = scaler

            # Scale the data
            flat_scaled = self.scaler.transform(data.values.flatten().reshape(-1, 1))
            self.scaled_data = flat_scaled.reshape(data.shape)

        self.data_tensor = torch.FloatTensor(self.scaled_data)
        self.n_proteins, self.n_samples = self.data_tensor.shape

    def __len__(self):
        return 1  # We treat the entire matrix as one sample

    def __getitem__(self, idx):
        return self.data_tensor

    def create_masked_batch(self, batch_size: int = 1) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Create masked version of data for training

        Returns:
            masked_data: Data with some values masked (set to 0)
            mask: Boolean mask indicating which values were masked
            target: Original unmasked data
        """
        # Create random mask
        mask = torch.rand(self.n_proteins, self.n_samples) < self.mask_probability

        # Create masked data
        masked_data = self.data_tensor.clone()
        masked_data[mask] = 0  # Set masked values to 0

        return masked_data.unsqueeze(0), mask.unsqueeze(0), self.data_tensor.unsqueeze(0)

class BiDirectionalAutoencoder(nn.Module):
    """
    Autoencoder that learns from both protein and sample dimensions
    Uses separate encoders for protein embeddings and sample embeddings
    """

    def __init__(
        self,
        n_proteins: int,
        n_samples: int,
        protein_embedding_dim: int = 128,
        sample_embedding_dim: int = 64,
        hidden_dims: List[int] = [256, 128],
        dropout_rate: float = 0.1,
        activation: str = 'relu'
    ):
        super().__init__()

        self.n_proteins = n_proteins
        self.n_samples = n_samples
        self.protein_embedding_dim = protein_embedding_dim
        self.sample_embedding_dim = sample_embedding_dim

        # Activation function
        if activation == 'relu':
            self.activation = nn.ReLU()
        elif activation == 'tanh':
            self.activation = nn.Tanh()
        elif activation == 'elu':
            self.activation = nn.ELU()
        else:
            raise ValueError("activation must be 'relu', 'tanh', or 'elu'")

        # Protein encoder (encodes across samples for each protein)
        self.protein_encoder = nn.Sequential(
            nn.Linear(n_samples, hidden_dims[0]),
            self.activation,
            nn.Dropout(dropout_rate),
            nn.Linear(hidden_dims[0], hidden_dims[1]),
            self.activation,
            nn.Dropout(dropout_rate),
            nn.Linear(hidden_dims[1], protein_embedding_dim)
        )

        # Sample encoder (encodes across proteins for each sample)
        self.sample_encoder = nn.Sequential(
            nn.Linear(n_proteins, hidden_dims[0]),
            self.activation,
            nn.Dropout(dropout_rate),
            nn.Linear(hidden_dims[0], hidden_dims[1]),
            self.activation,
            nn.Dropout(dropout_rate),
            nn.Linear(hidden_dims[1], sample_embedding_dim)
        )

        # Decoder that reconstructs from both embeddings
        combined_dim = protein_embedding_dim + sample_embedding_dim
        self.decoder = nn.Sequential(
            nn.Linear(combined_dim, hidden_dims[0]),
            self.activation,
            nn.Dropout(dropout_rate),
            nn.Linear(hidden_dims[0], hidden_dims[1]),
            self.activation,
            nn.Dropout(dropout_rate),
            nn.Linear(hidden_dims[1], 1)  # Single output for reconstruction
        )

        # Alternative: Direct reconstruction layers
        self.protein_decoder = nn.Sequential(
            nn.Linear(protein_embedding_dim, hidden_dims[1]),
            self.activation,
            nn.Dropout(dropout_rate),
            nn.Linear(hidden_dims[1], n_samples)
        )

        self.sample_decoder = nn.Sequential(
            nn.Linear(sample_embedding_dim, hidden_dims[1]),
            self.activation,
            nn.Dropout(dropout_rate),
            nn.Linear(hidden_dims[1], n_proteins)
        )

        # Learnable combination weights
        self.combination_weight = nn.Parameter(torch.tensor(0.5))

    def encode_proteins(self, x: torch.Tensor) -> torch.Tensor:
        """Encode each protein (row) across samples"""
        # x shape: [batch_size, n_proteins, n_samples]
        batch_size = x.shape[0]
        protein_embeddings = []

        for i in range(self.n_proteins):
            protein_data = x[:, i, :]  # [batch_size, n_samples]
            embedding = self.protein_encoder(protein_data)  # [batch_size, protein_embedding_dim]
            protein_embeddings.append(embedding)

        return torch.stack(protein_embeddings, dim=1)  # [batch_size, n_proteins, protein_embedding_dim]

    def encode_samples(self, x: torch.Tensor) -> torch.Tensor:
        """Encode each sample (column) across proteins"""
        # x shape: [batch_size, n_proteins, n_samples]
        batch_size = x.shape[0]
        sample_embeddings = []

        for j in range(self.n_samples):
            sample_data = x[:, :, j]  # [batch_size, n_proteins]
            embedding = self.sample_encoder(sample_data)  # [batch_size, sample_embedding_dim]
            sample_embeddings.append(embedding)

        return torch.stack(sample_embeddings, dim=1)  # [batch_size, n_samples, sample_embedding_dim]

    def forward(self, x: torch.Tensor, return_embeddings: bool = False) -> Union[torch.Tensor, Tuple[torch.Tensor, Dict]]:
        """
        Forward pass through the autoencoder

        Args:
            x: Input tensor [batch_size, n_proteins, n_samples]
            return_embeddings: Whether to return embeddings along with reconstruction

        Returns:
            reconstruction or (reconstruction, embeddings_dict)
        """
        batch_size = x.shape[0]

        # Get embeddings
        protein_embeddings = self.encode_proteins(x)  # [batch_size, n_proteins, protein_emb_dim]
        sample_embeddings = self.encode_samples(x)    # [batch_size, n_samples, sample_emb_dim]

        # Method 1: Direct reconstruction from embeddings
        protein_reconstruction = self.protein_decoder(protein_embeddings)  # [batch_size, n_proteins, n_samples]

        # For sample reconstruction, we need to transpose
        sample_reconstruction = self.sample_decoder(sample_embeddings)  # [batch_size, n_samples, n_proteins]
        sample_reconstruction = sample_reconstruction.transpose(1, 2)    # [batch_size, n_proteins, n_samples]

        # Combine reconstructions
        alpha = torch.sigmoid(self.combination_weight)
        reconstruction = alpha * protein_reconstruction + (1 - alpha) * sample_reconstruction

        if return_embeddings:
            embeddings = {
                'protein_embeddings': protein_embeddings,
                'sample_embeddings': sample_embeddings,
                'combination_weight': alpha.item()
            }
            return reconstruction, embeddings

        return reconstruction

    def get_protein_embeddings(self, x: torch.Tensor) -> torch.Tensor:
        """Get protein embeddings for similarity analysis"""
        with torch.no_grad():
            return self.encode_proteins(x)

    def get_sample_embeddings(self, x: torch.Tensor) -> torch.Tensor:
        """Get sample embeddings for analysis"""
        with torch.no_grad():
            return self.encode_samples(x)

class ProteomicsAutoencoderTrainer:
    """Trainer class for the proteomics autoencoder"""

    def __init__(
        self,
        model: BiDirectionalAutoencoder,
        learning_rate: float = 1e-3,
        weight_decay: float = 1e-5,
        reconstruction_loss: str = 'mse'
        #reconstruction_loss: str = 'mae'
    ):
        self.model = model
        self.optimizer = torch.optim.Adam(
            model.parameters(),
            lr=learning_rate,
            weight_decay=weight_decay
        )

        if reconstruction_loss == 'mse':
            self.criterion = nn.MSELoss()
        elif reconstruction_loss == 'mae':
            self.criterion = nn.L1Loss()
        elif reconstruction_loss == 'huber':
            self.criterion = nn.SmoothL1Loss()
        else:
            raise ValueError("reconstruction_loss must be 'mse', 'mae', or 'huber'")

    def train_epoch(self, dataset: ProteomicsDataset, device: torch.device, n_batches: int = 100) -> float:
        """Train for one epoch using random masking"""
        self.model.train()
        total_loss = 0.0

        for _ in range(n_batches):
            # Get masked batch
            masked_data, mask, target = dataset.create_masked_batch()
            masked_data = masked_data.to(device)
            mask = mask.to(device)
            target = target.to(device)

            self.optimizer.zero_grad()

            # Forward pass
            reconstruction = self.model(masked_data)

            # Calculate loss only on masked positions
            loss = self.criterion(reconstruction[mask], target[mask])

            # Backward pass
            loss.backward()
            self.optimizer.step()

            total_loss += loss.item()

        return total_loss / n_batches

    def validate(self, dataset: ProteomicsDataset, device: torch.device, n_batches: int = 20) -> float:
        """Validate the model"""
        self.model.eval()
        total_loss = 0.0

        with torch.no_grad():
            for _ in range(n_batches):
                masked_data, mask, target = dataset.create_masked_batch()
                masked_data = masked_data.to(device)
                mask = mask.to(device)
                target = target.to(device)

                reconstruction = self.model(masked_data)
                loss = self.criterion(reconstruction[mask], target[mask])
                total_loss += loss.item()

        return total_loss / n_batches

def train_proteomics_autoencoder(
    data: pd.DataFrame,
    protein_embedding_dim: int = 128,
    sample_embedding_dim: int = 64,
    hidden_dims: List[int] = [256, 128],
    epochs: int = 200,
    learning_rate: float = 1e-3,
    mask_probability: float = 0.15,
    scaling_method: str = 'robust',
    device: Optional[torch.device] = None,
    validation_split: float = 0.2,
    **kwargs
) -> Tuple[BiDirectionalAutoencoder, ProteomicsDataset, Dict]:
    """
    Train the proteomics autoencoder

    Args:
        data: DataFrame with proteins as rows, samples as columns
        protein_embedding_dim: Dimension of protein embeddings
        sample_embedding_dim: Dimension of sample embeddings
        hidden_dims: Hidden layer dimensions
        epochs: Number of training epochs
        learning_rate: Learning rate for optimizer
        mask_probability: Probability of masking values during training
        scaling_method: Method for scaling data
        device: Device for training
        validation_split: Fraction of data for validation

    Returns:
        Tuple of (trained_model, dataset, training_history)
    """

    if device is None:
        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        # We can enable this but for smaller models mps is a lot slower than cpu
        # <womp-womp>
        #device = torch.device('mps' if torch.mps.is_available() else 'cpu')

    print(f"Training on device: {device}")
    print(f"Data shape: {data.shape}")

    # Create dataset
    dataset = ProteomicsDataset(
        data,
        mask_probability=mask_probability,
        scaling_method=scaling_method
    )

    # Create model
    model = BiDirectionalAutoencoder(
        n_proteins=dataset.n_proteins,
        n_samples=dataset.n_samples,
        protein_embedding_dim=protein_embedding_dim,
        sample_embedding_dim=sample_embedding_dim,
        hidden_dims=hidden_dims
    ).to(device)

    # Create trainer
    trainer = ProteomicsAutoencoderTrainer(model, learning_rate=learning_rate)

    # Training loop
    train_losses = []
    val_losses = []

    print("Starting training...")
    for epoch in range(epochs):
        # Train
        train_loss = trainer.train_epoch(dataset, device)
        train_losses.append(train_loss)

        # Validate
        if epoch % 10 == 0:
            val_loss = trainer.validate(dataset, device)
            val_losses.append(val_loss)

            print(f"Epoch {epoch+1}/{epochs}, Train Loss: {train_loss:.6f}, Val Loss: {val_loss:.6f}")

    # Final validation
    final_val_loss = trainer.validate(dataset, device)
    val_losses.append(final_val_loss)

    training_history = {
        'train_losses': train_losses,
        'val_losses': val_losses,
        'final_train_loss': train_losses[-1],
        'final_val_loss': final_val_loss
    }

    print(f"Training completed. Final train loss: {train_losses[-1]:.6f}, Final val loss: {final_val_loss:.6f}")

    # Calculate similarity matrix
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    sim_df = calculate_protein_similarity_matrix(model, dataset, device)

    with torch.no_grad():
        # Get full data
        full_data = dataset.data_tensor.unsqueeze(0).to(device)

        # Get protein embeddings
        protein_embeddings = model.get_protein_embeddings(full_data)
        protein_embeddings = protein_embeddings.squeeze(0).cpu().numpy()  # [n_protein

        sample_embeddings = model.get_sample_embeddings(full_data)
        sample_embeddings = sample_embeddings.squeeze(0).cpu().numpy()

    analysis_results_dict = {
        'model': model,
        'embeddings': protein_embeddings,
        'protein_embeddings': protein_embeddings,
        'sample_embeddings': sample_embeddings,
        'similarity_matrix': sim_df,     ####
        'training_history': training_history,
        # 'relationship_analysis': {
        #     'statistics': {
        #         'n_similar_pairs': 45,
        #         'mean_similarity': 0.72,
        #         'threshold_used': 0.6
        #     },
        #     'top_similar_pairs': [
        #         {'protein1': f'Protein_{i:03d}', 'protein2': f'Protein_{i+1:03d}', 'similarity': 0.9 - 0.1*i/10}
        #         for i in range(15)
        #     ]
        # },
        # 'reconstruction_results': {
        #     'reconstruction_error': {
        #         'mse': 0.045,
        #         'mae': 0.012
        #     }
        # },
        'config': {
            'protein_embedding_dim': protein_embedding_dim,
            'sample_embedding_dim': sample_embedding_dim,
            'hidden_dims': hidden_dims,
            'epochs': epochs,
            'learning_rate': learning_rate
        }
    }

    analysis_results = ProteomicsAutoencoderResults(
                results_dict=analysis_results_dict,
                original_data=data,
                dataset=dataset
                )

    return analysis_results

def calculate_protein_similarity_matrix(
    model: BiDirectionalAutoencoder,
    dataset: ProteomicsDataset,
    device: torch.device,
    similarity_metric: str = 'cosine'
) -> pd.DataFrame:
    """
    Calculate protein-protein similarity matrix using learned embeddings

    Args:
        model: Trained autoencoder model
        dataset: Dataset used for training
        device: Device for computation
        similarity_metric: 'cosine', 'euclidean', or 'correlation'

    Returns:
        DataFrame with protein similarity matrix
    """

    model.eval()

    with torch.no_grad():
        # Get full data
        full_data = dataset.data_tensor.unsqueeze(0).to(device)

        # Get protein embeddings
        protein_embeddings = model.get_protein_embeddings(full_data)
        protein_embeddings = protein_embeddings.squeeze(0).cpu().numpy()  # [n_proteins, embedding_dim]

    # Calculate similarity matrix
    if similarity_metric == 'cosine':
        similarity_matrix = cosine_similarity(protein_embeddings)
    elif similarity_metric == 'euclidean':
        from sklearn.metrics.pairwise import euclidean_distances
        distances = euclidean_distances(protein_embeddings)
        # Convert to similarity (higher = more similar)
        similarity_matrix = 1 / (1 + distances)
    elif similarity_metric == 'correlation':
        similarity_matrix = np.corrcoef(protein_embeddings)
    else:
        raise ValueError("similarity_metric must be 'cosine', 'euclidean', or 'correlation'")

    # Create DataFrame
    similarity_df = pd.DataFrame(
        similarity_matrix,
        index=dataset.protein_names,
        columns=dataset.protein_names
    )

    return similarity_df

def save_autoencoder_results(model, dataset, training_history,
                            similarity_matrix, output_dir="proteomics_analysis",):
    # Compile results
    results = {
        'model': model,
        'dataset': dataset,
        'training_history': training_history,
        'similarity_matrix': similarity_matrix,
    }

    os.makedirs(output_dir, exist_ok=True)

    # Save similarity matrix
    similarity_matrix.to_csv(os.path.join(output_dir, 'protein_similarity_matrix.csv'))

    # Save model
    torch.save({
        'model_state_dict': model.state_dict(),
        'model_config': {
            'n_proteins': dataset.n_proteins,
            'n_samples': dataset.n_samples,
            'protein_embedding_dim': model.protein_embedding_dim,
            'sample_embedding_dim': model.sample_embedding_dim
        },
        'scaler': dataset.scaler
    }, os.path.join(output_dir, 'autoencoder_model.pth'))

    print(f"Results saved to {output_dir}/")

def load_proteomics_autoencoder(
    model_path: str,
    device: Optional[torch.device] = None
) -> Dict:
    """
    Load a saved proteomics autoencoder model and associated artifacts

    Args:
        model_path: Path to the saved model file (.pth)
        device: Device to load model on (if None, auto-detects)

    Returns:
        Dictionary containing loaded model, config, and scaler
    """

    if device is None:
        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

    print(f"Loading model from: {model_path}")
    print(f"Loading on device: {device}")

    # Load the saved checkpoint
    checkpoint = torch.load(model_path, map_location=device, weights_only=False)

    # Extract configuration
    config = checkpoint['model_config']
    print(f"Model configuration: {config}")

    # Recreate the model with the same architecture
    model = BiDirectionalAutoencoder(
        n_proteins=config['n_proteins'],
        n_samples=config['n_samples'],
        protein_embedding_dim=config['protein_embedding_dim'],
        sample_embedding_dim=config['sample_embedding_dim']
    ).to(device)

    # Load the trained weights
    model.load_state_dict(checkpoint['model_state_dict'])
    model.eval()  # Set to evaluation mode

    # Load the scaler
    scaler = checkpoint['scaler']

    loaded_artifacts = {
        'model': model,
        'config': config,
        'scaler': scaler,
        'device': device
    }

    print("Model loaded successfully!")
    return loaded_artifacts


class ProteomicsAutoencoderResults(AnalysisResults):
    """
    Specialized class for bidirectional autoencoder analysis results
    """

    def __init__(self, results_dict: Dict, original_data: pd.DataFrame = None,
                 model: torch.nn.Module = None, dataset = None):
        """
        Initialize proteomics autoencoder analysis results

        Args:
            results_dict: Results from analyze_proteomics_data function
            original_data: Original proteomics data used in analysis
            model: Trained autoencoder model
            dataset: ProteomicsDataset used for training
        """
        super().__init__(
            results_dict=results_dict,
            analysis_type="Proteomics Bidirectional Autoencoder Analysis",
            metadata=results_dict.get('config', {})
        )

        self.original_data = original_data
        self.trained_model = model or results_dict.get('model')
        self.dataset = dataset or results_dict.get('dataset')

        # Extract key components for easy access
        self.training_history = results_dict.get('training_history', {})
        self.similarity_matrix = results_dict.get('similarity_matrix')
        self.relationship_analysis = results_dict.get('relationship_analysis', {})
        self.embeddings = results_dict.get('embeddings')
        self.reconstruction_results = results_dict.get('reconstruction_results', {})
        self.config = results_dict.get('config', {})

        # Model architecture info
        self.architecture_info = self._extract_architecture_info()

        # Performance metrics
        self.performance_metrics = self._calculate_performance_metrics()

    def _extract_architecture_info(self) -> Dict:
        """Extract architecture information from model"""
        if self.trained_model is None:
            return {}

        try:
            arch_info = {}

            if hasattr(self.trained_model, 'n_proteins'):
                arch_info['n_proteins'] = self.trained_model.n_proteins
            if hasattr(self.trained_model, 'n_samples'):
                arch_info['n_samples'] = self.trained_model.n_samples
            if hasattr(self.trained_model, 'protein_embedding_dim'):
                arch_info['protein_embedding_dim'] = self.trained_model.protein_embedding_dim
            if hasattr(self.trained_model, 'sample_embedding_dim'):
                arch_info['sample_embedding_dim'] = self.trained_model.sample_embedding_dim

            # Count parameters
            if hasattr(self.trained_model, 'parameters'):
                total_params = sum(p.numel() for p in self.trained_model.parameters())
                trainable_params = sum(p.numel() for p in self.trained_model.parameters() if p.requires_grad)
                arch_info['total_parameters'] = total_params
                arch_info['trainable_parameters'] = trainable_params

            return arch_info

        except Exception as e:
            return {'error': f'Could not extract architecture info: {e}'}

    def _calculate_performance_metrics(self) -> Dict:
        """Calculate comprehensive performance metrics"""
        metrics = {}

        # Training metrics
        if self.training_history:
            train_losses = self.training_history.get('train_losses', [])
            if train_losses:
                metrics['final_train_loss'] = train_losses[-1]
                metrics['initial_train_loss'] = train_losses[0]
                metrics['loss_reduction'] = train_losses[0] - train_losses[-1]
                metrics['loss_reduction_percent'] = ((train_losses[0] - train_losses[-1]) / train_losses[0]) * 100
                metrics['training_epochs'] = len(train_losses)

                # Training stability
                if len(train_losses) > 10:
                    recent_losses = train_losses[-10:]
                    metrics['training_stability'] = np.std(recent_losses) / np.mean(recent_losses)

        # Reconstruction metrics
        if self.reconstruction_results:
            if 'reconstruction_error' in self.reconstruction_results:
                recon_error = self.reconstruction_results['reconstruction_error']
                metrics['reconstruction_mse'] = recon_error.get('mse', 0)
                metrics['reconstruction_mae'] = recon_error.get('mae', 0)

        # Similarity analysis metrics
        if self.relationship_analysis:
            stats = self.relationship_analysis.get('statistics', {})
            metrics['n_similar_pairs'] = stats.get('n_similar_pairs', 0)
            metrics['mean_similarity'] = stats.get('mean_similarity', 0)
            metrics['similarity_threshold'] = stats.get('threshold_used', 0)

        # Data coverage
        if self.original_data is not None and self.dataset is not None:
            if hasattr(self.dataset, 'n_proteins') and hasattr(self.dataset, 'n_samples'):
                metrics['data_proteins'] = self.dataset.n_proteins
                metrics['data_samples'] = self.dataset.n_samples
                metrics['data_completeness'] = (self.dataset.n_proteins * self.dataset.n_samples) / self.original_data.size

        return metrics

    def get_summary_stats(self) -> Dict:
        """Get comprehensive summary statistics"""
        base_stats = super().get_summary_stats()

        # Architecture information
        arch_stats = {}
        if self.architecture_info:
            arch_stats = {
                'protein_embedding_dim': self.architecture_info.get('protein_embedding_dim', 'N/A'),
                'sample_embedding_dim': self.architecture_info.get('sample_embedding_dim', 'N/A'),
                'total_parameters': self.architecture_info.get('total_parameters', 'N/A'),
                'n_proteins': self.architecture_info.get('n_proteins', 'N/A'),
                'n_samples': self.architecture_info.get('n_samples', 'N/A')
            }

        # Performance statistics
        perf_stats = {}
        if self.performance_metrics:
            perf_stats = {
                'final_loss': self.performance_metrics.get('final_train_loss', 'N/A'),
                'loss_reduction_percent': f"{self.performance_metrics.get('loss_reduction_percent', 0):.1f}%",
                'training_epochs': self.performance_metrics.get('training_epochs', 'N/A'),
                'reconstruction_quality': self._assess_reconstruction_quality(),
                'embedding_quality': self._assess_embedding_quality()
            }

        return {
            **base_stats,
            **arch_stats,
            **perf_stats
        }

    def _assess_reconstruction_quality(self) -> str:
        """Assess reconstruction quality based on error metrics"""
        if 'reconstruction_mse' not in self.performance_metrics:
            return "Unknown"

        mse = self.performance_metrics['reconstruction_mse']

        # These thresholds would need to be calibrated based on your data scale
        if mse < 0.01:
            return "Excellent"
        elif mse < 0.05:
            return "Good"
        elif mse < 0.1:
            return "Fair"
        elif mse < 0.2:
            return "Poor"
        else:
            return "Very Poor"

    def _assess_embedding_quality(self) -> str:
        """Assess embedding quality based on similarity analysis"""
        if not self.relationship_analysis or 'statistics' not in self.relationship_analysis:
            return "Unknown"

        n_similar = self.relationship_analysis['statistics'].get('n_similar_pairs', 0)
        mean_sim = self.relationship_analysis['statistics'].get('mean_similarity', 0)

        if n_similar > 50 and mean_sim > 0.7:
            return "Excellent"
        elif n_similar > 20 and mean_sim > 0.6:
            return "Good"
        elif n_similar > 10 and mean_sim > 0.5:
            return "Fair"
        elif n_similar > 5:
            return "Poor"
        else:
            return "Very Poor"

    def get_training_convergence_analysis(self) -> Dict:
        """Analyze training convergence patterns"""
        if not self.training_history or 'train_losses' not in self.training_history:
            return {}

        losses = self.training_history['train_losses']
        if len(losses) < 10:
            return {'status': 'Insufficient training data'}

        analysis = {}

        # Convergence detection
        recent_window = min(20, len(losses) // 4)
        recent_losses = losses[-recent_window:]
        early_losses = losses[:recent_window]

        # Calculate convergence metrics
        recent_trend = np.polyfit(range(len(recent_losses)), recent_losses, 1)[0]
        recent_variance = np.var(recent_losses)

        analysis['converged'] = abs(recent_trend) < 0.001 and recent_variance < 0.001
        analysis['trend_slope'] = recent_trend
        analysis['recent_variance'] = recent_variance
        analysis['improvement_rate'] = (early_losses[0] - recent_losses[-1]) / len(losses)

        # Identify potential issues
        issues = []
        if recent_trend > 0.001:
            issues.append("Loss still decreasing - may need more training")
        if recent_variance > 0.01:
            issues.append("High variance in recent losses - unstable training")
        if len(losses) > 100 and analysis['improvement_rate'] < 0.001:
            issues.append("Slow improvement rate - may be overfitting or poor initialization")

        analysis['potential_issues'] = issues

        return analysis

    def get_embedding_statistics(self) -> Dict:
        """Get statistics about learned embeddings"""
        if self.embeddings is None:
            return {}

        stats = {}

        try:
            # Convert to numpy if tensor
            if hasattr(self.embeddings, 'numpy'):
                emb_array = self.embeddings.numpy()
            elif isinstance(self.embeddings, np.ndarray):
                emb_array = self.embeddings
            else:
                return {'error': 'Unknown embedding format'}

            # Basic statistics
            stats['embedding_shape'] = emb_array.shape
            stats['mean_embedding_norm'] = np.mean(np.linalg.norm(emb_array, axis=1))
            stats['std_embedding_norm'] = np.std(np.linalg.norm(emb_array, axis=1))
            stats['max_embedding_value'] = np.max(emb_array)
            stats['min_embedding_value'] = np.min(emb_array)

            # Dimensionality analysis
            if emb_array.shape[1] > 1:
                # PCA to estimate effective dimensionality
                from sklearn.decomposition import PCA
                pca = PCA()
                pca.fit(emb_array)

                # Find number of components explaining 95% variance
                cumvar = np.cumsum(pca.explained_variance_ratio_)
                effective_dim = np.argmax(cumvar >= 0.95) + 1

                stats['effective_dimensionality'] = effective_dim
                stats['explained_variance_95'] = cumvar[effective_dim-1]
                stats['top_3_pc_variance'] = np.sum(pca.explained_variance_ratio_[:3])

        except Exception as e:
            stats['error'] = f'Error calculating embedding statistics: {e}'

        return stats

    def get_top_similar_proteins(self, n: int = 10) -> pd.DataFrame:
        """Get top N most similar protein pairs"""
        if not self.relationship_analysis or 'top_similar_pairs' not in self.relationship_analysis:
            return pd.DataFrame()

        similar_pairs = self.relationship_analysis['top_similar_pairs'][:n]

        df_data = []
        for pair in similar_pairs:
            df_data.append({
                'protein1': pair['protein1'],
                'protein2': pair['protein2'],
                'similarity': pair['similarity']
            })

        return pd.DataFrame(df_data)

    def _generate_detailed_text(self) -> List[str]:
        """Generate detailed text representation"""
        lines = []

        # Architecture Section
        lines.append("MODEL ARCHITECTURE:")
        if self.architecture_info:
            for key, value in self.architecture_info.items():
                if key != 'error':
                    display_key = key.replace('_', ' ').title()
                    lines.append(f"  {display_key}: {value}")
        lines.append("")

        # Training Performance
        lines.append("TRAINING PERFORMANCE:")
        if self.performance_metrics:
            lines.append(f"  Final Training Loss: {self.performance_metrics.get('final_train_loss', 'N/A'):.6f}")
            lines.append(f"  Loss Reduction: {self.performance_metrics.get('loss_reduction_percent', 0):.2f}%")
            lines.append(f"  Training Epochs: {self.performance_metrics.get('training_epochs', 'N/A')}")
            lines.append(f"  Reconstruction Quality: {self._assess_reconstruction_quality()}")

            if 'reconstruction_mse' in self.performance_metrics:
                lines.append(f"  Reconstruction MSE: {self.performance_metrics['reconstruction_mse']:.6f}")
            if 'reconstruction_mae' in self.performance_metrics:
                lines.append(f"  Reconstruction MAE: {self.performance_metrics['reconstruction_mae']:.6f}")
        lines.append("")

        # Convergence Analysis
        convergence = self.get_training_convergence_analysis()
        if convergence:
            lines.append("TRAINING CONVERGENCE:")
            lines.append(f"  Converged: {convergence.get('converged', 'Unknown')}")
            lines.append(f"  Recent Trend: {convergence.get('trend_slope', 0):.6f}")
            lines.append(f"  Recent Variance: {convergence.get('recent_variance', 0):.6f}")

            issues = convergence.get('potential_issues', [])
            if issues:
                lines.append("  Potential Issues:")
                for issue in issues:
                    lines.append(f"    - {issue}")
            lines.append("")

        # Embedding Analysis
        emb_stats = self.get_embedding_statistics()
        if emb_stats and 'error' not in emb_stats:
            lines.append("EMBEDDING ANALYSIS:")
            lines.append(f"  Embedding Shape: {emb_stats.get('embedding_shape', 'N/A')}")
            lines.append(f"  Mean Norm: {emb_stats.get('mean_embedding_norm', 0):.4f}")
            lines.append(f"  Effective Dimensionality: {emb_stats.get('effective_dimensionality', 'N/A')}")
            lines.append(f"  Top 3 PC Variance: {emb_stats.get('top_3_pc_variance', 0):.2%}")
            lines.append("")

        # Similarity Analysis
        if self.relationship_analysis and 'statistics' in self.relationship_analysis:
            stats = self.relationship_analysis['statistics']
            lines.append("PROTEIN SIMILARITY ANALYSIS:")
            lines.append(f"  Similar Pairs Found: {stats.get('n_similar_pairs', 0)}")
            lines.append(f"  Mean Similarity: {stats.get('mean_similarity', 0):.4f}")
            lines.append(f"  Similarity Threshold: {stats.get('threshold_used', 0):.4f}")
            lines.append(f"  Embedding Quality: {self._assess_embedding_quality()}")
            lines.append("")

            # Top similar pairs
            top_pairs = self.get_top_similar_proteins(5)
            if not top_pairs.empty:
                lines.append("TOP 5 SIMILAR PROTEIN PAIRS:")
                for idx, row in top_pairs.iterrows():
                    lines.append(f"  {row['protein1']} - {row['protein2']}: {row['similarity']:.4f}")
                lines.append("")

        # Configuration
        lines.append("CONFIGURATION:")
        for key, value in self.config.items():
            display_key = key.replace('_', ' ').title()
            lines.append(f"  {display_key}: {value}")
        lines.append("")

        return lines

    def _generate_detailed_html(self) -> str:
        """Generate detailed HTML representation"""
        html_parts = []

        # Architecture Information
        if self.architecture_info:
            html_parts.append('<h3>Model Architecture</h3>')
            html_parts.append('<table class="results-table">')
            html_parts.append('<tr><th>Component</th><th>Value</th><th>Description</th></tr>')

            arch_descriptions = {
                'n_proteins': 'Number of proteins in dataset',
                'n_samples': 'Number of experimental conditions',
                'protein_embedding_dim': 'Dimensionality of protein embeddings',
                'sample_embedding_dim': 'Dimensionality of sample embeddings',
                'total_parameters': 'Total model parameters',
                'trainable_parameters': 'Trainable model parameters'
            }

            for key, value in self.architecture_info.items():
                if key != 'error':
                    description = arch_descriptions.get(key, '')
                    display_key = key.replace('_', ' ').title()
                    html_parts.append(f'<tr><td>{display_key}</td><td>{value}</td><td>{description}</td></tr>')

            html_parts.append('</table>')

        # Training Performance
        html_parts.append('<h3>Training Performance</h3>')
        html_parts.append('<table class="results-table">')
        html_parts.append('<tr><th>Metric</th><th>Value</th><th>Assessment</th></tr>')

        if self.performance_metrics:
            final_loss = self.performance_metrics.get('final_train_loss', 0)
            loss_reduction = self.performance_metrics.get('loss_reduction_percent', 0)
            reconstruction_quality = self._assess_reconstruction_quality()
            embedding_quality = self._assess_embedding_quality()

            # Determine CSS classes for assessments
            recon_class = self._get_quality_css_class(reconstruction_quality)
            emb_class = self._get_quality_css_class(embedding_quality)

            html_parts.append(f'<tr><td>Final Training Loss</td><td>{final_loss:.6f}</td><td>-</td></tr>')
            html_parts.append(f'<tr><td>Loss Reduction</td><td>{loss_reduction:.2f}%</td><td>{"Good" if loss_reduction > 50 else "Poor"}</td></tr>')
            html_parts.append(f'<tr><td>Reconstruction Quality</td><td>-</td><td class="{recon_class}">{reconstruction_quality}</td></tr>')
            html_parts.append(f'<tr><td>Embedding Quality</td><td>-</td><td class="{emb_class}">{embedding_quality}</td></tr>')

            if 'reconstruction_mse' in self.performance_metrics:
                mse = self.performance_metrics['reconstruction_mse']
                html_parts.append(f'<tr><td>Reconstruction MSE</td><td>{mse:.6f}</td><td>-</td></tr>')

        html_parts.append('</table>')

        # Convergence Analysis
        convergence = self.get_training_convergence_analysis()
        if convergence and 'status' not in convergence:
            html_parts.append('<h3>Training Convergence Analysis</h3>')
            html_parts.append('<table class="results-table">')
            html_parts.append('<tr><th>Metric</th><th>Value</th><th>Interpretation</th></tr>')

            converged = convergence.get('converged', False)
            converged_class = "metric-good" if converged else "metric-warning"

            html_parts.append(f'<tr><td>Converged</td><td class="{converged_class}">{converged}</td><td>{"Training has stabilized" if converged else "May need more training"}</td></tr>')
            html_parts.append(f'<tr><td>Recent Trend</td><td>{convergence.get("trend_slope", 0):.6f}</td><td>{"Still improving" if convergence.get("trend_slope", 0) < -0.001 else "Plateaued"}</td></tr>')
            html_parts.append(f'<tr><td>Recent Variance</td><td>{convergence.get("recent_variance", 0):.6f}</td><td>{"Stable" if convergence.get("recent_variance", 0) < 0.01 else "Unstable"}</td></tr>')

            html_parts.append('</table>')

            # Issues
            issues = convergence.get('potential_issues', [])
            if issues:
                html_parts.append('<h4>Potential Issues</h4>')
                html_parts.append('<ul>')
                for issue in issues:
                    html_parts.append(f'<li>{issue}</li>')
                html_parts.append('</ul>')

        # Embedding Statistics
        emb_stats = self.get_embedding_statistics()
        if emb_stats and 'error' not in emb_stats:
            html_parts.append('<h3>Embedding Analysis</h3>')
            html_parts.append('<table class="results-table">')
            html_parts.append('<tr><th>Statistic</th><th>Value</th><th>Interpretation</th></tr>')

            shape = emb_stats.get('embedding_shape', (0, 0))
            effective_dim = emb_stats.get('effective_dimensionality', 0)
            variance_3pc = emb_stats.get('top_3_pc_variance', 0)

            html_parts.append(f'<tr><td>Embedding Shape</td><td>{shape}</td><td>{shape[0]} proteins, {shape[1]} dimensions</td></tr>')
            html_parts.append(f'<tr><td>Mean Norm</td><td>{emb_stats.get("mean_embedding_norm", 0):.4f}</td><td>Average embedding magnitude</td></tr>')
            html_parts.append(f'<tr><td>Effective Dimensionality</td><td>{effective_dim}</td><td>Dimensions explaining 95% variance</td></tr>')
            html_parts.append(f'<tr><td>Top 3 PC Variance</td><td>{variance_3pc:.2%}</td><td>Variance in top 3 components</td></tr>')

            html_parts.append('</table>')

        # Top Similar Proteins
        top_pairs = self.get_top_similar_proteins(10)
        if not top_pairs.empty:
            html_parts.append('<h3>Top Similar Protein Pairs</h3>')
            html_parts.append('<table class="results-table">')
            html_parts.append('<tr><th>Rank</th><th>Protein 1</th><th>Protein 2</th><th>Similarity</th></tr>')

            for idx, row in top_pairs.iterrows():
                html_parts.append(f'<tr><td>{idx + 1}</td><td>{row["protein1"]}</td><td>{row["protein2"]}</td><td>{row["similarity"]:.4f}</td></tr>')

            html_parts.append('</table>')

        # Configuration
        html_parts.append('<div class="config-section">')
        html_parts.append('<h3>Configuration</h3>')
        html_parts.append('<table class="results-table">')
        html_parts.append('<tr><th>Parameter</th><th>Value</th></tr>')

        for key, value in self.config.items():
            display_key = key.replace('_', ' ').title()
            html_parts.append(f'<tr><td>{display_key}</td><td>{value}</td></tr>')

        html_parts.append('</table>')
        html_parts.append('</div>')

        return '\n'.join(html_parts)

    def _get_quality_css_class(self, quality_str: str) -> str:
        """Get CSS class based on quality assessment"""
        quality_lower = quality_str.lower()
        if quality_lower in ['excellent', 'good']:
            return 'metric-good'
        elif quality_lower in ['fair']:
            return 'metric-warning'
        else:
            return 'metric-poor'

    def _generate_plots_html(self, plot_format: str = 'png', **plot_kwargs) -> str:
        """Generate plots HTML with embedded images"""
        html_parts = []

        try:
            plots = self.create_plots(**plot_kwargs)

            for plot_name, fig in plots.items():
                if fig is not None:
                    img_str = self._fig_to_base64(fig, format=plot_format)

                    html_parts.append(f'<div class="plot-container">')
                    html_parts.append(f'<div class="plot-title">{plot_name.replace("_", " ").title()}</div>')
                    html_parts.append(f'<img src="data:image/{plot_format};base64,{img_str}" alt="{plot_name}" style="max-width: 100%; height: auto;">')
                    html_parts.append('</div>')

                    plt.close(fig)

        except Exception as e:
            html_parts.append(f'<p class="error">Error generating plots: {str(e)}</p>')

        return '\n'.join(html_parts)

    def create_plots(self, figsize: Tuple[int, int] = (16, 12), **kwargs) -> Dict:
        """
        Create visualization plots for autoencoder analysis

        Args:
            figsize: Figure size for plots
            **kwargs: Additional plotting parameters

        Returns:
            Dictionary of plot names to figure objects
        """
        plots = {}

        try:
            # 1. Training Progress
            if self.training_history and 'train_losses' in self.training_history:
                fig1 = plt.figure(figsize=(14, 10))

                train_losses = self.training_history['train_losses']
                val_losses = self.training_history.get('val_losses', [])

                # Loss curves
                ax1 = plt.subplot(2, 3, 1)
                ax1.plot(train_losses, label='Training Loss', linewidth=2)
                if val_losses:
                    ax1.plot(val_losses, label='Validation Loss', linewidth=2)
                ax1.set_xlabel('Epoch')
                ax1.set_ylabel('Loss')
                ax1.set_title('Training Progress')
                ax1.legend()
                ax1.grid(True, alpha=0.3)

                # Loss distribution (recent epochs)
                ax2 = plt.subplot(2, 3, 2)
                recent_losses = train_losses[-20:] if len(train_losses) >= 20 else train_losses
                ax2.hist(recent_losses, bins=15, alpha=0.7, edgecolor='black')
                ax2.set_xlabel('Loss Value')
                ax2.set_ylabel('Frequency')
                ax2.set_title('Recent Loss Distribution')
                ax2.grid(True, alpha=0.3)

                # Loss improvement rate
                ax3 = plt.subplot(2, 3, 3)
                if len(train_losses) > 10:
                    # Calculate moving average of improvement
                    window = min(10, len(train_losses) // 4)
                    improvements = []
                    for i in range(window, len(train_losses)):
                        recent_avg = np.mean(train_losses[i-window:i])
                        prev_avg = np.mean(train_losses[i-2*window:i-window]) if i >= 2*window else train_losses[0]
                        improvement = prev_avg - recent_avg
                        improvements.append(improvement)

                    ax3.plot(range(window, len(train_losses)), improvements, linewidth=2)
                    ax3.set_xlabel('Epoch')
                    ax3.set_ylabel('Loss Improvement Rate')
                    ax3.set_title('Training Improvement Rate')
                    ax3.grid(True, alpha=0.3)
                    ax3.axhline(y=0, color='r', linestyle='--', alpha=0.5)

                # Convergence analysis
                ax4 = plt.subplot(2, 3, 4)
                convergence = self.get_training_convergence_analysis()
                if convergence and 'converged' in convergence:
                    # Plot recent variance
                    if len(train_losses) > 20:
                        window_size = 10
                        variances = []
                        epochs = []
                        for i in range(window_size, len(train_losses)):
                            window_losses = train_losses[i-window_size:i]
                            variances.append(np.var(window_losses))
                            epochs.append(i)

                        ax4.plot(epochs, variances, linewidth=2, color='orange')
                        ax4.set_xlabel('Epoch')
                        ax4.set_ylabel('Windowed Loss Variance')
                        ax4.set_title('Training Stability')
                        ax4.grid(True, alpha=0.3)

                # Training summary
                ax5 = plt.subplot(2, 3, 5)
                ax5.axis('off')

                # Create summary text
                summary_text = f"""Training Summary:

Final Loss: {train_losses[-1]:.6f}
Initial Loss: {train_losses[0]:.6f}
Improvement: {((train_losses[0] - train_losses[-1]) / train_losses[0] * 100):.1f}%
Epochs: {len(train_losses)}

Convergence: {convergence.get('converged', 'Unknown') if convergence else 'Unknown'}
Assessment: {self._assess_reconstruction_quality()}
                """

                ax5.text(0.1, 0.9, summary_text, transform=ax5.transAxes, fontsize=10,
                        verticalalignment='top',
                        bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.8))

                plt.tight_layout()
                plots['training_analysis'] = fig1

            # 2. Similarity Analysis
            if self.similarity_matrix is not None:
                fig2 = plt.figure(figsize=(14, 10))

                # Similarity matrix heatmap
                ax1 = plt.subplot(2, 3, 1)

                # Sample for visualization if too large
                if len(self.similarity_matrix) > 100:
                    sample_indices = np.random.choice(len(self.similarity_matrix), 100, replace=False)
                    plot_matrix = self.similarity_matrix.iloc[sample_indices, sample_indices]
                    title_suffix = " (100 random proteins)"
                else:
                    plot_matrix = self.similarity_matrix
                    title_suffix = ""

                sns.heatmap(plot_matrix, cmap='viridis', square=True,
                           cbar_kws={'label': 'Similarity'}, ax=ax1)
                ax1.set_title(f'Protein Similarity Matrix{title_suffix}')

                # Similarity distribution
                ax2 = plt.subplot(2, 3, 2)
                similarity_values = self.similarity_matrix.values
                # Remove diagonal and get upper triangle
                mask = np.triu(np.ones_like(similarity_values, dtype=bool), k=1)
                sim_values = similarity_values[mask]

                ax2.hist(sim_values, bins=50, alpha=0.7, edgecolor='black')
                ax2.axvline(np.mean(sim_values), color='red', linestyle='--',
                           label=f'Mean: {np.mean(sim_values):.3f}')
                ax2.set_xlabel('Similarity')
                ax2.set_ylabel('Frequency')
                ax2.set_title('Similarity Distribution')
                ax2.legend()
                ax2.grid(True, alpha=0.3)

                # Top similarities
                ax3 = plt.subplot(2, 3, 3)
                top_pairs = self.get_top_similar_proteins(15)
                if not top_pairs.empty:
                    y_pos = range(len(top_pairs))
                    similarities = top_pairs['similarity'].values

                    bars = ax3.barh(y_pos, similarities, alpha=0.7)
                    ax3.set_yticks(y_pos)
                    ax3.set_yticklabels([f"{row['protein1']}-{row['protein2']}"[:20] for _, row in top_pairs.iterrows()],
                                      fontsize=8)
                    ax3.set_xlabel('Similarity')
                    ax3.set_title('Top Similar Protein Pairs')
                    ax3.grid(True, alpha=0.3, axis='x')

                # Clustering visualization (if possible)
                ax4 = plt.subplot(2, 3, 4)
                try:
                    from sklearn.cluster import KMeans
                    from sklearn.manifold import TSNE

                    # Use embeddings if available, otherwise similarity matrix
                    if self.embeddings is not None:
                        if hasattr(self.embeddings, 'numpy'):
                            emb_data = self.embeddings.numpy()
                        else:
                            emb_data = self.embeddings

                        if len(emb_data) <= 500:  # Only for manageable sizes
                            # Cluster embeddings
                            n_clusters = min(8, len(emb_data) // 10)
                            if n_clusters >= 2:
                                kmeans = KMeans(n_clusters=n_clusters, random_state=42)
                                clusters = kmeans.fit_predict(emb_data)

                                # Use t-SNE for 2D visualization
                                if emb_data.shape[1] > 2:
                                    tsne = TSNE(n_components=2, random_state=42)
                                    emb_2d = tsne.fit_transform(emb_data[:200])  # Limit for t-SNE
                                    clusters_2d = clusters[:200]
                                else:
                                    emb_2d = emb_data
                                    clusters_2d = clusters

                                scatter = ax4.scatter(emb_2d[:, 0], emb_2d[:, 1],
                                                    c=clusters_2d, cmap='tab10', alpha=0.6)
                                ax4.set_title('Protein Clustering (t-SNE)')
                                ax4.set_xlabel('t-SNE 1')
                                ax4.set_ylabel('t-SNE 2')

                except ImportError:
                    ax4.text(0.5, 0.5, 'Clustering visualization\nrequires scikit-learn',
                            ha='center', va='center', transform=ax4.transAxes)
                except Exception:
                    ax4.text(0.5, 0.5, 'Clustering visualization\nnot available',
                            ha='center', va='center', transform=ax4.transAxes)

                ax4.set_title('Protein Clustering')

                plt.tight_layout()
                plots['similarity_analysis'] = fig2

            # 3. Embedding Analysis
            if self.embeddings is not None:
                fig3 = plt.figure(figsize=(12, 8))

                # Convert to numpy
                if hasattr(self.embeddings, 'numpy'):
                    emb_array = self.embeddings.numpy()
                else:
                    emb_array = self.embeddings

                # Embedding norms distribution
                ax1 = plt.subplot(2, 3, 1)
                norms = np.linalg.norm(emb_array, axis=1)
                ax1.hist(norms, bins=30, alpha=0.7, edgecolor='black')
                ax1.axvline(np.mean(norms), color='red', linestyle='--',
                           label=f'Mean: {np.mean(norms):.3f}')
                ax1.set_xlabel('Embedding Norm')
                ax1.set_ylabel('Frequency')
                ax1.set_title('Embedding Magnitude Distribution')
                ax1.legend()
                ax1.grid(True, alpha=0.3)

                # Dimension-wise statistics
                ax2 = plt.subplot(2, 3, 2)
                dim_means = np.mean(emb_array, axis=0)
                dim_stds = np.std(emb_array, axis=0)

                ax2.errorbar(range(len(dim_means)), dim_means, yerr=dim_stds,
                           capsize=3, alpha=0.7)
                ax2.set_xlabel('Embedding Dimension')
                ax2.set_ylabel('Mean ± Std')
                ax2.set_title('Per-Dimension Statistics')
                ax2.grid(True, alpha=0.3)

                # PCA analysis
                ax3 = plt.subplot(2, 3, 3)
                try:
                    from sklearn.decomposition import PCA
                    pca = PCA()
                    pca.fit(emb_array)

                    # Plot explained variance
                    cumvar = np.cumsum(pca.explained_variance_ratio_)
                    ax3.plot(range(1, len(cumvar) + 1), cumvar, 'bo-', linewidth=2)
                    ax3.axhline(y=0.95, color='red', linestyle='--', alpha=0.7, label='95% variance')
                    ax3.set_xlabel('Number of Components')
                    ax3.set_ylabel('Cumulative Explained Variance')
                    ax3.set_title('PCA Analysis')
                    ax3.legend()
                    ax3.grid(True, alpha=0.3)

                except ImportError:
                    ax3.text(0.5, 0.5, 'PCA analysis requires\nscikit-learn',
                            ha='center', va='center', transform=ax3.transAxes)

                # Embedding statistics summary
                ax4 = plt.subplot(2, 3, (4, 6))
                ax4.axis('off')

                emb_stats = self.get_embedding_statistics()
                stats_text = f"""Embedding Statistics:

Shape: {emb_stats.get('embedding_shape', 'N/A')}
Mean Norm: {emb_stats.get('mean_embedding_norm', 0):.4f}
Std Norm: {emb_stats.get('std_embedding_norm', 0):.4f}
Value Range: [{emb_stats.get('min_embedding_value', 0):.3f}, {emb_stats.get('max_embedding_value', 0):.3f}]

Effective Dimensionality: {emb_stats.get('effective_dimensionality', 'N/A')}
Top 3 PC Variance: {emb_stats.get('top_3_pc_variance', 0):.2%}

Quality Assessment: {self._assess_embedding_quality()}
                """

                ax4.text(0.05, 0.95, stats_text, transform=ax4.transAxes, fontsize=11,
                        verticalalignment='top',
                        bbox=dict(boxstyle='round', facecolor='lightgreen', alpha=0.8))

                plt.tight_layout()
                plots['embedding_analysis'] = fig3

        except Exception as e:
            print(f"Warning: Error creating plots: {e}")

        return plots

    def export_embeddings(self, filepath: str, format: str = 'csv'):
        """
        Export learned embeddings to file

        Args:
            filepath: Path to save embeddings
            format: Format to save ('csv', 'npy', 'pkl')
        """
        if self.embeddings is None:
            raise ValueError("No embeddings available to export")

        # Convert to numpy if needed
        if hasattr(self.embeddings, 'numpy'):
            emb_array = self.embeddings.numpy()
        else:
            emb_array = self.embeddings

        if format == 'csv':
            # Create DataFrame with protein names if available
            if self.original_data is not None:
                protein_names = self.original_data.index.tolist()[:len(emb_array)]
            else:
                protein_names = [f'Protein_{i}' for i in range(len(emb_array))]

            columns = [f'dim_{i}' for i in range(emb_array.shape[1])]
            emb_df = pd.DataFrame(emb_array, index=protein_names, columns=columns)
            emb_df.to_csv(filepath)

        elif format == 'npy':
            np.save(filepath, emb_array)

        elif format == 'pkl':
            import pickle
            with open(filepath, 'wb') as f:
                pickle.dump(emb_array, f)

        else:
            raise ValueError(f"Unsupported format: {format}")
