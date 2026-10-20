"use client";

import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  useMemo,
} from "react";
import en from "@/locales/en.json";
import tr from "@/locales/tr.json";
import {
  Locale,
  TranslationKey,
  DEFAULT_LOCALE,
  isValidLocale,
} from "./types";

const dictionaries: Record<Locale, Record<string, unknown>> = { en, tr };

export interface I18nContextType {
  locale: Locale;
  setLocale: (newLocale: Locale) => void;
  t: (key: TranslationKey, params?: Record<string, string | number>) => string;
}

const I18nContext = createContext<I18nContextType | null>(null);

function resolveKey(
  dict: Record<string, unknown>,
  keyPath: string
): string | undefined {
  const parts = keyPath.split(".");
  let current: unknown = dict;

  for (const part of parts) {
    if (
      current &&
      typeof current === "object" &&
      part in (current as Record<string, unknown>)
    ) {
      current = (current as Record<string, unknown>)[part];
    } else {
      return undefined;
    }
  }

  return typeof current === "string" ? current : undefined;
}

export function I18nProvider({
  children,
  initialLocale = DEFAULT_LOCALE,
}: {
  children: React.ReactNode;
  initialLocale?: Locale;
}) {
  const validatedInitial = isValidLocale(initialLocale)
    ? initialLocale
    : DEFAULT_LOCALE;

  const [locale, setLocaleState] = useState<Locale>(validatedInitial);

  // Synchronize document.documentElement.lang on mount and locale changes
  useEffect(() => {
    if (typeof document !== "undefined") {
      document.documentElement.lang = locale;
    }
  }, [locale]);

  const setLocale = useCallback((newLocale: Locale) => {
    if (!isValidLocale(newLocale)) return;

    setLocaleState(newLocale);

    if (typeof document !== "undefined") {
      // Set 1-year persistent cookie with Lax samesite
      document.cookie = `NEXT_LOCALE=${newLocale}; path=/; max-age=31536000; SameSite=Lax`;
      document.documentElement.lang = newLocale;
    }
  }, []);

  const t = useCallback(
    (key: TranslationKey, params?: Record<string, string | number>): string => {
      // 1. Attempt lookup in active locale dictionary
      let text = resolveKey(dictionaries[locale], key);

      // 2. Fallback to English dictionary if missing in current locale
      if (text === undefined && locale !== "en") {
        text = resolveKey(dictionaries.en, key);
      }

      // 3. Fallback to raw key if completely missing in both
      if (text === undefined) {
        if (process.env.NODE_ENV !== "production") {
          console.warn(`[i18n] Missing translation for key: "${key}" (locale: "${locale}")`);
        }
        return key;
      }

      // 4. Interpolate {param} placeholders if provided
      if (params) {
        return Object.entries(params).reduce(
          (acc, [placeholder, value]) =>
            acc.replace(new RegExp(`\\{${placeholder}\\}`, "g"), String(value)),
          text
        );
      }

      return text;
    },
    [locale]
  );

  const contextValue = useMemo<I18nContextType>(
    () => ({
      locale,
      setLocale,
      t,
    }),
    [locale, setLocale, t]
  );

  return (
    <I18nContext.Provider value={contextValue}>{children}</I18nContext.Provider>
  );
}

export function useTranslation(): I18nContextType {
  const context = useContext(I18nContext);
  if (!context) {
    throw new Error("useTranslation must be used within an I18nProvider");
  }
  return context;
}
