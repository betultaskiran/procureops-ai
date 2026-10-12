"""
app/services/embeddings/gemini.py

Google Gemini için Embedding sağlayıcısı.
"""

import asyncio
from typing import List
from google import genai

from app.services.embeddings.base import EmbeddingProvider


class GeminiEmbeddingProvider(EmbeddingProvider):
    """
    Google'ın gemini-embedding-2 modelini kullanarak metinleri
    vektöre çevirir.
    """

    def __init__(self, api_key: str):
        self._api_key = api_key
        # Google's latest embedding model
        self._model = "gemini-embedding-2"
        self._dimension = 3072
        self._client = None
        self._loop = None

    def _get_client(self) -> genai.Client:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if self._client is None or self._loop != loop or (self._loop and self._loop.is_closed()):
            self._client = genai.Client(api_key=self._api_key)
            self._loop = loop
        return self._client

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed_text(self, text: str) -> List[float]:
        client = self._get_client()
        response = await client.aio.models.embed_content(
            model=self._model,
            contents=text,
        )
        return response.embeddings[0].values

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Her metin için ayrı ayrı dense embedding üretir.
        google-genai SDK'da tek çağrıda liste verilmesi tek bir multi-part içerik
        olarak işlendiğinden, asyncio.gather ile paralel çağrı yapılır.
        """
        if not texts:
            return []
        tasks = [self.embed_text(text) for text in texts]
        return await asyncio.gather(*tasks)
