import {defineSecret, defineString} from "firebase-functions/params";
import {HttpsError} from "firebase-functions/v2/https";

export const MANAGER_API_KEY = defineSecret("MANAGER_API_KEY");
export const MANAGER_BASE_URL = defineString("MANAGER_BASE_URL");

export type ProvisionResponse = {
  subId: string;
  subscriptionUrl: string;
  perServer?: Record<string, unknown>;
};

export type RegenerateResponse = ProvisionResponse & {
  regeneratedAt?: string | null;
  regenerationCount?: number;
};

export type TrafficResponse = {
  userUid: string;
  up: number;
  down: number;
  total: number;
  syncedAt?: string | null;
  perServer?: Record<string, {up: number; down: number; total: number}>;
};

const RETRY_AFTER_RE = /retry in (\d+)s/i;

type ManagerRequestInit = {method?: string; body?: unknown};

/**
 * Issues a JSON HTTP request to the server_manager service.
 * @param {string} path Path under MANAGER_BASE_URL.
 * @param {ManagerRequestInit} init Optional method and JSON body.
 * @return {Promise<T>} Parsed JSON response.
 */
async function managerRequest<T>(
  path: string,
  init: ManagerRequestInit = {}
): Promise<T> {
  const baseRaw = MANAGER_BASE_URL.value();
  if (!baseRaw) {
    throw new HttpsError(
      "failed-precondition",
      "MANAGER_BASE_URL is not configured"
    );
  }
  const apiKey = MANAGER_API_KEY.value();
  if (!apiKey) {
    throw new HttpsError(
      "failed-precondition",
      "MANAGER_API_KEY is not configured"
    );
  }
  const base = baseRaw.replace(/\/+$/, "");
  const method = init.method ?? "GET";
  const body = init.body === undefined ? undefined : JSON.stringify(init.body);
  const response = await fetch(`${base}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": apiKey,
    },
    body,
  });

  if (response.status === 429) {
    const text = await response.text().catch(() => "");
    const retryHeader = response.headers.get("Retry-After");
    let retry = retryHeader ? parseInt(retryHeader, 10) : NaN;
    if (Number.isNaN(retry)) {
      const match = RETRY_AFTER_RE.exec(text);
      retry = match ? parseInt(match[1], 10) : 60;
    }
    throw new HttpsError(
      "resource-exhausted",
      `Cooldown active. Try again in ${retry}s.`,
      {retryAfterSeconds: retry}
    );
  }

  if (!response.ok) {
    const text = await response.text().catch(() => "");
    throw new HttpsError(
      "internal",
      `manager responded ${response.status}: ${text.slice(0, 200)}`
    );
  }
  return (await response.json()) as T;
}

/**
 * Provisions or returns the cached subscription URL for `userUid`.
 * @param {string} userUid Canonical Firestore users doc id.
 * @return {Promise<ProvisionResponse>} Cached or freshly created sub URL.
 */
export async function provisionClient(
  userUid: string
): Promise<ProvisionResponse> {
  return managerRequest<ProvisionResponse>("/clients/provision", {
    method: "POST",
    body: {userUid},
  });
}

/**
 * Rotates the subId and per-server VLESS UUIDs for `userUid`.
 * @param {string} userUid Canonical Firestore users doc id.
 * @return {Promise<RegenerateResponse>} Newly issued sub URL + metadata.
 */
export async function regenerateClient(
  userUid: string
): Promise<RegenerateResponse> {
  return managerRequest<RegenerateResponse>("/clients/regenerate", {
    method: "POST",
    body: {userUid},
  });
}

/**
 * Reads aggregated VPN traffic counters for `userUid`.
 * @param {string} userUid Canonical Firestore users doc id.
 * @return {Promise<TrafficResponse>} Aggregated and per-server traffic.
 */
export async function getClientTraffic(
  userUid: string
): Promise<TrafficResponse> {
  return managerRequest<TrafficResponse>(
    `/clients/${encodeURIComponent(userUid)}/traffic`
  );
}
