import {onRequest} from "firebase-functions/v2/https";
import {logger} from "firebase-functions";
import {db} from "./firebase";
import {provisionClient} from "./managerClient";

/**
 * Special endpoint to return a lifetime subscription for a user.
 * It ensures the user has a lifetime expiry in Firestore and returns a Happ subscription link.
 * The subscription itself (served via getSubscription) contains the routing profile in its headers.
 */
export const getLifetimeSubscription = onRequest(
  {cors: true, secrets: ["MANAGER_API_KEY"]},
  async (req, res) => {
    const uid = (req.query.uid as string);
    const tgId = (req.query.tgId as string);
    const vkId = (req.query.vkId as string);

    if (!uid && !tgId && !vkId) {
      res.status(400).send("Error: uid, tgId, or vkId query parameter is required.");
      return;
    }

    try {
      let userRef;
      if (uid) {
        userRef = db.collection("users").doc(uid);
      } else if (tgId) {
        const snap = await db.collection("users")
          .where("externalTg", "in", [tgId, `tg:${tgId}`])
          .limit(1)
          .get();
        if (snap.empty) {
          res.status(404).send("Error: User not found by tgId.");
          return;
        }
        userRef = snap.docs[0].ref;
      } else {
        const snap = await db.collection("users")
          .where("externalVk", "in", [vkId, `vk:${vkId}`])
          .limit(1)
          .get();
        if (snap.empty) {
          res.status(404).send("Error: User not found by vkId.");
          return;
        }
        userRef = snap.docs[0].ref;
      }

      const userSnap = await userRef.get();
      if (!userSnap.exists) {
        res.status(404).send("Error: User document not found.");
        return;
      }


      // 2. Provision client to get subId for the VPN link
      const provision = await provisionClient(userRef.id);
      const subId = provision.subId;

      // 3. Construct the subscription URL (proxy via getSubscription)
      const host = req.get("host") || "";
      let subUrl = "";
      if (host.toLowerCase().includes("getlifetimesubscription")) {
        // Default Firebase Run domain per function
        const subHost = host.toLowerCase().replace("getlifetimesubscription", "getsubscription");
        subUrl = `https://${subHost}/?id=${subId}`;
      } else {
        // Shared domain (e.g. cloudfunctions.net) or custom domain
        subUrl = `${req.protocol}://${host}/getSubscription?id=${subId}`;
      }

      // According to official documentation and generator at deeplink.happ.su
      // the correct format to add a subscription is happ://add/{URL}
      const happDeeplink = `happ://add/${subUrl}`;

      // 4. Return a landing page that opens Happ
      res.status(200).send(`
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MVMVpn Premium Connect</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: #0f172a;
            color: #f8fafc;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            height: 100vh;
            margin: 0;
            text-align: center;
        }
        .container {
            padding: 2rem;
            background: rgba(30, 41, 59, 0.7);
            backdrop-filter: blur(10px);
            border-radius: 1.5rem;
            border: 1px solid rgba(255, 255, 255, 0.1);
            max-width: 400px;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
        }
        h1 { font-size: 1.5rem; margin-bottom: 1rem; color: #38bdf8; }
        p { color: #94a3b8; line-height: 1.5; margin-bottom: 2rem; }
        .btn {
            display: inline-block;
            background: linear-gradient(135deg, #0ea5e9 0%, #2563eb 100%);
            color: white;
            padding: 0.8rem 2rem;
            border-radius: 9999px;
            text-decoration: none;
            font-weight: 600;
            transition: transform 0.2s;
            box-shadow: 0 10px 15px -3px rgba(37, 99, 235, 0.3);
        }
        .btn:hover { transform: scale(1.05); }
        .btn-secondary {
            display: block;
            margin-top: 1rem;
            background: none;
            border: 1px solid #38bdf8;
            color: #38bdf8;
            padding: 0.6rem 1.5rem;
            border-radius: 9999px;
            text-decoration: none;
            font-size: 0.9rem;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s;
        }
        .btn-secondary:hover { background: rgba(56, 189, 248, 0.1); }
    </style>
</head>
<body>
    <div class="container">
        <h1>Подключение</h1>
        <p>Нажмите кнопку ниже, чтобы добавить подписку и настройки в приложение Happ.</p>
        <a href="${happDeeplink}" class="btn">Подключить</a>
    </div>
    <script>
        function copyLink() {
            const el = document.createElement('textarea');
            el.value = "${subUrl}";
            document.body.appendChild(el);
            el.select();
            document.execCommand('copy');
            document.body.removeChild(el);
            alert('Ссылка скопирована!');
        }

        // Automatic redirect attempt after a short delay
        setTimeout(() => {
            window.location.href = "${happDeeplink}";
        }, 1500);
    </script>
</body>
</html>
      `);
    } catch (err) {
      logger.error("getLifetimeSubscription error:", err);
      res.status(500).send("Internal Server Error");
    }
  }
);

