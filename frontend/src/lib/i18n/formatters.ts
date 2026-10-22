/**
 * lib/i18n/formatters.ts — Locale-aware formatters for currencies, numbers, dates and percentages
 */

import { Locale } from "./types";

function getIntlLocale(locale: Locale = "en"): string {
  return locale === "tr" ? "tr-TR" : "en-US";
}

/**
 * Format currency amounts with locale-specific separators and symbols.
 * Does not mutate raw amounts or currency codes.
 */
export function formatCurrency(
  amount: number | null | undefined,
  currency: string = "USD",
  locale: Locale = "en"
): string {
  if (amount === null || amount === undefined || isNaN(amount)) {
    return "-";
  }

  const cleanCurrency = (currency || "USD").trim().toUpperCase();

  try {
    return new Intl.NumberFormat(getIntlLocale(locale), {
      style: "currency",
      currency: cleanCurrency,
      maximumFractionDigits: 2,
    }).format(amount);
  } catch {
    // Fallback if currency code is non-standard or unsupported
    return `${cleanCurrency} ${amount.toFixed(2)}`;
  }
}

/**
 * Format numbers with locale-specific thousand and decimal separators.
 */
export function formatNumber(
  value: number | null | undefined,
  locale: Locale = "en",
  options?: Intl.NumberFormatOptions
): string {
  if (value === null || value === undefined || isNaN(value)) {
    return "-";
  }

  try {
    return new Intl.NumberFormat(getIntlLocale(locale), options).format(value);
  } catch {
    return String(value);
  }
}

export interface FormatPercentOptions {
  /**
   * Set to true if input is already on a 0–100 scale (e.g. 95.5 for 95.5%).
   * Set to false if input is a 0–1 decimal ratio (e.g. 0.955 for 95.5%).
   * Defaults to false (standard Intl 0–1 ratio convention).
   */
  isAlreadyPercent?: boolean;
  minimumFractionDigits?: number;
  maximumFractionDigits?: number;
}

/**
 * Format percentages with locale-aware placement (%20 in tr-TR vs 20% in en-US).
 */
export function formatPercent(
  value: number | null | undefined,
  locale: Locale = "en",
  options?: FormatPercentOptions
): string {
  if (value === null || value === undefined || isNaN(value)) {
    return "-";
  }

  // Convert to 0–1 ratio if input was provided on 0–100 scale
  const ratio = options?.isAlreadyPercent ? value / 100 : value;

  try {
    return new Intl.NumberFormat(getIntlLocale(locale), {
      style: "percent",
      minimumFractionDigits: options?.minimumFractionDigits ?? 0,
      maximumFractionDigits: options?.maximumFractionDigits ?? 2,
    }).format(ratio);
  } catch {
    const rawVal = options?.isAlreadyPercent ? value : value * 100;
    return locale === "tr" ? `%${rawVal.toFixed(1)}` : `${rawVal.toFixed(1)}%`;
  }
}

/**
 * Format date values safely, preventing timezone day-shift on pure 'YYYY-MM-DD' dates.
 */
export function formatDate(
  dateInput: string | number | Date | null | undefined,
  locale: Locale = "en",
  options?: Intl.DateTimeFormatOptions
): string {
  if (!dateInput) {
    return "-";
  }

  let dateObj: Date;

  if (typeof dateInput === "string") {
    const trimmed = dateInput.trim();
    // Handle pure date strings (YYYY-MM-DD) without timezone shifts
    const pureDateMatch = trimmed.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (pureDateMatch) {
      const year = parseInt(pureDateMatch[1], 10);
      const month = parseInt(pureDateMatch[2], 10) - 1;
      const day = parseInt(pureDateMatch[3], 10);
      dateObj = new Date(year, month, day);
    } else {
      dateObj = new Date(trimmed);
    }
  } else if (dateInput instanceof Date) {
    dateObj = dateInput;
  } else {
    dateObj = new Date(dateInput);
  }

  if (isNaN(dateObj.getTime())) {
    return String(dateInput);
  }

  const defaultOptions: Intl.DateTimeFormatOptions = options || {
    year: "numeric",
    month: "short",
    day: "numeric",
  };

  try {
    return new Intl.DateTimeFormat(getIntlLocale(locale), defaultOptions).format(dateObj);
  } catch {
    return dateObj.toLocaleDateString();
  }
}

/**
 * Map recognized standard units for UI presentation without altering underlying DB records.
 * e.g., 'Adet' / 'adet' -> 'pcs' in EN, 'Adet' in TR.
 */
export function formatUnit(
  unit: string | null | undefined,
  locale: Locale = "en"
): string {
  if (!unit) {
    return "";
  }
  const clean = unit.trim().toLowerCase();
  if (clean === "adet" || clean === "parça" || clean === "tane") {
    return locale === "en" ? "pcs" : "Adet";
  }
  if (clean === "paket" || clean === "koli") {
    return locale === "en" ? "pack" : "Paket";
  }
  if (clean === "metre" || clean === "m") {
    return locale === "en" ? "m" : "Metre";
  }
  if (clean === "kg" || clean === "kilogram") {
    return "kg";
  }
  if (clean === "litre" || clean === "l") {
    return locale === "en" ? "L" : "Litre";
  }
  if (clean === "gün" || clean === "gun") {
    return locale === "en" ? "days" : "Gün";
  }
  if (clean === "ay") {
    return locale === "en" ? "months" : "Ay";
  }
  if (clean === "yıl" || clean === "yil" || clean === "sene") {
    return locale === "en" ? "years" : "Yıl";
  }
  if (clean === "pcs" || clean === "pieces" || clean === "units") {
    return locale === "en" ? "pcs" : "Adet";
  }
  return unit;
}

/**
 * Format deterministic rule title/description based on stable rule ID or known descriptions.
 */
export function formatRuleTitle(
  ruleName: string | null | undefined,
  ruleDescription: string | null | undefined,
  locale: Locale = "en"
): string {
  const cleanName = (ruleName || "").trim().toLowerCase();

  const titleMap: Record<string, { en: string; tr: string }> = {
    max_delivery_days: {
      en: "Maximum Delivery Time Check",
      tr: "Maksimum Teslimat Süresi Kontrolü",
    },
    min_warranty_months: {
      en: "Minimum Warranty Period Check",
      tr: "Minimum Garanti Süresi Kontrolü",
    },
    max_tco_budget: {
      en: "Maximum Budget Check",
      tr: "Maksimum Bütçe Kontrolü",
    },
    require_payment_terms: {
      en: "Required Payment Terms Check",
      tr: "Zorunlu Ödeme Koşulu Kontrolü",
    },
    cost_completeness: {
      en: "Cost Completeness Check",
      tr: "Maliyet Verisi Eksiksizlik Kontrolü",
    },
    extraction_confidence: {
      en: "Document Extraction Confidence Score Check",
      tr: "Doküman Veri Çıkarma Güven Skoru Kontrolü",
    },
  };

  if (cleanName in titleMap) {
    return titleMap[cleanName][locale];
  }

  // Fallback check against known descriptions in either language
  const desc = (ruleDescription || "").trim().toLowerCase();
  if (desc.includes("teslimat") || desc.includes("delivery")) {
    return titleMap.max_delivery_days[locale];
  }
  if (desc.includes("garanti") || desc.includes("warranty")) {
    return titleMap.min_warranty_months[locale];
  }
  if (desc.includes("bütçe") || desc.includes("budget")) {
    return titleMap.max_tco_budget[locale];
  }
  if (desc.includes("ödeme") || desc.includes("payment")) {
    return titleMap.require_payment_terms[locale];
  }
  if (desc.includes("maliyet") || desc.includes("cost completeness")) {
    return titleMap.cost_completeness[locale];
  }
  if (desc.includes("çıkarma") || desc.includes("confidence")) {
    return titleMap.extraction_confidence[locale];
  }

  return ruleDescription || ruleName || "-";
}

/**
 * Format deterministic rule evaluation notes based on current UI locale.
 * Seamlessly handles both new bilingual backend notes and historical single-language database records.
 */
export function formatRuleNotes(
  notes: string | null | undefined,
  locale: Locale = "en"
): string {
  if (!notes) return "-";
  const trimmed = notes.trim();

  // Static notes dictionary
  const staticNotes: Record<string, { en: string; tr: string }> = {
    "uygun.": { en: "Compliant.", tr: "Uygun." },
    "compliant.": { en: "Compliant.", tr: "Uygun." },
    "teslimat süresi belirtilmemiş.": {
      en: "Delivery time not specified.",
      tr: "Teslimat süresi belirtilmemiş.",
    },
    "delivery time not specified.": {
      en: "Delivery time not specified.",
      tr: "Teslimat süresi belirtilmemiş.",
    },
    "teslimat süresi sınırı aşıyor.": {
      en: "Delivery time exceeds limit.",
      tr: "Teslimat süresi sınırı aşıyor.",
    },
    "delivery time exceeds limit.": {
      en: "Delivery time exceeds limit.",
      tr: "Teslimat süresi sınırı aşıyor.",
    },
    "garanti süresi belirtilmemiş.": {
      en: "Warranty period not specified.",
      tr: "Garanti süresi belirtilmemiş.",
    },
    "warranty period not specified.": {
      en: "Warranty period not specified.",
      tr: "Garanti süresi belirtilmemiş.",
    },
    "garanti süresi yetersiz.": {
      en: "Warranty period insufficient.",
      tr: "Garanti süresi yetersiz.",
    },
    "warranty period insufficient.": {
      en: "Warranty period insufficient.",
      tr: "Garanti süresi yetersiz.",
    },
    "bütçeyi aşıyor.": { en: "Exceeds budget.", tr: "Bütçeyi aşıyor." },
    "exceeds budget.": { en: "Exceeds budget.", tr: "Bütçeyi aşıyor." },
    "para birimi belirtilmemiş: karşılaştırma yapılamıyor.": {
      en: "Currency not specified: Cannot compare.",
      tr: "Para birimi belirtilmemiş: Karşılaştırma yapılamıyor.",
    },
    "currency not specified: cannot compare.": {
      en: "Currency not specified: Cannot compare.",
      tr: "Para birimi belirtilmemiş: Karşılaştırma yapılamıyor.",
    },
    "ödeme koşulu belirtilmemiş.": {
      en: "Payment terms not specified.",
      tr: "Ödeme koşulu belirtilmemiş.",
    },
    "payment terms not specified.": {
      en: "Payment terms not specified.",
      tr: "Ödeme koşulu belirtilmemiş.",
    },
    "kabul edilemez ödeme koşulu.": {
      en: "Unacceptable payment terms.",
      tr: "Kabul edilemez ödeme koşulu.",
    },
    "unacceptable payment terms.": {
      en: "Unacceptable payment terms.",
      tr: "Kabul edilemez ödeme koşulu.",
    },
    "maliyet kalemleri eksiksiz.": {
      en: "Cost items complete.",
      tr: "Maliyet kalemleri eksiksiz.",
    },
    "cost items complete.": {
      en: "Cost items complete.",
      tr: "Maliyet kalemleri eksiksiz.",
    },
    "güven skoru yeterli.": {
      en: "Confidence score sufficient.",
      tr: "Güven skoru yeterli.",
    },
    "confidence score sufficient.": {
      en: "Confidence score sufficient.",
      tr: "Güven skoru yeterli.",
    },
  };

  const lower = trimmed.toLowerCase();
  if (lower in staticNotes) {
    return staticNotes[lower][locale];
  }

  // Dynamic parameterized patterns
  if (locale === "en") {
    // 1. Converted budget exceed
    const budgetMatchTR = trimmed.match(
      /^Bütçeyi aşıyor \(Dönüştürülmüş TCO:\s*([^,]+),\s*Orijinal:\s*([^)]+)\)\.?$/i
    );
    if (budgetMatchTR) {
      return `Exceeds budget (Converted TCO: ${budgetMatchTR[1]}, Original: ${budgetMatchTR[2]}).`;
    }

    // 2. Currency mismatch
    const currMatchTR = trimmed.match(
      /^Para birimi uyuşmazlığı: Teklif para birimi \(([^)]+)\) ile bütçe para birimi \(([^)]+)\) eşleşmiyor\. Doğrudan karşılaştırılamaz\.?$/i
    );
    if (currMatchTR) {
      return `Currency mismatch: Quote currency (${currMatchTR[1]}) does not match budget currency (${currMatchTR[2]}). Direct comparison not permitted.`;
    }

    // 3. Base price missing
    const basePriceTR = trimmed.match(
      /^Temel fiyat verisi eksik \(([^)]+)\)\. Fiyat doğrulaması yapılamadı\.?$/i
    );
    if (basePriceTR) {
      return `Base price data missing (${basePriceTR[1]}). Price validation failed.`;
    }

    // 4. Missing cost items
    const missingItemsTR = trimmed.match(
      /^Eksik maliyet kalemleri mevcut:\s*([^.]+)\.\s*İnsan incelemesi önerilir\.?$/i
    );
    if (missingItemsTR) {
      return `Missing cost items detected: ${missingItemsTR[1]}. Human review recommended.`;
    }

    // 5. Low confidence score
    const confTR = trimmed.match(
      /^Düşük güven skoru \(([^)]+)\)\.\s*Teklif belgesinin manuel kontrolü gereklidir\.?$/i
    );
    if (confTR) {
      return `Low confidence score (${confTR[1]}). Manual inspection of quote document required.`;
    }
  } else {
    // locale === "tr"
    // 1. Converted budget exceed
    const budgetMatchEN = trimmed.match(
      /^Exceeds budget \(Converted TCO:\s*([^,]+),\s*Original:\s*([^)]+)\)\.?$/i
    );
    if (budgetMatchEN) {
      return `Bütçeyi aşıyor (Dönüştürülmüş TCO: ${budgetMatchEN[1]}, Orijinal: ${budgetMatchEN[2]}).`;
    }

    // 2. Currency mismatch
    const currMatchEN = trimmed.match(
      /^Currency mismatch: Quote currency \(([^)]+)\) does not match budget currency \(([^)]+)\)\. Direct comparison not permitted\.?$/i
    );
    if (currMatchEN) {
      return `Para birimi uyuşmazlığı: Teklif para birimi (${currMatchEN[1]}) ile bütçe para birimi (${currMatchEN[2]}) eşleşmiyor. Doğrudan karşılaştırılamaz.`;
    }

    // 3. Base price missing
    const basePriceEN = trimmed.match(
      /^Base price data missing \(([^)]+)\)\. Price validation failed\.?$/i
    );
    if (basePriceEN) {
      return `Temel fiyat verisi eksik (${basePriceEN[1]}). Fiyat doğrulaması yapılamadı.`;
    }

    // 4. Missing cost items
    const missingItemsEN = trimmed.match(
      /^Missing cost items detected:\s*([^.]+)\.\s*Human review recommended\.?$/i
    );
    if (missingItemsEN) {
      return `Eksik maliyet kalemleri mevcut: ${missingItemsEN[1]}. İnsan incelemesi önerilir.`;
    }

    // 5. Low confidence score
    const confEN = trimmed.match(
      /^Low confidence score \(([^)]+)\)\.\s*Manual inspection of quote document required\.?$/i
    );
    if (confEN) {
      return `Düşük güven skoru (${confEN[1]}). Teklif belgesinin manuel kontrolü gereklidir.`;
    }
  }

  return trimmed;
}

/**
 * Format actual/required rule values (e.g. "Eksiksiz" -> "Complete", "Eksik: ..." -> "Missing: ...")
 */
export function formatRuleValue(
  value: string | null | undefined,
  locale: Locale = "en"
): string {
  if (value === null || value === undefined) return "-";
  const trimmed = value.trim();

  if (locale === "en") {
    if (trimmed.toLowerCase() === "eksiksiz") {
      return "Complete";
    }
    if (trimmed.startsWith("Eksik: ")) {
      return trimmed.replace(/^Eksik:\s*/, "Missing: ");
    }
  } else {
    if (trimmed.toLowerCase() === "complete") {
      return "Eksiksiz";
    }
    if (trimmed.startsWith("Missing: ")) {
      return trimmed.replace(/^Missing:\s*/, "Eksik: ");
    }
  }

  return trimmed;
}

/**
 * Format rule check outcome badge text (PASS/UYGUN, FAIL/UYGUN DEĞİL, WARNING/UYARI)
 */
export function formatRuleResult(
  result: string | null | undefined,
  locale: Locale = "en"
): string {
  const clean = (result || "").trim().toLowerCase();
  if (clean === "pass") {
    return locale === "tr" ? "UYGUN" : "PASS";
  }
  if (clean === "fail") {
    return locale === "tr" ? "UYGUN DEĞİL" : "FAIL";
  }
  if (clean === "warning") {
    return locale === "tr" ? "UYARI" : "WARNING";
  }
  return (result || "").toUpperCase();
}


