# VaLPAS Autoencoder Performance Optimization Plan

**Date:** 2026-06-29  
**Status:** Planning (no changes implemented yet)  
**Scope:** `src/valpas/_core/autoencoder.py`

---

## Architecture Summary

The core autoencoder (`BiDirectionalAutoencoder`) works as follows:

1. Encodes each protein (row) across samples → protein embeddings (dim=128)
2. Encodes each sample (column) across proteins → sample embeddings (dim=64)
3. Decodes from both embeddings with a learned combination weight (sigmoid-gated α)
4. Uses masked reconstruction loss (BERT-style 15% masking)

Training runs for **200 epochs × 100 batches/epoch = 20,000 forward/backward passes**.

Typical data dimensions:
- E. coli: 3036 proteins × 278 samples
- P. putida: 3036 KOs × 398 samples
- A. baumannii: 3036 KOs × 139 samples

---

## Critical Bottlenecks

### 🔴 Bottleneck 1: Sequential Protein/Sample Encoding (HIGHEST IMPACT)

**Location:** `encode_proteins()` (line ~188) and `encode_samples()` (line ~201)

```python
def encode_proteins(self, x):
    for i in range(self.n_proteins):          # loops over ~3036 proteins!
        protein_data = x[:, i, :]
        embedding = self.protein_encoder(protein_data)
        protein_embeddings.append(embedding)
    return torch.stack(protein_embeddings, dim=1)
```

This iterates **sequentially** over every protein (3036 for E. coli) calling the encoder one-at-a-time. The same `nn.Sequential` network is applied to each row — this is a textbook case for **batched matrix multiplication**.

**Fix (CPU + GPU):** Reshape and batch the entire operation:

```python
def encode_proteins(self, x):
    # x: [batch, n_proteins, n_samples] → [batch * n_proteins, n_samples]
    batch_size = x.shape[0]
    x_flat = x.reshape(-1, self.n_samples)       # [batch*n_proteins, n_samples]
    embeddings = self.protein_encoder(x_flat)     # single forward pass through nn.Sequential
    return embeddings.reshape(batch_size, self.n_proteins, -1)

def encode_samples(self, x):
    # x: [batch, n_proteins, n_samples] → transpose → [batch * n_samples, n_proteins]
    batch_size = x.shape[0]
    x_t = x.transpose(1, 2).reshape(-1, self.n_proteins)
    embeddings = self.sample_encoder(x_t)
    return embeddings.reshape(batch_size, self.n_samples, -1)
```

**Expected speedup:** 50–200× on CPU, 500–1000× on GPU (eliminates Python loop overhead and enables BLAS/cuBLAS parallelism over the batch dimension).

**Why this works:** `nn.Sequential` with `nn.Linear` layers already supports arbitrary batch dimensions. A `[3036, 278]` input to the protein_encoder (which expects `[*, 278]`) will produce `[3036, 128]` output in a single optimized GEMM call.

---

### 🔴 Bottleneck 2: Masking Creates New Tensors Every Batch

**Location:** `create_masked_batch()` (line ~85)

Every single training step (20,000×) allocates:
- A new random mask tensor via `torch.rand(...)`
- A `.clone()` of the full data tensor
- Three `.unsqueeze(0)` calls creating new views

**Fix (CPU):** Pre-allocate mask buffer and reuse:

```python
# In __init__:
self._mask_buffer = torch.empty(self.n_proteins, self.n_samples)
self._masked_data_buffer = torch.empty_like(self.data_tensor)

def create_masked_batch(self):
    self._mask_buffer.uniform_()
    mask = self._mask_buffer < self.mask_probability
    self._masked_data_buffer.copy_(self.data_tensor)
    self._masked_data_buffer[mask] = 0
    return self._masked_data_buffer.unsqueeze(0), mask.unsqueeze(0), self.data_tensor.unsqueeze(0)
```

**Expected speedup:** 2–5× reduction in memory allocation overhead per epoch.

---

### 🟡 Bottleneck 3: No `torch.compile()` / JIT Compilation

The model uses standard eager-mode PyTorch. For PyTorch 2.0+, wrapping with `torch.compile()` provides automatic kernel fusion and optimization.

**Fix (CPU + GPU):**

```python
model = BiDirectionalAutoencoder(...).to(device)
model = torch.compile(model)  # PyTorch 2.0+
```

**Expected speedup:** 1.3–2× on CPU (operator fusion), 1.5–3× on GPU (kernel fusion).

**Note:** Requires PyTorch ≥ 2.0. Add a version check:
```python
if hasattr(torch, 'compile'):
    model = torch.compile(model)
```

---

### 🟡 Bottleneck 4: Similarity Matrix Uses sklearn (CPU-only, O(n²))

**Location:** `calculate_protein_similarity_matrix()` (line ~464)

Calls `sklearn.metrics.pairwise.cosine_similarity` on CPU numpy arrays. For 3036 proteins × 128 dims, this is already fast (~9M pairwise ops), but for larger datasets it becomes a bottleneck.

**Fix (GPU):** Keep embeddings on GPU and compute similarity there:

```python
def calculate_protein_similarity_matrix(model, dataset, device, similarity_metric='cosine'):
    model.eval()
    with torch.no_grad():
        full_data = dataset.data_tensor.unsqueeze(0).to(device)
        protein_embeddings = model.encode_proteins(full_data).squeeze(0)  # [n_proteins, emb_dim]
        
        if similarity_metric == 'cosine':
            # GPU-accelerated cosine similarity
            embeddings_norm = F.normalize(protein_embeddings, dim=-1)
            similarity_matrix = torch.mm(embeddings_norm, embeddings_norm.t())
            similarity_matrix = similarity_matrix.cpu().numpy()
        elif similarity_metric == 'correlation':
            # Centered cosine = Pearson correlation
            centered = protein_embeddings - protein_embeddings.mean(dim=1, keepdim=True)
            centered_norm = F.normalize(centered, dim=-1)
            similarity_matrix = torch.mm(centered_norm, centered_norm.t())
            similarity_matrix = similarity_matrix.cpu().numpy()
    
    return pd.DataFrame(similarity_matrix, index=dataset.protein_names, columns=dataset.protein_names)
```

**Expected speedup:** 5–10× for large protein sets (>5000), negligible for n=3036.

---

### 🟡 Bottleneck 5: No Early Stopping

**Location:** `train_proteomics_autoencoder()` (line ~335)

Runs a fixed 200 epochs with no early stopping. Many runs converge by epoch 50–80.

**Fix:** Add patience-based early stopping:

```python
patience, best_loss, counter = 20, float('inf'), 0
best_model_state = None

for epoch in range(epochs):
    train_loss = trainer.train_epoch(dataset, device)
    train_losses.append(train_loss)
    
    if epoch % 10 == 0:
        val_loss = trainer.validate(dataset, device)
        val_losses.append(val_loss)
        
        if val_loss < best_loss - 1e-5:
            best_loss = val_loss
            counter = 0
            best_model_state = {k: v.clone() for k, v in model.state_dict().items()}
        else:
            counter += 1
            if counter >= patience:
                print(f"Early stopping at epoch {epoch+1}")
                model.load_state_dict(best_model_state)
                break
```

**Expected speedup:** 2–3× fewer epochs on average (saves wall-clock time without quality loss).

---

### 🟢 Bottleneck 6: `n_batches=100` Per Epoch is Arbitrary

**Location:** `train_epoch()` (line ~289)

Each "batch" is just a different random mask of the same full matrix. The 100 iterations per epoch with single-item "batches" means gradient steps on 100 different mask patterns.

**Fix:** Generate multiple masks simultaneously as a true batch:

```python
def train_epoch(self, dataset, device, n_batches=100):
    self.model.train()
    
    # Generate all masks at once
    all_masks = torch.rand(n_batches, dataset.n_proteins, dataset.n_samples) < dataset.mask_probability
    data_expanded = dataset.data_tensor.unsqueeze(0).expand(n_batches, -1, -1)  # [n_batches, P, S]
    masked_data = data_expanded.clone()
    masked_data[all_masks] = 0
    
    # Move to device once
    masked_data = masked_data.to(device)
    all_masks = all_masks.to(device)
    target = data_expanded.to(device)
    
    # Process in mini-batches of size B
    total_loss = 0.0
    B = 10  # mini-batch size
    for i in range(0, n_batches, B):
        self.optimizer.zero_grad()
        reconstruction = self.model(masked_data[i:i+B])
        batch_mask = all_masks[i:i+B]
        loss = self.criterion(reconstruction[batch_mask], target[i:i+B][batch_mask])
        loss.backward()
        self.optimizer.step()
        total_loss += loss.item()
    
    return total_loss / (n_batches // B)
```

**Expected speedup:** 1.5–3× (fewer device transfers, better GPU utilization).

---

## GPU Support Recommendations

### Current State

The code already has a device parameter and a commented-out MPS check (line ~371):

```python
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
# device = torch.device('mps' if torch.mps.is_available() else 'cpu')
```

The comment says *"for smaller models mps is a lot slower than cpu"* — this is true **because of the sequential encoding loop** (Bottleneck 1). Each loop iteration launches a tiny GPU kernel with massive overhead. Once batched, GPU becomes beneficial.

### Full GPU Support Implementation

```python
def get_optimal_device() -> torch.device:
    """Select best available device with preference cascade."""
    if torch.cuda.is_available():
        device = torch.device('cuda')
        print(f"Using CUDA: {torch.cuda.get_device_name(0)}")
    elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
        device = torch.device('mps')
        print("Using Apple Metal (MPS)")
    else:
        device = torch.device('cpu')
        n_threads = os.cpu_count()
        torch.set_num_threads(min(n_threads, 8))
        print(f"Using CPU with {torch.get_num_threads()} threads")
    return device
```

### Mixed Precision Training (CUDA only)

```python
from torch.cuda.amp import autocast, GradScaler

scaler = GradScaler()

for _ in range(n_batches):
    masked_data, mask, target = dataset.create_masked_batch()
    masked_data = masked_data.to(device)
    mask = mask.to(device)
    target = target.to(device)
    
    self.optimizer.zero_grad()
    
    with autocast():
        reconstruction = self.model(masked_data)
        loss = self.criterion(reconstruction[mask], target[mask])
    
    scaler.scale(loss).backward()
    scaler.step(self.optimizer)
    scaler.update()
```

**Expected speedup on GPU:** 1.5–2× throughput improvement + 50% memory reduction.

### Memory Pinning for CUDA

```python
# In ProteomicsDataset.__init__:
if torch.cuda.is_available():
    self.data_tensor = torch.FloatTensor(self.scaled_data).pin_memory()
else:
    self.data_tensor = torch.FloatTensor(self.scaled_data)
```

---

## CPU-Specific Acceleration Summary

| Technique | Change Required | Expected Gain |
|-----------|----------------|---------------|
| Batch encoding (remove for-loop) | Reshape + single forward pass | **50–200×** |
| `torch.compile()` | One-line wrapper | 1.3–2× |
| Early stopping | Add patience counter | 2–3× (wall time) |
| Buffer reuse for masks | Pre-allocate tensors | 1.2–1.5× |
| `torch.set_num_threads(N)` | Set to physical core count | 1.2–1.5× on multi-core |
| Intel MKL / OpenBLAS tuning | Environment variables | 1.1–1.3× |

---

## Priority-Ordered Implementation Plan

```
Priority 1 (Critical - do first):
  └── Fix encode_proteins/encode_samples loops → batched tensor ops
      Expected: 50-200× speedup on CPU, enables GPU

Priority 2 (High - do after Priority 1):
  ├── Enable GPU support (CUDA + MPS device cascade)
  ├── Add torch.compile() for PyTorch 2.0+
  └── Add early stopping with patience

Priority 3 (Medium - quality of life):
  ├── Mixed precision training (CUDA AMP)
  ├── Batch mask generation (process multiple masks per step)
  └── Buffer reuse for mask allocation

Priority 4 (Low - for production):
  ├── GPU-accelerated similarity matrix
  ├── Memory pinning for CUDA transfers
  └── Learning rate scheduler (OneCycleLR or CosineAnnealing)
```

---

## Estimated Total Speedup

| Scenario | Current (est.) | After Optimization | Factor |
|----------|---------------|-------------------|--------|
| E. coli (3036×278) CPU | ~25 min | ~1-2 min | 15–25× |
| E. coli (3036×278) GPU (A100) | N/A (slower than CPU due to loops) | ~15-30 sec | 50–100× |
| E. coli (3036×278) GPU (MPS M1) | N/A (slower) | ~45-90 sec | 20–35× |

*Estimates assume all Priority 1+2 changes implemented.*

---

## Backward Compatibility Notes

- All changes should preserve identical numerical results (same random seeds → same output)
- The `encode_proteins` reshape produces mathematically identical results to the loop
- Early stopping may produce slightly different models (trained fewer epochs) — consider making it opt-in via parameter
- `torch.compile()` should be wrapped in a try/except for older PyTorch versions
- GPU device selection should fall back gracefully to CPU

---

## Testing Strategy

1. **Unit test:** Verify batched `encode_proteins` produces same output as loop version
2. **Integration test:** Run E. coli pipeline end-to-end, compare similarity matrices (should be identical given same seed)
3. **Benchmark:** Time the training loop before/after on CPU and GPU
4. **Regression test:** Verify PPV/AUROC metrics are unchanged after optimization
