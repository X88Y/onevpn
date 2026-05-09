import * as crypto from "crypto";

import type {DocumentData} from "firebase-admin/firestore";
import {FieldValue, Timestamp} from "firebase-admin/firestore";
import type {Request} from "firebase-functions/v2/https";
import {onRequest} from "firebase-functions/v2/https";

import {db} from "./firebase";
import {notifyPurchase} from "./notifyUser";
import {defineSecret} from "firebase-functions/params";

const PLAN_DAYS: Record<string, number> = {
  plan_30: 30,
  plan_90: 90,
};

const ORDER_ID_RE = /^mvm-(tg|vk)-(\d+)-(plan_\d+)-([a-zA-Z0-9]+)$/;

type ParsedOrderId = {
  provider: "tg" | "vk";
  externalUserId: string;
  planKey: string;
};

/**
 * Verifies Heleket webhook ``sign`` (MD5 over base64 JSON + payment API key).
 * JSON must use escaped slashes ``\\/`` like PHP ``json_encode``.
 * @param {Record<string, unknown>} payloadForSign Body without ``sign``.
 * @param {string} receivedSign Value from the ``sign`` field.
 * @param {string} apiPaymentKey Payment API key from Heleket dashboard.
 * @return {boolean} True when the signature matches.
 * @see {@link https://doc.heleket.com/methods/payments/webhook}
 */
function verifyHeleketWebhookSign(
  payloadForSign: Record<string, unknown>,
  receivedSign: string,
  apiPaymentKey: string
): boolean {
  if (!receivedSign || !apiPaymentKey) {
    return false;
  }
  const json = JSON.stringify(payloadForSign).replace(/\//g, "\\/");
  const b64 = Buffer.from(json, "utf8").toString("base64");
  const hash = crypto
    .createHash("md5")
    .update(b64 + apiPaymentKey, "utf8")
    .digest("hex");
  try {
    const a = Buffer.from(hash, "utf8");
    const b = Buffer.from(receivedSign, "utf8");
    return a.length === b.length && crypto.timingSafeEqual(a, b);
  } catch {
    return false;
  }
}

/**
 * Parses Heleket ``order_id`` (alpha_dash format).
 * Example: ``mvm-tg-123-plan_30-abc``.
 * @param {unknown} orderId Field from the webhook payload.
 * @return {ParsedOrderId|null} Parsed provider and user, or null.
 */
function parseOrderId(orderId: unknown): ParsedOrderId | null {
  if (typeof orderId !== "string") {
    return null;
  }
  const tagged = ORDER_ID_RE.exec(orderId.trim());
  if (!tagged) {
    return null;
  }
  return {
    provider: tagged[1] as "tg" | "vk",
    externalUserId: tagged[2],
    planKey: tagged[3],
  };
}

/**
 * Subscription end baseline: max(now, current subscription end).
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
 * Processes Heleket ``url_callback`` payment webhooks.
 * On ``paid`` / ``paid_over``, extends ``users.subscriptionEndsAt``.
 */
export const heleketWebhook = onRequest(
  {
    cors: false,
    maxInstances: 10,
    memory: "256MiB",
    secrets: [
      defineSecret("HELEKET_PAYMENT_API_KEY"),
      defineSecret("MVMVPN_JWT_SECRET"),
      defineSecret("BOT_TOKEN"),
      defineSecret("VK_BOT_TOKEN"),
    ],
  },
  async (req: Request, res) => {
    if (req.method !== "POST") {
      res.status(405).send("Method Not Allowed");
      return;
    }

    const apiKey = process.env.HELEKET_PAYMENT_API_KEY;
    if (!apiKey) {
      res.status(500).send("HELEKET_PAYMENT_API_KEY is not configured");
      return;
    }

    let payload: Record<string, unknown>;
    try {
      const raw = req.rawBody?.length ? req.rawBody.toString("utf8") : "";
      if (raw) {
        const parsed = JSON.parse(raw) as unknown;
        if (
          typeof parsed !== "object" ||
          parsed === null ||
          Array.isArray(parsed)
        ) {
          res.status(400).send("Invalid body");
          return;
        }
        payload = parsed as Record<string, unknown>;
      } else if (
        typeof req.body === "object" &&
        req.body !== null &&
        !Array.isArray(req.body)
      ) {
        payload = {...(req.body as Record<string, unknown>)};
      } else {
        res.status(400).send("Invalid body");
        return;
      }
    } catch {
      res.status(400).send("Invalid JSON");
      return;
    }

    const receivedSign = payload.sign;
    if (typeof receivedSign !== "string") {
      res.status(400).send("Missing sign");
      return;
    }

    const payloadForSign = {...payload};
    delete payloadForSign.sign;

    if (!verifyHeleketWebhookSign(payloadForSign, receivedSign, apiKey)) {
      res.status(401).send("Invalid signature");
      return;
    }

    const status = typeof payload.status === "string" ? payload.status : "";
    if (status !== "paid" && status !== "paid_over") {
      res.status(200).send("Ignored");
      return;
    }

    const parsedOrder = parseOrderId(payload.order_id);
    if (!parsedOrder) {
      res.status(400).send("Invalid order_id");
      return;
    }
    const days = PLAN_DAYS[parsedOrder.planKey];
    if (!days) {
      res.status(400).send("Unknown plan");
      return;
    }

    const paymentUuidRaw = payload.uuid;
    const paymentUuid =
      paymentUuidRaw === undefined || paymentUuidRaw === null ?
        "" :
        String(paymentUuidRaw).trim();
    if (!paymentUuid) {
      res.status(400).send("Missing uuid");
      return;
    }

    const processedRef = db.collection("heleket_processed").doc(paymentUuid);
    const providerField =
      parsedOrder.provider === "tg" ? "externalTg" : "externalVk";
    const externalCandidates = [
      `${parsedOrder.provider}:${parsedOrder.externalUserId}`,
      parsedOrder.externalUserId,
    ];

    let notifyNewEnd: Date | null = null;

    try {
      await db.runTransaction(async (transaction) => {
        notifyNewEnd = null;
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
          throw new Error("User not found for payment order id");
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
          orderId: payload.order_id,
          planKey: parsedOrder.planKey,
          processedAt: FieldValue.serverTimestamp(),
        });
        notifyNewEnd = newEnd;
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      res.status(500).send(message);
      return;
    }

    if (notifyNewEnd !== null) {
      void notifyPurchase(
        parsedOrder.provider,
        parsedOrder.externalUserId,
        parsedOrder.planKey,
        notifyNewEnd
      );
    }

    res.status(200).send("OK");
  }
);
