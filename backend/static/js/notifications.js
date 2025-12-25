// ==================================================
// 🔔 FIREBASE CLOUD MESSAGING — CLIENT
// ==================================================

// Firebase config
const firebaseConfig = {
  apiKey: "AIzaSyCTjF_PJW03icRfxtnmwIhI8hDqv6XJscc",
  authDomain: "college-notifications-18747.firebaseapp.com",
  projectId: "college-notifications-18747",
  messagingSenderId: "721889955640",
  appId: "1:721889955640:web:d29f3d3f0829e8af89fbcd"
};

// Prevent duplicate init
if (!firebase.apps.length) {
  firebase.initializeApp(firebaseConfig);
}

// Firebase Messaging
const messaging = firebase.messaging();

// ==================================================
// ENABLE NOTIFICATIONS
// ==================================================
async function enableNotifications() {
  try {
    if (!("Notification" in window)) {
      console.warn("❌ Notifications not supported");
      return;
    }

    const enrollment = localStorage.getItem("enrollment");
    const studentClass = localStorage.getItem("studentClass");

    if (!enrollment) {
      console.warn("❌ Enrollment missing — login required");
      return;
    }

    // Ask permission
    const permission = await Notification.requestPermission();
    if (permission !== "granted") {
      console.warn("❌ Notification permission denied");
      return;
    }

    // Register ONLY Firebase SW
    const registration = await navigator.serviceWorker.register(
      "/firebase-messaging-sw.js"
    );

    // Get FCM token
    const token = await messaging.getToken({
      vapidKey: "BAbweZYXSFqhIpcYtIaea2229Mb7fkQoKOb22Z3ehLXejThUcMqXwG7zZb9irTJTX3LOq8IqOnadl9dr32h2DQ8",
      serviceWorkerRegistration: registration
    });

    if (!token) {
      console.warn("❌ FCM token not generated");
      return;
    }

    // Save token to backend
    const res = await fetch("/api/save-token", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        enrollment,
        studentClass,
        token
      })
    });

    const data = await res.json();
    if (!data.success) {
      console.error("❌ Token save failed:", data.message);
      return;
    }

    console.log("✅ FCM token saved successfully");

  } catch (err) {
    console.error("❌ Notification setup failed:", err);
  }
}

// ==================================================
// FOREGROUND MESSAGE HANDLER
// ==================================================
messaging.onMessage(payload => {
  console.log("📩 Foreground notification:", payload);

  const { title, body } = payload.notification || {};

  if (title && body) {
    new Notification(title, {
      body,
      icon: "/static/img/logo.png"
    });
  }
});

// ==================================================
// AUTO INIT ON PAGE LOAD
// ==================================================
window.addEventListener("load", () => {
  enableNotifications();
});
