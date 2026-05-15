import {onCall, HttpsError} from "firebase-functions/v2/https";

import {
  MANAGER_BASE_URL,
  regenerateClient,
} from "./managerClient";
import {hasActiveSubscription} from "./subscriptionTrials";
import {resolveUsersDoc} from "./userResolver";

void MANAGER_BASE_URL;

/**
 * Rotates the caller's subId and every per-server VLESS UUID, then returns
 * the freshly-issued subscription URL. Manager-enforced cooldown surfaces as
 * `resource-exhausted` so the app can show a "try again" message.
 */
export const regenerateVpnKey = onCall(
  {cors: true, maxInstances: 10, secrets: ["MANAGER_API_KEY"]},
  async (request) => {
    const decodedIdToken = request.auth?.token;
    if (!decodedIdToken) {
      throw new HttpsError("unauthenticated", "Authentication is required");
    }

    const resolved = await resolveUsersDoc(decodedIdToken);
    if (!resolved) {
      throw new HttpsError("not-found", "User record was not found");
    }

    const userSnap = await resolved.ref.get();
    const userData = userSnap.data() || {};
    if (!hasActiveSubscription(userData)) {
      throw new HttpsError(
        "failed-precondition",
        "An active subscription is required"
      );
    }

    const result = await regenerateClient(resolved.id);
    if (!result.subscriptionUrl) {
      throw new HttpsError(
        "failed-precondition",
        "No VPN servers are available"
      );
    }

    return {
      ok: true,
      key: result.subscriptionUrl,
      subId: result.subId,
      regeneratedAt: result.regeneratedAt ?? null,
      regenerationCount: result.regenerationCount ?? 0,
    };
  }
);
