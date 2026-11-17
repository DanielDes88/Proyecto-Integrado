"""Datos, consultas y operaciones del prototipo. No procesa dinero real."""
import uuid
from datetime import date, datetime, time, timedelta
from django.db import transaction
from django.utils import timezone
from .models import Service, DemoWorkspace, Appointment, Applicant, Review, Availability, UserProfile, TripLocation

DAYS = ['Lunes','Martes','Miércoles','Jueves','Viernes','Sábado','Domingo']
TIMES = ['09:00','10:00','11:30','14:00','16:00']
ADDRESSES = ['Domicilio de demostración','Segundo domicilio de demostración']
COMMENTS = ['La visita fue puntual y la atención muy amable.', 'La atención fue clara y bien organizada.', 'Me gustaría recibir más información antes de la visita.']

class DemoError(Exception):
    def __init__(self, message, status=400): self.message, self.status = message, status

def seed_workspace(w):
    services = list(Service.objects.order_by('id'))
    if len(services) < 4: raise DemoError('Falta el catálogo. Ejecuta python manage.py seed_demo.', 503)
    today = timezone.localdate()
    for s, delta, hour, status in [(services[0],2,'10:00','Confirmada'),(services[3],-3,'11:30','Finalizada')]:
        Appointment.objects.create(workspace=w, service=s, date=today+timedelta(days=delta), time=hour, status=status, address=ADDRESSES[0], price=s.price, duration=s.duration)
    Applicant.objects.bulk_create([Applicant(workspace=w,name='Valentina Rojas',area='Enfermería',experience='5 años'), Applicant(workspace=w,name='Diego Muñoz',area='Kinesiología',experience='3 años')])
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
    if p.role == 'admin':
        accounts = [{'name': x.user.get_full_name(), 'email':x.user.email, 'role':x.get_role_display(), 'active':x.user.is_active} for x in UserProfile.objects.filter(workspace=w).select_related('user')]
    return {
      'appointments': [{'id':a.code,'service':a.service_id,'date':a.date.isoformat(),'time':a.time.strftime('%H:%M'),'address':a.address,'status':a.status,'paid':a.paid,'price':a.price,'patient':a.patient.get_full_name() if a.patient else 'Sin asignar','professional':a.professional.get_full_name() if a.professional else 'Sin asignar'} for a in qs.select_related('patient','professional')],
      'applicants': list(Applicant.objects.filter(workspace=w).values('id','name','area','experience','status')) if p.role=='admin' else [],
      'reviews': [{'id':x.pk,'appointment':x.appointment.code,'rating':x.rating,'comment':x.comment,'status':x.status} for x in reviews],
      'slots': [{'id':x.pk,'label':f'{x.weekday} · {x.start:%H:%M} a {x.end:%H:%M}'} for x in slots],
      'bill':p.bill_sent,
      'bills':list(UserProfile.objects.filter(workspace=w,role='profesional',bill_sent=True).values('user__first_name','user__last_name')) if p.role=='admin' else [],
      'accounts':accounts,
    }

def catalog():
    return [{'id':s.pk,'name':s.name,'category':s.category,'icon':s.icon,'price':s.price,'time':f'{s.duration} min','code':s.code,'desc':s.description} for s in Service.objects.all()]

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
def act(w, payload, user):
    role = profile(user).role
    action = payload.get('action')
    actions = {
        'paciente': {'reserve','cancel','review'},
        'profesional': {'advance','slot_add','slot_remove','bill'},
        'admin': {'approve','reject','review_approve'},
    }
    if action not in actions.get(role,set()): raise DemoError('Tu perfil no tiene permiso para esta acción.',403)
    w = DemoWorkspace.objects.select_for_update().get(pk=w.pk)
    result = {}
    if action == 'reserve':
        try: key = uuid.UUID(str(payload.get('payment_key')))
        except (ValueError,TypeError): raise DemoError('Identificador de pago simulado inválido.')
        old = Appointment.objects.filter(workspace=w, patient=user, payment_key=key).first()
        if old: return {'state':serialize(w,user), 'appointment_id':old.code}
        if payload.get('accepted') is not True: raise DemoError('Debes aceptar las condiciones de demostración.')
        s = Service.objects.filter(pk=integer(payload.get('service'))).first()
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
        if not professional: raise DemoError('No hay un profesional de demostración disponible.',409)
        # El precio se toma del catálogo, nunca de un total enviado por el navegador.
        a = Appointment.objects.create(workspace=w,patient=user,professional=professional.user,service=s,date=day,time=hour,address=address,price=s.price,duration=s.duration,payment_key=key,conditions_accepted=True)
        result['appointment_id'] = a.code
    elif action in ['cancel','advance']:
        a = appointment(w,payload.get('id'),user)
        if action == 'cancel':
            if a.status != 'Confirmada': raise DemoError('Solo se puede cancelar una visita confirmada.',409)
            a.status = 'Cancelada'
        else:
            transitions = {'Confirmada':'En camino','En camino':'En atención','En atención':'Finalizada'}
            if a.status not in transitions: raise DemoError('La atención no admite otro avance.',409)
            # Evita que un reintento con una vista antigua avance dos estados.
            if payload.get('expected_status') != a.status: raise DemoError('El estado cambió. Actualiza la vista.',409)
            a.status = transitions[a.status]
        a.save(update_fields=['status'])
        if a.status != 'En camino':
            TripLocation.objects.filter(appointment=a).delete()
    elif action in ['approve','reject']:
        a = Applicant.objects.filter(workspace=w,pk=integer(payload.get('id'))).first()
        if not a: raise DemoError('Postulación no encontrada.',404)
        if a.status != 'Pendiente': raise DemoError('La postulación ya tiene una decisión.',409)
        a.status = 'Aprobado' if action == 'approve' else 'Rechazado'; a.save(update_fields=['status'])
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
        if not 1 <= rating <= 5 or comment not in COMMENTS: raise DemoError('Evaluación inválida.')
        if Review.objects.filter(appointment=a).exists(): raise DemoError('La atención ya fue evaluada.',409)
        Review.objects.create(appointment=a,rating=rating,comment=comment)
    elif action == 'review_approve':
        r = Review.objects.filter(appointment__workspace=w,pk=integer(payload.get('id'))).first()
        if not r: raise DemoError('Evaluación no encontrada.',404)
        r.status='Aprobado'; r.save(update_fields=['status'])
    else: raise DemoError('Acción no reconocida.')
    result['state'] = serialize(w,user)
    return result
