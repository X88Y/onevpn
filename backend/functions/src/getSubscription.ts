import {onRequest} from "firebase-functions/v2/https";
import {MANAGER_BASE_URL} from "./managerClient";
import {logger} from "firebase-functions";
import {getHappRoutingDeeplink} from "./happRouting";

/**
 * Proxy function to return subscription content from server_manager.
 * This ensures the user only sees a Google Function URL in their client app.
 */
export const getSubscription = onRequest(
  {cors: true, maxInstances: 50, secrets: ["MANAGER_API_KEY"]},
  async (req, res) => {
    // The subId can be passed as a query param or part of the path
    // e.g. /getUserSubscription?id=SUB_ID
    const subId = (req.query.id as string) || req.path.split("/").pop();

    if (!subId || subId === "getUserSubscription") {
      res.status(400).send("Error: Subscription ID is required.");
      return;
    }

    const baseRaw = MANAGER_BASE_URL.value();
    if (!baseRaw) {
      res.status(500).send("Error: MANAGER_BASE_URL is not configured.");
      return;
    }

    const base = baseRaw.replace(/\/+$/, "");
    const targetUrl = `${base}/sub/${subId}`;

    try {
      const response = await fetch(targetUrl);
      const content = await response.text();

      // Forward important headers from the manager
      // e.g. subscription-userinfo, x-config-version
      const headersToForward = [
        "subscription-userinfo",
        "x-config-version",
        "content-type",
        "cache-control",
      ];

      for (const header of headersToForward) {
        const val = response.headers.get(header);
        if (val) {
          res.setHeader(header, val);
        }
      }

      // Add the routing header for Happ
      res.setHeader("routing", getHappRoutingDeeplink(true));

      res.status(response.status).send(content);
    } catch (err) {
      logger.error("getUserSubscription proxy failed:", err);
      res.status(500).send("Internal Server Error");
    }
  }
);
