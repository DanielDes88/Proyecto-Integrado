import hashlib
import hmac
import json
import logging
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from django.conf import settings
from django.db import transaction

from .models import Appointment

logger = logging.getLogger(__name__)


class FlowError(Exception):
    pass


def validate_configuration():
    if not settings.FLOW_API_KEY or not settings.FLOW_SECRET_KEY:
        raise FlowError("Flow no está configurado. Define FLOW_API_KEY y FLOW_SECRET_KEY.")
    api_url = urlsplit(settings.FLOW_API_URL)
    if api_url.scheme != "https" or not api_url.netloc:
        raise FlowError("FLOW_API_URL debe ser una URL HTTPS válida.")
    _callback_url("flow_confirmation")
    _callback_url("flow_return")


def sign_params(params, secret_key):
    message = "".join(f"{key}{params[key]}" for key in sorted(params))
    return hmac.new(secret_key.encode(), message.encode(), hashlib.sha256).hexdigest()


def _api_request(endpoint, params, method):
    api_key = settings.FLOW_API_KEY
    secret_key = settings.FLOW_SECRET_KEY
    base_url = settings.FLOW_API_URL.rstrip("/")
    validate_configuration()

    signed_params = {key: str(value) for key, value in params.items()}
    signed_params["apiKey"] = api_key
    signed_params["s"] = sign_params(signed_params, secret_key)
    encoded = urlencode(signed_params).encode()
    url = f"{base_url}/{endpoint}"
    request = Request(
        f"{url}?{encoded}" if method == "GET" else url,
        data=None if method == "GET" else encoded,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method=method,
    )
    try:
        with urlopen(request, timeout=15) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        logger.warning("Flow respondió HTTP %s para %s", exc.code, endpoint)
        raise FlowError("Flow rechazó la solicitud de pago.") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise FlowError("No fue posible comunicarse con Flow.") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FlowError("Flow devolvió una respuesta inválida.") from exc
    if not isinstance(result, dict):
        raise FlowError("Flow devolvió una respuesta inválida.")
    if "code" in result and "message" in result:
        logger.warning("Flow reportó error %s: %s", result["code"], result["message"])
        raise FlowError("Flow no pudo procesar la solicitud de pago.")
    return result


def _callback_url(route_name):
    site_url = settings.FLOW_SITE_URL.rstrip("/")
    parsed = urlsplit(site_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise FlowError("Configura FLOW_SITE_URL con la URL HTTPS pública de la aplicación.")
    from django.urls import reverse

    return f"{site_url}{reverse(route_name)}"


def create_payment(appointment):
    response = _api_request(
        "payment/create",
        {
            "commerceOrder": str(appointment.payment_key),
            "subject": f"GoClinical - {appointment.service.name}"[:100],
            "currency": "CLP",
            "amount": appointment.price,
            "email": appointment.patient.email,
            "urlConfirmation": _callback_url("flow_confirmation"),
            "urlReturn": _callback_url("flow_return"),
            "timeout": 1800,
        },
        "POST",
    )
    url = response.get("url")
    token = response.get("token")
    if not isinstance(url, str) or not isinstance(token, str) or not token:
        raise FlowError("Flow devolvió una orden de pago incompleta.")
    payment_host = urlsplit(url)
    api_host = urlsplit(settings.FLOW_API_URL)
    if payment_host.scheme != "https" or payment_host.netloc != api_host.netloc:
        raise FlowError("Flow devolvió una URL de pago no confiable.")
    separator = "&" if "?" in url else "?"
    response["payment_url"] = f"{url}{separator}{urlencode({'token': token})}"
    return response


def get_payment_status(token):
    return _api_request("payment/getStatus", {"token": token}, "GET")


def confirm_payment(token):
    if not isinstance(token, str) or not token or len(token) > 100:
        raise FlowError("El token de Flow no es válido.")
    appointment = Appointment.objects.filter(flow_token=token).first()
    if not appointment:
        return None

    status_data = get_payment_status(token)
    try:
        received_amount = Decimal(str(status_data["amount"]))
        expected_amount = Decimal(appointment.price)
        status = int(status_data["status"])
    except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
        raise FlowError("Flow devolvió datos de pago incompletos.") from exc
    if (
        str(status_data.get("commerceOrder")) != str(appointment.payment_key)
        or received_amount != expected_amount
    ):
        logger.error("La orden o el monto confirmado por Flow no coincide con la reserva %s", appointment.pk)
        raise FlowError("Los datos confirmados por Flow no coinciden con la reserva.")
    if status not in {1, 2, 3, 4}:
        raise FlowError("Flow devolvió un estado de pago desconocido.")
    payment_status = {1: "pending", 2: "paid", 3: "rejected", 4: "cancelled"}[status]

    with transaction.atomic():
        appointment = Appointment.objects.select_for_update().get(pk=appointment.pk)
        if appointment.payment_status != "paid":
            appointment.payment_status = payment_status
            appointment.paid = payment_status == "paid"
            appointment.flow_order = str(status_data.get("flowOrder", ""))[:30]
            appointment.save(update_fields=["payment_status", "paid", "flow_order"])
    return appointment
