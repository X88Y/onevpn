import * as crypto from "crypto";

import type {DocumentData} from "firebase-admin/firestore";
import {FieldValue, Timestamp} from "firebase-admin/firestore";
import {onRequest} from "firebase-functions/v2/https";

import {db} from "./firebase";
import {notifyPurchase} from "./notifyUser";
import {defineSecret} from "firebase-functions/params";

/**
 * Days to extend subscription per plan key.
 */
const PLAN_DAYS: Record<string, number> = {
  plan_30: 30,
  plan_90: 90,
  plan_180: 180,
};

/**
 * FreeKassa server IPs allowed to send payment notifications.
 * https://docs.freekassa.net/#section/1.-Vvedenie/1.4.-Opoveshenie-o-platezhe
 */
const ALLOWED_IPS = new Set([
  "168.119.157.136",
  "168.119.60.227",
  "178.154.197.79",
  "51.250.54.238",
]);

// Order ID formats:
// 1) mvm:{provider}:{userId}:{planKey}:{nonce}
// 2) mvm_{provider}_{userId}_{planKey}_{nonce}
const ORDER_ID_RE =
  /^mvm(?::|_)(tg|vk)(?::|_)(\d+)(?::|_)(plan_\w+)(?::|_)\d+$/;
// Legacy format (Telegram-only, no provider prefix):
// mvm:{tgId}:{planKey}:{nonce} OR mvm_{tgId}_{planKey}_{nonce}
const ORDER_ID_RE_LEGACY =
  /^mvm(?::|_)(\d+)(?::|_)(plan_\w+)(?::|_)\d+$/;

type ParsedOrderId = {
  provider: "tg" | "vk";
  externalUserId: string;
  planKey: string;
};

/**
 * Parses MERCHANT_ORDER_ID into provider, user id and plan key.
 * Supports both the current ``mvm:{tg|vk}:{id}:{plan}:{nonce}`` format
 * and the legacy Telegram-only ``mvm:{id}:{plan}:{nonce}`` format.
 * @param {unknown} orderId Raw MERCHANT_ORDER_ID value from the notification.
 * @return {ParsedOrderId | null} Parsed fields or null if malformed.
 */
function parseOrderId(orderId: unknown): ParsedOrderId | null {
  if (typeof orderId !== "string") return null;
  const trimmed = orderId.trim();
  const tagged = ORDER_ID_RE.exec(trimmed);
  if (tagged) {
    return {
      provider: tagged[1] as "tg" | "vk",
      externalUserId: tagged[2],
      planKey: tagged[3],
    };
  }
  const legacy = ORDER_ID_RE_LEGACY.exec(trimmed);
  if (legacy) {
    return {provider: "tg", externalUserId: legacy[1], planKey: legacy[2]};
  }
  return null;
}

/**
 * Verifies the FreeKassa notification signature (Section 1.7).
 *
 * Expected:
 * MD5(MERCHANT_ID + ":" + AMOUNT + ":" + secretWord2 + ":" + MERCHANT_ORDER_ID)
 *
 * @param {string} merchantId MERCHANT_ID from notification body.
 * @param {string} amount AMOUNT from notification body.
 * @param {string} secretWord2 Secret word 2 from FreeKassa settings.
 * @param {string} merchantOrderId MERCHANT_ORDER_ID from notification body.
 * @param {string} sign SIGN from notification body.
 * @return {boolean} True when the signature is valid.
 */
function verifySign(
  merchantId: string,
  amount: string,
  secretWord2: string,
  merchantOrderId: string,
  sign: string
): boolean {
  const expected = crypto
    .createHash("md5")
    .update(`${merchantId}:${amount}:${secretWord2}:${merchantOrderId}`)
    .digest("hex");
  try {
    const a = Buffer.from(expected, "utf8");
    const b = Buffer.from(sign.toLowerCase(), "utf8");
    return a.length === b.length && crypto.timingSafeEqual(a, b);
  } catch {
    return false;
  }
}

/**
 * Returns the subscription baseline date: max(now, current subscriptionEndsAt).
 * @param {DocumentData} data Current Firestore user document data.
 * @return {Date} UTC instant to extend from.
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
 * Processes FreeKassa SCI payment notifications (Section 1.4).
 *
 * Request body is ``application/x-www-form-urlencoded`` with fields:
 * ``MERCHANT_ID``, ``AMOUNT``, ``intid``, ``MERCHANT_ORDER_ID``, ``SIGN``, etc.
 *
 * Validation steps:
 *  1. IP allowlist check (FreeKassa server IPs).
 *  2. Signature verification:
 *     MD5(MERCHANT_ID:AMOUNT:secretWord2:MERCHANT_ORDER_ID).
 *  3. Parse MERCHANT_ORDER_ID to extract provider / user / plan.
 *
 * Idempotency is guaranteed via ``freekassa_processed/{intid}`` in Firestore.
 * Responds with plain ``YES`` on success as required by FreeKassa.
 */

export const freeKassa = onRequest(
  {
    cors: false,
    maxInstances: 10,
    memory: "256MiB",
    secrets: [defineSecret("FREEKASSA_SECRET_WORD_2")],
  },
  async (req, res) => {
    if (req.method !== "POST" && req.method !== "GET") {
      res.status(405).send("Method Not Allowed");
      return;
    }

    const secretWord2 = process.env.FREEKASSA_SECRET_WORD_2;
    if (!secretWord2) {
      res.status(501).send("FREEKASSA_SECRET_WORD_2 is not configured");
      return;
    }

    // IP allowlist — skip in dev/test via env flag
    if (process.env.FREEKASSA_SKIP_IP_CHECK !== "true") {
      const clientIp = (
        req.header("x-real-ip") ||
        req.header("x-forwarded-for") ||
        req.ip ||
        ""
      )
        .split(",")[0]
        .trim();
      if (!ALLOWED_IPS.has(clientIp)) {
        res.status(403).send("Forbidden");
        return;
      }
    }

    const source = req.method === "GET" ?
      (req.query as Record<string, unknown>) :
      (req.body as Record<string, unknown>);
    if (
      typeof source !== "object" ||
      source === null ||
      Array.isArray(source)
    ) {
      res.status(403).send("Invalid payload");
      return;
    }

    const pick = (key: string): string => {
      const raw = source[key];
      if (Array.isArray(raw)) {
        return String(raw[0] ?? "").trim();
      }
      return String(raw ?? "").trim();
    };

    const merchantId = pick("MERCHANT_ID");
    const amount = pick("AMOUNT");
    const intid = pick("intid");
    const merchantOrderId = pick("MERCHANT_ORDER_ID");
    const sign = pick("SIGN");

    if (!merchantId || !amount || !intid || !merchantOrderId || !sign) {
      res.status(400).send("Missing required fields");
      return;
    }

    if (!verifySign(merchantId, amount, secretWord2, merchantOrderId, sign)) {
      res.status(401).send("Invalid signature");
      return;
    }

    const parsed = parseOrderId(merchantOrderId);
    if (!parsed) {
      res.status(400).send("Invalid MERCHANT_ORDER_ID format");
      return;
    }

    const days = PLAN_DAYS[parsed.planKey];
    if (!days) {
      res.status(400).send("Unknown plan key");
      return;
    }

    const processedRef = db.collection("freekassa_processed").doc(intid);
    const providerField =
      parsed.provider === "tg" ? "externalTg" : "externalVk";
    const prefixedExternalId = `${parsed.provider}:${parsed.externalUserId}`;
    const rawExternalId = parsed.externalUserId;

    let notifyAfter: {newEnd: Date} | null = null;

    try {
      await db.runTransaction(async (transaction) => {
        notifyAfter = null;

        // Idempotency — skip if already processed
        const processedSnap = await transaction.get(processedRef);
        if (processedSnap.exists) return;

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

        transaction.set(
          docRef,
          {
            subscriptionEndsAt: Timestamp.fromDate(newEnd),
            updatedAt: FieldValue.serverTimestamp(),
          },
          {merge: true}
        );
        transaction.set(processedRef, {
          intid,
          merchantOrderId,
          provider: parsed.provider,
          externalUserId: parsed.externalUserId,
          planKey: parsed.planKey,
          amount,
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

    // FreeKassa requires plain "YES" to acknowledge the notification
    res.send("YES");
  }
);
