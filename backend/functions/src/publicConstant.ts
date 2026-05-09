import {onRequest} from "firebase-functions/v2/https";

/** Fixed payload returned by the public constant endpoint. */
export const PUBLIC_CONSTANT = {
  ok: true,
  vk: "https://m.vk.com/write-199074445",
  tg: "https://t.me/mvmvpnbot",
} as const;

/** HTTP GET handler that returns a static JSON body. */
export const publicConstant = onRequest(
  {cors: true, maxInstances: 10},
  (_req, res) => {
    res.status(200).json(PUBLIC_CONSTANT);
  }
);
