/**
 * lib/i18n/apiErrorMap.ts — Secure, locale-aware API error mapper
 *
 * Normalizes HTTP status codes, structured API details, and error instances
 * into user-facing localized strings while preventing the exposure of internal server details.
 */

import { ApiError } from "@/lib/api/client";
import { Locale } from "./types";

interface LocalizedMessage {
  en: string;
  tr: string;
}

// Known backend error message patterns mapped to localized messages
const KNOWN_ERROR_MAPPINGS: Array<{ match: (msg: string) => boolean; localized: LocalizedMessage }> = [
  {
    match: (m) => m.includes("invalid email or password") || m.includes("geçersiz e-posta"),
    localized: {
      en: "Invalid email address or password.",
      tr: "Geçersiz e-posta adresi veya şifre.",
    },
  },
  {
    match: (m) => m.includes("inactive user account") || m.includes("pasife alınmış"),
    localized: {
      en: "This user account has been deactivated. Please contact your administrator.",
      tr: "Bu kullanıcı hesabı pasife alınmış. Lütfen yöneticinizle iletişime geçin.",
    },
  },
  {
    match: (m) => m.includes("organization is inactive") || m.includes("organizasyonunuz askıya"),
    localized: {
      en: "Your organization is inactive or suspended. Please contact support.",
      tr: "Organizasyonunuz askıya alınmış veya pasif durumda. Lütfen destek ile iletişime geçin.",
    },
  },
  {
    match: (m) => m.includes("email address already exists") || m.includes("kayıtlı bir kullanıcı"),
    localized: {
      en: "A user with this email address already exists.",
      tr: "Bu e-posta adresiyle kayıtlı bir kullanıcı zaten mevcut.",
    },
  },
  {
    match: (m) => m.includes("organization with this slug or name") || m.includes("organizasyon zaten mevcut") || m.includes("şirket adı"),
    localized: {
      en: "An organization with this name already exists. Please try a different company name.",
      tr: "Bu isimde bir organizasyon zaten mevcut. Lütfen farklı bir şirket adı deneyin.",
    },
  },
  {
    match: (m) => m.includes("unique constraint") || m.includes("kayıt çakışması"),
    localized: {
      en: "Registration conflict: an account with these details already exists.",
      tr: "Kayıt çakışması: Bu bilgilerle bir hesap zaten mevcut.",
    },
  },
  {
    match: (m) => m.includes("çok fazla istek") || m.includes("too many requests") || m.includes("rate limit"),
    localized: {
      en: "Too many requests. Please wait a moment before trying again.",
      tr: "Çok fazla istek gönderildi. Lütfen bir süre bekleyip tekrar deneyin.",
    },
  },
  {
    match: (m) => m.includes("rfq not found") || m.includes("rfq bulunamadı"),
    localized: {
      en: "The requested RFQ could not be found.",
      tr: "Talep edilen teklif çağrısı (RFQ) bulunamadı.",
    },
  },
  {
    match: (m) => m.includes("invitation expired") || m.includes("süresi dolmuş"),
    localized: {
      en: "This supplier invitation has expired.",
      tr: "Bu tedarikçi davetinin geçerlilik süresi dolmuştur.",
    },
  },
];

// Fallbacks strictly by HTTP Status Code
const HTTP_STATUS_FALLBACKS: Record<number, LocalizedMessage> = {
  400: {
    en: "The request could not be processed. Please check your input.",
    tr: "İstek işlenemedi. Lütfen girdiğiniz bilgileri kontrol edin.",
  },
  401: {
    en: "Invalid credentials or session expired. Please sign in again.",
    tr: "Geçersiz kimlik bilgisi veya oturum süresi doldu. Lütfen tekrar giriş yapın.",
  },
  403: {
    en: "You do not have permission to perform this action.",
    tr: "Bu işlemi gerçekleştirmek için yetkiniz bulunmamaktadır.",
  },
  404: {
    en: "The requested resource was not found.",
    tr: "İstenen kaynak bulunamadı.",
  },
  409: {
    en: "A conflict occurred with an existing record.",
    tr: "Mevcut bir kayıtla çakışma oluştu.",
  },
  422: {
    en: "Please correct the highlighted validation errors.",
    tr: "Lütfen belirtilen doğrulama hatalarını düzeltin.",
  },
  429: {
    en: "Too many requests. Please slow down and try again shortly.",
    tr: "Çok fazla istek gönderildi. Lütfen biraz bekleyip tekrar deneyin.",
  },
  500: {
    en: "An internal server error occurred. Please try again later.",
    tr: "Sunucuda bir hata oluştu. Lütfen daha sonra tekrar deneyin.",
  },
  502: {
    en: "The server is temporarily unavailable. Please try again later.",
    tr: "Sunucu geçici olarak kullanılamıyor. Lütfen daha sonra tekrar deneyin.",
  },
  503: {
    en: "The service is currently unavailable. Please try again later.",
    tr: "Servis şu anda kullanılamıyor. Lütfen daha sonra tekrar deneyin.",
  },
};

/**
 * Maps an ApiError, Error, or raw detail into a safe, localized message.
 * Internal server details and stack traces are never exposed.
 */
export function getLocalizedApiError(
  error: unknown,
  locale: Locale = "en"
): string {
  if (!error) {
    return locale === "tr"
      ? "Bilinmeyen bir hata oluştu."
      : "An unknown error occurred.";
  }

  // 1. Detect network connectivity errors
  if (error instanceof TypeError && error.message.includes("fetch")) {
    return locale === "tr"
      ? "Sunucuya bağlanılamadı. Lütfen internet bağlantınızı kontrol edin."
      : "Unable to connect to the server. Please check your internet connection.";
  }

  // 2. Extract status code and raw message
  let status: number | undefined;
  let rawMessage = "";

  if (error instanceof ApiError) {
    status = error.status;
    rawMessage = typeof error.message === "string" ? error.message : "";
  } else if (error instanceof Error) {
    rawMessage = error.message;
  } else if (typeof error === "string") {
    rawMessage = error;
  }

  const normalized = rawMessage.toLowerCase().trim();

  // 3. Check for specific known message pattern matches
  if (normalized) {
    for (const mapping of KNOWN_ERROR_MAPPINGS) {
      if (mapping.match(normalized)) {
        return mapping.localized[locale];
      }
    }
  }

  // 4. Fall back to status-code based localized message
  if (status && HTTP_STATUS_FALLBACKS[status]) {
    return HTTP_STATUS_FALLBACKS[status][locale];
  }

  // 5. Safe generic fallback
  return locale === "tr"
    ? "Beklenmeyen bir hata oluştu. Lütfen tekrar deneyin."
    : "An unexpected error occurred. Please try again.";
}
