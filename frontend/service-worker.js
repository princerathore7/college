/* =========================================================
   SERVICE WORKER — EVENTS & PUSH NOTIFICATIONS
   ========================================================= */

self.addEventListener("install", (event) => {
  console.log("[SW] Installed");
  self.skipWaiting(); // Immediately activate SW
});

self.addEventListener("activate", (event) => {
  console.log("[SW] Activated");
  event.waitUntil(self.clients.claim()); // Take control of pages
});

/* ---------------- PUSH NOTIFICATION ---------------- */
self.addEventListener("push", (event) => {
  console.log("[SW] Push Received");

  // Default data
  let data = {
    title: "New Notification",
    body: "You have a new update",
    url: "/",
    icon: "/logo.jpg",
    badge: "/logo.jpg"
  };

  if (event.data) {
    try {
      data = event.data.json();
    } catch (e) {
      console.error("[SW] Push data parse error", e);
    }
  }

  const options = {
    body: data.body,
    icon: data.icon || "/logo.jpg",
    badge: data.badge || "/logo.jpg",
    data: {
      url: data.url || "/"
    },
    // Optional: add vibrate pattern
    vibrate: [100, 50, 100],
    tag: data.tag || "global-notification", // prevent duplicates
    renotify: true
  };

  event.waitUntil(
    self.registration.showNotification(data.title, options)
  );
});

/* ---------------- NOTIFICATION CLICK ---------------- */
self.addEventListener("notificationclick", (event) => {
  console.log("[SW] Notification Clicked");

  event.notification.close();

  const targetUrl = event.notification.data?.url || "/";

  event.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true }).then(clientList => {
      // Try to focus if window with same URL exists
      for (const client of clientList) {
        if (client.url === targetUrl && "focus" in client) {
          return client.focus();
        }
      }
      // Otherwise open new window/tab
      if (clients.openWindow) {
        return clients.openWindow(targetUrl);
      }
    })
  );
});

/* ---------------- OPTIONAL: PUSH SUBSCRIPTION CHANGE ---------------- */
// This ensures subscription is updated when push subscription changes
self.addEventListener('pushsubscriptionchange', (event) => {
  console.log('[SW] Push Subscription change detected');
  event.waitUntil(
    self.registration.pushManager.subscribe(event.oldSubscription.options)
      .then(newSubscription => {
        // TODO: send newSubscription to server
        console.log('[SW] New subscription:', newSubscription);
      })
  );
});