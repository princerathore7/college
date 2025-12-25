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

// 🔔 BACKGROUND NOTIFICATIONS
messaging.onBackgroundMessage(payload => {
  console.log("[SW] Background message:", payload);

  const title = payload.notification.title;
  const options = {
    body: payload.notification.body,
    icon: "/static/img/logo.png"
  };

  self.registration.showNotification(title, options);
});
