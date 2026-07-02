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

from .classes.results import AnalysisResults

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

        # Pre-allocate buffers for mask generation (P3: buffer reuse)
        self._mask_buffer = torch.empty(self.n_proteins, self.n_samples)
        self._masked_data_buffer = torch.empty_like(self.data_tensor)

    def __len__(self):
        return 1  # We treat the entire matrix as one sample

    def __getitem__(self, idx):
        return self.data_tensor

    def create_masked_batch(self, batch_size: int = 1) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Create masked version of data for training using pre-allocated buffers.

        Returns:
            masked_data: Data with some values masked (set to 0)
            mask: Boolean mask indicating which values were masked
            target: Original unmasked data
        """
        # Use pre-allocated buffer for mask generation (avoids allocation each call)
        self._mask_buffer.uniform_()
        mask = self._mask_buffer < self.mask_probability

        # Reuse buffer for masked data
        self._masked_data_buffer.copy_(self.data_tensor)
        self._masked_data_buffer[mask] = 0

        return self._masked_data_buffer.unsqueeze(0), mask.unsqueeze(0), self.data_tensor.unsqueeze(0)

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
        """
        Encode each protein (row) across samples using batched matrix ops.

        Instead of looping over n_proteins sequentially, reshapes to process
        all proteins in a single forward pass through the shared encoder.
        """
        # x shape: [batch_size, n_proteins, n_samples]
        batch_size = x.shape[0]
        # Reshape: [batch_size, n_proteins, n_samples] → [batch_size * n_proteins, n_samples]
        x_flat = x.reshape(-1, self.n_samples)
        # Single forward pass through encoder for all proteins at once
        embeddings = self.protein_encoder(x_flat)  # [batch_size * n_proteins, protein_embedding_dim]
        # Reshape back: [batch_size, n_proteins, protein_embedding_dim]
        return embeddings.reshape(batch_size, self.n_proteins, -1)

    def encode_samples(self, x: torch.Tensor) -> torch.Tensor:
        """
        Encode each sample (column) across proteins using batched matrix ops.

        Instead of looping over n_samples sequentially, transposes and reshapes
        to process all samples in a single forward pass through the shared encoder.
        """
        # x shape: [batch_size, n_proteins, n_samples]
        batch_size = x.shape[0]
        # Transpose to [batch_size, n_samples, n_proteins], then flatten
        x_t = x.transpose(1, 2).reshape(-1, self.n_proteins)  # [batch_size * n_samples, n_proteins]
        # Single forward pass through encoder for all samples at once
        embeddings = self.sample_encoder(x_t)  # [batch_size * n_samples, sample_embedding_dim]
        # Reshape back: [batch_size, n_samples, sample_embedding_dim]
        return embeddings.reshape(batch_size, self.n_samples, -1)

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


class ModalityAwareAutoencoder(nn.Module):
    """
    Autoencoder with modality-specific encoders, optional VAE bottleneck,
    and embedding norm regularization.

    When modality_split is provided, separate encoders are used for each
    modality (e.g., proteins vs metabolites). Otherwise falls back to a
    single shared encoder (equivalent to BiDirectionalAutoencoder behavior).

    Supports:
        - Modality-specific feature encoders
        - Variational (VAE) bottleneck with KL divergence
        - Embedding norm regularization
        - Cosine auxiliary loss (positive pair mining)
    """

    def __init__(
        self,
        n_proteins: int,
        n_samples: int,
        protein_embedding_dim: int = 128,
        sample_embedding_dim: int = 64,
        hidden_dims: List[int] = [256, 128],
        dropout_rate: float = 0.1,
        activation: str = 'relu',
        modality_split: Optional[int] = None,
        use_vae: bool = False,
        embedding_norm_target: float = 1.0,
    ):
        """
        Args:
            n_proteins: Total number of features (rows) — proteins + metabolites
            n_samples: Number of samples (columns)
            protein_embedding_dim: Dimension of feature embeddings
            sample_embedding_dim: Dimension of sample embeddings
            hidden_dims: Hidden layer dimensions [first_hidden, second_hidden]
            dropout_rate: Dropout rate for regularization
            activation: Activation function ('relu', 'tanh', 'elu')
            modality_split: Row index where first modality ends. If None,
                uses single shared encoder (backward compatible).
            use_vae: If True, adds variational bottleneck (mu/logvar)
            embedding_norm_target: Target L2 norm for embedding regularization
        """
        super().__init__()

        self.n_proteins = n_proteins
        self.n_samples = n_samples
        self.protein_embedding_dim = protein_embedding_dim
        self.sample_embedding_dim = sample_embedding_dim
        self.modality_split = modality_split
        self.use_vae = use_vae
        self.embedding_norm_target = embedding_norm_target

        # Activation function
        if activation == 'relu':
            act_fn = nn.ReLU()
        elif activation == 'tanh':
            act_fn = nn.Tanh()
        elif activation == 'elu':
            act_fn = nn.ELU()
        else:
            raise ValueError("activation must be 'relu', 'tanh', or 'elu'")
        self.activation = act_fn

        # --- Feature Encoders ---
        if modality_split is not None and 0 < modality_split < n_proteins:
            # Modality-specific encoders
            self.modality_a_encoder = self._make_encoder(
                n_samples, hidden_dims, protein_embedding_dim, dropout_rate, act_fn
            )
            self.modality_b_encoder = self._make_encoder(
                n_samples, hidden_dims, protein_embedding_dim, dropout_rate, act_fn
            )
            self.has_dual_encoders = True
        else:
            # Shared encoder (same as BiDirectionalAutoencoder)
            self.protein_encoder = self._make_encoder(
                n_samples, hidden_dims, protein_embedding_dim, dropout_rate, act_fn
            )
            self.has_dual_encoders = False

        # --- Sample Encoder ---
        self.sample_encoder = self._make_encoder(
            n_proteins, hidden_dims, sample_embedding_dim, dropout_rate, act_fn
        )

        # --- VAE Bottleneck ---
        if use_vae:
            # Separate mu/logvar projections for feature and sample embeddings
            self.protein_mu = nn.Linear(protein_embedding_dim, protein_embedding_dim)
            self.protein_logvar = nn.Linear(protein_embedding_dim, protein_embedding_dim)
            self.sample_mu = nn.Linear(sample_embedding_dim, sample_embedding_dim)
            self.sample_logvar = nn.Linear(sample_embedding_dim, sample_embedding_dim)

        # --- Decoders ---
        self.protein_decoder = nn.Sequential(
            nn.Linear(protein_embedding_dim, hidden_dims[1]),
            act_fn,
            nn.Dropout(dropout_rate),
            nn.Linear(hidden_dims[1], n_samples)
        )

        self.sample_decoder = nn.Sequential(
            nn.Linear(sample_embedding_dim, hidden_dims[1]),
            act_fn,
            nn.Dropout(dropout_rate),
            nn.Linear(hidden_dims[1], n_proteins)
        )

        # Learnable combination weight
        self.combination_weight = nn.Parameter(torch.tensor(0.5))

        # Store last KL for loss computation
        self._last_kl_loss = torch.tensor(0.0)

    @staticmethod
    def _make_encoder(input_dim, hidden_dims, output_dim, dropout_rate, act_fn):
        """Build a standard encoder block."""
        return nn.Sequential(
            nn.Linear(input_dim, hidden_dims[0]),
            act_fn,
            nn.Dropout(dropout_rate),
            nn.Linear(hidden_dims[0], hidden_dims[1]),
            act_fn,
            nn.Dropout(dropout_rate),
            nn.Linear(hidden_dims[1], output_dim)
        )

    def _reparameterize(self, mu: torch.Tensor, logvar: torch.Tensor) -> torch.Tensor:
        """VAE reparameterization trick."""
        if self.training:
            std = (0.5 * logvar).exp()
            eps = torch.randn_like(std)
            return mu + eps * std
        return mu

    def encode_proteins(self, x: torch.Tensor) -> torch.Tensor:
        """
        Encode features (rows) with optional modality-specific encoders.

        Args:
            x: [batch_size, n_proteins, n_samples]

        Returns:
            embeddings: [batch_size, n_proteins, protein_embedding_dim]
        """
        batch_size = x.shape[0]

        if self.has_dual_encoders:
            # Split by modality
            x_a = x[:, :self.modality_split, :]  # [B, split, S]
            x_b = x[:, self.modality_split:, :]  # [B, n_proteins-split, S]

            # Encode each modality with its own encoder
            emb_a = self.modality_a_encoder(
                x_a.reshape(-1, self.n_samples)
            ).reshape(batch_size, self.modality_split, -1)

            n_b = self.n_proteins - self.modality_split
            emb_b = self.modality_b_encoder(
                x_b.reshape(-1, self.n_samples)
            ).reshape(batch_size, n_b, -1)

            embeddings = torch.cat([emb_a, emb_b], dim=1)
        else:
            x_flat = x.reshape(-1, self.n_samples)
            embeddings = self.protein_encoder(x_flat).reshape(batch_size, self.n_proteins, -1)

        # VAE bottleneck
        if self.use_vae:
            mu = self.protein_mu(embeddings)
            logvar = self.protein_logvar(embeddings)
            embeddings = self._reparameterize(mu, logvar)
            # Store KL for loss (summed across embedding dims, averaged across batch & features)
            kl = -0.5 * (1 + logvar - mu.pow(2) - logvar.exp()).sum(dim=-1).mean()
            self._last_kl_loss = kl
        else:
            self._last_kl_loss = torch.tensor(0.0, device=x.device)

        return embeddings

    def encode_samples(self, x: torch.Tensor) -> torch.Tensor:
        """
        Encode samples (columns) across all features.

        Args:
            x: [batch_size, n_proteins, n_samples]

        Returns:
            embeddings: [batch_size, n_samples, sample_embedding_dim]
        """
        batch_size = x.shape[0]
        x_t = x.transpose(1, 2).reshape(-1, self.n_proteins)
        embeddings = self.sample_encoder(x_t).reshape(batch_size, self.n_samples, -1)

        # VAE bottleneck for samples
        if self.use_vae:
            mu = self.sample_mu(embeddings)
            logvar = self.sample_logvar(embeddings)
            embeddings = self._reparameterize(mu, logvar)
            kl = -0.5 * (1 + logvar - mu.pow(2) - logvar.exp()).sum(dim=-1).mean()
            self._last_kl_loss = self._last_kl_loss + kl

        return embeddings

    def forward(self, x: torch.Tensor, return_embeddings: bool = False) -> Union[torch.Tensor, Tuple[torch.Tensor, Dict]]:
        """
        Forward pass through the autoencoder.

        Args:
            x: Input tensor [batch_size, n_proteins, n_samples]
            return_embeddings: Whether to return embeddings along with reconstruction

        Returns:
            reconstruction or (reconstruction, embeddings_dict)
        """
        # Encode
        protein_embeddings = self.encode_proteins(x)
        sample_embeddings = self.encode_samples(x)

        # Decode
        protein_reconstruction = self.protein_decoder(protein_embeddings)
        sample_reconstruction = self.sample_decoder(sample_embeddings).transpose(1, 2)

        # Combine
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

    def get_kl_loss(self) -> torch.Tensor:
        """Return KL divergence loss from last forward pass."""
        return self._last_kl_loss

    def get_embedding_norm_loss(self, protein_embeddings: torch.Tensor) -> torch.Tensor:
        """
        Compute embedding norm regularization loss.

        Penalizes deviation of embedding L2 norms from target.
        """
        norms = protein_embeddings.norm(dim=-1)  # [B, n_proteins]
        return (norms - self.embedding_norm_target).pow(2).mean()


class DecoyGenerator:
    """
    Generates decoy inputs from real data using configurable strategies.

    Decoys are randomized versions of real data that destroy biological signal
    while preserving statistical properties. Used for negative contrastive learning.
    """

    STRATEGIES = ('row_shuffle', 'col_shuffle', 'full_shuffle', 'gaussian', 'block_shuffle')

    def __init__(self, strategy: str = 'row_shuffle', n_decoys: int = 1):
        """
        Args:
            strategy: One of 'row_shuffle', 'col_shuffle', 'full_shuffle',
                      'gaussian', 'block_shuffle'
            n_decoys: Number of decoy variants to generate per real batch
        """
        if strategy not in self.STRATEGIES:
            raise ValueError(f"strategy must be one of {self.STRATEGIES}, got '{strategy}'")
        self.strategy = strategy
        self.n_decoys = n_decoys

    def generate(self, real_data: torch.Tensor) -> torch.Tensor:
        """
        Generate decoy batch from real data.

        Args:
            real_data: [B, n_proteins, n_samples]

        Returns:
            decoys: [B * n_decoys, n_proteins, n_samples]
        """
        decoys = []
        for _ in range(self.n_decoys):
            if self.strategy == 'row_shuffle':
                decoys.append(self._row_shuffle(real_data))
            elif self.strategy == 'col_shuffle':
                decoys.append(self._col_shuffle(real_data))
            elif self.strategy == 'full_shuffle':
                decoys.append(self._full_shuffle(real_data))
            elif self.strategy == 'gaussian':
                decoys.append(self._gaussian(real_data))
            elif self.strategy == 'block_shuffle':
                decoys.append(self._block_shuffle(real_data))
        return torch.cat(decoys, dim=0)

    def _row_shuffle(self, x: torch.Tensor) -> torch.Tensor:
        """Independently shuffle each row (protein) across samples."""
        B, P, S = x.shape
        decoy = x.clone()
        for b in range(B):
            for p in range(P):
                idx = torch.randperm(S)
                decoy[b, p, :] = decoy[b, p, idx]
        return decoy

    def _col_shuffle(self, x: torch.Tensor) -> torch.Tensor:
        """Independently shuffle each column (sample) across proteins."""
        B, P, S = x.shape
        decoy = x.clone()
        for b in range(B):
            for s in range(S):
                idx = torch.randperm(P)
                decoy[b, :, s] = decoy[b, idx, s]
        return decoy

    def _full_shuffle(self, x: torch.Tensor) -> torch.Tensor:
        """Shuffle entire matrix flat — destroys all structure."""
        B, P, S = x.shape
        decoy = x.clone()
        for b in range(B):
            flat = decoy[b].reshape(-1)
            idx = torch.randperm(flat.shape[0])
            decoy[b] = flat[idx].reshape(P, S)
        return decoy

    def _gaussian(self, x: torch.Tensor) -> torch.Tensor:
        """Replace with Gaussian noise matching per-row mean and std."""
        B, P, S = x.shape
        mean = x.mean(dim=2, keepdim=True)  # [B, P, 1]
        std = x.std(dim=2, keepdim=True).clamp(min=1e-6)   # [B, P, 1]
        return torch.randn_like(x) * std + mean

    def _block_shuffle(self, x: torch.Tensor) -> torch.Tensor:
        """Shuffle contiguous blocks of rows (proteins) together."""
        B, P, S = x.shape
        block_size = max(1, P // 10)  # ~10 blocks
        decoy = x.clone()
        for b in range(B):
            n_blocks = (P + block_size - 1) // block_size
            block_order = torch.randperm(n_blocks)
            rows = []
            for bi in block_order:
                start = bi * block_size
                end = min(start + block_size, P)
                rows.append(decoy[b, start:end, :])
            decoy[b] = torch.cat(rows, dim=0)[:P]
        return decoy


class NegativeContrastiveLoss(nn.Module):
    """
    Computes negative contrastive loss on decoy reconstructions.

    The model should reconstruct decoys poorly — this loss encourages
    high reconstruction error on decoy inputs.
    """

    LOSS_TYPES = ('margin', 'negative_mse', 'log_ratio')

    def __init__(
        self,
        loss_type: str = 'margin',
        margin: float = 1.0,
        clip_value: float = 10.0
    ):
        """
        Args:
            loss_type: One of 'margin', 'negative_mse', 'log_ratio'
            margin: Margin threshold for margin-based loss
            clip_value: Maximum value to clip negative loss (stability)
        """
        super().__init__()
        if loss_type not in self.LOSS_TYPES:
            raise ValueError(f"loss_type must be one of {self.LOSS_TYPES}, got '{loss_type}'")
        self.loss_type = loss_type
        self.margin = margin
        self.clip_value = clip_value

    def forward(
        self,
        decoy_input: torch.Tensor,
        decoy_reconstruction: torch.Tensor,
        real_loss: Optional[torch.Tensor] = None
    ) -> torch.Tensor:
        """
        Compute negative contrastive loss.

        Args:
            decoy_input: Original decoy tensor
            decoy_reconstruction: Model output for decoy input
            real_loss: Reconstruction loss on real data (needed for log_ratio)

        Returns:
            Scalar loss tensor (to be minimized — negative values push decoy error up)
        """
        # Reconstruction error on decoys (we want this to be HIGH)
        decoy_error = F.mse_loss(decoy_reconstruction, decoy_input)

        if self.loss_type == 'margin':
            # Loss = max(0, margin - decoy_error)
            # Zero gradient once decoy error exceeds margin
            loss = torch.clamp(self.margin - decoy_error, min=0.0)

        elif self.loss_type == 'negative_mse':
            # Directly minimize negative of decoy error (maximize error)
            loss = -decoy_error

        elif self.loss_type == 'log_ratio':
            # Encourage high ratio of decoy error to real error
            if real_loss is None:
                raise ValueError("real_loss is required for log_ratio loss type")
            eps = 1e-8
            loss = -torch.log(decoy_error / (real_loss + eps) + eps)

        # Clip for stability
        loss = torch.clamp(loss, min=-self.clip_value, max=self.clip_value)
        return loss


class ProteomicsAutoencoderTrainer:
    """Trainer class for the proteomics autoencoder"""

    def __init__(
        self,
        model: BiDirectionalAutoencoder,
        learning_rate: float = 1e-3,
        weight_decay: float = 1e-5,
        reconstruction_loss: str = 'mse',
        device: Optional[torch.device] = None,
        contrastive_args: Optional[Dict] = None
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

        # Mixed precision training support (P3: CUDA AMP)
        self.use_amp = (device is not None and device.type == 'cuda')
        if self.use_amp:
            self.scaler = torch.amp.GradScaler('cuda')

        # Negative contrastive loss setup
        self._setup_contrastive(contrastive_args)

    def _setup_contrastive(self, contrastive_args: Optional[Dict]):
        """Initialize contrastive loss components from config dict."""
        if contrastive_args is None:
            contrastive_args = {}

        self.use_contrastive = contrastive_args.get('enabled', False)

        if self.use_contrastive:
            self.decoy_generator = DecoyGenerator(
                strategy=contrastive_args.get('decoy_strategy', 'row_shuffle'),
                n_decoys=contrastive_args.get('n_decoys', 1),
            )
            self.negative_loss_fn = NegativeContrastiveLoss(
                loss_type=contrastive_args.get('loss_type', 'margin'),
                margin=contrastive_args.get('margin', 1.0),
                clip_value=contrastive_args.get('clip_negative_loss', 10.0),
            )
            self.contrastive_lambda = contrastive_args.get('lambda_negative', 0.1)
            self.contrastive_max_lambda = contrastive_args.get('max_lambda', 0.5)
            self.contrastive_warmup = contrastive_args.get('warmup_epochs', 10)
            # Track for logging
            self.negative_losses: List[float] = []

    def _get_current_lambda(self, epoch: int) -> float:
        """Compute lambda for negative loss with linear ramp-up after warmup."""
        if epoch < self.contrastive_warmup:
            return 0.0
        # Linear ramp from lambda_negative to max_lambda over same number of epochs as warmup
        ramp_epochs = max(self.contrastive_warmup, 1)
        progress = min((epoch - self.contrastive_warmup) / ramp_epochs, 1.0)
        return self.contrastive_lambda + (self.contrastive_max_lambda - self.contrastive_lambda) * progress

    def train_epoch(
        self,
        dataset: ProteomicsDataset,
        device: torch.device,
        n_batches: int = 100,
        mini_batch_size: int = 10,
        epoch: int = 0
    ) -> float:
        """
        Train for one epoch using random masking with batched mask generation.

        Args:
            dataset: The proteomics dataset
            device: Device for computation
            n_batches: Total number of mask patterns to train on per epoch
            mini_batch_size: Number of masks to process simultaneously per gradient step
            epoch: Current epoch number (for contrastive lambda scheduling)
        """
        self.model.train()
        total_loss = 0.0
        total_neg_loss = 0.0
        n_steps = 0

        # Determine contrastive lambda for this epoch
        use_neg = self.use_contrastive and epoch >= self.contrastive_warmup
        current_lambda = self._get_current_lambda(epoch) if use_neg else 0.0

        for i in range(0, n_batches, mini_batch_size):
            B = min(mini_batch_size, n_batches - i)

            # Generate multiple masks at once (P3: batch mask generation)
            masks = torch.rand(B, dataset.n_proteins, dataset.n_samples) < dataset.mask_probability
            data_expanded = dataset.data_tensor.unsqueeze(0).expand(B, -1, -1)
            masked_data = data_expanded.clone()
            masked_data[masks] = 0

            # Move to device once per mini-batch (reduces transfers)
            masked_data = masked_data.to(device)
            masks = masks.to(device)
            target = data_expanded.to(device)

            self.optimizer.zero_grad()

            # Forward pass with optional mixed precision
            if self.use_amp:
                with torch.amp.autocast('cuda'):
                    reconstruction = self.model(masked_data)
                    recon_loss = self.criterion(reconstruction[masks], target[masks])

                    # Negative contrastive loss
                    if use_neg and current_lambda > 0:
                        decoys = self.decoy_generator.generate(data_expanded).to(device)
                        decoy_reconstruction = self.model(decoys)
                        neg_loss = self.negative_loss_fn(decoys, decoy_reconstruction, recon_loss)
                        loss = recon_loss + current_lambda * neg_loss
                        total_neg_loss += neg_loss.item()
                    else:
                        loss = recon_loss

                self.scaler.scale(loss).backward()
                self.scaler.step(self.optimizer)
                self.scaler.update()
            else:
                reconstruction = self.model(masked_data)
                recon_loss = self.criterion(reconstruction[masks], target[masks])

                # Negative contrastive loss
                if use_neg and current_lambda > 0:
                    decoys = self.decoy_generator.generate(data_expanded).to(device)
                    decoy_reconstruction = self.model(decoys)
                    neg_loss = self.negative_loss_fn(decoys, decoy_reconstruction, recon_loss)
                    loss = recon_loss + current_lambda * neg_loss
                    total_neg_loss += neg_loss.item()
                else:
                    loss = recon_loss

                loss.backward()
                self.optimizer.step()

            total_loss += loss.item()
            n_steps += 1

        # Track negative loss history
        if self.use_contrastive:
            self.negative_losses.append(total_neg_loss / max(n_steps, 1))

        return total_loss / n_steps

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

def get_optimal_device() -> torch.device:
    """
    Select best available compute device with preference cascade.

    Returns CUDA if available, then Apple Metal (MPS), then CPU with
    optimized thread count. With batched encoding (no sequential loops),
    GPU acceleration is now beneficial even for smaller models.
    """
    if torch.cuda.is_available():
        device = torch.device('cuda')
        print(f"Using CUDA: {torch.cuda.get_device_name(0)}")
    elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
        device = torch.device('mps')
        print("Using Apple Metal (MPS)")
    else:
        device = torch.device('cpu')
        n_threads = min(os.cpu_count() or 4, 8)
        torch.set_num_threads(n_threads)
        print(f"Using CPU with {n_threads} threads")
    return device


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
    early_stopping_patience: int = 20,
    min_delta: float = 1e-5,
    contrastive_args: Optional[Dict] = None,
    modality_split: Optional[int] = None,
    use_vae: bool = False,
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
        early_stopping_patience: Number of validation checks without improvement
            before stopping. Set to 0 to disable early stopping.
        min_delta: Minimum improvement in validation loss to reset patience counter.
        contrastive_args: Optional dict configuring negative contrastive loss.
            Keys: strategy (str), n_decoys (int), loss_type (str), margin (float),
            lambda_weight (float), warmup_epochs (int), ramp_epochs (int).
            If None, contrastive loss is disabled.
        modality_split: Row index where first modality ends. When provided,
            ModalityAwareAutoencoder is used with separate encoders per modality.
            If None (default), uses BiDirectionalAutoencoder (backward compatible).
        use_vae: If True, enables variational bottleneck (requires modality_split
            to use ModalityAwareAutoencoder). Default False.

    Returns:
        Tuple of (trained_model, dataset, training_history)
    """

    if device is None:
        device = get_optimal_device()

    print(f"Training on device: {device}")
    print(f"Data shape: {data.shape}")

    # Create dataset
    dataset = ProteomicsDataset(
        data,
        mask_probability=mask_probability,
        scaling_method=scaling_method
    )

    # Create model — use ModalityAwareAutoencoder when modality_split is specified
    if modality_split is not None or use_vae:
        model = ModalityAwareAutoencoder(
            n_proteins=dataset.n_proteins,
            n_samples=dataset.n_samples,
            protein_embedding_dim=protein_embedding_dim,
            sample_embedding_dim=sample_embedding_dim,
            hidden_dims=hidden_dims,
            modality_split=modality_split,
            use_vae=use_vae,
        ).to(device)
        if modality_split is not None:
            print(f"Using ModalityAwareAutoencoder (split at row {modality_split})")
        if use_vae:
            print("VAE bottleneck enabled")
    else:
        model = BiDirectionalAutoencoder(
            n_proteins=dataset.n_proteins,
            n_samples=dataset.n_samples,
            protein_embedding_dim=protein_embedding_dim,
            sample_embedding_dim=sample_embedding_dim,
            hidden_dims=hidden_dims
        ).to(device)

    # Apply torch.compile() for PyTorch 2.0+ (P2: kernel fusion optimization)
    # Only use on CUDA — MPS Metal shader compilation is experimental and buggy
    if hasattr(torch, 'compile') and device.type == 'cuda':
        try:
            model = torch.compile(model)
            print("Model compiled with torch.compile()")
        except Exception as e:
            print(f"torch.compile() failed, using eager mode: {e}")

    # Create trainer with device info for AMP support
    trainer = ProteomicsAutoencoderTrainer(
        model, learning_rate=learning_rate, device=device,
        contrastive_args=contrastive_args
    )

    # Training loop with early stopping (P2)
    train_losses = []
    val_losses = []
    best_val_loss = float('inf')
    patience_counter = 0
    best_model_state = None

    print("Starting training...")
    for epoch in range(epochs):
        # Train
        train_loss = trainer.train_epoch(dataset, device, epoch=epoch)
        train_losses.append(train_loss)

        # Validate every 10 epochs
        if epoch % 10 == 0:
            val_loss = trainer.validate(dataset, device)
            val_losses.append(val_loss)

            print(f"Epoch {epoch+1}/{epochs}, Train Loss: {train_loss:.6f}, Val Loss: {val_loss:.6f}")

            # Early stopping check
            if val_loss < best_val_loss - min_delta:
                best_val_loss = val_loss
                patience_counter = 0
                best_model_state = {k: v.clone() for k, v in model.state_dict().items()}
            else:
                patience_counter += 1
                if early_stopping_patience > 0 and patience_counter >= early_stopping_patience:
                    print(f"Early stopping at epoch {epoch+1} (no improvement for {patience_counter} checks)")
                    if best_model_state:
                        model.load_state_dict(best_model_state)
                    break

    # Final validation
    final_val_loss = trainer.validate(dataset, device)
    val_losses.append(final_val_loss)

    training_history = {
        'train_losses': train_losses,
        'val_losses': val_losses,
        'final_train_loss': train_losses[-1],
        'final_val_loss': final_val_loss,
        'epochs_trained': len(train_losses),
        'early_stopped': len(train_losses) < epochs
    }

    # Include negative contrastive loss history if enabled
    if trainer.use_contrastive and trainer.negative_losses:
        training_history['negative_losses'] = trainer.negative_losses

    print(f"Training completed. Final train loss: {train_losses[-1]:.6f}, Final val loss: {final_val_loss:.6f}")
    if training_history['early_stopped']:
        print(f"  (early stopped after {len(train_losses)} of {epochs} epochs)")

    # Calculate similarity matrix
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
        device = get_optimal_device()

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
