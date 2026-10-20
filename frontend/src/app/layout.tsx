/**
 * app/layout.tsx — Root Layout
 *
 * In Next.js App Router, every page is wrapped by the nearest layout.tsx.
 * This root layout wraps EVERY page in the application.
 *
 * Responsibilities:
 *   - Set HTML metadata (title, description) — important for SEO
 *   - Import global CSS
 *   - Define the outermost HTML structure
 *
 * The {children} slot is where each individual page renders.
 */

import type { Metadata } from "next";
import { Inter } from "next/font/google";
import { cookies } from "next/headers";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });

import { ThemeProvider } from "@/components/theme-provider";
import { AuthProvider } from "@/lib/auth/AuthContext";
import { I18nProvider } from "@/lib/i18n/I18nContext";
import { Locale, DEFAULT_LOCALE, isValidLocale } from "@/lib/i18n/types";

export const metadata: Metadata = {
  title: {
    template: "%s | ProcureOps AI",
    default: "ProcureOps AI",
  },
  description:
    "Evidence-backed procurement decision & workflow engine. " +
    "Compare supplier quotes, verify policy compliance, and make " +
    "auditable procurement decisions with AI assistance.",
};

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const cookieStore = await cookies();
  const rawLocale = cookieStore.get("NEXT_LOCALE")?.value;
  const initialLocale: Locale = isValidLocale(rawLocale) ? rawLocale : DEFAULT_LOCALE;

  return (
    <html lang={initialLocale} suppressHydrationWarning>
      <body className={`${inter.variable} font-sans antialiased bg-bg text-text-primary`} suppressHydrationWarning>
        <ThemeProvider
          attribute="class"
          defaultTheme="light"
          enableSystem={false}
          disableTransitionOnChange
        >
          <I18nProvider initialLocale={initialLocale}>
            <AuthProvider>
              {children}
            </AuthProvider>
          </I18nProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
