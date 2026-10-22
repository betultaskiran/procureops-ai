"""
app/services/deterministic/orchestrator.py

Deterministik analiz sürecini (TCO ve Hard Rules) yöneten orkestratör.
"""

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional, TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.analysis import Analysis, AnalysisStatus, ComplianceResult
from app.models.quote import Quote
from app.services.deterministic.schemas import PolicyRules
from app.services.deterministic.tco import TCOCalculator
from app.services.deterministic.compliance import ComplianceChecker

if TYPE_CHECKING:
    from app.services.fx.service import ExchangeRateService

logger = logging.getLogger("app.services.deterministic.orchestrator")


def localize_fx_note(note: str | None, locale: str = "tr") -> str | None:
    """
    Localizes human-readable explanatory tokens in FX calculation notes.
    Preserves all currency codes, numbers, rates, formulas, dates, provider identifiers,
    and conversion path indicators (cross, inverse, direct).
    """
    if not note or locale != "en":
        return note

    res = note
    # Conversions & paths
    res = res.replace("Doğrudan Kur:", "Direct Rate:")
    res = res.replace("Ters Kur:", "Inverse Rate:")
    res = res.replace("Çapraz Kur:", "Cross Rate:")
    res = res.replace("Aynı Para Birimi:", "Same Currency:")
    # Common labels
    res = res.replace("Kur: ", "Rate: ")
    res = res.replace("Ortak Tarih: ", "Common Date: ")
    res = res.replace("Tarih: ", "Date: ")
    res = res.replace("Döviz kuru temin edilemedi:", "FX rate unavailable:")
    return res


class DeterministicEngine:
    """
    Bir RFQ'ya ait tüm teklifleri alır, TCO hesaplar ve şirket kurallarına
    (PolicyRules) göre doğrular.
    """

    def __init__(
        self,
        db: AsyncSession,
        fx_service: Optional["ExchangeRateService"] = None,
    ):
        self.db = db
        self.fx_service = fx_service

    async def run_analysis(
        self, 
        rfq_id: uuid.UUID, 
        rules: PolicyRules,
        locale: str = "tr",
    ) -> Analysis:
        """
        1. Yeni bir Analysis kaydı oluşturur.
        2. İlgili RFQ'nun tüm Quote'larını çeker.
        3. Her Quote için TCO hesaplar.
        4. Her Quote için Hard Rule (Compliance) kontrolleri yapar.
        5. Quote'un is_compliant alanını günceller.
        """
        # 1. Yeni Analysis kaydı
        analysis = Analysis(
            rfq_id=rfq_id,
            status=AnalysisStatus.RUNNING
        )
        self.db.add(analysis)
        await self.db.flush() # analysis.id oluşturulması için

        # 2. Quote'ları çek (kalemleriyle beraber)
        result = await self.db.execute(
            select(Quote)
            .where(Quote.rfq_id == rfq_id)
            .options(selectinload(Quote.items))
        )
        quotes: List[Quote] = list(result.scalars().all())

        # En az 2 teklif kontrolü (karşılaştırmalı çoklu analiz gereksinimi)
        if len(quotes) < 2:
            analysis.status = AnalysisStatus.FAILED
            await self.db.commit()
            raise ValueError(
                f"Karşılaştırmalı analiz için en az 2 teklif gereklidir. "
                f"Bu talep için {len(quotes)} teklif bulundu."
            )

        # Para birimi geçerlilik kontrolü
        if any(not q.currency or not q.currency.strip() for q in quotes):
            analysis.status = AnalysisStatus.FAILED
            await self.db.commit()
            raise ValueError("Tüm tekliflerin geçerli bir para birimi belirtmesi zorunludur.")

        target_currency = (rules.budget_currency or "TRY").strip().upper()
        currencies = {q.currency.strip().upper() for q in quotes if q.currency and q.currency.strip()}

        # Farklı para birimleri var ve FX servisi yapılandırılmamışsa, doğrudan kıyaslama fail-closed engellenir
        if len(currencies) > 1 and self.fx_service is None:
            analysis.status = AnalysisStatus.FAILED
            await self.db.commit()
            curr_str = ", ".join(sorted(currencies))
            raise ValueError(
                f"Teklifler farklı para birimleri içermektedir ({curr_str}). "
                "Doğrulanmış döviz kuru olmadan doğrudan sayısal karşılaştırmaya izin verilmez."
            )

        # Teklif belgesi parse durum kontrolü
        doc_ids = [q.quote_document_id for q in quotes if q.quote_document_id]
        if doc_ids:
            from app.models.rfq import QuoteDocument, ParseStatus
            docs_res = await self.db.execute(
                select(QuoteDocument).where(QuoteDocument.id.in_(doc_ids))
            )
            docs = docs_res.scalars().all()
            for doc in docs:
                if doc.parse_status != ParseStatus.COMPLETED and doc.parse_status != "completed":
                    analysis.status = AnalysisStatus.FAILED
                    await self.db.commit()
                    raise ValueError(
                        f"'{doc.file_name}' isimli teklif belgesinin işlenmesi henüz tamamlanmadı "
                        f"(durum: {doc.parse_status})."
                    )

        # 3 & 4. TCO, FX Dönüşümü ve Compliance adımları
        today_date = datetime.now(timezone.utc).date()

        for quote in quotes:
            # TCO Hesapla (Orijinal para biriminde)
            tco_result = TCOCalculator.calculate(quote=quote, analysis_id=analysis.id)
            quote_curr = (quote.currency or "").strip().upper()

            # FX Çevrimi & Denetim Kanıtı (Milestone 2C)
            if quote_curr == target_currency:
                # Aynı para birimi (Identity path): Dış sağlayıcı / DB araması yapmadan 1.0 kimlik kuru
                tco_result.converted_total_tco = tco_result.total_tco
                tco_result.target_currency = target_currency
                tco_result.exchange_rate = Decimal("1.000000")
                tco_result.exchange_rate_source = "IDENTITY"
                tco_result.exchange_rate_type = "ForexSelling"
                tco_result.exchange_rate_date = today_date
                same_note = (
                    f"[Same Currency: {quote_curr} = {target_currency} (Rate: 1.0)]"
                    if locale == "en"
                    else f"[Aynı Para Birimi: {quote_curr} = {target_currency} (Kur: 1.0)]"
                )
                tco_result.calculation_notes = (
                    f"{tco_result.calculation_notes} | {same_note}"
                    if tco_result.calculation_notes
                    else same_note
                )
            elif self.fx_service is not None:
                # Farklı para birimi ve FX servisi mevcut: dönüştür
                try:
                    converted_amount, rate_dto = await self.fx_service.convert_amount(
                        amount=tco_result.total_tco,
                        source_currency=quote_curr,
                        target_currency=target_currency,
                        quantize_places="0.0001",
                    )
                    tco_result.converted_total_tco = converted_amount
                    tco_result.target_currency = target_currency
                    tco_result.exchange_rate = rate_dto.rate
                    tco_result.exchange_rate_date = rate_dto.rate_date
                    tco_result.exchange_rate_source = rate_dto.source
                    tco_result.exchange_rate_type = rate_dto.rate_type
                    raw_fx_note = rate_dto.calculation_notes or f"[{rate_dto.conversion_path} Kur: {quote_curr}/{target_currency} = {rate_dto.rate}]"
                    fx_note = (
                        localize_fx_note(raw_fx_note, locale=locale)
                        if locale == "en"
                        else raw_fx_note
                    )
                    tco_result.calculation_notes = (
                        f"{tco_result.calculation_notes} | {fx_note}"
                        if tco_result.calculation_notes
                        else fx_note
                    )
                except Exception as exc:
                    logger.warning(
                        f"Döviz kuru çevrimi başarısız oldu (Teklif {quote.id}, {quote_curr} -> {target_currency}): {exc}"
                    )
                    if len(currencies) > 1:
                        # Karma para birimli RFQ'da bir teklif dahi çevrilemezse karşılaştırma yapılamaz (fail-closed)
                        analysis.status = AnalysisStatus.FAILED
                        await self.db.commit()
                        curr_str = ", ".join(sorted(currencies))
                        fail_msg = (
                            f"Quotes contain different currencies ({curr_str}). "
                            "Direct numerical comparison is not permitted without verified FX rates."
                            if locale == "en"
                            else f"Teklifler farklı para birimleri içermektedir ({curr_str}). "
                            "Doğrulanmış döviz kuru olmadan doğrudan sayısal karşılaştırmaya izin verilmez."
                        )
                        raise ValueError(fail_msg)
                    else:
                        # Tek para birimli ancak bütçeden farklı teklif: TCO çevrimi None bırakılır, Compliance fail-closed kararı verir
                        tco_result.converted_total_tco = None
                        tco_result.target_currency = target_currency
                        fail_note = (
                            f"[FX rate unavailable: {quote_curr} -> {target_currency} (fail-closed)]"
                            if locale == "en"
                            else f"[Döviz kuru temin edilemedi: {quote_curr} -> {target_currency} (fail-closed)]"
                        )
                        tco_result.calculation_notes = (
                            f"{tco_result.calculation_notes} | {fail_note}"
                            if tco_result.calculation_notes
                            else fail_note
                        )
            else:
                # Farklı para birimi ancak fx_service None: tek para birimli teklif Compliance'a bırakılır
                tco_result.converted_total_tco = None
                tco_result.target_currency = target_currency

            self.db.add(tco_result)
            await self.db.flush() # TCOResult'a ait ID'nin üretilmesi için

            # Döviz Çevrim Kanıtı Kaydı (EvidenceItem - Milestone 2D)
            if quote_curr != target_currency and tco_result.exchange_rate is not None:
                from app.models.analysis import EvidenceItem
                source_reference = f"{tco_result.exchange_rate_source or 'TCMB'} ({tco_result.exchange_rate_date or today_date}, {tco_result.exchange_rate_type or 'ForexSelling'})"
                claim = (
                    f"FX Conversion: {quote_curr} -> {target_currency} (Quote #{str(quote.id)[:8]})"
                    if locale == "en"
                    else f"Döviz Kuru Çevrimi: {quote_curr} -> {target_currency} (Teklif #{str(quote.id)[:8]})"
                )
                fallback_content = (
                    f"Rate: {tco_result.exchange_rate}. TCO: {tco_result.total_tco} {quote_curr} -> {tco_result.converted_total_tco} {target_currency}"
                    if locale == "en"
                    else f"Kur: {tco_result.exchange_rate}. TCO: {tco_result.total_tco} {quote_curr} -> {tco_result.converted_total_tco} {target_currency}"
                )
                content_text = (
                    localize_fx_note(tco_result.calculation_notes, locale=locale)
                    if locale == "en"
                    else (tco_result.calculation_notes or fallback_content)
                ) or fallback_content
                fx_ev = EvidenceItem(
                    analysis_id=analysis.id,
                    source_type="fx_rate",
                    source_reference=source_reference,
                    claim=claim,
                    content=content_text,
                )
                self.db.add(fx_ev)

            # Hard Rule Kontrolleri
            compliance_checks = ComplianceChecker.check_quote(
                quote=quote,
                tco_result=tco_result,
                rules=rules,
                analysis_id=analysis.id,
                locale=locale,
            )
            
            is_quote_compliant = True
            for check in compliance_checks:
                self.db.add(check)
                if check.result == ComplianceResult.FAIL:
                    is_quote_compliant = False
            
            # 5. Quote'un uyumluluk durumunu güncelle
            quote.is_compliant = is_quote_compliant

        # Deterministik adımlar tamamlandı.
        # Analiz durumu Agent adımı sonuna kadar RUNNING olarak korunur.
        await self.db.commit()
        
        # Sonuçları tam haliyle geri döndürmek için ilişkilerle birlikte yükleyelim
        await self.db.refresh(analysis, ["tco_results", "compliance_checks", "evidence_items"])
        
        return analysis
