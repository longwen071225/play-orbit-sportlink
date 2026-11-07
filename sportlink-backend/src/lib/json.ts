/** Serialize a value for storage in a TEXT column. */
export function toJson(value: unknown): string {
  return JSON.stringify(value ?? null);
}

/** Parse a JSON TEXT column. Returns null (never throws) on missing/invalid input. */
export function fromJson<T = unknown>(text: string | null | undefined): T | null {
  if (text == null || text === '') return null;
  try {
    return JSON.parse(text) as T;
  } catch {
    return null;
  }
}
