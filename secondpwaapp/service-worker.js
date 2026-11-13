/* Manifest version: zYulACHK */
self.importScripts('./service-worker-assets.js');

const version = '11.0';

const scopeUrl = new URL(self.registration.scope);
const indexUrl = new URL('index.html', scopeUrl).href;

const cacheNamePrefix = `static-site:${scopeUrl.href}|`;
const cacheName =
    `${cacheNamePrefix}${self.assetsManifest.version}`;

const offlineAssetsInclude = [
    /\.dll$/,
    /\.pdb$/,
    /\.wasm$/,
    /\.html$/,
    /\.js$/,
    /\.json$/,
    /\.css$/,
    /\.woff2?$/,
    /\.ttf$/,
    /\.png$/,
    /\.jpe?g$/,
    /\.gif$/,
    /\.ico$/,
    /\.svg$/,
    /\.blat$/,
    /\.dat$/,
    /\.webmanifest$/
];

self.addEventListener('install', event => {
    event.waitUntil((async () => {
        const assets = self.assetsManifest.assets
            .filter(asset =>
                offlineAssetsInclude.some(pattern =>
                    pattern.test(asset.url)))
            .map(asset => ({
                asset,
                url: new URL(asset.url, scopeUrl)
            }))
            .filter(entry =>
                entry.url.origin === scopeUrl.origin &&
                entry.url.href.startsWith(scopeUrl.href) &&
                entry.url.href !==
                    new URL('service-worker.js', scopeUrl).href);

        const requests = assets.map(entry =>
            new Request(entry.url.href, {
                integrity: entry.asset.hash,
                cache: 'no-cache'
            }));

        const cache = await caches.open(cacheName);

        // Activate only after the complete offline snapshot is cached.
        await cache.addAll(requests);
        await self.skipWaiting();
    })());
});

self.addEventListener('activate', event => {
    event.waitUntil((async () => {
        const keys = await caches.keys();

        await Promise.all(
            keys
                .filter(key =>
                    key.startsWith(cacheNamePrefix) &&
                    key !== cacheName)
                .map(key => caches.delete(key))
        );

        await self.clients.claim();
    })());
});

self.addEventListener('fetch', event => {
    if (event.request.method !== 'GET') {
        return;
    }

    const requestUrl = new URL(event.request.url);

    if (requestUrl.origin !== scopeUrl.origin ||
        !requestUrl.href.startsWith(scopeUrl.href)) {
        return;
    }

    event.respondWith((async () => {
        const cache = await caches.open(cacheName);

        if (event.request.mode === 'navigate') {
            const page = await cache.match(indexUrl);

            if (page) {
                return page;
            }

            return fetch(event.request);
        }

        const cached = await cache.match(event.request);

        return cached || fetch(event.request);
    })());
});