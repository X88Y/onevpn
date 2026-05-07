import {FieldValue} from "firebase-admin/firestore";
import {onCall, HttpsError} from "firebase-functions/v2/https";

import {db} from "./firebase";
import {serializeFirestoreValue} from "./firestoreData";
import {
  buildTrialActivationPayload,
  connectedTrialProviders,
  TRIAL_FLAG_FIELDS,
  type TrialProvider,
} from "./subscriptionTrials";
import {resolveUsersDoc} from "./userResolver";

const TRIAL_PROVIDER_IDS = new Set<TrialProvider>(["tg", "apple", "vk"]);

/**
 * Parses optional trial provider from callable `data.provider`.
 * @param {unknown} raw Callable `data.provider`; undefined/null means all
 *     eligible trials.
 * @return {TrialProvider|undefined} Valid provider id, or undefined if omitted.
 */
function parseOptionalTrialProvider(raw: unknown): TrialProvider | undefined {
  if (raw === undefined || raw === null) {
    return undefined;
  }
  if (
    typeof raw !== "string" ||
    !TRIAL_PROVIDER_IDS.has(raw as TrialProvider)
  ) {
    throw new HttpsError(
      "invalid-argument",
      "provider must be one of: tg, apple, vk"
    );
  }
  return raw as TrialProvider;
}

/**
 * Explicitly starts connected provider trials that are still unused.
 * Pass `data.provider` as `"tg" | "apple" | "vk"` to start only that service's
 * trial.
 * Omit `provider` to activate every connected service that still has an unused
 * trial.
 */
export const startTrial = onCall(
  {cors: true, maxInstances: 10},
  async (request) => {
    const decodedIdToken = request.auth?.token;
    if (!decodedIdToken) {
      throw new HttpsError("unauthenticated", "Authentication is required");
    }

    const onlyProvider = parseOptionalTrialProvider(
      (request.data as {provider?: unknown} | undefined)?.provider
    );

    const resolved = await resolveUsersDoc(decodedIdToken);
    if (!resolved) {
      throw new HttpsError("not-found", "User record was not found");
    }

    const result = await db.runTransaction(async (transaction) => {
      const snap = await transaction.get(resolved.ref);
      if (!snap.exists) {
        throw new HttpsError("not-found", "User record was not found");
      }

      const data = snap.data() || {};
      const connectedProviders = connectedTrialProviders(data);
      if (connectedProviders.length === 0) {
        throw new HttpsError(
          "failed-precondition",
          "Connect at least one app before starting a trial"
        );
      }

      let providersToActivate: TrialProvider[];
      if (onlyProvider !== undefined) {
        if (!connectedProviders.includes(onlyProvider)) {
          throw new HttpsError(
            "failed-precondition",
            "That service is not connected for this account"
          );
        }
        const flag = TRIAL_FLAG_FIELDS[onlyProvider];
        if (data[flag] === true) {
          throw new HttpsError(
            "failed-precondition",
            "Trial already activated for this service"
          );
        }
        providersToActivate = [onlyProvider];
      } else {
        providersToActivate = connectedProviders;
      }

      const {payload, activatedProviders} = buildTrialActivationPayload(
        data,
        providersToActivate
      );
      const updatePayload = {
        ...payload,
        updatedAt: FieldValue.serverTimestamp(),
      };
      transaction.set(resolved.ref, updatePayload, {merge: true});

      return {
        activatedProviders,
        user: {
          ...data,
          ...payload,
        },
      };
    });

    return {
      ok: true,
      usersDocId: resolved.id,
      activatedProviders: result.activatedProviders,
      user: serializeFirestoreValue(result.user),
    };
  }
);
