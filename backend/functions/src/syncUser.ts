import {logger} from "firebase-functions";
import {onCall, HttpsError} from "firebase-functions/v2/https";
import {getAuth, type DecodedIdToken} from "firebase-admin/auth";
import {FieldValue} from "firebase-admin/firestore";

import {APPLE_PROVIDER} from "./apple/constants";
import {findOrCreateAppleUserRecord} from "./apple/userStore";
import {
  decodeExternalAuthJwt,
  externalIdCandidates,
  PROVIDER_FIELDS,
  type ExternalAuthProvider,
} from "./externalAuthJwt";
import {db} from "./firebase";
import {
  initialTrialFields,
  mergeTrialFields,
  missingTrialDefaults,
} from "./subscriptionTrials";

/**
 * Generates a UID for Telegram/external authentication.
 * @param {string} provider The authentication provider.
 * @param {string} externalUserId The external user ID.
 * @return {string} The generated UID.
 */
function telegramAuthUid(provider: string, externalUserId: string): string {
  if (externalUserId.startsWith(`${provider}:`)) {
    return externalUserId;
  }
  return `${provider}:${externalUserId}`;
}

/**
 * Extracts the raw external ID by removing the provider prefix if present.
 * @param {string} provider The authentication provider.
 * @param {string} externalUserId The external user ID.
 * @return {string} The raw user ID.
 */
function rawExternalId(provider: string, externalUserId: string): string {
  const prefix = `${provider}:`;
  if (externalUserId.startsWith(prefix)) {
    return externalUserId.slice(prefix.length);
  }
  return externalUserId;
}

/**
 * Ensures a Firebase Auth user exists for the given external provider and ID.
 * @param {ExternalAuthProvider} provider The external provider.
 * @param {string} externalUserId The external user ID.
 * @return {Promise<string>} The user's UID.
 */
async function ensureExternalAuthUser(
  provider: ExternalAuthProvider,
  externalUserId: string
): Promise<string> {
  const uid = telegramAuthUid(provider, externalUserId);
  const rawId = rawExternalId(provider, externalUserId);
  const auth = getAuth();

  try {
    await auth.getUser(uid);
  } catch (err) {
    const error = err as {code?: string};
    if (error.code !== "auth/user-not-found") {
      throw err;
    }
    await auth.createUser({uid});
  }

  await auth.setCustomUserClaims(uid, {
    provider,
    [`${provider}Id`]: rawId,
  });

  return uid;
}

/**
 * Determines the document ID in the 'users' collection for the authorized user.
 * @param {DecodedIdToken} decoded The decoded ID token.
 * @return {Promise<string>} The document ID.
 */
async function authorizedUsersDocId(decoded: DecodedIdToken): Promise<string> {
  if (decoded.firebase?.sign_in_provider === APPLE_PROVIDER) {
    return findOrCreateAppleUserRecord(decoded.uid);
  }

  const users = db.collection("users");
  const existing = await users
    .where("externalAppleId", "==", decoded.uid)
    .limit(1)
    .get();
  if (!existing.empty) {
    return existing.docs[0].id;
  }

  const uidDoc = await users.doc(decoded.uid).get();
  if (uidDoc.exists) {
    return uidDoc.id;
  }

  return findOrCreateAppleUserRecord(decoded.uid);
}

export const syncUser = onCall(
  {cors: true, maxInstances: 10},
  async (request) => {
    const decodedIdToken = request.auth?.token;
    const externalJwt = request.data?.externalJwt;

    if (!decodedIdToken && !externalJwt) {
      throw new HttpsError(
        "invalid-argument",
        "No authentication credentials provided"
      );
    }

    let externalPayload: {
    provider: ExternalAuthProvider,
    externalUserId: string
  } | null = null;
    if (externalJwt) {
      try {
        externalPayload = decodeExternalAuthJwt(externalJwt);
      } catch (err) {
        logger.warn("syncUser: invalid external JWT", err);
        throw new HttpsError("unauthenticated", "Invalid external JWT");
      }
    }

    try {
      const users = db.collection("users");

      // Case 1: Both tokens provided (Merge Scenario)
      if (decodedIdToken && externalPayload) {
        const {provider, externalUserId} = externalPayload;
        const providerField = PROVIDER_FIELDS[provider];
        const rawId = rawExternalId(provider, externalUserId);

        const destinationDocId = await authorizedUsersDocId(decodedIdToken);
        const destinationRef = users.doc(destinationDocId);
        const sourceQuery = users
          .where(
            providerField,
            "in",
            externalIdCandidates(provider, externalUserId)
          )
          .limit(1);

        const result = await db.runTransaction(async (transaction) => {
          const [destinationSnap, sourceSnap] = await Promise.all([
            transaction.get(destinationRef),
            transaction.get(sourceQuery),
          ]);

          const destinationData: Record<string, unknown> =
            destinationSnap.exists ? (destinationSnap.data() || {}) : {};
          let sourceData: Record<string, unknown> = {};
          let sourceDoc = null;
          if (!sourceSnap.empty) {
            sourceDoc = sourceSnap.docs[0];
            sourceData = sourceDoc.data();
          }

          const payload: Record<string, unknown> = {
            ...destinationData,
          };

          for (const [key, value] of Object.entries(sourceData)) {
            const destValue = payload[key];
            if (value !== null && value !== undefined && value !== "") {
              if (
                destValue === null ||
                destValue === undefined ||
                destValue === ""
              ) {
                payload[key] = value;
              }
            }
          }

          Object.assign(payload, mergeTrialFields(destinationData, sourceData));

          payload.externalAppleId =
            destinationData.externalAppleId ??
            sourceData.externalAppleId ??
            (decodedIdToken.firebase?.sign_in_provider === APPLE_PROVIDER ?
              decodedIdToken.uid : null);
          payload[providerField] = rawId;
          payload.updatedAt = FieldValue.serverTimestamp();

          transaction.set(destinationRef, payload, {merge: true});
          if (sourceDoc && sourceDoc.id !== destinationRef.id) {
            transaction.delete(sourceDoc.ref);
          }

          return {
            ok: true,
            action: "merged",
            uid: decodedIdToken.uid,
            usersDocId: destinationDocId,
            merged: sourceDoc ? (sourceDoc.id !== destinationRef.id) : false,
          };
        });

        if (result.merged) {
          const oldUid = telegramAuthUid(provider, externalUserId);
          try {
            await getAuth().deleteUser(oldUid);
            logger.info(
              `Deleted old Firebase Auth user after merge: ${oldUid}`
            );
          } catch (e) {
            logger.warn(
              `Could not delete old Firebase Auth user: ${oldUid}`,
              e
            );
          }
        }

        return result;
      }

      // Case 2: Only Firebase ID Token provided (Apple Login)
      if (decodedIdToken && !externalPayload) {
        const destinationDocId = await authorizedUsersDocId(decodedIdToken);
        return {
          ok: true,
          action: "login_apple",
          uid: decodedIdToken.uid,
          usersDocId: destinationDocId,
        };
      }

      // Case 3: Only External JWT provided (Telegram / VK Login)
      if (!decodedIdToken && externalPayload) {
        const {provider, externalUserId} = externalPayload;
        const providerField = PROVIDER_FIELDS[provider];
        const rawId = rawExternalId(provider, externalUserId);

        const uid = await ensureExternalAuthUser(provider, externalUserId);

        const existing = await users
          .where(
            providerField,
            "in",
            externalIdCandidates(provider, externalUserId)
          )
          .limit(1)
          .get();

        let usersDocId: string;
        let targetUid: string = uid;
        if (!existing.empty) {
          const doc = existing.docs[0];
          const data = doc.data();
          await doc.ref.set(
            {
              ...missingTrialDefaults(data),
              updatedAt: FieldValue.serverTimestamp(),
            },
            {merge: true}
          );
          usersDocId = doc.id;
          if (data.externalAppleId) {
            targetUid = data.externalAppleId;
            // Ensure the Apple account has the external provider claims
            await getAuth().setCustomUserClaims(targetUid, {
              provider,
              [`${provider}Id`]: rawId,
            });
          }
        } else {
          const ref = users.doc();
          await ref.set({
            ...initialTrialFields(),
            externalAppleId: null,
            externalTg: provider === "tg" ? rawId : null,
            externalVk: provider === "vk" ? rawId : null,
            createdAt: FieldValue.serverTimestamp(),
            updatedAt: FieldValue.serverTimestamp(),
          }, {merge: true});
          usersDocId = ref.id;
        }

        const customToken = await getAuth().createCustomToken(targetUid, {
          provider: provider,
          [`${provider}Id`]: rawId,
        });

        return {
          ok: true,
          action: "login_external",
          customToken,
          uid: targetUid,
          usersDocId,
        };
      }

      throw new HttpsError("internal", "Unhandled sync state");
    } catch (err) {
      logger.error("syncUser: failed", err);
      throw new HttpsError("internal", "Internal server error during sync");
    }
  });
