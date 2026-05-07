import {FieldValue} from "firebase-admin/firestore";

import {db} from "../firebase";
import {
  APPLE_PROVIDER,
  type AuthProviderData,
} from "./constants";
import {
  initialTrialFields,
  missingTrialDefaults,
} from "../subscriptionTrials";

/**
 * Whether linked provider list includes Sign in with Apple.
 * @param {Array<{providerId: string}>|undefined} providerData Auth provider
 *     entries from a user record.
 * @return {boolean} True if Apple is among linked providers.
 */
export function providerDataHasApple(
  providerData: AuthProviderData | undefined
): boolean {
  return providerData?.some((p) => p.providerId === APPLE_PROVIDER) ?? false;
}

/**
 * Finds or creates a `users` record for Sign in with Apple.
 * @param {string} externalAppleId Firebase Auth UID from `apple_user.uid`.
 * @return {Promise<string>} Firestore document ID for the user record.
 */
export async function findOrCreateAppleUserRecord(
  externalAppleId: string
): Promise<string> {
  const users = db.collection("users");
  const existing = await users
    .where("externalAppleId", "==", externalAppleId)
    .limit(1)
    .get();

  if (!existing.empty) {
    const doc = existing.docs[0];
    const data = doc.data();
    const payload: Record<string, unknown> = {
      externalAppleId,
      ...missingTrialDefaults(data),
    };

    if (data.externalTg === undefined) {
      payload.externalTg = null;
    }
    if (data.externalVk === undefined) {
      payload.externalVk = null;
    }

    await doc.ref.set(payload, {merge: true});
    return doc.id;
  }

  const ref = users.doc(externalAppleId);
  await ref.set({
    ...initialTrialFields(),
    externalAppleId,
    externalTg: null,
    externalVk: null,
  }, {merge: true});

  return ref.id;
}

/**
 * Upserts `apple_user/{uid}` with timestamps and email fields.
 * @param {string} uid Firebase Auth UID.
 * @param {string|undefined} email User email if present.
 * @param {boolean} emailVerified Whether email is verified.
 * @return {Promise<void>} Resolves when Firestore write completes.
 */
export async function persistAppleUserDoc(
  uid: string,
  email: string | undefined,
  emailVerified: boolean
): Promise<void> {
  const ref = db.collection("apple_user").doc(uid);
  const snap = await ref.get();

  const payload: Record<string, unknown> = {
    uid,
    email: email ?? null,
    emailVerified,
    updatedAt: FieldValue.serverTimestamp(),
  };
  if (!snap.exists) {
    payload.createdAt = FieldValue.serverTimestamp();
  }

  await ref.set(payload, {merge: true});
}
