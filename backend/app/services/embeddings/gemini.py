"""
app/services/embeddings/gemini.py

Google Gemini için Embedding sağlayıcısı.
"""

from typing import List
from google import genai

from app.services.embeddings.base import EmbeddingProvider


class GeminiEmbeddingProvider(EmbeddingProvider):
    """
    Google'ın text-embedding-004 modelini kullanarak metinleri
    vektöre çevirir.
    """

    def __init__(self, api_key: str):
        self._client = genai.Client(api_key=api_key)
        # Google's latest embedding model
        self._model = "gemini-embedding-2"
        self._dimension = 3072

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed_text(self, text: str) -> List[float]:
        # genai.Client() async destekliyor ama embed için
        # .aio_models yerine genai.Client().aio.models kullanılıyor
        # Şimdilik basit tutmak için asenkron wrapper içinden sekron
        # veya SDK'nın async metodunu çağıralım.
        response = await self._client.aio.models.embed_content(
            model=self._model,
            contents=text,
        )
        return response.embeddings[0].values

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        # Gemini API list of string kabul eder
        response = await self._client.aio.models.embed_content(
            model=self._model,
            contents=texts,
        )
        return [emb.values for emb in response.embeddings]
