import jwt, {type JwtPayload} from "jsonwebtoken";

export const PROVIDER_FIELDS = {
  tg: "externalTg",
  vk: "externalVk",
} as const;

export type ExternalAuthProvider = keyof typeof PROVIDER_FIELDS;

/**
 * Returns the shared secret used by bot-issued auth JWTs.
 * @return {string} Configured HS256 secret.
 */
function jwtSecret(): string {
  const secret = process.env.MVMVPN_JWT_SECRET?.trim();
  if (!secret) {
    throw new Error("MVMVPN_JWT_SECRET is not configured");
  }

  return secret;
}

/**
 * Reads an auth JWT from the JSON request body.
 * @param {unknown} body Parsed request body.
 * @return {string|null} Auth JWT when present.
 */
export function requestToken(body: unknown): string | null {
  if (!body || typeof body !== "object") {
    return null;
  }

  const payload = body as Record<string, unknown>;
  const token = payload.token ?? payload.jwt;
  if (typeof token !== "string") {
    return null;
  }

  const trimmed = token.trim();
  return trimmed || null;
}

/**
 * Reads an auth JWT from a query string value.
 * @param {unknown} value Query string value.
 * @return {string|null} Auth JWT when present.
 */
export function queryToken(value: unknown): string | null {
  if (typeof value === "string") {
    const trimmed = value.trim();
    return trimmed || null;
  }

  return null;
}

/**
 * Checks if an unknown value is a supported external provider.
 * @param {unknown} value Value to validate.
 * @return {boolean} True when the provider can be authenticated.
 */
function isExternalAuthProvider(
  value: unknown
): value is ExternalAuthProvider {
  return value === "tg" || value === "vk";
}

/**
 * Verifies and validates the bot-issued auth JWT.
 * @param {string} token HS256 JWT from the external provider auth flow.
 * @return {{provider: ExternalAuthProvider, externalUserId: string}} Target.
 */
export function decodeExternalAuthJwt(token: string): {
  provider: ExternalAuthProvider;
  externalUserId: string;
} {
  const decoded = jwt.verify(token, jwtSecret(), {
    algorithms: ["HS256"],
  });
  if (!decoded || typeof decoded !== "object") {
    throw new Error("Invalid JWT payload");
  }

  const payload = decoded as JwtPayload;
  if (!isExternalAuthProvider(payload.provider)) {
    throw new Error("Invalid JWT provider");
  }

  const externalUserId =
    typeof payload.user === "number" ? String(payload.user) : payload.user;
  if (typeof externalUserId !== "string" || !externalUserId.trim()) {
    throw new Error("Invalid JWT user");
  }

  return {
    provider: payload.provider,
    externalUserId: externalUserId.trim(),
  };
}

/**
 * Builds lookup values for current and previously-prefixed external IDs.
 * @param {ExternalAuthProvider} provider External provider.
 * @param {string} externalUserId Raw external provider user ID.
 * @return {string[]} Firestore lookup candidates.
 */
export function externalIdCandidates(
  provider: ExternalAuthProvider,
  externalUserId: string
): string[] {
  const prefixed = `${provider}:${externalUserId}`;
  if (externalUserId.startsWith(`${provider}:`)) {
    return [externalUserId];
  }

  return [externalUserId, prefixed];
}
