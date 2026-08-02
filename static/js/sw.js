const CACHE = 'morena-v1';

self.addEventListener('install', (e) => {
    self.skipWaiting();
});

self.addEventListener('activate', (e) => {
    e.waitUntil(clients.claim());
});

self.addEventListener('fetch', (e) => {
    if (e.request.method !== 'GET') return;
    e.respondWith(
        fetch(e.request)
            .then(r => {
                const clone = r.clone();
                caches.open(CACHE).then(c => c.put(e.request, clone));
                return r;
            })
            .catch(() => caches.match(e.request))
    );
});

self.addEventListener('push', (e) => {
    let payload = {};
    try {
        payload = e.data.json();
    } catch (_) {}
    const origin = (self.location && self.location.origin) || '';
    const title = payload.title || 'Morena Sin Gluten';
    const options = {
        body: payload.body || '',
        icon: origin + '/images/logo_frente.png',
        badge: origin + '/images/icon-192.png',
        data: payload.data || {},
        vibrate: [200, 100, 200]
    };
    e.waitUntil(self.registration.showNotification(title, options));
    const badgeCount = payload.data && payload.data.badge;
    if (badgeCount && 'setAppBadge' in self.registration) {
        self.registration.setAppBadge(badgeCount);
    }
});

self.addEventListener('notificationclick', (e) => {
    e.notification.close();
    const url = e.notification.data && e.notification.data.url;
    e.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then((list) => {
            for (const c of list) {
                if (url && c.url.includes(url)) {
                    return c.focus();
                }
            }
            if (url) {
                return clients.openWindow(url);
            }
        })
    );
});
