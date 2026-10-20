/**
 * lib/i18n/types.ts — Type definitions & compile-time parity contracts for i18n
 */

import en from "@/locales/en.json";
import tr from "@/locales/tr.json";

export type Locale = "en" | "tr";
export const SUPPORTED_LOCALES: readonly Locale[] = ["en", "tr"] as const;
export const DEFAULT_LOCALE: Locale = "en";

export function isValidLocale(val: unknown): val is Locale {
  return typeof val === "string" && (val === "en" || val === "tr");
}

// Deep key type for nested object paths (e.g., 'common.actions.save' or 'auth.login.title')
type Join<K, P> = K extends string | number
  ? P extends string | number
    ? `${K}${"" extends P ? "" : "."}${P}`
    : never
  : never;

type Prev = [never, 0, 1, 2, 3, 4, 5, ...never[]];

export type NestedKeyOf<T, Depth extends number = 5> = [Depth] extends [never]
  ? never
  : T extends object
  ? {
      [K in keyof T & (string | number)]: T[K] extends (...args: any[]) => any
        ? never
        : T[K] extends object
        ? Join<K, NestedKeyOf<T[K], Prev[Depth]>>
        : `${K}`;
    }[keyof T & (string | number)]
  : "";

export type TranslationSchema = typeof en;
export type TurkishSchema = typeof tr;

export type TranslationKey = NestedKeyOf<TranslationSchema>;

/**
 * Compile-time Bidirectional Parity Enforcement:
 * 1. tr must fulfill all keys and structure of en (no missing keys in tr).
 * 2. en must fulfill all keys and structure of tr (no missing keys in en, no extra keys in tr).
 * Any mismatch will fail `tsc --noEmit` build.
 */
export const _enFulfillsSchema: TranslationSchema = en;
export const _trFulfillsSchema: TranslationSchema = tr;
export const _enFulfillsTurkish: TurkishSchema = en;
export const _trFulfillsTurkish: TurkishSchema = tr;
