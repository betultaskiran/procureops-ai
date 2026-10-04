/**
 * src/types/global.d.ts
 *
 * Global TypeScript declarations for the ProcureOps frontend.
 *
 * WHY THIS FILE EXISTS:
 * TypeScript only understands .ts and .tsx files natively. When you write:
 *   import "./globals.css"
 * TypeScript doesn't know what a .css file is — it's not a JS module.
 *
 * Next.js normally generates a `next-env.d.ts` file at the root when you
 * run `npm install`, which includes these declarations automatically.
 * But since we run npm install inside Docker (not on the host machine),
 * the IDE can't find that file and shows an error.
 *
 * This file fixes the IDE error by telling TypeScript:
 * "Any file ending in .css is a valid import — trust the build system."
 *
 * The actual CSS processing is handled by PostCSS + Tailwind at build time.
 * TypeScript doesn't need to understand the contents, just that the import
 * is valid.
 */

// Allow importing any .css file as a side-effect import (import "./foo.css")
// or as a default import (import styles from "./foo.module.css")
declare module "*.css" {
  const styles: { readonly [className: string]: string };
  export default styles;
}
