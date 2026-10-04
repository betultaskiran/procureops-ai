/**
 * postcss.config.mjs
 *
 * PostCSS processes our CSS files. With Tailwind v4, the @tailwindcss/postcss
 * plugin handles everything — no separate tailwind.config.js needed.
 */
const config = {
  plugins: {
    "@tailwindcss/postcss": {},
  },
};

export default config;
