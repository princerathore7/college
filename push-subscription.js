/* =========================================================
   PUSH SUBSCRIPTION (CLIENT SIDE)
   ========================================================= */

const PUBLIC_VAPID_KEY = "BNubnwV8CTYrdDmpyhdl4f8kHXQ8Q9XpTDYNsuN59eEgDXDgsm3ecXvO-rRWbQH6MR25RJWUm3-_813aDEHpzZ8";

/* ---------- Base64 → Uint8Array ---------- */
function urlBase64ToUint8Array(base64String) {
  const padding = "=".repeat((4 - base64String.length % 4) % 4);
  const base64 = (base64String + padding)
    .replace(/-/g, "+")
    .replace(/_/g, "/");

  const rawData = window.atob(base64);
  const outputArray = new Uint8Array(rawData.length);

  for (let i = 0; i < rawData.length; ++i) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
}

/* ---------- Subscribe User ---------- */
async function subscribeUserToPush() {
  try {
    if (!("serviceWorker" in navigator)) {
      console.log("Service Worker not supported");
      return;
    }

    if (!("PushManager" in window)) {
      console.log("Push not supported");
      return;
    }

    const permission = Notification.permission;
    if (permission !== "granted") {
      console.log("Notification permission not granted");
      return;
    }

    const registration = await navigator.serviceWorker.ready;

    let subscription = await registration.pushManager.getSubscription();

    if (!subscription) {
      subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(PUBLIC_VAPID_KEY)
      });

      console.log("✅ New Push Subscription:", subscription);
    } else {
      console.log("ℹ️ Already subscribed");
    }

    // Send subscription to backend
    await fetch("https://college-hwbb.onrender.com/api/subscribe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(subscription)
    });

    console.log("📡 Subscription sent to backend");

  } catch (err) {
    console.error("❌ Push subscription failed:", err);
  }
}

/* ---------- Auto Subscribe ---------- */
document.addEventListener("DOMContentLoaded", () => {
  subscribeUserToPush();
});
