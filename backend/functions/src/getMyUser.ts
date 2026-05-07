import {onCall, HttpsError} from "firebase-functions/v2/https";

import {serializeFirestoreValue} from "./firestoreData";
import {missingTrialDefaults} from "./subscriptionTrials";
import {resolveUsersDoc} from "./userResolver";
import {PUBLIC_CONSTANT} from "./publicConstant";

/**
 * Returns the authenticated caller's canonical `users` document.
 */
export const getMyUser = onCall(
  {cors: true, maxInstances: 10},
  async (request) => {
    const decodedIdToken = request.auth?.token;
    if (!decodedIdToken) {
      throw new HttpsError("unauthenticated", "Authentication is required");
    }

    const resolved = await resolveUsersDoc(decodedIdToken);
    if (!resolved) {
      throw new HttpsError("not-found", "User record was not found");
    }

    const snap = await resolved.ref.get();
    const data = snap.data() || {};
    const defaults = missingTrialDefaults(data);
    if (Object.keys(defaults).length > 0) {
      await resolved.ref.set(defaults, {merge: true});
    }

    return {
      ok: true,
      usersDocId: resolved.id,
      user: serializeFirestoreValue({
        ...data,
        ...defaults,
      }),
      publicConstant: PUBLIC_CONSTANT,
    };
  }
);
