# Heleket (NOWPayments replacement)

Crypto and RUB-to-gateway flows use [Heleket](https://doc.heleket.com/). Configure the items below after deploying Firebase Functions.

## Telegram / VK bots (`backend/bot`)

Set in `bot/.env` (or your process environment):

| Variable | Description |
| -------- | ----------- |
| `HELEKET_MERCHANT_UUID` | Merchant UUID from Heleket settings (sent as HTTP header `merchant`). |
| `HELEKET_PAYMENT_API_KEY` | Payment API key used to sign invoice requests (`sign` header). |
| `HELEKET_CALLBACK_URL` | Full HTTPS URL of the **`heleketWebhook`** Cloud Function. Passed as `url_callback` on each invoice so payment notifications reach Firebase. |

After deployment the URL looks like:

`https://<region>-<project-id>.cloudfunctions.net/heleketWebhook`

Use your actual region and project ID from the Firebase console or deploy logs.

## Firebase Functions (`backend/functions`)

The webhook handler reads **`HELEKET_PAYMENT_API_KEY`** (same payment key as the bots). Configure it with `firebase functions:config:set`, `.env` for emulators, or **Secret Manager** depending on your setup.

There is no separate IPN secret: verification uses the `sign` field in the JSON body (see Heleket webhook docs).

## Firestore

Processed payments are tracked under collection **`heleket_processed`** (document id = webhook `uuid`) to prevent duplicate subscription extensions.

## Optional hardening

Heleket documents webhook source IP **`31.133.220.8`**. You may restrict access at the edge or inside the function if your deployment allows reliable client IP detection.
