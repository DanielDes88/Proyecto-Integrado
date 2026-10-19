import json
import logging
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.core.cache import cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.cache import never_cache
from django.db import IntegrityError, OperationalError
from .demo import workspace, serialize, catalog, act, DemoError, profile
logger = logging.getLogger(__name__)

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
        return render(request, 'clinical/index.html', {'bootstrap': {'services':catalog(), 'state':serialize(w, request.user), 'user': {'role':p.role, 'name':request.user.get_full_name(), 'email':request.user.email, 'username':request.user.username, 'is_staff':request.user.is_staff}}})
    except DemoError as e:
        return HttpResponse(e.message, status=e.status, content_type='text/plain; charset=utf-8')

@never_cache
@require_GET
def state_view(request):
    try: return JsonResponse({'state':serialize(workspace(request), request.user), 'services':catalog()})
    except DemoError as e: return JsonResponse({'error':e.message},status=e.status)

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

@require_POST
def logout_view(request):
    logout(request)
    return redirect('inicio')
