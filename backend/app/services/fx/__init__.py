"""
app/services/fx

FX Engine (Döviz Kuru Çevirisi) modülü.
"""

from app.services.fx.base import BaseExchangeRateProvider
from app.services.fx.exceptions import (
    CurrencyConversionUnavailableException,
    FXEngineError,
    FXFutureDateError,
    FXInvalidDataError,
    FXLookbackLimitExceededError,
    FXProviderError,
    FXRateNotFoundError,
)
from app.services.fx.mock_provider import MockExchangeRateProvider
from app.services.fx.policy import (
    calculate_conversion,
    is_same_currency,
    resolve_candidate_dates,
    validate_currency_code,
)
from app.services.fx.schemas import ExchangeRateDTO
from app.services.fx.service import ExchangeRateService
from app.services.fx.tcmb_provider import (
    SUPPORTED_RATE_TYPES,
    TCMBExchangeRateProvider,
    parse_tcmb_xml,
)

__all__ = [
    "BaseExchangeRateProvider",
    "CurrencyConversionUnavailableException",
    "ExchangeRateDTO",
    "ExchangeRateService",
    "FXEngineError",
    "FXFutureDateError",
    "FXInvalidDataError",
    "FXLookbackLimitExceededError",
    "FXProviderError",
    "FXRateNotFoundError",
    "MockExchangeRateProvider",
    "SUPPORTED_RATE_TYPES",
    "TCMBExchangeRateProvider",
    "calculate_conversion",
    "is_same_currency",
    "parse_tcmb_xml",
    "resolve_candidate_dates",
    "validate_currency_code",
]
