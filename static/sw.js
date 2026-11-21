// 陪你的 Service Worker：只负责接收推送 + 点开回到页面
self.addEventListener("install", (e) => {
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(self.clients.claim());
});

self.addEventListener("push", (e) => {
  let data = { title: "陪你", body: "她给你留了一句话", url: "/app" };
  try {
    if (e.data) data = Object.assign(data, e.data.json());
  } catch (err) {
    if (e.data) data.body = e.data.text();
  }
  e.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: "/app/icon-192.png",
      badge: "/app/icon-192.png",
      tag: "peini-proactive",
      renotify: false,
      data: { url: data.url || "/app" },
    })
  );
});

self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || "/app";
  e.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((list) => {
      for (const c of list) {
        if (c.url.includes("/app") && "focus" in c) return c.focus();
      }
      return self.clients.openWindow(url);
    })
  );
});
