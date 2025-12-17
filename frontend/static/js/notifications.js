// notification.js (NO <script> TAGS)

// Firebase must be loaded BEFORE this file in HTML
// firebase-app-compat.js
// firebase-messaging-compat.js

const firebaseConfig = {
  apiKey: "AIzaSyCTjF_PJW03icRfxtnmwIhI8hDqv6XJscc",
  authDomain: "college-notifications-18747.firebaseapp.com",
  projectId: "college-notifications-18747",
  messagingSenderId: "721889955640",
  appId: "1:721889955640:web:d29f3d3f0829e8af89fbcd"
};

// Prevent duplicate initialization
if (!firebase.apps.length) {
  firebase.initializeApp(firebaseConfig);
}

const messaging = firebase.messaging();

async function enableNotifications() {
  try {
    if (!("Notification" in window)) return;

    const permission = await Notification.requestPermission();
    if (permission !== "granted") return;

    const registration = await navigator.serviceWorker.register("/firebase-messaging-sw.js");

    const token = await messaging.getToken({
      vapidKey: "BAbweZYXSFqhIpcYtIaea2229Mb7fkQoKOb22Z3ehLXejThUcMqXwG7zZb9irTJTX3LOq8IqOnadl9dr32h2DQ8",
      serviceWorkerRegistration: registration
    });

    if (!token) return;

    await fetch("/api/save-token", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        token: token,
        enrollment: localStorage.getItem("enrollment"),
        studentClass: localStorage.getItem("studentClass")
      })
    });

    console.log("✅ Notification token saved");

  } catch (err) {
    console.error("❌ Notification error:", err);
  }
}
