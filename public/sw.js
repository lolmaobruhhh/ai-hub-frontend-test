/* AI Hub root service worker — clears stale PWA caches from subpath apps
 * and ensures fresh content is always served for hub pages. */

const CACHE_NAME = "ai-hub-v2";
const NO_CACHE_PATHS = ["/hub", "/hub/", "/api/hub", "/api/hub/", "/hub.html",
                        "/switching.html", "/api/switch/", "/api/sync",
                        "/api/ready", "/api/active", "/api/debug"];

self.addEventListener("install", (event) => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      // Delete ALL old caches on activation
      const keys = await caches.keys();
      await Promise.all(keys.map((key) => caches.delete(key)));
      // Claim all clients immediately
      await self.clients.claim();
    })()
  );
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  const path = url.pathname;

  // Never cache hub pages or API endpoints
  if (NO_CACHE_PATHS.some((p) => path === p || path.startsWith(p))) {
    event.respondWith(fetch(event.request));
    return;
  }

  // For everything else, network-first with no offline fallback
  event.respondWith(
    fetch(event.request).catch(() => {
      return new Response("Offline - AI Hub", {
        status: 503,
        headers: { "Content-Type": "text/plain" },
      });
    })
  );
});
