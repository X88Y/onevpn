import {logger} from "firebase-functions/v2";
import jwt from "jsonwebtoken";

import {db} from "./firebase";
import {externalIdCandidates, PROVIDER_FIELDS} from "./externalAuthJwt";

const PLAN_LABEL: Record<string, string> = {
  plan_30: "30 дней",
  plan_90: "90 дней",
  plan_180: "180 дней",
};

const CONNECT_REDIRECT_ORIGIN =
  process.env.CONNECT_REDIRECT_ORIGIN || "https://front-redirect.vercel.app";

/**
 * Formats a UTC Date as DD.MM.YYYY in the Russian locale.
 * @param {Date} d The date to format.
 * @return {string} Formatted date string.
 */
function formatDate(d: Date): string {
  return d.toLocaleDateString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    timeZone: "UTC",
  });
}

/**
 * Looks up the user's raw Remnawave subscription URL.
 * @param {"tg"|"vk"} provider Messaging platform.
 * @param {string} userId Platform-specific numeric user id.
 * @return {Promise<string|null>} Subscription URL when found.
 */
async function getRemnawaveSubUrl(
  provider: "tg" | "vk",
  userId: string
): Promise<string | null> {
  const field = PROVIDER_FIELDS[provider];
  const candidates = externalIdCandidates(provider, userId);
  const snap = await db.collection("users")
    .where(field, "in", candidates)
    .limit(1)
    .get();
  if (snap.empty) {
    return null;
  }
  const data = snap.docs[0].data();
  const url = data.remnawaveSubscriptionUrl;
  return typeof url === "string" && url ? url : null;
}

/**
 * Sends a purchase success notification to the user via Telegram or VK.
 * Failures are logged but never throw — the subscription is already saved.
 * @param {"tg"|"vk"} provider Messaging platform.
 * @param {string} userId Platform-specific numeric user id.
 * @param {string} planKey Plan key, e.g. "plan_30".
 * @param {Date} newEnd New subscription expiry date.
 */
export async function notifyPurchase(
  provider: "tg" | "vk",
  userId: string,
  planKey: string,
  newEnd: Date
): Promise<void> {
  const label = PLAN_LABEL[planKey] ?? planKey;
  const endStr = formatDate(newEnd);
  const text =
    "✅ Оплата прошла успешно!\n\n" +
    `📅 Подписка активна до ${endStr}\n` +
    `(+${label})`;
  let connectUrl = await getRemnawaveSubUrl(provider, userId);
  if (!connectUrl) {
    connectUrl = buildConnectRedirectUrl(provider, userId);
  }

  try {
    if (provider === "tg") {
      await notifyTelegram(userId, text, connectUrl);
    } else {
      await notifyVk(userId, text, connectUrl);
    }
  } catch (err) {
    logger.warn("notifyPurchase: unexpected error", {provider, userId, err});
  }
}

/**
 * Sends a plain-text Telegram message to a single chat id.
 * @param {string} userId Telegram chat/user id.
 * @param {string} text Message body.
 * @param {string} connectUrl Deep link redirect URL for account login.
 * @return {Promise<void>} Resolves after the API call attempt.
 */
async function notifyTelegram(
  userId: string,
  text: string,
  connectUrl: string
): Promise<void> {
  const token = process.env.BOT_TOKEN;
  if (!token) {
    logger.warn("notifyTelegram: BOT_TOKEN not configured");
    return;
  }
  const url = `https://api.telegram.org/bot${token}/sendMessage`;
  const resp = await fetch(url, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      chat_id: userId,
      text,
      reply_markup: {
        inline_keyboard: [[
          {text: "🔗 Подключить", url: connectUrl, style: "success"},
        ]],
      },
    }),
  });
  if (!resp.ok) {
    const body = await resp.text();
    logger.warn("notifyTelegram: request failed", {status: resp.status, body});
  }
}

/**
 * Builds VK inline keyboard JSON with a connect link.
 * @param {string} connectUrl Deep link redirect URL.
 * @return {string} JSON keyboard payload.
 */
function buildVkKeyboard(connectUrl: string): string {
  return JSON.stringify({
    inline: true,
    buttons: [
      [
        {
          action: {
            type: "open_link",
            link: connectUrl,
            label: "🔗 Подключить",
          },
        },
      ],
    ],
  });
}

/**
 * Attempts to send a VK message using a single token.
 * @param {string} userId VK user id.
 * @param {string} text Message body.
 * @param {string} keyboard Keyboard JSON string.
 * @param {string} token VK bot token.
 * @return {Promise<boolean>} True when the API reports success.
 */
async function sendVkMessageWithToken(
  userId: string,
  text: string,
  keyboard: string,
  token: string
): Promise<boolean> {
  const params = new URLSearchParams({
    user_id: userId,
    message: text,
    random_id: String(Date.now()),
    keyboard,
    access_token: token,
    v: "5.231",
  });
  const resp = await fetch(
    `https://api.vk.com/method/messages.send?${params.toString()}`,
    {method: "POST"}
  );
  if (!resp.ok) {
    const body = await resp.text();
    logger.warn("notifyVk: request failed", {status: resp.status, body});
    return false;
  }
  const json = (await resp.json()) as {
    error?: {error_msg: string; error_code: number};
  };
  if (json.error) {
    logger.warn("notifyVk: API error", {
      error: json.error,
      tokenPrefix: token.slice(0, 8),
    });
    return false;
  }
  return true;
}

/**
 * Sends a plain-text VK message to a single user id.
 * Tries all configured VK bot tokens (multi-bot support) and stops at the
 * first successful delivery.
 * @param {string} userId VK user id.
 * @param {string} text Message body.
 * @param {string} connectUrl Deep link redirect URL for account login.
 * @return {Promise<void>} Resolves after the API call attempt.
 */
async function notifyVk(
  userId: string,
  text: string,
  connectUrl: string
): Promise<void> {
  const rawTokens =
    process.env.VK_BOT_TOKENS || process.env.VK_BOT_TOKEN || "";
  const tokens = rawTokens
    .split(",")
    .map((t) => t.trim())
    .filter(Boolean);

  if (tokens.length === 0) {
    logger.warn("notifyVk: no VK tokens configured");
    return;
  }

  const keyboard = buildVkKeyboard(connectUrl);
  for (const token of tokens) {
    const ok = await sendVkMessageWithToken(userId, text, keyboard, token);
    if (ok) {
      return;
    }
  }
  logger.warn("notifyVk: all tokens failed", {userId});
}

/**
 * Reads the shared HS256 secret for auth deep links.
 * @return {string} Configured JWT secret.
 */
function jwtSecret(): string {
  const secret = process.env.MVMVPN_JWT_SECRET?.trim();
  if (!secret) {
    throw new Error("MVMVPN_JWT_SECRET is not configured");
  }
  return secret;
}

/**
 * Builds an app connect redirect URL for Telegram/VK users.
 * @param {"tg"|"vk"} provider Messaging platform provider.
 * @param {string} userId Platform user id.
 * @return {string} Web redirect URL containing deep link token.
 */
function buildConnectRedirectUrl(
  provider: "tg" | "vk",
  userId: string
): string {
  const now = Math.floor(Date.now() / 1000);
  const token = jwt.sign(
    {
      provider,
      user: userId,
      iat: now,
      exp: now + 24 * 30 * 60 * 60,
    },
    jwtSecret(),
    {algorithm: "HS256"}
  );
  const deepLink = `mvmvpn://auth/${token}`;
  return `${CONNECT_REDIRECT_ORIGIN}/?${new URLSearchParams({
    redirect: deepLink,
  }).toString()}`;
}
