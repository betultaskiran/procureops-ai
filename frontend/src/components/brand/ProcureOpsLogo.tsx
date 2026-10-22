"use client";

import React from "react";

interface ProcureOpsLogoProps {
  className?: string;
  size?: number; // Size in pixels (default 32)
  theme?: "dark" | "light" | "auto"; // Theme mode (default "auto" adapts to Light/Dark)
}

/**
 * ProcureOps AI — Official Brand Guide Logo Mark (Precision Apex)
 * Adaptive Dual-Theme Vector SVG:
 * - Dark Mode:  Vibrant royal blue P loop + emerald-cyan swoop + Luminous White (#FFFFFF) Arrow
 * - Light Mode: Vibrant royal blue P loop + emerald-cyan swoop + Deep Midnight Navy (#0B1F44) Arrow
 * 
 * Implemented via pure CSS dark-variant toggling for instant zero-flash theme transitions.
 */
export const ProcureOpsLogo: React.FC<ProcureOpsLogoProps> = ({
  className = "",
  size = 32,
  theme = "auto",
}) => {
  const lightClass =
    theme === "light" ? "block" : theme === "dark" ? "hidden" : "block dark:hidden";
  const darkClass =
    theme === "dark" ? "block" : theme === "light" ? "hidden" : "hidden dark:block";

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 100 100"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={`shrink-0 ${className}`}
    >
      <defs>
        {/* P Outer Loop Gradient: Royal Blue (#3B82F6 -> #2563EB) to Deep Cobalt & Cyan Hook */}
        <linearGradient id="po-brand-loop" x1="20%" y1="10%" x2="85%" y2="85%">
          <stop offset="0%" stopColor="#3B82F6" />
          <stop offset="40%" stopColor="#2563EB" />
          <stop offset="75%" stopColor="#1D4ED8" />
          <stop offset="100%" stopColor="#06B6D4" />
        </linearGradient>

        {/* Lower Stem & Swoop Gradient: Emerald Green to Vibrant Cyan */}
        <linearGradient id="po-brand-swoop" x1="0%" y1="100%" x2="70%" y2="20%">
          <stop offset="0%" stopColor="#10B981" />
          <stop offset="50%" stopColor="#06B6D4" />
          <stop offset="100%" stopColor="#38BDF8" />
        </linearGradient>

        {/* Dark Mode Luminous Arrowhead Gradient (#FFFFFF) */}
        <linearGradient id="po-brand-arrow-dark" x1="0%" y1="100%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="#BAE6FD" />
          <stop offset="50%" stopColor="#FFFFFF" />
          <stop offset="100%" stopColor="#F8FAFC" />
        </linearGradient>

        {/* Light Mode High-Contrast Arrowhead Gradient (#0B1F44 Deep Midnight Navy) */}
        <linearGradient id="po-brand-arrow-light" x1="0%" y1="100%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="#07152E" />
          <stop offset="100%" stopColor="#0B1F44" />
        </linearGradient>

        {/* Drop shadow for arrowhead depth in Dark Mode */}
        <filter id="po-arrow-shadow" x="-20%" y="-20%" width="140%" height="140%">
          <feDropShadow dx="-1.5" dy="2" stdDeviation="2.5" floodColor="#050C1A" floodOpacity="0.55" />
        </filter>
      </defs>

      {/* 1. The P Outer Loop (Upper Body — Common to both themes) */}
      <path
        d="M 25 18 L 62 18 C 78 18 90 28 90 46 C 90 62 76 74 58 74 C 48 74 40 70 36 64 C 42 66 50 66 58 64 C 69 60 76 53 76 45 C 76 33 67 28 55 28 L 30 28 L 25 18 Z"
        fill="url(#po-brand-loop)"
      />

      {/* 2. Lower Stem & Curved Body (Common to both themes) */}
      <path
        d="M 12 84 L 20 48 C 22 38 29 32 37 32 L 32 40 C 26 40 22 45 20 54 L 14 82 C 13.5 83.5 12.5 84 12 84 Z"
        fill="url(#po-brand-swoop)"
      />

      {/* 3. Common Dynamic Arrow Shaft */}
      <path
        d="M 18 78 C 23 54 33 42 45 36 L 50 42 C 39 47 31 58 26 80 Z"
        fill="url(#po-brand-swoop)"
      />

      {/* 4A. LIGHT MODE ARROWHEAD: Deep Midnight Navy (#0B1F44) for crisp contrast on white surfaces */}
      <g className={lightClass}>
        <path
          d="M 72 23 L 45 28 L 52 36 L 44 44 L 50 50 L 58 42 L 65 49 L 72 23 Z"
          fill="url(#po-brand-arrow-light)"
        />
      </g>

      {/* 4B. DARK MODE ARROWHEAD: Luminous White (#FFFFFF) with depth shadow for dark surfaces */}
      <g className={darkClass} filter="url(#po-arrow-shadow)">
        <path
          d="M 72 23 L 45 28 L 52 36 L 44 44 L 50 50 L 58 42 L 65 49 L 72 23 Z"
          fill="url(#po-brand-arrow-dark)"
        />
      </g>
    </svg>
  );
};
