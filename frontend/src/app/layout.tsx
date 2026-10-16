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
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });

import { ThemeProvider } from "@/components/theme-provider";
import { AuthProvider } from "@/lib/auth/AuthContext";

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

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${inter.variable} font-sans antialiased bg-bg text-text-primary`} suppressHydrationWarning>
        <ThemeProvider
          attribute="class"
          defaultTheme="light"
          enableSystem={false}
          disableTransitionOnChange
        >
          <AuthProvider>
            {children}
          </AuthProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
