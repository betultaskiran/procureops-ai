import { ImageResponse } from "next/og";

export const size = {
  width: 32,
  height: 32,
};
export const contentType = "image/png";

export default function Icon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "transparent",
        }}
      >
        <svg
          width="32"
          height="32"
          viewBox="0 0 100 100"
          fill="none"
        >
          {/* P Outer Loop */}
          <path
            d="M 25 18 L 62 18 C 78 18 90 28 90 46 C 90 62 76 74 58 74 C 48 74 40 70 36 64 C 42 66 50 66 58 64 C 69 60 76 53 76 45 C 76 33 67 28 55 28 L 30 28 L 25 18 Z"
            fill="#2563EB"
          />
          {/* Lower Stem */}
          <path
            d="M 12 84 L 20 48 C 22 38 29 32 37 32 L 32 40 C 26 40 22 45 20 54 L 14 82 C 13.5 83.5 12.5 84 12 84 Z"
            fill="#06B6D4"
          />
          {/* Ascending Arrow Shaft */}
          <path
            d="M 18 78 C 23 54 33 42 45 36 L 50 42 C 39 47 31 58 26 80 Z"
            fill="#06B6D4"
          />
          {/* Ascending Arrow Head with Dark Outline for multi-theme tab bar contrast */}
          <path
            d="M 72 23 L 45 28 L 52 36 L 44 44 L 50 50 L 58 42 L 65 49 L 72 23 Z"
            fill="#FFFFFF"
            stroke="#0B1F44"
            strokeWidth="1.5"
          />
        </svg>
      </div>
    ),
    {
      ...size,
    }
  );
}
