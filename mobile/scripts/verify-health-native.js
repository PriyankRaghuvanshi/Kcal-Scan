#!/usr/bin/env node
/**
 * Fail fast if react-native-health still contains known nil-in-NSDictionary crash patterns.
 * Run after patch-health.js (postinstall / pre-build).
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
  console.log("[verify-health-native] react-native-health not found, skip.");
  process.exit(0);
}

const files = fs.readdirSync(RN_HEALTH_DIR).filter((f) => f.endsWith(".m"));
let errors = [];

/** Patterns that must NOT appear after patching (nil in @{ } or return nil dates). */
const BANNED = [
  {
    re: /@"eventTypeInt":eventType,/,
    msg: 'workout event type from KVC can be nil — use (eventType ?: @(0))',
  },
  {
    re: /@"metadata"\s*:\s*\[sample metadata\],/,
    msg: 'Bare [sample metadata] in dictionary (nil crashes) — patch-health Queries rule',
  },
  {
    re: /@"sourceId"\s*:\s*bundleIdentifier,/,
    msg: 'HKSource.bundleIdentifier can be nil — use (bundleIdentifier ?: @"")',
  },
  {
    re: /@"sourceName"\s*:\s*name,/,
    msg: 'HKSource.name can be nil — use (name ?: @"")',
  },
];

for (const file of files) {
  const text = fs.readFileSync(path.join(RN_HEALTH_DIR, file), "utf8");
  for (const { re, msg } of BANNED) {
    if (re.test(text)) {
      errors.push(`${file}: ${msg}`);
    }
  }
}

const utilsPath = path.join(RN_HEALTH_DIR, "RCTAppleHealthKit+Utils.m");
if (fs.existsSync(utilsPath)) {
  const utils = fs.readFileSync(utilsPath, "utf8");
  const start = utils.indexOf("+ (NSString *)buildISO8601StringFromDate:");
  const end = utils.indexOf("+ (NSPredicate *)predicateForSamplesToday", start);
  if (start !== -1 && end !== -1) {
    const body = utils.slice(start, end);
    if (body.includes("return nil")) {
      errors.push(
        "RCTAppleHealthKit+Utils.m: buildISO8601StringFromDate must not return nil (use @\"\")"
      );
    }
    if (!body.includes("if (date == nil)")) {
      errors.push(
        "RCTAppleHealthKit+Utils.m: buildISO8601StringFromDate must guard nil date"
      );
    }
    if (!body.includes("return s ?: @\"\"")) {
      errors.push(
        "RCTAppleHealthKit+Utils.m: buildISO8601StringFromDate must use (s ?: @\"\") for formatter output"
      );
    }
  }
}

if (errors.length) {
  console.error("[verify-health-native] FAILED — crash-prone native patterns still present:\n");
  for (const e of errors) console.error("  -", e);
  console.error(
    "\nFix: update mobile/scripts/patch-health.js for upstream changes, then reinstall node_modules."
  );
  process.exit(1);
}

console.log("[verify-health-native] OK — no known HealthKit nil-dictionary patterns detected.");
