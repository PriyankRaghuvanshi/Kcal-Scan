#!/usr/bin/env node
/**
 * Postinstall script: patches react-native-health's nil-unsafe NSDictionary
 * literals in ALL native Objective-C files. The library crashes when HealthKit
 * samples have nil source name, bundleIdentifier, or UUID.
 *
 * This runs after `npm install` — including on EAS Build servers.
 */

const fs = require("fs");
const path = require("path");

const RN_HEALTH_DIR = path.join(
  __dirname,
  "..",
  "node_modules",
  "react-native-health",
  "RCTAppleHealthKit"
);

if (!fs.existsSync(RN_HEALTH_DIR)) {
  console.log("[patch-health] react-native-health not found, skipping.");
  process.exit(0);
}

const files = fs.readdirSync(RN_HEALTH_DIR).filter((f) => f.endsWith(".m"));
let totalPatches = 0;

for (const file of files) {
  const filePath = path.join(RN_HEALTH_DIR, file);
  let src = fs.readFileSync(filePath, "utf8");
  const original = src;

  // Nil-guard [[[...sourceRevision] source] name]
  src = src.replace(
    /\[\[\[(\w+) sourceRevision\] source\] name\](?!\s*\?:)/g,
    "([[[$1 sourceRevision] source] name] ?: @\"\")"
  );

  // Nil-guard [[[...sourceRevision] source] bundleIdentifier]
  src = src.replace(
    /\[\[\[(\w+) sourceRevision\] source\] bundleIdentifier\](?!\s*\?:)/g,
    "([[[$1 sourceRevision] source] bundleIdentifier] ?: @\"\")"
  );

  // Nil-guard [[...UUID] UUIDString] — must wrap full expr in ( ) for valid Obj-C
  src = src.replace(
    /\[\[(\w+) UUID\] UUIDString\](?!\s*\?:)/g,
    "([[$1 UUID] UUIDString] ?: @\"\")"
  );

  // Nil-guard [[...sourceRevision] productType]
  src = src.replace(
    /\[\[(\w+) sourceRevision\] productType\](?!\s*\?:)/g,
    "([[$1 sourceRevision] productType] ?: @\"\")"
  );

  if (src !== original) {
    fs.writeFileSync(filePath, src, "utf8");
    totalPatches++;
    console.log(`[patch-health] Patched ${file}`);
  }
}

if (totalPatches > 0) {
  console.log(`[patch-health] Done — patched ${totalPatches} file(s).`);
} else {
  console.log("[patch-health] No changes needed (already patched).");
}
