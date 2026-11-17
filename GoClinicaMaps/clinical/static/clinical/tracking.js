'use strict';

window.GoClinicalTracking = (() => {
    const settings = JSON.parse(document.getElementById('bootstrap').textContent).maps;
    const statusBar = document.getElementById('sharingStatus');
    let sharing = null;
    let mapLoader;
    let panel;

    async function request(url, options = {}) {
        const response = await fetch(url, {cache: 'no-store', ...options});
        const data = await response.json();
        if (!response.ok) {
            const error = new Error(data.error || 'El seguimiento no está disponible.');
            error.status = response.status;
            throw error;
        }
        return data;
    }

    function csrfToken() {
        return document.querySelector('.logoutform input[name="csrfmiddlewaretoken"]').value;
    }

    function send(session, action, coords, keepalive = false) {
        return request(session.url, {
            method: 'POST',
            keepalive,
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken()},
            body: JSON.stringify({
                action,
                share_id: session.token,
                ...(coords && {latitude: coords.latitude, longitude: coords.longitude}),
            }),
        });
    }

    function sharingMessage(message) {
        statusBar.hidden = false;
        statusBar.replaceChildren();
        const text = document.createElement('span');
        text.setAttribute('role', 'status');
        text.textContent = message;
        statusBar.append(text);
        if (sharing) {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'button secondary';
            button.textContent = 'Dejar de compartir';
            button.addEventListener('click', () => stopSharing());
            statusBar.append(button);
        }
        updateShareButtons();
    }

    function updateShareButtons() {
        for (const button of document.querySelectorAll('[data-share-trip]')) {
            button.disabled = Boolean(sharing);
            button.textContent = sharing?.id === button.dataset.shareTrip
                ? 'Ubicación compartida' : 'Compartir ubicación';
        }
    }

    async function stopSharing(message = 'Dejaste de compartir tu ubicación.') {
        const session = sharing;
        if (!session || session.stopping) return;
        session.stopping = true;
        clearTimeout(session.timer);
        statusBar.querySelector('button').disabled = true;
        try {
            await session.pending?.catch(() => {});
            await send(session, 'stop');
        } catch {
            message = 'Se detuvo el envío. La última ubicación dejará de verse en hasta 45 segundos.';
        } finally {
            sharing = null;
            sharingMessage(message);
        }
    }

    function locate(session) {
        if (sharing !== session || session.stopping) return;
        navigator.geolocation.getCurrentPosition(async ({coords}) => {
            if (sharing !== session || session.stopping) return;
            try {
                session.pending = send(session, 'position', coords);
                await session.pending;
                if (!session.stopping) sharingMessage(`Compartiendo ubicación · ${session.id}`);
            } catch (error) {
                if (session.stopping) return;
                if ([400, 401, 403, 404, 409].includes(error.status)) {
                    stopSharing(error.message);
                    return;
                }
                sharingMessage('No se pudo enviar la ubicación. Reintentando…');
            }
            if (!session.stopping) session.timer = setTimeout(() => locate(session), 10000);
        }, (error) => {
            if (sharing !== session || session.stopping) return;
            if (error.code === 1) {
                stopSharing('Permite el acceso a la ubicación en el navegador y vuelve a intentarlo.');
                return;
            }
            sharingMessage('No se pudo obtener el GPS. Reintentando…');
            session.timer = setTimeout(() => locate(session), 10000);
        }, {enableHighAccuracy: true, maximumAge: 0, timeout: 10000});
    }

    document.addEventListener('click', (event) => {
        const button = event.target.closest('[data-share-trip]');
        if (!button || sharing) return;
        if (!window.isSecureContext || !navigator.geolocation || !crypto.randomUUID) {
            sharingMessage('Abre GoClinical desde HTTPS o localhost para usar la ubicación del navegador.');
            return;
        }
        const id = button.dataset.shareTrip;
        sharing = {id, url: `/api/tracking/${Number(id.slice(3))}/`, token: crypto.randomUUID()};
        sharingMessage('Obteniendo GPS. Mantén GoClinical abierto mientras vas en camino.');
        locate(sharing);
    });

    window.addEventListener('pagehide', () => {
        if (!sharing) return;
        const session = sharing;
        sharing = null;
        session.stopping = true;
        clearTimeout(session.timer);
        send(session, 'stop', null, true).catch(() => {});
        sharingMessage('El envío de ubicación se detuvo al salir de la página.');
    });

    function loadMaps() {
        if (!mapLoader) {
            mapLoader = new Promise((resolve, reject) => {
                const script = document.createElement('script');
                const finish = (error) => {
                    clearTimeout(timeout);
                    if (error) reject(error);
                    else resolve();
                };
                const timeout = setTimeout(() => finish(new Error('Google Maps tardó demasiado en responder.')), 15000);
                window.goClinicalMapsReady = () => finish();
                window.gm_authFailure = () => {
                    finish(new Error('Google Maps rechazó la clave.'));
                    if (panel) panel.mapError = 'Google Maps rechazó la clave. Revisa las credenciales.';
                };
                script.onerror = () => finish(new Error('No se pudo cargar Google Maps.'));
                const params = new URLSearchParams({
                    key: settings.key, callback: 'goClinicalMapsReady', loading: 'async', v: 'quarterly',
                });
                script.src = `https://maps.googleapis.com/maps/api/js?${params}`;
                script.async = true;
                document.head.append(script);
            }).then(() => Promise.all([
                google.maps.importLibrary('maps'), google.maps.importLibrary('marker'),
            ]));
        }
        return mapLoader;
    }

    function clearMap(view) {
        if (view.marker) view.marker.map = null;
        if (view.destination) view.destination.map = null;
        view.mapElement.hidden = true;
        view.legend.hidden = true;
        view.mappedTrip = null;
    }

    async function showMap(view, trip) {
        if (!settings.key) {
            view.mapStatus.textContent = 'Google Maps requiere una clave de navegador para mostrar la ubicación.';
            return;
        }
        try {
            const version = ++view.version;
            const [{Map}, {AdvancedMarkerElement, PinElement}] = await loadMaps();
            if (panel !== view || view.version !== version) return;
            if (view.mapError) throw new Error(view.mapError);
            view.mapElement.hidden = false;
            view.legend.hidden = !trip.destination;
            view.mapStatus.textContent = '';
            if (!view.map) {
                view.map = new Map(view.mapElement, {
                    center: trip.position, zoom: 15, mapId: settings.mapId,
                    streetViewControl: false, mapTypeControl: false,
                });
                view.marker = new AdvancedMarkerElement({title: 'Profesional'});
                view.destination = new AdvancedMarkerElement({
                    title: 'Destino de la visita',
                    content: new PinElement({background: '#187d70', borderColor: '#125b52', glyphColor: '#fff'}).element,
                });
            }
            view.marker.position = trip.position;
            view.marker.title = trip.professional;
            view.marker.map = view.map;
            view.destination.position = trip.destination;
            view.destination.map = trip.destination ? view.map : null;
            if (view.mappedTrip !== trip.id) {
                view.map.setCenter(trip.position);
                view.map.setZoom(15);
                if (trip.destination && (trip.position.lat !== trip.destination.lat || trip.position.lng !== trip.destination.lng)) {
                    const bounds = new google.maps.LatLngBounds();
                    bounds.extend(trip.position);
                    bounds.extend(trip.destination);
                    view.map.fitBounds(bounds, 40);
                }
                view.mappedTrip = trip.id;
            } else if (view.map.getBounds() && !view.map.getBounds().contains(trip.position)) {
                view.map.panTo(trip.position);
            }
            updateEta(view, trip);
        } catch (error) {
            if (panel !== view) return;
            clearMap(view);
            view.eta.textContent = 'Tiempo estimado de llegada no disponible.';
            view.mapStatus.textContent = error.message;
        }
    }

    function showTrip(view) {
        view.version++;
        const trip = view.trips.find((item) => item.id === view.select.value);
        view.mapStatus.textContent = '';
        view.updated.textContent = '';
        if (!trip?.position) {
            clearMap(view);
            view.eta.textContent = trip
                ? 'Esperando una ubicación reciente del profesional.'
                : 'No tienes visitas en camino en este momento.';
            return;
        }
        const estimate = view.estimates.get(trip.share_id);
        view.eta.textContent = estimate?.text || (settings.key
            ? 'Consultando el tiempo estimado de llegada…' : 'Tiempo estimado de llegada no disponible.');
        view.updated.textContent = 'Ubicación actualizada a las ' + new Date(trip.updated_at).toLocaleTimeString('es-CL');
        showMap(view, trip);
    }

    async function updateEta(view, trip) {
        const previous = view.estimates.get(trip.share_id);
        if (previous && Date.now() - previous.requested < 61000) return;
        const estimate = {requested: Date.now(), text: previous?.text};
        view.estimates.set(trip.share_id, estimate);
        let seconds;
        try {
            const result = await request(`/api/tracking/${Number(trip.id.slice(3))}/eta/`, {
                method: 'POST',
                headers: {'X-CSRFToken': csrfToken()},
                signal: view.controller.signal,
            });
            if (result.share_id === trip.share_id) seconds = result.eta_seconds;
        } catch {
            // El mapa y la ubicación se siguen actualizando si falla el cálculo.
        }
        estimate.text = seconds == null ? 'Tiempo estimado de llegada no disponible.'
            : seconds < 60 ? 'Llegada estimada en menos de 1 min.'
            : `Llegada estimada en ${Math.ceil(seconds / 60)} min.`;
        if (panel === view && view.select.value === trip.id
            && view.trips.some((item) => item.share_id === trip.share_id) && !view.mapElement.hidden) {
            view.eta.textContent = estimate.text;
        }
    }

    async function updatePanel(view) {
        try {
            const {trips} = await request('/api/tracking/', {signal: view.controller.signal});
            if (panel !== view) return;
            const previous = view.select.value;
            const signature = JSON.stringify(trips.map(({id, professional}) => [id, professional]));
            if (signature !== view.signature) {
                view.select.replaceChildren(...trips.map((trip) =>
                    new Option(`${trip.id} · ${trip.professional}`, trip.id)));
                if (trips.some((trip) => trip.id === previous)) view.select.value = previous;
                view.signature = signature;
            }
            view.select.parentElement.hidden = trips.length === 0;
            view.trips = trips;
            for (const shareId of view.estimates.keys()) {
                if (!trips.some((trip) => trip.share_id === shareId)) view.estimates.delete(shareId);
            }
            showTrip(view);
        } catch {
            if (panel !== view) return;
            view.version++;
            clearMap(view);
            view.eta.textContent = 'No se pudo consultar la ubicación. Reintentando…';
            view.mapStatus.textContent = '';
            view.updated.textContent = '';
        }
        if (panel === view) view.timer = setTimeout(() => updatePanel(view), 5000);
    }

    function attachPanel(host) {
        if (panel) {
            host.append(panel.element);
            return;
        }
        const element = document.createElement('section');
        element.className = 'card tracking-panel';
        element.innerHTML = `
            <h2>Seguimiento de mi visita</h2>
            <label hidden>Atención <select></select></label>
            <p class="tracking-eta" role="status">Consultando tus visitas…</p>
            <p class="tracking-updated muted"></p>
            <p class="tracking-map-status muted"></p>
            <div class="tracking-map" aria-label="Mapa de ubicación del profesional" hidden></div>
            <p class="tracking-legend muted" hidden><span>Profesional</span><span>Destino de la visita</span></p>
        `;
        const view = {
            element, trips: [], estimates: new Map(), version: 0, controller: new AbortController(),
            select: element.querySelector('select'),
            eta: element.querySelector('.tracking-eta'),
            updated: element.querySelector('.tracking-updated'),
            mapStatus: element.querySelector('.tracking-map-status'),
            mapElement: element.querySelector('.tracking-map'),
            legend: element.querySelector('.tracking-legend'),
        };
        view.select.addEventListener('change', () => showTrip(view));
        host.append(element);
        panel = view;
        updatePanel(view);
    }

    return {
        render() {
            updateShareButtons();
            const host = document.getElementById('patientTracking');
            if (host) attachPanel(host);
            else if (panel) {
                clearTimeout(panel.timer);
                panel.controller.abort();
                clearMap(panel);
                panel = null;
            }
        },
        visitChanged(id, status) {
            if (sharing?.id === id && status !== 'En camino') {
                stopSharing('Atención iniciada. El envío de ubicación se detuvo.');
            }
        },
    };
})();
