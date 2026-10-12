"""
app/services/llm/gemini.py

Google Gemini implementasyonu — LLMProvider interface'ini implemente eder.

SDK SEÇİMİ:
  google-genai  ← Kullandığımız (yeni, unified SDK)
  google-generativeai ← Eski SDK (deprecated, kullanmıyoruz)

  Neden yeni SDK?
  - Hem Google AI Developer API hem Vertex AI'ı destekler
  - Async API desteği (client.aio.*)
  - Pydantic model'ini doğrudan response_schema olarak kabul eder
  - Aktif olarak geliştiriliyor

THINKING BUDGET:
  Gemini 2.5 Flash "düşünme" modeline sahip.
  thinking_budget=0 → Thinking kapalı (extraction için: hızlı, ucuz)
  thinking_budget>0 → Model bu kadar token'a kadar "düşünebilir"

  Extraction görevi için thinking'e gerek yok:
    "Bu metinden fiyatı çıkar" → deterministik, düşünme gerektirmez
  Agent reasoning için thinking değerli (Phase 9):
    "Bu tedarikçileri karşılaştır, risk-fayda analizi yap" → karmaşık muhakeme
"""

import json

from google import genai
from google.genai import types
from pydantic import BaseModel

from app.services.llm.base import (
    ExtractionConfig,
    EXTRACTION_CONFIG,
    LLMExtractionError,
    LLMProvider,
)


class GeminiProvider(LLMProvider):
    """
    Google Gemini API provider.

    Oluşturma:
        provider = GeminiProvider(
            api_key="AIza...",
            model="gemini-2.5-flash",
        )

    Kullanım:
        result = await provider.extract_structured(
            prompt=pdf_text,
            schema=QuoteExtractionSchema,
        )
    """

    def __init__(self, api_key: str, model: str = "gemini-3.8-flash"):
        # client.aio.* → async API
        # client.models.* → sync API (kullanmıyoruz)
        self._client = genai.Client(api_key=api_key)
        self._model = model

    @property
    def model_name(self) -> str:
        return self._model

    def _build_config(
        self,
        schema: type[BaseModel],
        system_prompt: str | None,
        config: ExtractionConfig,
    ) -> types.GenerateContentConfig:
        """
        GenerateContentConfig oluşturur.

        response_mime_type="application/json" + response_schema=PydanticClass:
          Gemini'yi belirli bir JSON şemasında yanıt vermeye zorlar.
          Bu "structured output" veya "constrained decoding" olarak bilinir.
          Model sadece geçerli JSON üretebilir — serbest metin üretemez.

        ThinkingConfig(thinking_budget=0):
          Extraction için thinking'i devre dışı bırakır.
          Bu ~2-5 saniyelik latency kazancı ve önemli token tasarrufu sağlar.
        """
        kwargs = {
            "response_mime_type": "application/json",
            "response_schema": schema,
            "system_instruction": system_prompt,
            "temperature": config.temperature,
        }
        if "lite" not in self._model.lower() and config.thinking_budget is not None:
            kwargs["thinking_config"] = types.ThinkingConfig(
                thinking_budget=config.thinking_budget,
            )
        if config.max_output_tokens:
            kwargs["max_output_tokens"] = config.max_output_tokens

        return types.GenerateContentConfig(**kwargs)

    async def extract_structured(
        self,
        prompt: str,
        schema: type[BaseModel],
        system_prompt: str | None = None,
        config: ExtractionConfig | None = None,
    ) -> BaseModel:
        """
        Metinden Pydantic şemasına uygun veri çıkarır.

        Neden iki aşamalı validation?
        1. Gemini → JSON (API seviyesi şema zorlaması)
        2. schema.model_validate_json() → Pydantic validation
           (field_validator'lar çalışır: vat_rate normalizasyonu vb.)

        Bu iki aşama birbirini tamamlar:
          API → doğru şekil garantisi
          Pydantic → doğru değer garantisi
        """
        cfg = config or EXTRACTION_CONFIG
        gen_config = self._build_config(schema, system_prompt, cfg)

        try:
            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=prompt,
                config=gen_config,
            )
        except Exception as e:
            raise LLMExtractionError(
                f"Gemini API call failed: {e}"
            ) from e

        raw_text = response.text
        if not raw_text:
            raise LLMExtractionError(
                "Gemini returned empty response",
                raw_response=str(response),
            )

        try:
            # Pydantic validation — field_validator'lar burada çalışır
            return schema.model_validate_json(raw_text)
        except Exception as e:
            raise LLMExtractionError(
                f"Pydantic validation failed after Gemini extraction: {e}",
                raw_response=raw_text,
            ) from e

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        config: ExtractionConfig | None = None,
    ) -> str:
        """
        Serbest metin üretir. Phase 9'da agent reasoning için kullanılacak.
        Structured output yok — sadece metin döner.
        """
        cfg = config or EXTRACTION_CONFIG
        kwargs = {
            "system_instruction": system_prompt,
            "temperature": cfg.temperature,
        }
        if "lite" not in self._model.lower() and cfg.thinking_budget is not None:
            kwargs["thinking_config"] = types.ThinkingConfig(
                thinking_budget=cfg.thinking_budget,
            )
        gen_config = types.GenerateContentConfig(**kwargs)

        try:
            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=prompt,
                config=gen_config,
            )
        except Exception as e:
            raise LLMExtractionError(f"Gemini API call failed: {e}") from e

        return response.text or ""
