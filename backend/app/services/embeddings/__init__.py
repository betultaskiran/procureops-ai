from functools import lru_cache

from app.core.config import settings
from app.services.embeddings.base import EmbeddingProvider
from app.services.embeddings.gemini import GeminiEmbeddingProvider

@lru_cache(maxsize=1)
def get_embedding_provider() -> EmbeddingProvider:
    """
    Uygulama genelinde tek bir EmbeddingProvider (Singleton) örneği döndürür.
    """
    return GeminiEmbeddingProvider(api_key=settings.GEMINI_API_KEY)
