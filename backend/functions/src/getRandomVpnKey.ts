import {onCall, HttpsError} from "firebase-functions/v2/https";

import {
  MANAGER_BASE_URL,
  provisionClient,
} from "./managerClient";
import {hasActiveSubscription} from "./subscriptionTrials";
import {resolveUsersDoc} from "./userResolver";
import {db} from "./firebase";

void MANAGER_BASE_URL;

/**
 * Returns the caller's existing (last-used) subscription URL when present,
 * otherwise provisions one across the healthy server pool. Idempotent;
 * rotation is exposed via `regenerateVpnKey`.
 */
export const getRandomVpnKey = onCall(
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

    const clientSnap =
      await db.collection("vpn_clients").doc(resolved.id).get();
    const clientData = clientSnap.data();
    if (clientData?.subscriptionUrl) {
      return {
        ok: true,
        key: clientData.subscriptionUrl as string,
        subId: clientData.subId as string,
      };
    }

    const result = await provisionClient(resolved.id);
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
    };
  }
);
