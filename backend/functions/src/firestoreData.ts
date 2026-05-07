import {Timestamp} from "firebase-admin/firestore";

/**
 * Converts Firestore data to JSON-friendly values for callable responses.
 * @param {unknown} value Firestore value.
 * @return {unknown} JSON-friendly value.
 */
export function serializeFirestoreValue(value: unknown): unknown {
  if (value instanceof Timestamp) {
    return value.toDate().toISOString();
  }
  if (value instanceof Date) {
    return value.toISOString();
  }
  if (Array.isArray(value)) {
    return value.map(serializeFirestoreValue);
  }
  if (value && typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>);
    return Object.fromEntries(
      entries.map(([key, nested]) => [key, serializeFirestoreValue(nested)])
    );
  }

  return value;
}
