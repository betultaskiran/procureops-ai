"""
app/services/fx/tcmb_provider.py

Türkiye Cumhuriyet Merkez Bankası (TCMB) resmi günlük döviz kurları sağlayıcısı.

XML Formatı:
  <Tarih_Date Tarih="20.10.2026" Date="10/20/2026" Bulten_No="2026/198">
    <Currency CrossOrder="0" Kod="USD" CurrencyCode="USD">
      <Unit>1</Unit>
      <Isim>ABD DOLARI</Isim>
      <CurrencyName>US DOLLAR</CurrencyName>
      <ForexBuying>49.4889</ForexBuying>
      <ForexSelling>49.5780</ForexSelling>
      <BanknoteBuying>49.4542</BanknoteBuying>
      <BanknoteSelling>49.6524</BanknoteSelling>
    </Currency>
  </Tarih_Date>
"""

import asyncio
import logging
import ssl
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import List

import httpx

from app.services.fx.base import BaseExchangeRateProvider
from app.services.fx.exceptions import (
    FXInvalidDataError,
    FXProviderError,
    FXRateNotFoundError,
)
from app.services.fx.schemas import ExchangeRateDTO

logger = logging.getLogger("app.services.fx.tcmb_provider")


def create_tcmb_ssl_context() -> ssl.SSLContext:
    """
    TCMB web sunucusuna bağlantı için TLS 1.2 uyumluluk SSL bağlamı oluşturur.

    UYUMLULUK NOTU:
    Bu ayar gözlemlenen ağ davranışı temelinde bir uyumluluk çözümüdür (workaround).
    TCMB sunucusu (185.98.252.10) bazı ortamlarda TLS 1.3 handshake sırasında
    zaman aşımına uğramakta (Client Hello paketine cevap dönülmemesi), ancak
    TLS 1.2 ile derhal (<200ms) yanıt vermektedir. Bu durum TCMB'nin TLS 1.3'ü
    kasıtlı olarak engellediğinin kesin kanıtı değildir.

    GÜVENLİK İLKELERİ:
    - Sertifika doğrulaması (verify_mode = CERT_REQUIRED) ve hostname doğrulaması
      (check_hostname = True) KESİNLİKLE devrede tutulur; asla verify=False kullanılmaz.
    - Sistem güvenilen kök sertifika deposu (default CA bundle) kullanılır.
    """
    ctx = ssl.create_default_context()
    ctx.maximum_version = ssl.TLSVersion.TLSv1_2
    return ctx


SUPPORTED_RATE_TYPES = (
    "ForexSelling",
    "ForexBuying",
    "BanknoteSelling",
    "BanknoteBuying",
)


def parse_tcmb_xml(
    content: bytes | str,
    fetched_at: datetime | None = None,
) -> List[ExchangeRateDTO]:
    """
    Saf (pure) TCMB XML ayrıştırıcı fonksiyonu.
    Ağ veya I/O işlemi yapmaz; gelen XML içeriğini parse edip ExchangeRateDTO listesi döner.

    Önemli Normalizasyon:
    - JPY gibi para birimlerinde Unit 100 olarak gelir.
    - Normalized rate = (ham_oran / Unit).
    - Böylece 1 birim kaynak para biriminin TRY karşılığı kesin olarak elde edilir.
    """
    if fetched_at is None:
        fetched_at = datetime.now(timezone.utc)

    if not content or (isinstance(content, (bytes, str)) and len(content.strip()) == 0):
        raise FXInvalidDataError("TCMB XML content is empty.")

    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise FXInvalidDataError(f"Malformed TCMB XML response: {exc}") from exc

    # 1. Bülten tarihi ve numarasını al
    tarih_str = root.attrib.get("Tarih")
    bulten_no = root.attrib.get("Bulten_No")

    if not tarih_str:
        raise FXInvalidDataError("TCMB XML missing 'Tarih' attribute in Tarih_Date tag.")

    try:
        rate_date = datetime.strptime(tarih_str.strip(), "%d.%m.%Y").date()
    except ValueError as exc:
        raise FXInvalidDataError(f"Invalid date format in TCMB XML: {tarih_str!r}") from exc

    rates: List[ExchangeRateDTO] = []

    # 2. Her Currency elementini ayrıştır
    for currency_elem in root.findall("Currency"):
        code = currency_elem.attrib.get("CurrencyCode") or currency_elem.attrib.get("Kod")
        if not code or len(code.strip()) != 3:
            continue
        source_currency = code.strip().upper()

        unit_str = currency_elem.findtext("Unit") or "1"
        try:
            unit = int(unit_str.strip())
            if unit <= 0:
                unit = 1
        except ValueError:
            unit = 1

        unit_decimal = Decimal(unit)

        for rate_type in SUPPORTED_RATE_TYPES:
            val_text = currency_elem.findtext(rate_type)
            if not val_text or not val_text.strip():
                continue

            try:
                clean_val = val_text.strip().replace(",", ".")
                raw_rate = Decimal(clean_val)
            except Exception:
                continue

            if raw_rate <= Decimal("0"):
                continue

            # Birim normalizasyonu: 1 birim dövizin TRY değeri
            normalized_rate = raw_rate / unit_decimal

            rates.append(
                ExchangeRateDTO(
                    source_currency=source_currency,
                    target_currency="TRY",
                    rate=normalized_rate,
                    rate_type=rate_type,
                    source="TCMB",
                    rate_date=rate_date,
                    fetched_at=fetched_at,
                    unit=unit,
                    bulletin_no=bulten_no,
                )
            )

    if not rates:
        raise FXInvalidDataError("No valid currency rates found in TCMB XML payload.")

    return rates


class TCMBExchangeRateProvider(BaseExchangeRateProvider):
    """
    Türkiye Cumhuriyet Merkez Bankası (TCMB) resmi günlük döviz kurları sağlayıcısı.

    Yalnızca resmi TCMB XML bültenlerinden doğrulanmış kurları çeker.
    Üretim modunda sahte veya hardcoded kurlara sessizce düşmez;
    resmi bülten bulunamazsa fail-closed prensibiyle hata fırlatır.
    """

    def __init__(
        self,
        base_url: str = "https://www.tcmb.gov.tr/kurlar",
        timeout: float = 5.0,
        max_retries: int = 2,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries

    def _build_url(self, target_date: date | None = None) -> str:
        """İstenen tarih için TCMB XML URL'ini üretir."""
        today = datetime.now(timezone.utc).date()
        if target_date is None or target_date == today:
            return f"{self.base_url}/today.xml"

        # Geçmiş tarih formatı: https://www.tcmb.gov.tr/kurlar/YYYYMM/DDMMYYYY.xml
        year_month = target_date.strftime("%Y%m")
        day_month_year = target_date.strftime("%d%m%Y")
        return f"{self.base_url}/{year_month}/{day_month_year}.xml"

    async def fetch_rates(self, target_date: date | None = None) -> List[ExchangeRateDTO]:
        today = datetime.now(timezone.utc).date()

        # Hafta sonu kontrolü: TCMB hafta sonları bülten yayımlamaz
        if target_date is not None and target_date < today and target_date.weekday() >= 5:
            raise FXRateNotFoundError(
                f"TCMB does not publish exchange rate bulletins on weekends ({target_date})."
            )

        url = self._build_url(target_date)
        fetched_at = datetime.now(timezone.utc)

        headers = {
            "User-Agent": "ProcureOps-AI/1.0 (+https://procureops.local; procurement-fx)",
            "Accept": "application/xml, text/xml",
        }

        # TLS 1.2 uyumluluk transport'u (sertifika doğrulaması kesinlikle aktif)
        ssl_ctx = create_tcmb_ssl_context()
        transport = httpx.AsyncHTTPTransport(verify=ssl_ctx)
        client_timeout = httpx.Timeout(
            connect=self.timeout,
            read=self.timeout * 2,
            write=self.timeout,
            pool=self.timeout,
        )

        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                async with httpx.AsyncClient(transport=transport, timeout=client_timeout) as client:
                    resp = await client.get(url, headers=headers)

                if resp.status_code == 404:
                    raise FXRateNotFoundError(
                        f"TCMB bulletin not found for date {target_date} (HTTP 404 at {url})."
                    )

                if resp.status_code != 200:
                    raise FXProviderError(
                        f"TCMB server returned unexpected HTTP status {resp.status_code}: {resp.text[:200]}"
                    )

                return parse_tcmb_xml(resp.content, fetched_at=fetched_at)

            except (FXRateNotFoundError, FXInvalidDataError):
                # 404 veya geçersiz XML veri hataları retry edilmez, doğrudan yükseltilir
                raise

            except (httpx.TimeoutException, httpx.RequestError) as exc:
                last_error = exc
                logger.warning(
                    f"[TCMBProvider] Attempt {attempt}/{self.max_retries} failed for {url}: "
                    f"{type(exc).__name__}: {exc}"
                )
                if attempt < self.max_retries:
                    await asyncio.sleep(0.5 * attempt)

        # Tüm yeniden denemeler başarısız oldu: fail-closed
        raise FXProviderError(
            f"TCMB network communication error after {self.max_retries} attempts: {last_error}"
        ) from last_error


