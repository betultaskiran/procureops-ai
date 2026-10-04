"""
app/services/llm/__init__.py

LLM provider singleton'ı burada yönetilir.

get_llm_provider():
  FastAPI dependency olarak kullanılabilir veya
  doğrudan import edilebilir.

  Neden singleton?
    - Her request'te yeni bir google.genai.Client oluşturmak gereksiz
    - Client bir connection pool yönetir — tek instance daha verimli
    - Thread-safe (genai.Client async-safe)
"""

from functools import lru_cache

from app.core.config import settings
from app.services.llm.base import LLMProvider, EXTRACTION_CONFIG, REASONING_CONFIG
from app.services.llm.gemini import GeminiProvider


@lru_cache(maxsize=1)
def get_llm_provider() -> LLMProvider:
    """
    LLMProvider singleton'ı döndürür.

    lru_cache(maxsize=1):
      İlk çağrıda oluşturulur, sonraki çağrılarda aynı instance döner.
      Bu bir Python-native singleton pattern'idir.

    Ileride başka bir provider'a geçmek için sadece bu fonksiyonu değiştir:
      return OpenAIProvider(api_key=settings.OPENAI_API_KEY)
      return AnthropicProvider(api_key=settings.ANTHROPIC_API_KEY)
    """
    return GeminiProvider(
        api_key=settings.GEMINI_API_KEY,
        model=settings.GEMINI_MODEL,
    )


__all__ = [
    "get_llm_provider",
    "LLMProvider",
    "EXTRACTION_CONFIG",
    "REASONING_CONFIG",
]
