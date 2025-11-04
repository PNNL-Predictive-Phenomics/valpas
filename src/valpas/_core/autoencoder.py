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
from typing import Optional, Tuple, Dict, List, Union
import warnings
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

    return model, dataset, training_history

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

# Complete analysis pipeline
def analyze_proteomics_data(
    data: pd.DataFrame,
    protein_embedding_dim: int = 128,
    epochs: int = 200,
    similarity_threshold: float = 0.8,
    save_results: bool = True,
    show_plot: bool=False,
    load_model: bool=False,
    output_dir: str = 'proteomics_analysis'
) -> Dict:
    """
    Complete pipeline for proteomics data analysis using autoencoder

    Args:
        data: DataFrame with proteins as rows, samples as columns
        protein_embedding_dim: Dimension of protein embeddings
        epochs: Number of training epochs
        similarity_threshold: Threshold for defining protein relationships
        save_results: Whether to save results to files
        show_plot: Whether to show the plot upon execution
        load_model: Whether to load an existing model if present
        output_dir: Directory to save results

    Returns:
        Dictionary with all analysis results
    """

    print("Starting proteomics data analysis...")
    print(f"Data shape: {data.shape}")

    # Train autoencoder
    model, dataset, training_history = train_proteomics_autoencoder(
        data,
        protein_embedding_dim=protein_embedding_dim,
        epochs=epochs
    )

    # Calculate similarity matrix
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    similarity_matrix = calculate_protein_similarity_matrix(model, dataset, device)

    # Analyze relationships
    relationship_analysis = analyze_protein_relationships(
        similarity_matrix,
        data,
        threshold=similarity_threshold
    )

    # Create visualizations
    fig = visualize_protein_relationships(similarity_matrix, relationship_analysis)

    # Compile results
    results = {
        'model': model,
        'dataset': dataset,
        'training_history': training_history,
        'similarity_matrix': similarity_matrix,
        'relationship_analysis': relationship_analysis,
        'visualization': fig
    }

    # Save results if requested
    if save_results:
        import os
        os.makedirs(output_dir, exist_ok=True)

        # Save similarity matrix
        similarity_matrix.to_csv(os.path.join(output_dir, 'protein_similarity_matrix.csv'))

        # Save relationship analysis
        pairs_df = pd.DataFrame(relationship_analysis['pair_analysis'])
        pairs_df.to_csv(os.path.join(output_dir, 'protein_relationships.csv'), index=False)

        # Save visualization
        fig.savefig(os.path.join(output_dir, 'protein_relationships_analysis.png'),
                   dpi=300, bbox_inches='tight')

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

    if show_plot:
        plt.show()

    return results

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

# Example usage
if __name__ == "__main__":
    # Create sample proteomics data
    np.random.seed(42)
    n_proteins = 200
    n_samples = 50

    # Generate realistic proteomics data with some structure
    # Simulate protein groups with similar expression patterns
    protein_groups = 5
    proteins_per_group = n_proteins // protein_groups

    data_matrix = np.zeros((n_proteins, n_samples))
    protein_names = [f'Protein_{i:03d}' for i in range(n_proteins)]
    sample_names = [f'Sample_{i:02d}' for i in range(n_samples)]

    for group in range(protein_groups):
        start_idx = group * proteins_per_group
        end_idx = min((group + 1) * proteins_per_group, n_proteins)

        # Create base expression pattern for this group
        base_pattern = np.random.randn(n_samples) * 2 + group * 3

        # Add group-specific variation
        for i in range(start_idx, end_idx):
            noise = np.random.randn(n_samples) * 0.5
            data_matrix[i] = base_pattern + noise

    # Add some random proteins
    remaining = n_proteins - protein_groups * proteins_per_group
    if remaining > 0:
        data_matrix[-remaining:] = np.random.randn(remaining, n_samples) * 3

    # Ensure positive values (typical for abundance data)
    data_matrix = np.abs(data_matrix) + 0.1

    input_file = "../valpas-analysis-and-benchmark/data/Lipomyces/Lipomyces_protein_abundance__proteomics.csv"
    df = pd.read_csv(input_file, index_col=0).fillna(0)


    # Create DataFrame
    proteomics_df = pd.DataFrame(
        df.to_numpy(),
        index=df.index,
        columns=df.columns
    )

    print(f"Created sample proteomics dataset: {proteomics_df.shape}")
    print("Running complete analysis...")

    # Run analysis
    results = analyze_proteomics_data(
        proteomics_df,
        protein_embedding_dim=64,
        epochs=100,
        similarity_threshold=0.7
    )

    print("\nAnalysis complete!")
    print(f"Found {results['relationship_analysis']['statistics']['n_similar_pairs']} similar protein pairs")
    print("Check 'proteomics_analysis' directory for saved results")
