import {onCall, HttpsError} from "firebase-functions/v2/https";

import {
  MANAGER_API_KEY,
  MANAGER_BASE_URL,
  getClientTraffic,
} from "./managerClient";
import {resolveUsersDoc} from "./userResolver";

void MANAGER_BASE_URL;

/**
 * Returns the caller's aggregated VPN traffic counters. Read-only — values
 * are populated by the manager's traffic_sync worker.
 */
export const getMyVpnUsage = onCall(
  {cors: true, maxInstances: 10, secrets: [MANAGER_API_KEY]},
  async (request) => {
    const decodedIdToken = request.auth?.token;
    if (!decodedIdToken) {
      throw new HttpsError("unauthenticated", "Authentication is required");
    }

    const resolved = await resolveUsersDoc(decodedIdToken);
    if (!resolved) {
      throw new HttpsError("not-found", "User record was not found");
    }

    const traffic = await getClientTraffic(resolved.id);
    return {
      ok: true,
      up: traffic.up,
      down: traffic.down,
      total: traffic.total,
      syncedAt: traffic.syncedAt ?? null,
      perServer: traffic.perServer ?? {},
    };
  }
);
