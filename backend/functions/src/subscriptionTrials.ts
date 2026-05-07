import {
  Timestamp,
  type DocumentData,
  type Transaction,
} from "firebase-admin/firestore";

export const TRIAL_DAYS = 1;

export type TrialProvider = "tg" | "apple" | "vk";

export const TRIAL_FLAG_FIELDS: Record<TrialProvider, string> = {
  tg: "isTelegramTrialActivated",
  apple: "isAppleTrialActivated",
  vk: "isVkTrialActivated",
};

const MS_PER_DAY = 24 * 60 * 60 * 1000;

/**
 * Initial subscription fields for newly-created user documents.
 * @return {Record<string, unknown>} Default user subscription fields.
 */
export function initialTrialFields(): Record<string, unknown> {
  return {
    subscriptionEndsAt: null,
    isTelegramTrialActivated: false,
    isAppleTrialActivated: false,
    isVkTrialActivated: false,
  };
}

/**
 * Missing defaults for existing user documents.
 * @param {DocumentData} data Existing Firestore data.
 * @return {Record<string, unknown>} Defaults for fields that are absent.
 */
export function missingTrialDefaults(
  data: DocumentData
): Record<string, unknown> {
  const payload: Record<string, unknown> = {};
  if (data.subscriptionEndsAt === undefined) {
    payload.subscriptionEndsAt = null;
  }
  for (const field of Object.values(TRIAL_FLAG_FIELDS)) {
    if (data[field] === undefined) {
      payload[field] = false;
    }
  }

  return payload;
}

/**
 * Converts a stored Firestore date value into milliseconds.
 * @param {unknown} value Firestore timestamp-like value.
 * @return {number|null} Milliseconds since epoch, if valid.
 */
function timestampMillis(value: unknown): number | null {
  if (value instanceof Timestamp) {
    return value.toMillis();
  }
  if (value instanceof Date) {
    return value.getTime();
  }

  return null;
}

/**
 * Whether the user currently has an active paid/trial window.
 * @param {DocumentData} data User document fields.
 * @return {boolean} True when `subscriptionEndsAt` is in the future.
 */
export function hasActiveSubscription(data: DocumentData): boolean {
  const end = timestampMillis(data.subscriptionEndsAt);
  if (end === null) {
    return false;
  }
  return end > Date.now();
}

/**
 * Creates the payload for activating eligible provider trials.
 * @param {DocumentData} data Existing Firestore user data.
 * @param {TrialProvider[]} providers Connected providers to activate.
 * @return {{payload: Record<string, unknown>, activatedProviders: string[]}}
 *     Firestore update payload and activated provider ids.
 */
export function buildTrialActivationPayload(
  data: DocumentData,
  providers: TrialProvider[]
): {
  payload: Record<string, unknown>;
  activatedProviders: TrialProvider[];
} {
  const activatedProviders = providers.filter((provider) => {
    const flag = TRIAL_FLAG_FIELDS[provider];
    return data[flag] !== true;
  });

  const payload = missingTrialDefaults(data);
  if (activatedProviders.length === 0) {
    return {payload, activatedProviders};
  }

  const now = Date.now();
  const currentEnd = timestampMillis(data.subscriptionEndsAt);
  const base = currentEnd && currentEnd > now ? currentEnd : now;
  const extraMs = activatedProviders.length * TRIAL_DAYS * MS_PER_DAY;

  payload.subscriptionEndsAt = Timestamp.fromMillis(base + extraMs);
  for (const provider of activatedProviders) {
    payload[TRIAL_FLAG_FIELDS[provider]] = true;
  }

  return {payload, activatedProviders};
}

/**
 * Returns providers that are currently connected on a user record.
 * @param {DocumentData} data Existing Firestore user data.
 * @return {TrialProvider[]} Connected trial providers.
 */
export function connectedTrialProviders(data: DocumentData): TrialProvider[] {
  const providers: TrialProvider[] = [];
  if (data.externalTg) {
    providers.push("tg");
  }
  if (data.externalAppleId) {
    providers.push("apple");
  }
  if (data.externalVk) {
    providers.push("vk");
  }

  return providers;
}

/**
 * Remaining subscription window in ms after `now`
 *  or 0 if none / already ended.
 * @param {number|null} endMs subscriptionEndsAt in ms, or null.
 * @param {number} now Reference time (merge instant), ms since epoch.
 * @return {number} Non-negative remaining ms.
 */
function remainingSubscriptionMs(endMs: number | null, now: number): number {
  if (endMs === null) {
    return 0;
  }
  return Math.max(0, endMs - now);
}

/**
 * Merges subscription/trial fields when two user documents are linked.
 * Sets subscription end to today (merge time) plus the sum of each account's
 * remaining subscription duration, so combined paid time is preserved.
 * @param {DocumentData} destinationData Destination user data.
 * @param {DocumentData} sourceData Source user data.
 * @return {Record<string, unknown>} Merged trial fields without activation.
 */
export function mergeTrialFields(
  destinationData: DocumentData,
  sourceData: DocumentData
): Record<string, unknown> {
  const now = Date.now();
  const destinationEnd = timestampMillis(destinationData.subscriptionEndsAt);
  const sourceEnd = timestampMillis(sourceData.subscriptionEndsAt);
  const payload: Record<string, unknown> = {};
  const totalRemaining =
    remainingSubscriptionMs(destinationEnd, now) +
    remainingSubscriptionMs(sourceEnd, now);

  payload.subscriptionEndsAt =
    totalRemaining > 0 ? Timestamp.fromMillis(now + totalRemaining) : null;
  for (const field of Object.values(TRIAL_FLAG_FIELDS)) {
    payload[field] = destinationData[field] === true ||
      sourceData[field] === true;
  }

  return payload;
}

/**
 * Activates all eligible connected provider trials in a transaction.
 * @param {Transaction} transaction Firestore transaction.
 * @param {DocumentData} data Existing user data.
 * @return {{payload: Record<string, unknown>, activatedProviders: string[]}}
 *     Payload and providers activated by this request.
 */
export function activateConnectedTrials(
  transaction: Transaction,
  data: DocumentData
): {
  payload: Record<string, unknown>;
  activatedProviders: TrialProvider[];
} {
  const result = buildTrialActivationPayload(
    data,
    connectedTrialProviders(data)
  );
  void transaction;
  return result;
}
