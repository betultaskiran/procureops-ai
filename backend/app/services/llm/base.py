"""
app/services/llm/base.py

Provider-agnostic LLM interface.

NEDEN ABSTRACTION?

Doğrudan openai.chat.completions.create() veya google.genai.generate_content()
yazmak yerine bir interface tanımlıyoruz. Bu sayede:

1. Provider değişikliği = sadece bir dosyayı değiştirmek
2. Test ortamında LLM'i mock'lamak kolay (MockProvider)
3. Hangi yeteneğin hangi provider'dan bekleneceği açık

Protocol vs ABC:
  Python'da iki yol var: ABC (abstract base class) veya Protocol.
  ABC kullandık çünkü:
    - Subclass zorunluluğu → provider yanlışlıkla interface'i atlamaz
    - IDE desteği daha iyi
    - Beklenti açık: "Sen bir LLMProvider'sın, bu metodları ZORUNLU implemente et"
"""

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel


class ExtractionConfig:
    """
    LLM'e extraction görevi verirken kullanılan konfigürasyon.

    thinking_budget:
      Gemini 2.5 Flash'ın "düşünme" token bütçesi.
        0    = Thinking kapalı (hızlı, ucuz — extraction için ideal)
        1024 = Kısa düşünme (orta karmaşıklık)
        8192 = Uzun düşünme (Phase 9 agent reasoning için)

      Neden burada? Her provider'ın "thinking" kavramı farklı.
      Bu config hem Gemini hem de gelecekte eklenen başka
      provider'lar için ortak bir dil sağlar.
    """
    def __init__(
        self,
        thinking_budget: int = 0,
        temperature: float = 0.1,
        max_output_tokens: int | None = None,
    ):
        self.thinking_budget = thinking_budget
        self.temperature = temperature         # 0.0 = deterministic, 1.0 = creative
        self.max_output_tokens = max_output_tokens


# Extraction için önerilen konfig (hızlı ve deterministik)
EXTRACTION_CONFIG = ExtractionConfig(thinking_budget=0, temperature=0.1)

# Agent reasoning için önerilen konfig (Phase 9)
REASONING_CONFIG = ExtractionConfig(thinking_budget=4096, temperature=0.3)


class LLMProvider(ABC):
    """
    Abstract base class. Tüm LLM provider'ları bu interface'i implemente etmeli.

    Subclass yazan kişi iki metod yazmak zorunda:
      1. extract_structured — belirli bir Pydantic şemasında veri çıkar
      2. generate           — serbest metin üret
    """

    @abstractmethod
    async def extract_structured(
        self,
        prompt: str | list[Any],
        schema: type[BaseModel],
        system_prompt: str | None = None,
        config: ExtractionConfig | None = None,
    ) -> BaseModel:
        """
        Metinden structured veri çıkar.

        Args:
            prompt:        Extraction yapılacak metin (PDF içeriği vb.)
            schema:        Dönüş tipi — Pydantic model class'ı
            system_prompt: Provider'a verilen rol/talimat
            config:        Thinking budget, temperature vb.

        Returns:
            schema tipinde bir Pydantic instance

        Raises:
            LLMExtractionError: Extraction başarısız olursa
        """
        ...

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        config: ExtractionConfig | None = None,
    ) -> str:
        """
        Serbest metin üret. Phase 9'da agent reasoning için kullanılacak.

        Args:
            prompt:        Kullanıcı/sistem prompt'u
            system_prompt: Provider'a verilen rol/talimat
            config:        Thinking budget, temperature vb.

        Returns:
            Model'in ürettiği metin
        """
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Kullanılan model adı. Log ve audit için."""
        ...

    @property
    def last_usage_metadata(self) -> Any:
        """Son model çağrısının usage_metadata bilgisi (varsa)."""
        return None


class LLMExtractionError(Exception):
    """
    LLM extraction başarısız olduğunda fırlatılır.

    Attributes:
        message:   İnsan-okunabilir hata mesajı
        raw_response: Provider'dan gelen ham yanıt (debug için)
    """
    def __init__(self, message: str, raw_response: str | None = None):
        super().__init__(message)
        self.raw_response = raw_response
