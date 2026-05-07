import {type DecodedIdToken} from "firebase-admin/auth";
import {type DocumentReference} from "firebase-admin/firestore";

import {APPLE_PROVIDER} from "./apple/constants";
import {findOrCreateAppleUserRecord} from "./apple/userStore";
import {
  externalIdCandidates,
  PROVIDER_FIELDS,
  type ExternalAuthProvider,
} from "./externalAuthJwt";
import {db} from "./firebase";

export type ResolvedUsersDoc = {
  id: string;
  ref: DocumentReference;
};

/**
 * Extracts a supported external provider from auth custom claims.
 * @param {DecodedIdToken} decoded Auth token claims.
 * @return {ExternalAuthProvider|null} External provider, if present.
 */
function providerFromClaims(
  decoded: DecodedIdToken
): ExternalAuthProvider | null {
  if (decoded.provider === "tg" || decoded.provider === "telegram") {
    return "tg";
  }
  if (decoded.provider === "vk") {
    return "vk";
  }

  return null;
}

/**
 * Reads the provider user id stored in auth custom claims.
 * @param {DecodedIdToken} decoded Auth token claims.
 * @param {ExternalAuthProvider} provider External provider.
 * @return {string|null} External user id, if present.
 */
function externalIdFromClaims(
  decoded: DecodedIdToken,
  provider: ExternalAuthProvider
): string | null {
  const claim = provider === "tg" ? decoded.tgId : decoded.vkId;
  if (typeof claim !== "string" && typeof claim !== "number") {
    return null;
  }

  const value = String(claim).trim();
  return value || null;
}

/**
 * Resolves the `users` document for an authenticated caller.
 * @param {DecodedIdToken} decoded Auth token claims.
 * @return {Promise<ResolvedUsersDoc|null>} Matching users document, if any.
 */
export async function resolveUsersDoc(
  decoded: DecodedIdToken
): Promise<ResolvedUsersDoc | null> {
  const users = db.collection("users");
  const provider = providerFromClaims(decoded);
  if (provider) {
    const externalId = externalIdFromClaims(decoded, provider);
    if (externalId) {
      const external = await users
        .where(
          PROVIDER_FIELDS[provider],
          "in",
          externalIdCandidates(provider, externalId)
        )
        .limit(1)
        .get();
      if (!external.empty) {
        const doc = external.docs[0];
        return {id: doc.id, ref: doc.ref};
      }
    }
  }

  const apple = await users
    .where("externalAppleId", "==", decoded.uid)
    .limit(1)
    .get();
  if (!apple.empty) {
    const doc = apple.docs[0];
    return {id: doc.id, ref: doc.ref};
  }

  const uidDoc = await users.doc(decoded.uid).get();
  if (uidDoc.exists) {
    return {id: uidDoc.id, ref: uidDoc.ref};
  }

  if (decoded.firebase?.sign_in_provider === APPLE_PROVIDER) {
    const id = await findOrCreateAppleUserRecord(decoded.uid);
    return {id, ref: users.doc(id)};
  }

  return null;
}
