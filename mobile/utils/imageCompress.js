/**
 * Resize and compress image before upload to reduce latency.
 * Target: max 768px long edge, JPEG quality 0.58 (faster upload).
 * This trims upload + decode latency while keeping food-shape fidelity.
 */
const MAX_EDGE_PX = 768;
const COMPRESS_QUALITY = 0.58;

export async function prepareImageForScan(uri) {
  if (!uri || typeof uri !== "string") return uri;
  try {
    const { manipulateAsync, SaveFormat } = await import("expo-image-manipulator");
    const result = await manipulateAsync(
      uri,
      [{ resize: { width: MAX_EDGE_PX } }],
      { compress: COMPRESS_QUALITY, format: SaveFormat.JPEG }
    );
    return result?.uri || uri;
  } catch (e) {
    return uri;
  }
}
