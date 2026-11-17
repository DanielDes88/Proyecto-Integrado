import json
import logging
from datetime import timedelta
from math import ceil, isfinite
from urllib.error import URLError
from urllib.request import Request, urlopen
from uuid import UUID

from django.conf import settings
from django.db.models import Q
from django.db import OperationalError, transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from .demo import ADDRESSES, DemoError, allowed_appointments, profile
from .models import DemoWorkspace, TripLocation

logger = logging.getLogger(__name__)
LOCATION_TTL = timedelta(seconds=45)
ROUTE_INTERVAL = timedelta(seconds=60)
MIN_POSITION_INTERVAL = timedelta(seconds=5)
DEMO_DESTINATIONS = {
    ADDRESSES[0]: (-33.4379, -70.6505),  # Plaza de Armas, Santiago
    ADDRESSES[1]: (-33.4397, -70.6436),  # Cerro Santa Lucía, Santiago
}


def destination(visit):
    if visit.destination_latitude is not None and visit.destination_longitude is not None:
        return visit.destination_latitude, visit.destination_longitude
    return DEMO_DESTINATIONS.get(visit.address)


def compute_eta(origin, target):
    def waypoint(point):
        return {"location": {"latLng": {"latitude": point[0], "longitude": point[1]}}}

    body = {
        "origin": waypoint(origin),
        "destination": waypoint(target),
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_AWARE",
    }
    request = Request(
        "https://routes.googleapis.com/directions/v2:computeRoutes",
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": settings.GOOGLE_MAPS_ROUTES_KEY,
            "X-Goog-FieldMask": "routes.duration",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=4) as response:
            routes = json.load(response).get("routes", [])
        if routes:
            duration = routes[0]["duration"]
            if duration.endswith("s"):
                return max(0, ceil(float(duration[:-1])))
    except (URLError, OSError, ValueError, OverflowError, KeyError, TypeError, AttributeError):
        logger.warning("Google Routes no pudo proporcionar un tiempo de llegada.")
    return None


@never_cache
@require_GET
def patient_trips(request):
    try:
        user_profile = profile(request.user)
        if user_profile.role != "paciente":
            raise DemoError("Solo el paciente puede consultar su seguimiento.", 403)
        visits = allowed_appointments(user_profile.workspace, request.user)
        active = visits.filter(status="En camino", professional__isnull=False)
        now = timezone.now()
        TripLocation.objects.filter(appointment__in=visits, received_at__lt=now - LOCATION_TTL).delete()
        trips = []
        for visit in active.select_related("professional", "triplocation"):
            location = getattr(visit, "triplocation", None)
            current = location and location.received_at >= now - LOCATION_TTL
            target = destination(visit)
            trips.append({
                "id": visit.code,
                "professional": visit.professional.get_full_name() or visit.professional.username,
                "destination": dict(zip(("lat", "lng"), target)) if target and current else None,
                "position": {"lat": location.latitude, "lng": location.longitude} if current else None,
                "updated_at": location.received_at.isoformat() if current else None,
                "share_id": str(location.share_id) if current else None,
            })
        return JsonResponse({"trips": trips})
    except DemoError as error:
        return JsonResponse({"error": error.message}, status=error.status)
    except OperationalError:
        return JsonResponse({"error": "No se pudo consultar el seguimiento."}, status=503)


def coordinate(data, name, limit):
    value = data.get(name)
    if type(value) not in (int, float) or not -limit <= value <= limit or not isfinite(value):
        raise DemoError("Coordenadas inválidas.")
    return float(value)


@never_cache
@require_POST
def share_location(request, appointment_id):
    try:
        user_profile = profile(request.user)
        if user_profile.role != "profesional":
            raise DemoError("Solo el profesional asignado puede compartir su ubicación.", 403)
        if request.content_type != "application/json":
            raise DemoError("Se requiere JSON.", 415)
        if len(request.body) > 1024:
            raise DemoError("Petición demasiado extensa.", 413)
        try:
            data = json.loads(request.body)
            share_id = UUID(data["share_id"])
            action = data["action"]
        except (ValueError, KeyError, TypeError, AttributeError):
            raise DemoError("Solicitud de seguimiento inválida.")
        if action not in ("position", "stop"):
            raise DemoError("Acción de seguimiento inválida.")
        origin = None if action == "stop" else (
            coordinate(data, "latitude", 90),
            coordinate(data, "longitude", 180),
        )

        with transaction.atomic():
            # Usa el mismo bloqueo que la transición de estado de la visita.
            workspace = DemoWorkspace.objects.select_for_update().get(pk=user_profile.workspace_id)
            visit = allowed_appointments(workspace, request.user).filter(pk=appointment_id).first()
            if not visit or not visit.patient_id:
                raise DemoError("Atención no encontrada.", 404)
            if action == "stop":
                TripLocation.objects.filter(appointment=visit, share_id=share_id).delete()
                return JsonResponse({"sharing": False})
            if visit.status != "En camino":
                raise DemoError("El seguimiento está disponible cuando la visita está En camino.", 409)

            now = timezone.now()
            location = TripLocation.objects.filter(appointment=visit).first()
            if location and location.received_at >= now - LOCATION_TTL:
                if location.share_id != share_id:
                    raise DemoError("Ya estás compartiendo esta visita desde otra pestaña.", 409)
                if location.received_at > now - MIN_POSITION_INTERVAL:
                    return JsonResponse({"sharing": True})
                TripLocation.objects.filter(appointment=visit).update(
                    latitude=origin[0], longitude=origin[1], received_at=now,
                )
            else:
                TripLocation.objects.update_or_create(appointment=visit, defaults={
                    "share_id": share_id, "latitude": origin[0], "longitude": origin[1],
                    "received_at": now, "route_requested_at": None,
                })

        return JsonResponse({"sharing": True})
    except DemoError as error:
        return JsonResponse({"error": error.message}, status=error.status)
    except OperationalError:
        return JsonResponse({"error": "No se pudo guardar la ubicación. Intenta en unos segundos."}, status=503)


@never_cache
@require_POST
def patient_eta(request, appointment_id):
    try:
        user_profile = profile(request.user)
        if user_profile.role != "paciente":
            raise DemoError("Solo el paciente puede consultar su seguimiento.", 403)
        visit = allowed_appointments(user_profile.workspace, request.user).filter(pk=appointment_id).first()
        if not visit:
            raise DemoError("Atención no encontrada.", 404)
        target = destination(visit)
        if not target or not settings.GOOGLE_MAPS_ROUTES_KEY:
            return JsonResponse({"eta_seconds": None})

        now = timezone.now()
        active_location = TripLocation.objects.filter(
            appointment=visit, appointment__status="En camino", received_at__gte=now - LOCATION_TTL,
        )
        location = active_location.first()
        if not location:
            return JsonResponse({"eta_seconds": None})
        same_share = active_location.filter(share_id=location.share_id)
        claimed = same_share.filter(
            Q(route_requested_at__isnull=True) | Q(route_requested_at__lte=now - ROUTE_INTERVAL),
        ).update(route_requested_at=now)
        if not claimed:
            raise DemoError("La estimación se consultó recientemente.", 429)

        eta = compute_eta((location.latitude, location.longitude), target)
        if not same_share.exists():
            eta = None
        return JsonResponse({"eta_seconds": eta, "share_id": str(location.share_id)})
    except DemoError as error:
        return JsonResponse({"error": error.message}, status=error.status)
    except OperationalError:
        return JsonResponse({"error": "No se pudo consultar el tiempo de llegada."}, status=503)
