// firebase-messaging-sw.js
importScripts('https://www.gstatic.com/firebasejs/10.7.0/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/10.7.0/firebase-messaging-compat.js');

// Initialize Firebase
firebase.initializeApp({
  apiKey: "AIzaSyCTjF_PJW03icRfxtnmwIhI8hDqv6XJscc",
  authDomain: "college-notifications-18747.firebaseapp.com",
  projectId: "college-notifications-18747",
  messagingSenderId: "721889955640",
  appId: "1:721889955640:web:d29f3d3f0829e8af89fbcd"
});

// Retrieve Firebase Messaging object
const messaging = firebase.messaging();

// Handle background messages
messaging.onBackgroundMessage(function(payload) {
  console.log('[firebase-messaging-sw.js] Received background message ', payload);

  const notificationTitle = payload.notification.title || "Notification";
  const notificationOptions = {
    body: payload.notification.body || "",
    icon: "/logo.jpg", // your logo path
    data: payload.data || {}
  };

  self.registration.showNotification(notificationTitle, notificationOptions);
});

// Optional: Click action for notifications
self.addEventListener('notificationclick', function(event) {
  event.notification.close();
  if(event.notification.data && event.notification.data.url){
    event.waitUntil(clients.openWindow(event.notification.data.url));
  }
});
