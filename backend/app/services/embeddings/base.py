"""
app/services/embeddings/base.py

Embedding (Vektörleştirme) servisleri için soyutlama (abstraction).
Tıpkı LLMProvider gibi, projemizi tek bir provider'a (Google) bağımlı yapmıyoruz.
Yarın OpenAI veya lokal bir model kullanmak istersek sadece yeni bir class ekleyeceğiz.
"""

from abc import ABC, abstractmethod
from typing import List


class EmbeddingProvider(ABC):
    """
    Tüm embedding sağlayıcılarının uyması gereken şablon.
    """

    @abstractmethod
    async def embed_text(self, text: str) -> List[float]:
        """
        Tek bir metni alır, sayısal bir vektöre çevirip döndürür.
        """
        pass

    @abstractmethod
    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Birden fazla metni aynı anda vektöre çevirir (performans için).
        """
        pass

    @property
    @abstractmethod
    def dimension(self) -> int:
        """
        Bu provider'ın döndürdüğü vektörlerin boyutu (Örn: Gemini için 768).
        Qdrant koleksiyonunu oluştururken buna ihtiyacımız var.
        """
        pass
