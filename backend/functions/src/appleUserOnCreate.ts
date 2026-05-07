import {logger} from "firebase-functions";
import {auth} from "firebase-functions/v1";

import {
  findOrCreateAppleUserRecord,
  persistAppleUserDoc,
  providerDataHasApple,
} from "./apple/userStore";

/**
 * Runs when a new Firebase Auth user is created (1st gen trigger). Writes
 * `apple_user/{uid}` for Apple sign-in without GCIP / blocking functions.
 *
 * Renamed from `onAppleAuthUserCreate` so deploy succeeds if a Gen2 attempt
 * left an orphaned Cloud Run service with that name (409 ALREADY_EXISTS).
 *
 * Uses Node 20 from `package.json` engines — Gen1 auth triggers do not
 * support Node 24; keep `"node": "20"` while this export exists.
 */
export const appleUserOnCreate = auth.user().onCreate(async (user) => {
  if (!providerDataHasApple(user.providerData)) {
    return;
  }
  const externalAppleId = user.uid;

  try {
    await Promise.all([
      persistAppleUserDoc(
        user.uid,
        user.email,
        user.emailVerified
      ),
      findOrCreateAppleUserRecord(externalAppleId),
    ]);
  } catch (err) {
    logger.error("appleUserOnCreate: firestore write failed", {
      uid: user.uid,
      err,
    });
    throw err;
  }
});
