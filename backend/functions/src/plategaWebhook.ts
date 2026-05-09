import type {DocumentData} from "firebase-admin/firestore";
import {FieldValue, Timestamp} from "firebase-admin/firestore";
import {onRequest} from "firebase-functions/v2/https";

import {db} from "./firebase";
import {notifyPurchase} from "./notifyUser";
import {defineSecret} from "firebase-functions/params";

/**
 * Days to extend subscription per plan key.
 * plan_30 / plan_90 are used by user bots (mvm_bot, mvm_vk_bot).
 * plan_30 / plan_90 / plan_180 are also used by the admin bot purchase flow.
 */
const PLAN_DAYS: Record<string, number> = {
  plan_30: 30,
  plan_90: 90,
  plan_180: 180,
};

type ParsedPayload = {
  provider: "tg" | "vk";
  externalUserId: string;
  planKey: string;
};

/**
 * Parses the Platega transaction payload: "{provider}:{userId}:{planKey}".
 * @param {unknown} raw The ``payload`` field from the Platega callback body.
 * @return {ParsedPayload | null} Parsed fields or null if malformed.
 */
function parsePayload(raw: unknown): ParsedPayload | null {
  if (typeof raw !== "string") {
    return null;
  }
  const parts = raw.trim().split(":");
  if (parts.length !== 3) {
    return null;
  }
  const [provider, userId, planKey] = parts;
  if (provider !== "tg" && provider !== "vk") {
    return null;
  }
  if (!userId || !planKey) {
    return null;
  }
  return {provider, externalUserId: userId, planKey};
}

/**
 * Subscription end baseline: max(now, current subscriptionEndsAt).
 * @param {DocumentData} data Current Firestore user document data.
 * @return {Date} UTC instant to extend from.
 */
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
 * Processes Platega payment callbacks.
 *
 * Validates the request by comparing ``X-MerchantId`` and ``X-Secret``
 * headers against the ``PLATEGA_MERCHANT_ID`` and ``PLATEGA_SECRET``
 * environment variables.
 *
 * On ``status === "CONFIRMED"`` the function looks up the user in Firestore
 * by their ``externalTg`` / ``externalVk`` field (encoded in the transaction
 * ``payload``) and extends their ``subscriptionEndsAt``.
 *
 * Idempotency is guaranteed via the ``platega_processed/{transactionId}``
 * collection — duplicate callbacks are silently accepted.
 */
// eslint-disable-next-line camelcase
export const plategaWebhook = onRequest(
  {
    cors: false,
    maxInstances: 10,
    memory: "256MiB",
    secrets: [
      defineSecret("PLATEGA_MERCHANT_ID"),
      defineSecret("PLATEGA_SECRET"),
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

    const merchantId = process.env.PLATEGA_MERCHANT_ID;
    const secret = process.env.PLATEGA_SECRET;
    if (!merchantId || !secret) {
      res
        .status(500)
        .send("PLATEGA_MERCHANT_ID or PLATEGA_SECRET is not configured");
      return;
    }

    const headerMerchantId = (
      req.header("x-merchantid") ||
      req.header("X-MerchantId") ||
      ""
    ).trim();
    const headerSecret = (
      req.header("x-secret") ||
      req.header("X-Secret") ||
      ""
    ).trim();

    if (headerMerchantId !== merchantId || headerSecret !== secret) {
      res.status(401).send("Unauthorized");
      return;
    }

    const body = req.body;
    if (typeof body !== "object" || body === null || Array.isArray(body)) {
      res.status(400).send("Invalid body");
      return;
    }

    const cb = body as Record<string, unknown>;
    const status = typeof cb.status === "string" ? cb.status : "";

    if (status !== "CONFIRMED") {
      res.status(200).send("Ignored");
      return;
    }

    const transactionId = typeof cb.id === "string" ? cb.id.trim() : "";
    if (!transactionId) {
      res.status(400).send("Missing transaction id");
      return;
    }

    const parsed = parsePayload(cb.payload);
    if (!parsed) {
      res.status(400).send("Invalid or missing payload");
      return;
    }

    const days = PLAN_DAYS[parsed.planKey];
    if (!days) {
      res.status(400).send("Unknown plan key");
      return;
    }

    const processedRef = db.collection("platega_processed").doc(transactionId);
    const providerField =
      parsed.provider === "tg" ? "externalTg" : "externalVk";
    const externalCandidates = [
      `${parsed.provider}:${parsed.externalUserId}`,
      parsed.externalUserId,
    ];

    let notifyAfter: {newEnd: Date} | null = null;

    try {
      await db.runTransaction(async (transaction) => {
        notifyAfter = null;
        const processedSnap = await transaction.get(processedRef);
        if (processedSnap.exists) {
          return;
        }

        const userQuery = db
          .collection("users")
          .where(providerField, "in", externalCandidates)
          .limit(1);
        const userSnap = await transaction.get(userQuery);
        if (userSnap.empty) {
          const message =
            `User not found for provider=${parsed.provider} ` +
            `id=${parsed.externalUserId}`;
          throw new Error(message);
        }

        const docRef = userSnap.docs[0].ref;
        const data = userSnap.docs[0].data() || {};
        const base = subscriptionBaseDate(data);
        const newEnd = new Date(base.getTime());
        newEnd.setUTCDate(newEnd.getUTCDate() + days);

        transaction.set(
          docRef,
          {
            subscriptionEndsAt: Timestamp.fromDate(newEnd),
            updatedAt: FieldValue.serverTimestamp(),
          },
          {merge: true}
        );
        transaction.set(processedRef, {
          transactionId,
          provider: parsed.provider,
          externalUserId: parsed.externalUserId,
          planKey: parsed.planKey,
          amount: cb.amount ?? null,
          currency: cb.currency ?? null,
          processedAt: FieldValue.serverTimestamp(),
        });
        notifyAfter = {newEnd};
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      res.status(500).send(message);
      return;
    }

    if (notifyAfter !== null) {
      void notifyPurchase(
        parsed.provider,
        parsed.externalUserId,
        parsed.planKey,
        (notifyAfter as {newEnd: Date}).newEnd
      );
    }

    res.status(200).send("OK");
  }
);
