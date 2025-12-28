/* firebase-messaging-sw.js */

importScripts("https://www.gstatic.com/firebasejs/9.23.0/firebase-app-compat.js");
importScripts("https://www.gstatic.com/firebasejs/9.23.0/firebase-messaging-compat.js");

firebase.initializeApp({
  apiKey: "AIzaSyCTjF_PJW03icRfxtnmwIhI8hDqv6XJscc",
  authDomain: "college-notifications-18747.firebaseapp.com",
  projectId: "college-notifications-18747",
  messagingSenderId: "721889955640",
  appId: "1:721889955640:web:d29f3d3f0829e8af89fbcd"
});

const messaging = firebase.messaging();

/**
 * Background notification handler
 * (jab website band ho ya background me ho)
 */
messaging.onBackgroundMessage(function (payload) {
  console.log("[SW] Background message received:", payload);

  const notificationTitle = payload.notification?.title || "New Notification";
  const notificationOptions = {
    body: payload.notification?.body || "",
    icon: "/static/logo.jpg",   // optional
    data: payload.data || {}
  };

  self.registration.showNotification(notificationTitle, notificationOptions);
});

/**
 * Notification click handler
 */
self.addEventListener("notificationclick", function (event) {
  event.notification.close();

  const url = event.notification?.data?.url || "/notifications.html";

  event.waitUntil(
    clients.openWindow(url)
  );
});
