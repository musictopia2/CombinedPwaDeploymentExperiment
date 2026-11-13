let cleanup = null;

export async function registerAndListen(dotNetHelper) {
    dispose();

    if (!('serviceWorker' in navigator)) {
        return;
    }

    const workerUrl = new URL('service-worker.js', document.baseURI);

    const registration = await navigator.serviceWorker.register(
        workerUrl.href,
        { updateViaCache: 'none' }
    );

    let disposed = false;
    let notified = false;
    const workerListeners = [];

    function notifyUpdate() {
        if (disposed || notified) {
            return;
        }

        notified = true;

        dotNetHelper.invokeMethodAsync('NotifyUpdateAvailable')
            .catch(error => {
                if (!disposed) {
                    console.debug('Update notification failed.', error);
                }
            });
    }

    function watchWorker(worker) {
        if (!worker) {
            return;
        }

        function stateChanged() {
            if (worker.state === 'installed' &&
                navigator.serviceWorker.controller) {
                notifyUpdate();
            }
        }

        worker.addEventListener('statechange', stateChanged);
        workerListeners.push({ worker, stateChanged });

        stateChanged();
    }

    function updateFound() {
        watchWorker(registration.installing);
    }

    async function checkForUpdate() {
        try {
            await registration.update();
        } catch (error) {
            console.debug(
                'Update check unavailable; keeping the current version.',
                error
            );
        }
    }

    registration.addEventListener('updatefound', updateFound);

    watchWorker(registration.installing);

    if (registration.waiting && navigator.serviceWorker.controller) {
        notifyUpdate();
    }

    const timer = setInterval(checkForUpdate, 60_000);
    window.addEventListener('online', checkForUpdate);

    cleanup = () => {
        disposed = true;

        clearInterval(timer);
        window.removeEventListener('online', checkForUpdate);
        registration.removeEventListener('updatefound', updateFound);

        for (const entry of workerListeners) {
            entry.worker.removeEventListener(
                'statechange',
                entry.stateChanged
            );
        }
    };

    await checkForUpdate();
}

export function dispose() {
    if (cleanup) {
        cleanup();
        cleanup = null;
    }
}