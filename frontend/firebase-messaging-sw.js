/* firebase-messaging-sw.js */
importScripts("https://www.gstatic.com/firebasejs/9.23.0/firebase-app-compat.js");
importScripts("https://www.gstatic.com/firebasejs/9.23.0/firebase-messaging-compat.js");

// Firebase initialization
firebase.initializeApp({
  apiKey: "AIzaSyCTjF_PJW03icRfxtnmwIhI8hDqv6XJscc",
  authDomain: "college-notifications-18747.firebaseapp.com",
  projectId: "college-notifications-18747",
  messagingSenderId: "721889955640",
  appId: "1:721889955640:web:d29f3d3f0829e8af89fbcd"
});

const messaging = firebase.messaging();

/* 🔔 BACKGROUND PUSH */
// Ye tab trigger hoga jab notification background me aaye
messaging.onBackgroundMessage(function(payload) {
  const notificationTitle = payload.notification?.title || "New Notification";
  const notificationOptions = {
    body: payload.notification?.body || "",
    icon: "/favicon.ico", // optional icon
    data: {
      url: payload.data?.url || "/", // redirect URL
    },
    // badge: "/badge-icon.png", // optional small icon
  };

  self.registration.showNotification(notificationTitle, notificationOptions);
});

/* 👉 Notification click */
self.addEventListener("notificationclick", function(event) {
  event.notification.close();

  const urlToOpen = event.notification.data?.url || "/";

  // Agar multiple clients open hain, pehle check karo
  event.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true }).then(windowClients => {
      // Pehle dekho koi window already open hai kya
      for (let client of windowClients) {
        if (client.url === urlToOpen && "focus" in client) {
          return client.focus();
        }
      }
      // Nahi hai toh nayi window open karo
      if (clients.openWindow) {
        return clients.openWindow(urlToOpen);
      }
    })
  );
});