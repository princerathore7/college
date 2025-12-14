/* =========================================================
   SERVICE WORKER — EVENTS & PUSH NOTIFICATIONS
   ========================================================= */

self.addEventListener("install", (event) => {
  console.log("[SW] Installed");
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  console.log("[SW] Activated");
  event.waitUntil(self.clients.claim());
});

/* ---------------- PUSH NOTIFICATION ---------------- */
self.addEventListener("push", (event) => {
  console.log("[SW] Push Received");

  let data = {
    title: "New Notification",
    body: "You have a new update",
    url: "/",
    icon: "/logo.jpg"
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
    badge: "/logo.jpg",
    data: {
      url: data.url || "/"
    }
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
    clients.matchAll({ type: "window", includeUncontrolled: true })
      .then(clientList => {
        for (const client of clientList) {
          if (client.url.includes(targetUrl) && "focus" in client) {
            return client.focus();
          }
        }
        if (clients.openWindow) {
          return clients.openWindow(targetUrl);
        }
      })
  );
});
