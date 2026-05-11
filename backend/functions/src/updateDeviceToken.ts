import {onCall, HttpsError} from "firebase-functions/v2/https";
import {FieldValue} from "firebase-admin/firestore";
import {resolveUsersDoc} from "./userResolver";

interface DeviceInfo {
  random_uuid: string;
  name: string;
  os: "android" | "ios";
  sendnotifyToken: string;
  createdAt?: FieldValue;
}

/**
 * Updates or adds a device notification token for the authenticated user.
 */
export const updateDeviceToken = onCall(
  {cors: true, maxInstances: 10},
  async (request) => {
    const decodedIdToken = request.auth?.token;
    if (!decodedIdToken) {
      throw new HttpsError("unauthenticated", "Authentication is required");
    }

    const {random_uuid, name, os, sendnotifyToken} = request.data as DeviceInfo;

    if (!random_uuid || !name || !os || !sendnotifyToken) {
      throw new HttpsError(
        "invalid-argument",
        "Missing required device information"
      );
    }

    const resolved = await resolveUsersDoc(decodedIdToken);
    if (!resolved) {
      throw new HttpsError("not-found", "User record was not found");
    }

    const snap = await resolved.ref.get();
    const data = snap.data() || {};
    const devices = (data.devices as DeviceInfo[]) || [];

    const deviceIndex = devices.findIndex((d) => d.random_uuid === random_uuid);

    const updatedDevice: DeviceInfo = {
      random_uuid,
      name,
      os,
      sendnotifyToken,
      createdAt: FieldValue.serverTimestamp()
    };

    if (deviceIndex > -1) {
      devices[deviceIndex] = updatedDevice;
    } else {
      devices.push(updatedDevice);
    }

    await resolved.ref.update({
      devices,
      updatedAt: FieldValue.serverTimestamp(),
    });

    return {ok: true};
  }
);
