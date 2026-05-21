import {FieldValue, Timestamp} from "firebase-admin/firestore";
import type {DocumentData, Transaction} from "firebase-admin/firestore";
import {db} from "./firebase";

const REFERRAL_PURCHASE_BONUS_DAYS = 15;

function subscriptionBaseDate(data: DocumentData): Date {
  const now = new Date();
  const endRaw = data.subscriptionEndsAt;
  if (!endRaw) {
    return now;
  }
  const end =
    endRaw instanceof Timestamp ? endRaw.toDate() : new Date(endRaw as string);
  if (Number.isNaN(end.getTime())) {
    return now;
  }
  return end > now ? end : now;
}

/**
 * Extends the referrer's subscription when a referred user makes a purchase.
 * Looks up the referrer via the purchaser's referredByCode and adds bonus days.
 * Guards against self-referral.
 */
export async function extendReferrerOnPurchase(
  transaction: Transaction,
  purchaserDocRef: FirebaseFirestore.DocumentReference,
  purchaserData: DocumentData
): Promise<void> {
  const referredByCode = purchaserData.referredByCode;
  if (!referredByCode || typeof referredByCode !== "string") {
    return;
  }

  const referrerQuery = db
    .collection("users")
    .where("referralCode", "==", referredByCode)
    .limit(1);
  const referrerSnap = await transaction.get(referrerQuery);
  if (referrerSnap.empty) {
    return;
  }

  const referrerDoc = referrerSnap.docs[0];
  if (referrerDoc.ref.path === purchaserDocRef.path) {
    return;
  }

  const referrerData = referrerDoc.data() || {};
  const base = subscriptionBaseDate(referrerData);
  const newEnd = new Date(base.getTime());
  newEnd.setUTCDate(newEnd.getUTCDate() + REFERRAL_PURCHASE_BONUS_DAYS);

  transaction.set(
    referrerDoc.ref,
    {
      subscriptionEndsAt: Timestamp.fromDate(newEnd),
      updatedAt: FieldValue.serverTimestamp(),
    },
    {merge: true}
  );
}
