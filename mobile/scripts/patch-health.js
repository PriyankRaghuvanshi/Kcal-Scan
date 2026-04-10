#!/usr/bin/env node
/**
 * Postinstall: harden react-native-health native code against nil in NSDictionary
 * literals. HealthKit often returns nil for metadata, source fields, UUID strings, etc.
 * Inserting nil into @{ ... } throws NSInvalidArgumentException (build 179 crash).
 *
 * Runs on every npm install including EAS Build.
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

/** Original upstream implementation — replace with nil-safe version. */
const BUILD_ISO_OLD = `+ (NSString *)buildISO8601StringFromDate:(NSDate *)date
{
    @try {
        NSDateFormatter *dateFormatter = [NSDateFormatter new];
        NSLocale *posix = [NSLocale localeWithLocaleIdentifier:@"en_US_POSIX"];
        dateFormatter.locale = posix;
        dateFormatter.dateFormat = @"yyyy'-'MM'-'dd'T'HH':'mm':'ss.SSSZ";
        return [dateFormatter stringFromDate:date];
    } @catch (NSException *exception) {
        NSLog(@"RNHealth: An error occured while trying parse ISO8601 string from date");
        return nil;
    }   
}`;

const BUILD_ISO_NEW = `+ (NSString *)buildISO8601StringFromDate:(NSDate *)date
{
    if (date == nil) {
        return @"";
    }
    @try {
        NSDateFormatter *dateFormatter = [NSDateFormatter new];
        NSLocale *posix = [NSLocale localeWithLocaleIdentifier:@"en_US_POSIX"];
        dateFormatter.locale = posix;
        dateFormatter.dateFormat = @"yyyy'-'MM'-'dd'T'HH':'mm':'ss.SSSZ";
        NSString *s = [dateFormatter stringFromDate:date];
        return s ?: @"";
    } @catch (NSException *exception) {
        NSLog(@"RNHealth: An error occured while trying parse ISO8601 string from date");
        return @"";
    }
}`;

function patchFile(filePath, fileName) {
  let src = fs.readFileSync(filePath, "utf8");
  const original = src;

  // --- RCTAppleHealthKit+Utils.m: never return nil from ISO string builder ---
  if (fileName === "RCTAppleHealthKit+Utils.m") {
    if (src.includes(BUILD_ISO_OLD)) {
      src = src.replace(BUILD_ISO_OLD, BUILD_ISO_NEW);
    } else if (!src.includes("if (date == nil)") && src.includes("buildISO8601StringFromDate")) {
      console.warn(
        `[patch-health] ${fileName}: buildISO8601StringFromDate shape changed upstream — verify manually`
      );
    }
    // KVC type can be nil — cannot put nil in @{ }
    src = src.replace(
      /@"eventTypeInt":eventType,/g,
      '@"eventTypeInt":(eventType ?: @(0)),'
    );
  }

  // --- RCTAppleHealthKit+Queries.m: HKSample.metadata can be nil (workout anchored query) ---
  src = src.replace(
    /@"metadata"\s*:\s*\[sample metadata\],/g,
    '@"metadata" : [sample metadata] ? [sample metadata] : [NSNull null],'
  );

  // --- HKSource bundleIdentifier / name can be nil (statistics query breakdown) ---
  src = src.replace(
    /@"sourceId"\s*:\s*bundleIdentifier,/g,
    '@"sourceId" : (bundleIdentifier ?: @""),'
  );
  src = src.replace(
    /@"sourceName"\s*:\s*name,/g,
    '@"sourceName" : (name ?: @""),'
  );

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

  // Nil-guard [[...UUID] UUIDString]
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
    return true;
  }
  return false;
}

let patched = 0;
for (const file of files) {
  const filePath = path.join(RN_HEALTH_DIR, file);
  if (patchFile(filePath, file)) {
    patched++;
    console.log(`[patch-health] Patched ${file}`);
  }
}

if (patched > 0) {
  console.log(`[patch-health] Done — patched ${patched} file(s).`);
} else {
  console.log("[patch-health] No changes needed (already patched).");
}
