/**
 * scripts/check-i18n-parity.mjs
 *
 * Verifies 1:1 bidirectional structural parity between en.json and tr.json:
 * - Checks for missing keys in tr.json
 * - Checks for superfluous keys in tr.json not in en.json
 * - Checks for value type mismatches
 * - Verifies parameter placeholder consistency ({param})
 *
 * Exits with code 0 on success, code 1 on failure.
 */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const enPath = path.resolve(__dirname, "../src/locales/en.json");
const trPath = path.resolve(__dirname, "../src/locales/tr.json");

if (!fs.existsSync(enPath) || !fs.existsSync(trPath)) {
  console.error("❌ Error: en.json or tr.json file not found!");
  process.exit(1);
}

const en = JSON.parse(fs.readFileSync(enPath, "utf-8"));
const tr = JSON.parse(fs.readFileSync(trPath, "utf-8"));

const errors = [];
let keysChecked = 0;

function extractPlaceholders(str) {
  const matches = str.match(/\{([a-zA-Z0-9_]+)\}/g);
  return matches ? matches.sort() : [];
}

function compareObjects(enObj, trObj, currentPath = "") {
  const enKeys = Object.keys(enObj);
  const trKeys = Object.keys(trObj);

  // 1. Check for keys in en missing from tr
  for (const key of enKeys) {
    const fullPath = currentPath ? `${currentPath}.${key}` : key;
    if (!(key in trObj)) {
      errors.push(`[MISSING_KEY] Key "${fullPath}" exists in en.json but is MISSING in tr.json`);
      continue;
    }

    const enVal = enObj[key];
    const trVal = trObj[key];

    const enType = typeof enVal;
    const trType = typeof trVal;

    if (enType !== trType) {
      errors.push(`[TYPE_MISMATCH] "${fullPath}": en is ${enType}, tr is ${trType}`);
      continue;
    }

    if (enType === "object" && enVal !== null && trVal !== null) {
      compareObjects(enVal, trVal, fullPath);
    } else if (enType === "string") {
      keysChecked++;
      if (trVal.trim() === "") {
        errors.push(`[EMPTY_VALUE] "${fullPath}" has an empty string in tr.json`);
      }

      // Check placeholder parity
      const enParams = extractPlaceholders(enVal);
      const trParams = extractPlaceholders(trVal);
      if (enParams.join(",") !== trParams.join(",")) {
        errors.push(
          `[PARAM_MISMATCH] "${fullPath}": en params [${enParams.join(", ")}] != tr params [${trParams.join(", ")}]`
        );
      }
    }
  }

  // 2. Check for extra keys in tr not in en
  for (const key of trKeys) {
    const fullPath = currentPath ? `${currentPath}.${key}` : key;
    if (!(key in enObj)) {
      errors.push(`[EXTRA_KEY] Key "${fullPath}" exists in tr.json but DOES NOT EXIST in en.json`);
    }
  }
}

console.log("🔍 Checking translation parity between en.json and tr.json...");
compareObjects(en, tr);

if (errors.length > 0) {
  console.error(`\n❌ Translation parity check FAILED with ${errors.length} issue(s):`);
  for (const err of errors) {
    console.error(`  - ${err}`);
  }
  process.exit(1);
} else {
  console.log(`\n✅ Parity check PASSED: en.json and tr.json have 100% parity (${keysChecked} string keys verified).`);
  process.exit(0);
}
