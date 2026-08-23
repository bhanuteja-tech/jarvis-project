// Shared tokenization for the frontend (mirrors backend normalization).

export function contentTokens(text) {
  return new Set(
    (text || "").toLowerCase().match(/[a-z0-9+#]{3,}/g) || []
  );
}
