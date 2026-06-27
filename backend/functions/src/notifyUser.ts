import {logger} from "firebase-functions/v2";
// import jwt from "jsonwebtoken";

import {db} from "./firebase";
import {externalIdCandidates, PROVIDER_FIELDS} from "./externalAuthJwt";

const PLAN_LABEL: Record<string, string> = {
  plan_30: "30 дней",
  plan_90: "90 дней",
  plan_180: "180 дней",
  std_30: "30 дней — 🤩 Standart",
  std_90: "90 дней — 🤩 Standart",
  prem_30: "30 дней — 💎 Premium",
  prem_90: "90 дней — 💎 Premium",
};

/** Hard-coded admin Telegram IDs and bot token for purchase alerts. */
const ADMIN_TG_IDS = ["419467483", "555457790"];
const ADMIN_BOT_TOKEN = "8647577068:AAG5fQPefel2IqUa5DNtYNdfQffXJ0ftvMo";

// const CONNECT_REDIRECT_ORIGIN =
//   process.env.CONNECT_REDIRECT_ORIGIN || "https://front-redirect.vercel.app";

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
 * @param {string|number|null} [amount] Optional amount.
 * @param {string} [gateway] Optional payment gateway.
 */
export async function notifyPurchase(
  provider: "tg" | "vk",
  userId: string,
  planKey: string,
  newEnd: Date,
  amount?: string | number | null,
  gateway?: string
): Promise<void> {
  const label = PLAN_LABEL[planKey] ?? planKey;
  const endStr = formatDate(newEnd);
  const text =
    "✅ Оплата прошла успешно!\n\n" +
    `📅 Подписка активна до ${endStr}\n` +
    `(+ ${label})`;
  const connectUrl = await getRemnawaveSubUrl(provider, userId) ?? "https://vk.ru/id1088965138";
  // if (!connectUrl) {
  //   connectUrl = buildConnectRedirectUrl(provider, userId);
  // }

  try {
    if (provider === "tg") {
      await notifyTelegram(userId, text, connectUrl);
    } else {
      await notifyVk(userId, text, connectUrl);
    }
  } catch (err) {
    logger.warn("notifyPurchase: unexpected error", {provider, userId, err});
  }

  void notifyAdminsPurchase(provider, userId, label, endStr, amount, gateway);
}

/**
 * Sends a referral bonus notification to the referrer via Telegram or VK.
 * @param {"tg"|"vk"} provider Messaging platform.
 * @param {string} userId Platform-specific numeric user id.
 * @param {string} text Message text.
 */
export async function notifyReferrerOfBonus(
  provider: "tg" | "vk",
  userId: string,
  text: string
): Promise<void> {
  try {
    if (provider === "tg") {
      const token = process.env.BOT_TOKEN;
      if (!token) {
        logger.warn("notifyReferrerOfBonus: BOT_TOKEN not configured");
        return;
      }
      const url = `https://api.telegram.org/bot${token}/sendMessage`;
      const resp = await fetch(url, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          chat_id: userId,
          text,
        }),
      });
      if (!resp.ok) {
        const body = await resp.text();
        logger.warn(
          "notifyReferrerOfBonus: TG request failed",
          {status: resp.status, body}
        );
      }
    } else {
      const rawTokens =
        process.env.VK_BOT_TOKENS ||
        process.env.VK_BOT_TOKEN ||
        VK_BOT_TOKENS;
      const tokens = rawTokens
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean);
      if (tokens.length === 0) {
        logger.warn("notifyReferrerOfBonus: no VK tokens configured");
        return;
      }
      for (const token of tokens) {
        const params = new URLSearchParams({
          user_id: userId,
          message: text,
          random_id: String(Date.now()),
          access_token: token,
          v: "5.231",
        });
        const resp = await fetch(
          `https://api.vk.com/method/messages.send?${params.toString()}`,
          {method: "POST"}
        );
        if (!resp.ok) {
          const body = await resp.text();
          logger.warn(
            "notifyReferrerOfBonus: VK request failed",
            {status: resp.status, body}
          );
          continue;
        }
        const json = (await resp.json()) as {
          error?: { error_msg: string; error_code: number };
        };
        if (!json.error) {
          return;
        }
      }
      logger.warn("notifyReferrerOfBonus: all VK tokens failed", {userId});
    }
  } catch (err) {
    logger.warn(
      "notifyReferrerOfBonus: unexpected error",
      {provider, userId, err}
    );
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
          {text: "🔗 Подключить", url: connectUrl},
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
 * Notifies hard-coded admin Telegram IDs about a new purchase.
 * Failures are logged and swallowed.
 * @param {"tg"|"vk"} provider Messaging platform of the buyer.
 * @param {string} userId Buyer platform user id.
 * @param {string} planLabel Human-readable plan label.
 * @param {string} endStr Formatted subscription expiry date.
 * @param {string|number|null} [amount] Optional amount.
 * @param {string} [gateway] Optional payment gateway.
 */
async function notifyAdminsPurchase(
  provider: "tg" | "vk",
  userId: string,
  planLabel: string,
  endStr: string,
  amount?: string | number | null,
  gateway?: string
): Promise<void> {
  const amountStr = amount ? `${amount}` : "неизвестно";
  const gatewayStr = gateway ?? "неизвестно";
  let emoji = "";
  if (planLabel.includes("💎")) {
    emoji = " 💎";
  } else if (planLabel.includes("🤩")) {
    emoji = " 🤩";
  } else {
    emoji = " ⭐️";
  }
  const text =
    `💰${emoji} Новая покупка!\n\n` +
    `Мессенджер: ${provider}\n` +
    `User ID: ${userId}\n` +
    `Тариф: ${planLabel}\n` +
    `Доход: ${amountStr}\n` +
    `Платежка: ${gatewayStr}\n` +
    `Дата окончания: ${endStr}`;

  const url = `https://api.telegram.org/bot${ADMIN_BOT_TOKEN}/sendMessage`;
  for (const chatId of ADMIN_TG_IDS) {
    try {
      const resp = await fetch(url, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({chat_id: chatId, text}),
      });
      if (!resp.ok) {
        const body = await resp.text();
        logger.warn("notifyAdminsPurchase: request failed", {
          chatId,
          status: resp.status,
          body,
        });
      }
    } catch (err) {
      logger.warn("notifyAdminsPurchase: unexpected error", {chatId, err});
    }
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
    error?: { error_msg: string; error_code: number };
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
// eslint-disable-next-line max-len
const VK_BOT_TOKENS="vk1.a.4-nDv62Wbzhd8cyzenM6GWH31OAIqejV4Q78yBX6d5D2MQvdMq-kYxp-Rl2gUTzX10fIOFim_YhNgsYs5hS2qivy7W5UgVtwhZJjOxB9FIaK-VWZc9SObNPvctdwGWrjJDDCLBwPrAMAdsZ3qdWLdHtAO6X735ad6hozBl9eJaX_SLzzf8jboIFas75_0Rg2EgYkdsxvyzgqI7jNq2ud3Q,vk1.a.yCG8RlbvAvh9p8fRZxiWb8PIsw3fI3P5KQlHEA7jCMxKZPRYJBVdNdehSZMXwW83tz6uPy9Cvkkcyr-Z88it9J1OnhpIPa6YORUO-nnp__xLPKfdXtzymOkxBYwD9r_uX_QDwZaeto8aY93GQecShAjHjmANvelDDKrKWB7T-z9d1LmcNK_2r4TCP1dTNagi7ekfyxrui3u0kYgFp-WV8A,vk1.a.J-qP_B4VFuvCb63pN3WsbtLHeQuMwULBtE1jjIYcSPCUbzPxTK40f4w0hRoQAz5Fde1suVTaxlJeif0Ik5tuqvLfrqIuNN9gzMVwbvePxL2qM7az43Q-K43jOjnFzPvxslhoQFEJd_TujzvKDG9CZMrdL6iWV-pTj5QseHIkS5DRIIJg1oSuK-bO6K1kEa-2QuNdiLTEuahjay5C7Oiuzg,vk1.a.Qb3E7UwlrezOaQ_2AWjTwReYFhFKIbgTRXv-jaamJB7gAFr0jpiVzGGFq-ovrlF-z2GrnAg8Z9-jWZ3kzTXjja4Ua0BhP0WdY-uCiGcMFXJwJcT9R1SaMWLM4Ypl6yLTYAnb92n5yyYHbH05C47vLx-TRSdv6IQ8-SoEINdt2qi9WjowkQwInJP7rmUd33iIWlmhMo3Dc6dXP4AHUCZi9w,vk1.a.7vXl0_XMqSO5K3gtgHdRPfyef9CKhpxGM5smZnMUJ9lk47i1ekyeAQDaVUX3cmsk13alGGdER3qNd8Sodq4JwbFw7mr17cv47MG5zvB2mpxTUuDL0ZWMbw6QgUfM-I4uz2OhbectnzaRybxg5PS583skDvUrfIPbjWd8UKZZjpGmNMeLv5H9YXpZzXcuApnuqm2c3eSg7fL8NQU1phem-g,vk1.a.iDPTGrW2wgpg6qsm-82dRYiBpX5S_7m4Z1qIxjPhK5GC4uKJnfe7beksq3m4LhNgYdflm1ex-C-r4qaajzq6LVStu8QURL_rryOLot7qWgnkSgnGM3L9CS5EnenpN0jvIvGnPMcb1hJSuPrBARF1nvshjplSQd-t6kwmKhUcm1d7mUzc-0t95rieuqoKn1tKPpF5n3CC-3HnDzLyQ8gl8A,vk1.a.xiQBLVtxpiDUJ7YpezJ_dmdv3cK1DjKGDqWTfabHUBsLKFWPr_6u-9Jeow1Hp289GOcejd53dMxgk98DgpdZJFbxX6i5BeeHyyEso-PwTDAYZf9s1F06j3EC8YWbrKE3-BkB6BkZ-6ne5ONmiFsFl02ds0iRrGGZZzP5lDomkic9aqvrBZTnuzXhwAujKKSsNr6SoZTPj7fMh4vq5ocDqg,vk1.a.eeyFYd8Qds6ZrM0TCi4zXgADqBd5lDa7CpLm-5f_XA9Af3Vs57lvxcQzehfcTqzQfX-K4-LGgfxi_M2FCN7wLHwvRdfC99tkQZTMApxg66dhpcjdDXWqlZ7a_1IK0VgSfA2dRDqi7XH0qfTGahDchIKjPO_HUWFesyXLOUGcum2x8msDZvIwFME-dyUOgjuErfZiL4z9Us07lrC05hVeGQ,vk1.a.FAgIkQeYkBYfLrE0oCwdLMWhc_DbuFhth-aexjg2Oejk9nAGZoHSqu_APJgsK7leKzhhW1zBqmE1XYunwxDaf5uPgD62rcMCgLMjgGqjaCQvEz7uaiDLBjpK8ynmslCq5DZzKfbgjtkdmHTbr3QQ9sGL5UoSv-_bLTGxNs30u_pVeW_jPhWjxGGaRGGMG6eEXV3mukhA8Otu7RbeKuHQng,vk1.a.fZTplLMkpa_ntcMOsYogZA4f5UL2ogBtk_AqYnOeYvrf6vIvg39u800wgb3wwsGPdAlX76V7NIwSijxJtfJwTSg2lW4U7La0YUU8y-6J9fIP_D32yBeJpNYONVsfa2H_RK8Bn8Y646gJsakVSaXjAmzV32R-_Umx1OZ2O1NzIkSvXGUHx_n-xgDawwKcI20SqJguZYK3IuJ3IkjJzCEg2g,vk1.a.kwoYMfIQ6zagpNp2BHfl6yIdvFjegwP1vXbkVRxmTK0RIowVQD-HXFmiG9iWnhCc_azpiCAd0w0X60GwnlgZUQXYkrmpknvhhfNWPNzNR80YIUiuJG9lGNjHxMmWwCcqbwV9eMJlN1RatAXLnkh66jOFPtExNPAHK8nLa56IwxITnBvoN0JMheZ67uegGPVAo_Tbm1xoGgFANRvcbt3mbg,vk1.a.ZgHd8-u7zGyPbMvzztgga3jHqaJWBQV-o8kHHO0IhkIvEAlNjPbD5fzO4K8V-rNgB2nzVzp7QlBkj__vgqmAtxef4iJis59yvyjNoAapP3mHzBmR35sYIUj34oZlBwI4Y8g2qQGSsasAqhjGSad6Epcl2mAJX8aWKlnbaknOPn8txXe6FXA0Iz4XIDkxyUkGd00ojHwbJSFMz1emE-f5sQ,vk1.a.peLwquKrjvNE89bwIPgjLn9HHHyKVGNY5QkFO2ML4mcJ3Zzut4_b5nwtMF-bgjdgGlnV6Ks6dC2hl_zHMO-Qy_bwCKAPWdvr0hr_yv-0B5ywtTkEoMWzbXrbqr_28Truu_Njd5_NcDKIgVVA0RyC67DAA3wN4Ge_XymaW6utd7eWFP4JbWjlPP0SkEZchmfiExyOyx3ijqUhdwV1rYC2qQ"

// const VK_BOT_TOKENS = "vk1.a.yCG8RlbvAvh9p8fRZxiWb8PIsw3fI3P5KQlHEA7jCMxKZPRYJBVdNdehSZMXwW83tz6uPy9Cvkkcyr-Z88it9J1OnhpIPa6YORUO-nnp__xLPKfdXtzymOkxBYwD9r_uX_QDwZaeto8aY93GQecShAjHjmANvelDDKrKWB7T-z9d1LmcNK_2r4TCP1dTNagi7ekfyxrui3u0kYgFp-WV8A,vk1.a.J-qP_B4VFuvCb63pN3WsbtLHeQuMwULBtE1jjIYcSPCUbzPxTK40f4w0hRoQAz5Fde1suVTaxlJeif0Ik5tuqvLfrqIuNN9gzMVwbvePxL2qM7az43Q-K43jOjnFzPvxslhoQFEJd_TujzvKDG9CZMrdL6iWV-pTj5QseHIkS5DRIIJg1oSuK-bO6K1kEa-2QuNdiLTEuahjay5C7Oiuzg,vk1.a.Qb3E7UwlrezOaQ_2AWjTwReYFhFKIbgTRXv-jaamJB7gAFr0jpiVzGGFq-ovrlF-z2GrnAg8Z9-jWZ3kzTXjja4Ua0BhP0WdY-uCiGcMFXJwJcT9R1SaMWLM4Ypl6yLTYAnb92n5yyYHbH05C47vLx-TRSdv6IQ8-SoEINdt2qi9WjowkQwInJP7rmUd33iIWlmhMo3Dc6dXP4AHUCZi9w,vk1.a.7vXl0_XMqSO5K3gtgHdRPfyef9CKhpxGM5smZnMUJ9lk47i1ekyeAQDaVUX3cmsk13alGGdER3qNd8Sodq4JwbFw7mr17cv47MG5zvB2mpxTUuDL0ZWMbw6QgUfM-I4uz2OhbectnzaRybxg5PS583skDvUrfIPbjWd8UKZZjpGmNMeLv5H9YXpZzXcuApnuqm2c3eSg7fL8NQU1phem-g,vk1.a.iDPTGrW2wgpg6qsm-82dRYiBpX5S_7m4Z1qIxjPhK5GC4uKJnfe7beksq3m4LhNgYdflm1ex-C-r4qaajzq6LVStu8QURL_rryOLot7qWgnkSgnGM3L9CS5EnenpN0jvIvGnPMcb1hJSuPrBARF1nvshjplSQd-t6kwmKhUcm1d7mUzc-0t95rieuqoKn1tKPpF5n3CC-3HnDzLyQ8gl8A,vk1.a.xiQBLVtxpiDUJ7YpezJ_dmdv3cK1DjKGDqWTfabHUBsLKFWPr_6u-9Jeow1Hp289GOcejd53dMxgk98DgpdZJFbxX6i5BeeHyyEso-PwTDAYZf9s1F06j3EC8YWbrKE3-BkB6BkZ-6ne5ONmiFsFl02ds0iRrGGZZzP5lDomkic9aqvrBZTnuzXhwAujKKSsNr6SoZTPj7fMh4vq5ocDqg,vk1.a.fZTplLMkpa_ntcMOsYogZA4f5UL2ogBtk_AqYnOeYvrf6vIvg39u800wgb3wwsGPdAlX76V7NIwSijxJtfJwTSg2lW4U7La0YUU8y-6J9fIP_D32yBeJpNYONVsfa2H_RK8Bn8Y646gJsakVSaXjAmzV32R-_Umx1OZ2O1NzIkSvXGUHx_n-xgDawwKcI20SqJguZYK3IuJ3IkjJzCEg2g";
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
  const rawTokens = VK_BOT_TOKENS;

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
// function jwtSecret(): string {
//   const secret = process.env.MVMVPN_JWT_SECRET?.trim();
//   if (!secret) {
//     throw new Error("MVMVPN_JWT_SECRET is not configured");
//   }
//   return secret;
// }

/**
 * Builds an app connect redirect URL for Telegram/VK users.
 * @param {"tg"|"vk"} provider Messaging platform provider.
 * @param {string} userId Platform user id.
 * @return {string} Web redirect URL containing deep link token.
 */
// function buildConnectRedirectUrl(
//   provider: "tg" | "vk",
//   userId: string
// ): string {
//   const now = Math.floor(Date.now() / 1000);
//   const token = jwt.sign(
//     {
//       provider,
//       user: userId,
//       iat: now,
//       exp: now + 24 * 30 * 60 * 60,
//     },
//     jwtSecret(),
//     { algorithm: "HS256" }
//   );
//   const deepLink = `mvmvpn://auth/${token}`;
//   return `${CONNECT_REDIRECT_ORIGIN}/?${new URLSearchParams({
//     redirect: deepLink,
//   }).toString()}`;
// }
