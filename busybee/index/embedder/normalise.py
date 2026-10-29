"""Shared row normalisation for the embedder implementations.

Every provider returns unit-length rows so the vector store can use a dot product as cosine
similarity. All-zero rows (for example the embedding of empty text) are left as zeros because
there is no meaningful direction to normalise.
"""

import numpy as np


def normalise_rows(matrix: np.ndarray) -> np.ndarray:
    """Return a float32 copy of matrix with every non-zero row scaled to unit L2 length."""
    result = np.array(matrix, dtype=np.float32, copy=True)
    if result.ndim == 1:
        result = result.reshape(1, -1)
    norms = np.linalg.norm(result, axis=1, keepdims=True)
    np.divide(result, norms, out=result, where=norms > 0)
    return result
