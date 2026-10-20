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
