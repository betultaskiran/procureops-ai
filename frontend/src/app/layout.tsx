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
import "./globals.css";

export const metadata: Metadata = {
  title: {
    // %s is replaced by the page's title. "| ProcureOps AI" is the suffix.
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
    <html lang="en">
      {/*
       * suppressHydrationWarning: prevents a React warning when the server
       * and client render slightly different HTML (e.g. browser extensions
       * that add attributes to <body>). Safe to add here.
       */}
      <body suppressHydrationWarning>{children}</body>
    </html>
  );
}
