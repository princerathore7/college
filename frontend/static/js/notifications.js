// notifications.js (no <script> tags)

// Firebase must be loaded BEFORE this file in HTML
// firebase-app-compat.js
// firebase-messaging-compat.js

const firebaseConfig = {
  apiKey: "AIzaSyCTjF_PJW03icRfxtnmwI8hDqv6XJscc",
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

// Enrollment & class from localStorage
const ENROLLMENT = localStorage.getItem("enrollment");
const STUDENT_CLASS = localStorage.getItem("studentClass");

// Register service worker & save token
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

    // Save token on backend with enrollment info
    await fetch("/api/save-token", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        token: token,
        enrollment: ENROLLMENT,
        studentClass: STUDENT_CLASS
      })
    });

    console.log("✅ Notification token saved for:", ENROLLMENT);

    // Listen for messages while page is in focus
    messaging.onMessage(payload => {
      if (!payload?.data) return;

      const { type, enrollment, message } = payload.data;

      // Only show if enrollment matches OR type is global
      if (type === "global" || enrollment === ENROLLMENT) {
        showBrowserNotification(type, message);
      }
    });

  } catch (err) {
    console.error("❌ Notification error:", err);
  }
}

// Show browser notification
function showBrowserNotification(type, message) {
  const titleMap = {
    "attendance": "Attendance Update",
    "fees": "Pending Fees Update",
    "global": "College Notification"
  };

  const title = titleMap[type] || "Notification";

  const options = {
    body: message,
    icon: "/static/images/logo.jpg",
    badge: "/static/images/logo.jpg",
    vibrate: [200, 100, 200],
    tag: `notif-${Date.now()}`,
    renotify: true
  };

  try {
    new Notification(title, options);
  } catch (err) {
    console.error("Notification display error:", err);
  }
}

// Automatically enable notifications
enableNotifications();
