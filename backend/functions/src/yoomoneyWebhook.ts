import type {DocumentData} from "firebase-admin/firestore";
import {FieldValue, Timestamp} from "firebase-admin/firestore";
import {onRequest} from "firebase-functions/v2/https";
import {defineSecret} from "firebase-functions/params";

import {db} from "./firebase";
import {notifyPurchase, notifyReferrerOfBonus} from "./notifyUser";
import {extendReferrerOnPurchase} from "./referral";

/**
 * Days to extend subscription per plan key.
 */
const PLAN_DAYS: Record<string, number> = {
  plan_30: 30,
  plan_90: 90,
  plan_180: 180,
};

/**
 * Parses the YooKassa `label` field sent in the payment metadata.
 * Expected format:
 *   mvm_{provider}_{userId}_{planKey}_{nonce}
 */
const LABEL_RE =
  /^mvm(?::|_)(tg|vk)(?::|_)(\d+)(?::|_)(plan_\w+)(?::|_)\d+$/;

type ParsedLabel = {
  provider: "tg" | "vk";
  externalUserId: string;
  planKey: string;
};

interface YooKassaPayment {
  status: string;
  amount: {
    value: string;
    currency: string;
  };
  metadata?: {
    label?: string;
  };
  payment_method?: {
    id: string;
    saved: boolean;
  };
}

/**
 * Parses label metadata string into components.
 * @param {unknown} label The metadata label.
 * @return {ParsedLabel | null} The parsed components or null.
 */
function parseLabel(label: unknown): ParsedLabel | null {
  if (typeof label !== "string") return null;
  const m = LABEL_RE.exec(label.trim());
  if (!m) return null;
  return {
    provider: m[1] as "tg" | "vk",
    externalUserId: m[2],
    planKey: m[3],
  };
}

/**
 * Returns the subscription baseline date: max(now, current subscriptionEndsAt).
 * @param {DocumentData} data The user document data.
 * @return {Date} The baseline date.
 */
function subscriptionBaseDate(data: DocumentData): Date {
  const now = new Date();
  const endRaw = data.subscriptionEndsAt;
  if (!endRaw) return now;
  const end =
    endRaw instanceof Timestamp ? endRaw.toDate() : new Date(endRaw as string);
  if (Number.isNaN(end.getTime())) return now;
  return end > now ? end : now;
}

/**
 * Processes YooKassa HTTP payment notifications.
 *
 * YooKassa sends a POST with a JSON body representing the event:
 *   type, event, object
 *
 * Validation is performed by querying the YooKassa REST API directly.
 *
 * Idempotency is guaranteed via `yoomoney_processed/{payment_id}`.
 */
export const yoomoneyWebhook = onRequest(
  {
    cors: false,
    maxInstances: 10,
    memory: "256MiB",
    secrets: [
      defineSecret("YOOMONEY_SECRET"),
      defineSecret("YOOMONEY_RECEIVER"),
      defineSecret("MVMVPN_JWT_SECRET"),
      defineSecret("BOT_TOKEN"),
      defineSecret("VK_BOT_TOKEN"),
    ],
  },
  async (req, res) => {
    if (req.method !== "POST") {
      res.status(405).send("Method Not Allowed");
      return;
    }

    const shopId = process.env.YOOMONEY_RECEIVER?.trim();
    const apiKey = process.env.YOOMONEY_SECRET?.trim();
    if (!shopId || !apiKey) {
      res.status(501).send(
        "YOOMONEY_RECEIVER or YOOMONEY_SECRET is not configured"
      );
      return;
    }

    const body = req.body as Record<string, unknown>;
    if (typeof body !== "object" || body === null || Array.isArray(body)) {
      res.status(400).send("Invalid payload");
      return;
    }

    if (body.event !== "payment.succeeded") {
      // Only handle succeeded payments
      res.status(200).send("Event ignored");
      return;
    }

    const eventObject = body.object as Record<string, unknown> | undefined;
    const paymentId = eventObject?.id as string | undefined;
    if (!paymentId) {
      res.status(400).send("Missing payment ID");
      return;
    }

    // Verify payment by fetching directly from YooKassa API
    let paymentData: YooKassaPayment;
    try {
      const auth = Buffer.from(`${shopId}:${apiKey}`).toString("base64");
      const url = `https://api.yookassa.ru/v3/payments/${paymentId}`;
      const response = await fetch(url, {
        headers: {
          "Authorization": `Basic ${auth}`,
        },
      });

      if (!response.ok) {
        const errText = await response.text();
        console.error(
          `YooKassa GET payment failed: ${response.status} ${errText}`
        );
        res.status(response.status >= 500 ? 502 : 400).send(
          "Verification request failed"
        );
        return;
      }

      paymentData = await response.json() as YooKassaPayment;
    } catch (err) {
      console.error("YooKassa fetch error:", err);
      res.status(500).send("Failed to query YooKassa API");
      return;
    }

    if (paymentData.status !== "succeeded") {
      res.status(400).send("Payment status is not succeeded");
      return;
    }

    const label = paymentData.metadata?.label;
    const parsed = parseLabel(label);
    if (!parsed) {
      // Not our payment (e.g. a manual transfer without label)
      res.status(200).send("");
      return;
    }

    const days = PLAN_DAYS[parsed.planKey];
    if (!days) {
      res.status(400).send("Unknown plan key");
      return;
    }

    const processedRef = db
      .collection("yoomoney_processed")
      .doc(paymentId);
    const providerField =
      parsed.provider === "tg" ? "externalTg" : "externalVk";
    const prefixedExternalId = `${parsed.provider}:${parsed.externalUserId}`;
    const rawExternalId = parsed.externalUserId;

    let transactionResult: {
      notifyAfter: { newEnd: Date } | null;
      referrerNotify: { provider: "tg" | "vk"; externalUserId: string } | null;
    };

    try {
      transactionResult = await db.runTransaction(async (transaction) => {
        // Idempotency — skip if already processed
        const processedSnap = await transaction.get(processedRef);
        if (processedSnap.exists) {
          return {
            notifyAfter: null,
            referrerNotify: null,
          };
        }

        const usersRef = db.collection("users");
        const prefixedQuery = usersRef
          .where(providerField, "==", prefixedExternalId)
          .limit(1);
        const prefixedSnap = await transaction.get(prefixedQuery);
        const userSnap = prefixedSnap.empty ?
          await transaction.get(
            usersRef.where(providerField, "==", rawExternalId).limit(1)
          ) :
          prefixedSnap;
        if (userSnap.empty) {
          throw new Error(
            `User not found for provider=${parsed.provider} ` +
              `id=${parsed.externalUserId}`
          );
        }

        const docRef = userSnap.docs[0].ref;
        const data = userSnap.docs[0].data() || {};
        const base = subscriptionBaseDate(data);
        const newEnd = new Date(base.getTime());
        newEnd.setUTCDate(newEnd.getUTCDate() + days);

        // All reads must happen before all writes in a Firestore transaction.
        const refNotify = await extendReferrerOnPurchase(
          transaction,
          docRef,
          data
        );

        const updateData: Record<string, unknown> = {
          subscriptionEndsAt: Timestamp.fromDate(newEnd),
          updatedAt: FieldValue.serverTimestamp(),
        };

        const paymentMethod = paymentData.payment_method;
        if (paymentMethod && paymentMethod.saved === true) {
          updateData.yookassaPaymentMethodId = paymentMethod.id;
          updateData.yookassaPlanKey = parsed.planKey;
        }

        transaction.set(docRef, updateData, {merge: true});
        transaction.set(processedRef, {
          operationId: paymentId,
          label,
          provider: parsed.provider,
          externalUserId: parsed.externalUserId,
          planKey: parsed.planKey,
          amount: paymentData.amount.value,
          notificationType: body.event,
          processedAt: FieldValue.serverTimestamp(),
        });

        return {
          notifyAfter: {newEnd},
          referrerNotify: refNotify,
        };
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      res.status(500).send(message);
      return;
    }

    if (transactionResult.notifyAfter !== null) {
      void notifyPurchase(
        parsed.provider,
        parsed.externalUserId,
        parsed.planKey,
        transactionResult.notifyAfter.newEnd,
        paymentData.amount.value,
        "yoomoney"
      );
      const refInfo = transactionResult.referrerNotify;
      if (refInfo) {
        void notifyReferrerOfBonus(
          refInfo.provider,
          refInfo.externalUserId,
          "Друг, зарегистрировавшийся по вашей реферальной ссылке, " +
            "совершил покупку! Вам начислено +15 дней подписки. 🎉"
        );
      }
    }

    // YooKassa requires a 200 response to acknowledge the notification
    res.status(200).send("");
  }
);
