"""Lazy-load sentence-transformers for story memory retrieval."""

import logging

logger = logging.getLogger(__name__)

# Default model: BGE-small Chinese, ~100MB, CPU-friendly, 512-dim
DEFAULT_MODEL = "BAAI/bge-small-zh-v1.5"

# Keep the query instruction expected by the original Chinese embedding model.
BGE_ZH_QUERY_INSTRUCTION = "为这个句子生成表示以用于检索相关文章："
BGE_QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "


class Embedder:
    """Lazy-loading embedding model for novel text.

    The model is loaded on first use, not at import time. This means
    the module can be imported even without sentence-transformers installed —
    you only get an error when you actually call embed().
    """

    def __init__(self, model_name: str | None = None):
        self._model_name = model_name or DEFAULT_MODEL
        self._query_instruction = (
            BGE_ZH_QUERY_INSTRUCTION if "-zh" in self._model_name.lower() else BGE_QUERY_INSTRUCTION
        )
        self._model = None

    @property
    def model(self):
        """Lazy-load the sentence-transformers model."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError:
                raise ImportError(
                    "sentence-transformers is required for RAG embeddings. Install with: pip install novel-agent[rag]"
                )
            logger.info(f"Loading embedding model: {self._model_name}")
            self._model = SentenceTransformer(self._model_name)
            logger.info(f"Model loaded, dim={self._model.get_sentence_embedding_dimension()}")
        return self._model

    @property
    def dim(self) -> int:
        """Embedding dimension."""
        return self.model.get_sentence_embedding_dimension()

    def embed(self, texts: list[str], show_progress: bool = False) -> list[list[float]]:
        """Embed a batch of document texts.

        Documents are encoded as-is (no instruction prefix for BGE).
        """
        if not texts:
            return []
        embeddings = self.model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=show_progress,
        )
        return embeddings.tolist()

    def embed_query(self, query: str) -> list[float]:
        """Embed a search query.

        For BGE models, queries get an instruction prefix to
        differentiate them from documents in the embedding space.
        """
        result = self.model.encode(
            [self._query_instruction + query],
            normalize_embeddings=True,
        )
        return result[0].tolist()

    def embed_queries(self, queries: list[str]) -> list[list[float]]:
        """Embed multiple search queries."""
        if not queries:
            return []
        prefixed = [self._query_instruction + q for q in queries]
        embeddings = self.model.encode(prefixed, normalize_embeddings=True)
        return embeddings.tolist()
