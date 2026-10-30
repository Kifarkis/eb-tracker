
self.addEventListener('install', function () { self.skipWaiting(); });
self.addEventListener('activate', function (event) { event.waitUntil(self.clients.claim()); });

self.addEventListener('push', function (event) {
  var data = {};
  try { data = event.data ? event.data.json() : {}; } catch (e) { data = { body: event.data ? event.data.text() : '' }; }
  event.waitUntil(self.registration.showNotification(data.title || 'EuroBonus Shopping', {
    body: data.body || '',
    tag: data.tag || undefined,
    renotify: !!data.tag,
    icon: 'icon-192.png',
    badge: 'icon-192.png',
    data: { url: data.url || './' },
  }));
});

self.addEventListener('notificationclick', function (event) {
  event.notification.close();
  var target;
  try { target = new URL((event.notification.data && event.notification.data.url) || './', self.location.href); } catch (e) { target = null; }
  if (!target || target.origin !== self.location.origin) target = new URL('./', self.location.href);
  event.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (list) {
    for (var i = 0; i < list.length; i++) {
      var c = list[i];
      if (c.url.indexOf(self.location.origin) === 0 && 'navigate' in c) {
        return c.navigate(target.href).then(function (w) { return (w || c).focus(); });
      }
    }
    return self.clients.openWindow(target.href);
  }));
});
