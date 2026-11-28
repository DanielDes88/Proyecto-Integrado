"""Datos, consultas y operaciones del prototipo. No procesa dinero real."""
import uuid
from datetime import date, datetime, time, timedelta
from django.db import transaction
from django.utils import timezone
from .models import Service, DemoWorkspace, Appointment, Applicant, Review, Availability, UserProfile, UserRoleChange, TripLocation

DAYS = ['Lunes','Martes','Miércoles','Jueves','Viernes','Sábado','Domingo']
TIMES = ['09:00','10:00','11:30','14:00','16:00']
ADDRESSES = ['Domicilio de demostración','Segundo domicilio de demostración']
COMMENTS = ['La visita fue puntual y la atención muy amable.', 'La atención fue clara y bien organizada.', 'Me gustaría recibir más información antes de la visita.']
PROFESSIONAL_UNAVAILABLE_NOTICE = 'Esta atención fue cancelada porque el profesional ya no está disponible. Por favor, vuelve a agendar este servicio desde el catálogo.'

class DemoError(Exception):
    def __init__(self, message, status=400): self.message, self.status = message, status

def seed_workspace(w):
    services = list(Service.objects.defer('image_data').filter(is_active=True).order_by('id'))
    today = timezone.localdate()
    examples = []
    if services:
        examples = [(services[0],2,'10:00','Confirmada'),(services[min(3, len(services)-1)],-3,'11:30','Finalizada')]
    for s, delta, hour, status in examples:
        Appointment.objects.create(workspace=w, service=s, date=today+timedelta(days=delta), time=hour, status=status, address=ADDRESSES[0], price=s.price, duration=s.duration, paid=True, payment_status='paid')
    Availability.objects.bulk_create([Availability(workspace=w,weekday='Lunes',start='09:00',end='13:00'), Availability(workspace=w,weekday='Miércoles',start='14:00',end='18:00')])

def profile(user):
    if not user.is_authenticated: raise DemoError('Inicia sesión para continuar.',401)
    try: return user.clinical_profile
    except UserProfile.DoesNotExist: raise DemoError('Esta cuenta no tiene un perfil GoClinical asignado.',403)

def workspace(request): return profile(request.user).workspace

def allowed_appointments(w, user):
    role = profile(user).role
    qs = Appointment.objects.filter(workspace=w)
    if role == 'paciente': qs = qs.filter(patient=user)
    elif role == 'profesional': qs = qs.filter(professional=user)
    return qs

def serialize(w, user):
    p = profile(user); qs = allowed_appointments(w,user)
    reviews = Review.objects.select_related('appointment').filter(appointment__in=qs)
    if p.role == 'profesional': reviews = reviews.filter(status='Aprobado')
    slots = Availability.objects.filter(workspace=w)
    if p.role == 'profesional': slots = slots.filter(professional=user)
    elif p.role == 'paciente': slots = slots.none()
    accounts = []
    applicants = []
    my_application = None
    if p.role == 'admin':
        accounts = [{'id':x.user_id,'name':x.user.get_full_name(), 'email':x.user.email, 'role':x.get_role_display(), 'role_key':x.role, 'admin_level':x.admin_level, 'admin_level_label':x.get_admin_level_display(), 'active':x.user.is_active} for x in UserProfile.objects.filter(workspace=w).select_related('user')]
        applications = Applicant.objects.filter(workspace=w,user__isnull=False).select_related('user').prefetch_related('documents')
        applicants = [{
            'id': a.pk,
            'name': a.name,
            'email': a.user.email,
            'area': a.area,
            'experience': a.experience,
            'has_vehicle': a.has_vehicle,
            'status': a.status,
            'submitted_at': a.submitted_at.isoformat() if a.submitted_at else None,
            'documents': [{
                'id': document.pk,
                'document_type': document.document_type,
                'name': document.original_name,
                'size': document.size,
            } for document in a.documents.all()],
        } for a in applications]
    elif p.role == 'paciente':
        application = Applicant.objects.filter(workspace=w,user=user).order_by('-submitted_at','-pk').first()
        if application:
            my_application = {
                'status': application.status,
                'area': application.area,
                'experience': application.experience,
                'has_vehicle': application.has_vehicle,
                'submitted_at': application.submitted_at.isoformat() if application.submitted_at else None,
            }
    return {
      'appointments': [{'id':a.code,'service':a.service_id,'date':a.date.isoformat(),'time':a.time.strftime('%H:%M'),'address':a.address,'status':a.status,'patient_notice':a.patient_notice,'paid':a.paid,'payment_status':a.payment_status,'price':a.price,'patient':a.patient.get_full_name() if a.patient else 'Sin asignar','professional':a.professional.get_full_name() if a.professional else 'Sin asignar'} for a in qs.select_related('patient','professional')],
      'applicants': applicants,
      'my_application': my_application,
      'reviews': [{'id':x.pk,'appointment':x.appointment.code,'professional':x.professional.get_full_name() if x.professional else 'Sin asignar','rating':x.rating,'comment':x.comment,'status':x.status,'created_at':x.created_at.isoformat()} for x in reviews],
      'slots': [{'id':x.pk,'label':f'{x.weekday} · {x.start:%H:%M} a {x.end:%H:%M}'} for x in slots],
      'bill':p.bill_sent,
      'bills':list(UserProfile.objects.filter(workspace=w,role='profesional',bill_sent=True).values('user__first_name','user__last_name')) if p.role=='admin' else [],
      'accounts':accounts,
    }

def catalog(include_inactive=False):
    services = Service.objects.defer('image_data')
    if not include_inactive:
        services = services.filter(is_active=True)
    return [{
        'id': service.pk,
        'name': service.name,
        'is_active': service.is_active,
        'duration': service.duration,
        'category': service.category,
        'icon': service.icon,
        'price': service.price,
        'price_label': f"${service.price:,} CLP".replace(",", "."),
        'time': f'{service.duration} min',
        'code': service.code,
        'desc': service.description,
        'image_url': service.image_url,
        'revision': str(service.revision),
    } for service in services]


def appointment(w, code, user):
    if not isinstance(code,str) or not code.startswith('GC-') or not code[3:].isdigit(): raise DemoError('Atención no encontrada.',404)
    a = allowed_appointments(w,user).filter(pk=int(code[3:])).first()
    if not a: raise DemoError('Atención no encontrada.',404)
    return a

def integer(value):
    if isinstance(value,bool): raise DemoError('Identificador inválido.')
    try: return int(value)
    except (ValueError,TypeError,OverflowError): raise DemoError('Valor numérico inválido.')


@transaction.atomic
def create_reservation(w, payload, user):
    if profile(user).role != 'paciente': raise DemoError('Tu perfil no tiene permiso para reservar.',403)
    w = DemoWorkspace.objects.select_for_update().get(pk=w.pk)
    try: key = uuid.UUID(str(payload.get('payment_key')))
    except (ValueError,TypeError): raise DemoError('Identificador de pago inválido.')
    old = Appointment.objects.filter(workspace=w, patient=user, payment_key=key).first()
    if old:
        if old.status == 'Cancelada': raise DemoError('Esta reserva ya fue cancelada.',409)
        return old
    if payload.get('accepted') is not True: raise DemoError('Debes aceptar las condiciones antes de continuar.')
    s = Service.objects.select_for_update().defer('image_data').filter(pk=integer(payload.get('service')), is_active=True).first()
    if not s: raise DemoError('Servicio no disponible.')
    try: day = date.fromisoformat(str(payload.get('date')))
    except ValueError: raise DemoError('Fecha inválida.')
    if day <= timezone.localdate(): raise DemoError('Elige una fecha desde mañana.')
    if day > timezone.localdate()+timedelta(days=365): raise DemoError('Selecciona una fecha dentro del próximo año.')
    hour = payload.get('time')
    address = payload.get('address')
    if hour not in TIMES or address not in ADDRESSES: raise DemoError('Horario o dirección de ejemplo inválidos.')
    start = datetime.combine(day,time.fromisoformat(hour)); end = start+timedelta(minutes=s.duration)
    for existing in Appointment.objects.filter(workspace=w,date=day).exclude(status='Cancelada'):
        other = datetime.combine(day,existing.time)
        if start < other+timedelta(minutes=existing.duration) and end > other:
            raise DemoError('El horario se superpone con otra visita. Selecciona otro.',409)
    professional = UserProfile.objects.filter(workspace=w,role='profesional',user__is_active=True).select_related('user').first()
    if not professional: raise DemoError('No hay un profesional disponible.',409)
    return Appointment.objects.create(
        workspace=w,patient=user,professional=professional.user,service=s,date=day,time=hour,
        address=address,price=s.price,duration=s.duration,payment_key=key,
        conditions_accepted=True,paid=False,payment_status='pending',
    )


@transaction.atomic
def act(w, payload, user):
    user_profile = profile(user)
    role = user_profile.role
    action = payload.get('action')
    actions = {
        'paciente': {'cancel','review'},
        'profesional': {'advance','slot_add','slot_remove','bill'},
        'admin': {'approve','reject','review_approve'},
    }
    if action == 'set_user_role':
        if role != 'admin' or user_profile.admin_level != 'super_admin':
            raise DemoError('Solo un superadministrador puede cambiar roles.',403)
    elif action not in actions.get(role,set()):
        raise DemoError('Tu perfil no tiene permiso para esta acción.',403)
    w = DemoWorkspace.objects.select_for_update().get(pk=w.pk)
    result = {}
    if action == 'set_user_role':
        target_id = integer(payload.get('user_id'))
        new_role = payload.get('target_role')
        new_admin_level = payload.get('admin_level')
        if new_role not in {'paciente','admin'}:
            raise DemoError('Solo se puede asignar el rol de paciente o administrador.')
        if new_admin_level not in {'normal','super_admin'}:
            raise DemoError('Selecciona un nivel de administrador válido.')
        if new_role == 'paciente' and new_admin_level != 'normal':
            raise DemoError('Una cuenta de paciente no puede tener nivel de administrador.')
        target = UserProfile.objects.select_for_update().filter(workspace=w,user_id=target_id).select_related('user').first()
        if not target:
            raise DemoError('La cuenta no existe en esta clínica.',404)
        if target.user_id == user.pk:
            raise DemoError('No puedes cambiar tu propio rol.',403)
        if target.role == 'profesional' and new_role != 'paciente':
            raise DemoError('Un profesional solo puede volver al rol de paciente.')
        if target.role not in {'paciente','admin','profesional'}:
            raise DemoError('Solo se pueden cambiar roles de pacientes, profesionales y administradores.')
        if target.role == new_role and target.admin_level == new_admin_level:
            raise DemoError('La cuenta ya tiene ese rol y nivel.',409)
        if target.role == 'profesional':
            in_progress = Appointment.objects.filter(
                workspace=w,
                professional_id=target.user_id,
                status__in=['En camino','En atención'],
            ).exists()
            if in_progress:
                raise DemoError('No se puede convertir al profesional mientras tenga una atención en curso.',409)
            Appointment.objects.filter(
                workspace=w,
                professional_id=target.user_id,
                status='Confirmada',
            ).update(
                status='Cancelada',
                professional=None,
                patient_notice=PROFESSIONAL_UNAVAILABLE_NOTICE,
            )
            Availability.objects.filter(workspace=w,professional_id=target.user_id).delete()
        UserRoleChange.objects.create(
            workspace=w,
            changed_by=user,
            target_user=target.user,
            previous_role=target.role,
            new_role=new_role,
            previous_admin_level=target.admin_level,
            new_admin_level=new_admin_level,
        )
        target.role = new_role
        target.admin_level = new_admin_level
        target.save(update_fields=['role','admin_level'])
    elif action in ['cancel','advance']:
        a = appointment(w,payload.get('id'),user)
        if action == 'cancel':
            if a.status != 'Confirmada': raise DemoError('Solo se puede cancelar una visita confirmada.',409)
            a.status = 'Cancelada'
        else:
            if not a.paid: raise DemoError('La atención requiere un pago confirmado.',409)
            transitions = {'Confirmada':'En camino','En camino':'En atención','En atención':'Finalizada'}
            if a.status not in transitions: raise DemoError('La atención no admite otro avance.',409)
            # Evita que un reintento con una vista antigua avance dos estados.
            if payload.get('expected_status') != a.status: raise DemoError('El estado cambió. Actualiza la vista.',409)
            a.status = transitions[a.status]
        a.save(update_fields=['status'])
        if a.status != 'En camino':
            TripLocation.objects.filter(appointment=a).delete()
    elif action in ['approve','reject']:
        a = Applicant.objects.select_for_update().filter(workspace=w,pk=integer(payload.get('id'))).first()
        if not a: raise DemoError('Postulación no encontrada.',404)
        if a.status != 'Pendiente': raise DemoError('La postulación ya tiene una decisión.',409)
        if not a.user_id: raise DemoError('Esta postulación no está vinculada a una cuenta.',409)
        a.status = 'Aprobado' if action == 'approve' else 'Rechazado'
        a.reviewed_by = user
        a.reviewed_at = timezone.now()
        a.save(update_fields=['status','reviewed_by','reviewed_at'])
        if action == 'approve':
            target = UserProfile.objects.select_for_update().filter(workspace=w,user_id=a.user_id).first()
            if not target or target.role != 'paciente':
                raise DemoError('La cuenta vinculada ya no es un paciente de esta clínica.',409)
            UserRoleChange.objects.create(
                workspace=w,
                changed_by=user,
                target_user_id=target.user_id,
                previous_role=target.role,
                new_role='profesional',
                previous_admin_level=target.admin_level,
                new_admin_level='normal',
            )
            target.role = 'profesional'
            target.admin_level = 'normal'
            target.save(update_fields=['role','admin_level'])
    elif action == 'slot_add':
        weekday = payload.get('weekday')
        try:
            start = time.fromisoformat(str(payload.get('from'))); end = time.fromisoformat(str(payload.get('to')))
        except ValueError: raise DemoError('Horario inválido.')
        if weekday not in DAYS or start >= end: raise DemoError('El día o rango horario no son válidos.')
        if Availability.objects.filter(workspace=w,professional=user,weekday=weekday,start__lt=end,end__gt=start).exists(): raise DemoError('El bloque se superpone con otro.',409)
        Availability.objects.create(workspace=w,professional=user,weekday=weekday,start=start,end=end)
    elif action == 'slot_remove':
        removed,_ = Availability.objects.filter(workspace=w,professional=user,pk=integer(payload.get('id'))).delete()
        if not removed: raise DemoError('Bloque no encontrado.',404)
    elif action == 'bill':
        if not allowed_appointments(w,user).filter(status='Finalizada').exists(): raise DemoError('No hay honorarios por atenciones finalizadas.')
        p = profile(user); p.bill_sent = True; p.save(update_fields=['bill_sent'])
    elif action == 'review':
        a = appointment(w,payload.get('id'),user); rating = integer(payload.get('rating')); comment = payload.get('comment')
        if a.status != 'Finalizada': raise DemoError('Solo puedes evaluar una atención finalizada.',409)
        if not isinstance(comment,str): raise DemoError('El comentario no es válido.')
        comment = comment.strip()
        if not 1 <= rating <= 5: raise DemoError('Selecciona una puntuación entre 1 y 5.')
        if not comment: raise DemoError('Escribe un comentario sobre la atención.')
        if len(comment) > 300: raise DemoError('El comentario no puede superar los 300 caracteres.',400)
        if Review.objects.filter(appointment=a).exists(): raise DemoError('La atención ya fue evaluada.',409)
        Review.objects.create(appointment=a, professional=a.professional, rating=rating, comment=comment)
    elif action == 'review_approve':
        r = Review.objects.filter(appointment__workspace=w,pk=integer(payload.get('id'))).first()
        if not r: raise DemoError('Evaluación no encontrada.',404)
        r.status='Aprobado'; r.save(update_fields=['status'])
    else: raise DemoError('Acción no reconocida.')
    result['state'] = serialize(w,user)
    return result
