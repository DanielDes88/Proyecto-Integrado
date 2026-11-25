import json
import logging
import re
from django.conf import settings
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.core.cache import cache
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from django.views.decorators.cache import never_cache
from django.db import IntegrityError, OperationalError, transaction
from django.urls import reverse
from django.utils.text import get_valid_filename
from .demo import workspace, serialize, catalog, act, create_reservation, DemoError, profile
from .document_store import delete_document, read_document, save_document
from .flow import FlowError, confirm_payment, create_payment, validate_configuration
from .forms import PatientRegistrationForm
from .models import Applicant, ApplicantDocument, Appointment, ClinicalDocument, DemoWorkspace, UserProfile
logger = logging.getLogger(__name__)
MAX_DOCUMENT_SIZE = 10 * 1024 * 1024
DOCUMENT_CATEGORIES = {label for value, label in ClinicalDocument.CATEGORIES}

@ensure_csrf_cookie
@never_cache
@require_GET
def index(request):
    return render(request, 'clinical/public.html', {'services': catalog()})

@ensure_csrf_cookie
@never_cache
@require_GET
def portal(request, role):
    if not request.user.is_authenticated: return redirect('login')
    try:
        p = profile(request.user)
        if role != p.role: return HttpResponse('No tienes permiso para acceder a este portal.', status=403)
        w = workspace(request)
        return render(request, 'clinical/index.html', {'bootstrap': {'maps': {'key': settings.GOOGLE_MAPS_BROWSER_KEY, 'mapId': settings.GOOGLE_MAPS_MAP_ID} if p.role == 'paciente' else {}, 'services':catalog(), 'state':serialize(w, request.user), 'user': {'id':request.user.pk, 'role':p.role, 'admin_level':p.admin_level, 'name':request.user.get_full_name(), 'email':request.user.email, 'username':request.user.username, 'date_of_birth':p.date_of_birth.isoformat() if p.date_of_birth else '', 'phone':p.phone, 'address':p.address, 'city':p.city, 'is_staff':request.user.is_staff}}})
    except DemoError as e:
        return HttpResponse(e.message, status=e.status, content_type='text/plain; charset=utf-8')

@never_cache
@require_GET
def state_view(request):
    try: return JsonResponse({'state':serialize(workspace(request), request.user), 'services':catalog()})
    except DemoError as e: return JsonResponse({'error':e.message},status=e.status)

@never_cache
@require_GET
def documents_view(request):
    try:
        p = profile(request.user)
        documents = ClinicalDocument.objects.select_related('patient', 'appointment', 'uploaded_by')
        if p.role == 'paciente': documents = documents.filter(patient=request.user)
        elif p.role == 'profesional': documents = documents.filter(appointment__professional=request.user)
        else: documents = documents.filter(uploaded_by=request.user)
        return JsonResponse({'documents': [{
            'id': d.pk, 'category': d.category, 'name': d.original_name,
            'appointment': d.appointment_id, 'patient': d.patient.get_full_name(),
            'uploaded_by': d.uploaded_by.get_full_name(), 'created_at': d.created_at.isoformat(),
            'size': d.size,
        } for d in documents]})
    except DemoError as e: return JsonResponse({'error':e.message},status=e.status)

@never_cache
@require_POST
def document_upload_view(request):
    try:
        p = profile(request.user)
        uploaded = request.FILES.get('file')
        if not uploaded: return JsonResponse({'error':'Selecciona un archivo.'},status=400)
        if uploaded.size > MAX_DOCUMENT_SIZE:
            return JsonResponse({'error':'El archivo supera el límite de 10 MiB.'},status=413)
        category = request.POST.get('category', '')
        if category not in DOCUMENT_CATEGORIES:
            return JsonResponse({'error':'Selecciona una categoría válida.'},status=400)
        match = re.fullmatch(r'GC-(\d+)', request.POST.get('appointment', ''))
        if not match: return JsonResponse({'error':'Selecciona una atención válida.'},status=400)
        appointments = Appointment.objects.filter(workspace=p.workspace, pk=int(match.group(1)))
        if p.role == 'paciente': appointments = appointments.filter(patient=request.user)
        elif p.role == 'profesional': appointments = appointments.filter(professional=request.user)
        appointment = appointments.select_related('patient').first()
        if not appointment or not appointment.patient_id:
            return JsonResponse({'error':'No tienes permiso para asociar el documento a esa atención.'},status=404)
        data = uploaded.read(MAX_DOCUMENT_SIZE + 1)
        if len(data) > MAX_DOCUMENT_SIZE:
            return JsonResponse({'error':'El archivo supera el límite de 10 MiB.'},status=413)
        if data.startswith(b'%PDF-'): content_type = 'application/pdf'
        elif data.startswith(b'\x89PNG\r\n\x1a\n'): content_type = 'image/png'
        elif data.startswith(b'\xff\xd8\xff'): content_type = 'image/jpeg'
        else: return JsonResponse({'error':'Solo se aceptan PDF, PNG o JPEG válidos.'},status=400)
        filename = get_valid_filename(uploaded.name)[:120] or 'documento'
        mongo_id = save_document(data, content_type)
        try:
            ClinicalDocument.objects.create(
                patient=appointment.patient, appointment=appointment, uploaded_by=request.user,
                category=category, original_name=filename, content_type=content_type,
                size=len(data), mongo_id=mongo_id,
            )
        except Exception:
            try: delete_document(mongo_id)
            except Exception: logger.exception('No se pudo limpiar un archivo MongoDB huérfano')
            raise
        return JsonResponse({'ok':True})
    except DemoError as e: return JsonResponse({'error':e.message},status=e.status)
    except Exception:
        logger.exception('No se pudo guardar el documento clínico')
        return JsonResponse({'error':'No se pudo guardar el documento. Revisa la conexión con MongoDB e inténtalo nuevamente.'},status=503)

@never_cache
@require_GET
def document_download_view(request, document_id):
    try:
        p = profile(request.user)
        documents = ClinicalDocument.objects.filter(pk=document_id)
        if p.role == 'paciente': documents = documents.filter(patient=request.user)
        elif p.role == 'profesional': documents = documents.filter(appointment__professional=request.user)
        else: documents = documents.filter(uploaded_by=request.user)
        document = documents.first()
        if not document: return HttpResponse(status=404)
        content = read_document(document.mongo_id)
        if content is None: return HttpResponse('Documento no disponible.',status=404)
        response = HttpResponse(content, content_type='application/octet-stream')
        response['Content-Disposition'] = f'attachment; filename="{document.original_name.replace(chr(34), "")}"'
        response['X-Content-Type-Options'] = 'nosniff'
        response['Cache-Control'] = 'private, no-store'
        return response
    except DemoError as e: return JsonResponse({'error':e.message},status=e.status)
    except Exception:
        logger.exception('No se pudo descargar el documento clínico')
        return HttpResponse('Almacenamiento de documentos no disponible.',status=503)

def _read_application_document(uploaded):
    if not uploaded:
        raise DemoError('Adjunta el título o certificado y el currículum vitae.')
    if uploaded.size > MAX_DOCUMENT_SIZE:
        raise DemoError('Cada documento debe pesar como máximo 10 MiB.',413)
    data = uploaded.read(MAX_DOCUMENT_SIZE + 1)
    if len(data) > MAX_DOCUMENT_SIZE:
        raise DemoError('Cada documento debe pesar como máximo 10 MiB.',413)
    if data.startswith(b'%PDF-'):
        content_type = 'application/pdf'
    elif data.startswith(b'\x89PNG\r\n\x1a\n'):
        content_type = 'image/png'
    elif data.startswith(b'\xff\xd8\xff'):
        content_type = 'image/jpeg'
    else:
        raise DemoError('Los documentos deben ser archivos PDF, PNG o JPEG válidos.')
    filename = get_valid_filename(uploaded.name)[:120] or 'documento'
    return data, content_type, filename


@never_cache
@require_POST
def professional_application_view(request):
    try:
        current_profile = profile(request.user)
        if current_profile.role != 'paciente':
            raise DemoError('Solo un paciente puede postular a profesional.',403)

        area = request.POST.get('area','').strip()
        experience = request.POST.get('experience','').strip()
        has_vehicle_value = request.POST.get('has_vehicle','')
        if not area or len(area) > 50:
            raise DemoError('Indica un área o especialidad de hasta 50 caracteres.')
        if not experience or len(experience) > 30:
            raise DemoError('Indica tus años de experiencia (máximo 30 caracteres).')
        if has_vehicle_value not in {'true','false'}:
            raise DemoError('Indica si dispones de vehículo propio.')
        documents = [
            ('Título o certificado', request.FILES.get('credential')),
            ('Currículum vitae', request.FILES.get('cv')),
        ]
        prepared_documents = [
            (document_type, *_read_application_document(uploaded))
            for document_type, uploaded in documents
        ]
        stored_ids = []
        try:
            with transaction.atomic():
                locked_profile = UserProfile.objects.select_for_update().get(user=request.user)
                if locked_profile.role != 'paciente':
                    raise DemoError('Solo un paciente puede postular a profesional.',403)
                if Applicant.objects.filter(
                    workspace=locked_profile.workspace,
                    user=request.user,
                    status='Pendiente',
                ).exists():
                    raise DemoError('Ya tienes una postulación pendiente.',409)

                applicant = Applicant.objects.create(
                    workspace=locked_profile.workspace,
                    user=request.user,
                    name=(request.user.get_full_name() or request.user.username)[:100],
                    area=area,
                    experience=experience,
                    has_vehicle=has_vehicle_value == 'true',
                )
                for document_type, data, content_type, filename in prepared_documents:
                    mongo_id = save_document(data, content_type)
                    stored_ids.append(mongo_id)
                    ApplicantDocument.objects.create(
                        applicant=applicant,
                        document_type=document_type,
                        original_name=filename,
                        content_type=content_type,
                        size=len(data),
                        mongo_id=mongo_id,
                    )
        except DemoError:
            for mongo_id in stored_ids:
                try:
                    delete_document(mongo_id)
                except Exception:
                    logger.exception('No se pudo limpiar un documento de postulación huérfano')
            raise
        except IntegrityError:
            for mongo_id in stored_ids:
                try:
                    delete_document(mongo_id)
                except Exception:
                    logger.exception('No se pudo limpiar un documento de postulación huérfano')
            raise DemoError('No se pudo guardar la postulación. Actualiza la página e inténtalo nuevamente.',409)
        except Exception:
            for mongo_id in stored_ids:
                try:
                    delete_document(mongo_id)
                except Exception:
                    logger.exception('No se pudo limpiar un documento de postulación huérfano')
            raise
        return JsonResponse({'ok':True},status=201)
    except DemoError as e:
        return JsonResponse({'error':e.message},status=e.status)
    except Exception:
        logger.exception('No se pudo guardar la postulación profesional')
        return JsonResponse({'error':'No se pudo guardar la postulación. Revisa la conexión e inténtalo nuevamente.'},status=503)


@never_cache
@require_GET
def applicant_document_download_view(request, applicant_id, document_id):
    try:
        current_profile = profile(request.user)
        if current_profile.role != 'admin':
            return HttpResponse('No tienes permiso para consultar estos antecedentes.',status=403)
        document = ApplicantDocument.objects.filter(
            pk=document_id,
            applicant_id=applicant_id,
            applicant__workspace=current_profile.workspace,
            applicant__user__isnull=False,
        ).first()
        if not document:
            return HttpResponse(status=404)
        content = read_document(document.mongo_id)
        if content is None:
            return HttpResponse('Documento no disponible.',status=404)
        response = HttpResponse(content,content_type='application/octet-stream')
        response['Content-Disposition'] = f'attachment; filename="{document.original_name.replace(chr(34), "")}"'
        response['X-Content-Type-Options'] = 'nosniff'
        response['Cache-Control'] = 'private, no-store'
        return response
    except DemoError as e:
        return JsonResponse({'error':e.message},status=e.status)
    except Exception:
        logger.exception('No se pudo descargar un documento de postulación')
        return HttpResponse('Almacenamiento de documentos no disponible.',status=503)


@never_cache
@require_POST
def action_view(request):
    if request.content_type != 'application/json': return JsonResponse({'error':'Se requiere JSON.'},status=415)
    if len(request.body) > 8192: return JsonResponse({'error':'Petición demasiado extensa.'},status=413)
    try:
        data = json.loads(request.body)
        if not isinstance(data,dict): raise ValueError()
    except (ValueError,UnicodeDecodeError): return JsonResponse({'error':'JSON inválido.'},status=400)
    try: return JsonResponse(act(workspace(request),data,request.user))
    except DemoError as e: return JsonResponse({'error':e.message},status=e.status)
    except IntegrityError: return JsonResponse({'error':'La operación entra en conflicto con un registro existente. Actualiza e intenta otra vez.'},status=409)
    except OperationalError:
        logger.exception('Fallo de base de datos en la demostración')
        return JsonResponse({'error':'No se pudo guardar. Intenta nuevamente en unos segundos.'},status=503)


@never_cache
@require_POST
def flow_checkout_view(request):
    if request.content_type != 'application/json': return JsonResponse({'error':'Se requiere JSON.'},status=415)
    if len(request.body) > 8192: return JsonResponse({'error':'Petición demasiado extensa.'},status=413)
    try:
        data = json.loads(request.body)
        if not isinstance(data,dict): raise ValueError()
    except (ValueError,UnicodeDecodeError): return JsonResponse({'error':'JSON inválido.'},status=400)
    try:
        p = profile(request.user)
        if p.role != 'paciente': raise DemoError('Solo un paciente puede iniciar un pago.',403)
        validate_configuration()
        if not request.user.email: raise DemoError('Tu cuenta necesita un correo antes de iniciar el pago.')
        appointment = create_reservation(p.workspace,data,request.user)
        if appointment.paid:
            return JsonResponse({'paid':True,'appointment_id':appointment.code})
        if appointment.payment_status != 'pending':
            return JsonResponse({'error':'Esta reserva ya no admite pagos. Crea una nueva reserva.'},status=409)
        if appointment.flow_token and appointment.flow_url:
            return JsonResponse({'redirect_url':appointment.flow_url,'appointment_id':appointment.code})
        payment = create_payment(appointment)
        appointment.flow_token = payment['token']
        appointment.flow_order = str(payment.get('flowOrder',''))[:30]
        appointment.flow_url = payment['payment_url']
        appointment.save(update_fields=['flow_token','flow_order','flow_url'])
        return JsonResponse({'redirect_url':appointment.flow_url,'appointment_id':appointment.code})
    except DemoError as e:
        return JsonResponse({'error':e.message},status=e.status)
    except FlowError as e:
        logger.exception('No se pudo iniciar el pago en Flow')
        return JsonResponse({'error':str(e)},status=503)
    except IntegrityError:
        return JsonResponse({'error':'El horario acaba de ser reservado. Selecciona otro.'},status=409)
    except OperationalError:
        logger.exception('Fallo de base de datos al iniciar el pago')
        return JsonResponse({'error':'No se pudo guardar la reserva. Intenta nuevamente.'},status=503)


@csrf_exempt
@never_cache
@require_POST
def flow_confirmation_view(request):
    token = request.POST.get('token','')
    if not token: return HttpResponse('Falta el token de Flow.',status=400)
    try:
        appointment = confirm_payment(token)
    except FlowError:
        logger.exception('No se pudo confirmar el pago notificado por Flow')
        return HttpResponse('No se pudo confirmar el pago.',status=503)
    if not appointment: return HttpResponse('Orden de pago no encontrada.',status=404)
    return HttpResponse('OK')


@csrf_exempt
@never_cache
@require_http_methods(["GET", "POST"])
def flow_return_view(request):
    result = 'error'
    token = request.GET.get('token') or request.POST.get('token','')
    if token:
        try:
            appointment = confirm_payment(token)
        except FlowError:
            logger.exception('No se pudo verificar el pago al volver desde Flow')
        else:
            if appointment:
                result = appointment.payment_status
    return redirect(f"{reverse('portal',kwargs={'role':'paciente'})}?flow_payment={result}#paciente")


def csrf_failure(request, reason=''):
    if request.path.startswith('/api/'):
        return JsonResponse({'error':'La sesión de seguridad cambió. Recarga la página.'},status=403)
    return HttpResponse('Solicitud rechazada. Recarga la página e inténtalo nuevamente.',status=403)

@ensure_csrf_cookie
@never_cache
def login_view(request):
    if request.user.is_authenticated:
        try: return redirect('portal', role=profile(request.user).role)
        except DemoError: logout(request)
    form = AuthenticationForm(request, data=request.POST or None)
    if request.method == 'POST':
        key = 'gc-login-' + request.META.get('REMOTE_ADDR','local')
        failures = cache.get(key,0)
        if failures >= 10:
            form.add_error(None,'Demasiados intentos. Espera cinco minutos.')
        elif form.is_valid():
            user = form.get_user()
            try: profile(user)
            except DemoError: form.add_error(None,'Cuenta sin perfil GoClinical. Solicita su configuración al administrador.')
            else:
                cache.delete(key); login(request,user)
                return redirect('portal',role=profile(user).role)
        else: cache.set(key,failures+1,300)
    return render(request,'clinical/login.html',{'form':form})

@ensure_csrf_cookie
@never_cache
@require_http_methods(["GET", "POST"])
def register_view(request):
    if request.user.is_authenticated:
        try:
            current_profile = profile(request.user)
        except DemoError:
            logout(request)
        else:
            return redirect('portal', role=current_profile.role)

    form = PatientRegistrationForm(request.POST if request.method == "POST" else None)
    response_status = 200
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                workspace_ids = list(
                    UserProfile.objects.filter(
                        role="admin",
                        admin_level="super_admin",
                        user__is_active=True,
                    )
                    .values_list("workspace_id", flat=True)
                    .distinct()[:2]
                )
                if len(workspace_ids) != 1:
                    raise DemoError(
                        "El registro no está disponible por el momento. Contacta a la clínica.",
                        503,
                    )

                user = form.save()
                UserProfile.objects.create(
                    user=user,
                    role="paciente",
                    workspace=DemoWorkspace.objects.get(pk=workspace_ids[0]),
                    date_of_birth=form.cleaned_data["date_of_birth"],
                    phone=form.cleaned_data["phone"],
                    address=form.cleaned_data["address"],
                    city=form.cleaned_data["city"],
                )
        except DemoError as e:
            form.add_error(None, e.message)
            response_status = e.status
        except IntegrityError:
            logger.exception("No se pudo crear una cuenta de paciente.")
            form.add_error(
                None,
                "No se pudo crear la cuenta con esos datos. Revisa el usuario y el correo e inténtalo nuevamente.",
            )
        else:
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            return redirect("portal", role="paciente")

    return render(request, "clinical/register.html", {"form": form}, status=response_status)

@require_POST
def logout_view(request):
    logout(request)
    return redirect('inicio')
