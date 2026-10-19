"""Permisos por rol, acceso a objetos y recorridos del prototipo."""
import uuid
from datetime import timedelta
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.cache import cache
from django.utils import timezone
from .models import Appointment, Service, UserProfile

class RoleTests(TestCase):
    @classmethod
    def setUpTestData(cls): call_command('preparar_demo', verbosity=0)
    def setUp(self):
        cache.clear()
        self.clients={}
        for role in ['paciente','profesional','admin']:
            c=Client(enforce_csrf_checks=True);c.force_login(get_user_model().objects.get(username=role));c.get('/portal/'+role+'/');self.clients[role]=c
        self.client=self.clients['paciente']
    def post(self, action, role='paciente', **data):
        c=self.clients[role]
        return c.post('/api/action/',{'action':action,**data},content_type='application/json',HTTP_X_CSRFTOKEN=c.cookies['csrftoken'].value)
    def state(self,role='paciente'):return self.clients[role].get('/api/state/').json()['state']
    def data(self,**changes):return {'service':Service.objects.first().pk,'date':(timezone.localdate()+timedelta(days=10)).isoformat(),'time':'09:00','address':'Domicilio de demostración','accepted':True,'payment_key':str(uuid.uuid4()),**changes}
    def test_login_redirects_each_role(self):
        for role in self.clients:
            c=Client();r=c.post('/login/',{'username':role,'password':'GoClinical2026!'})
            self.assertRedirects(r,'/portal/'+role+'/')
    def test_wrong_password_and_login_throttle(self):
        c=Client()
        for i in range(11):r=c.post('/login/',{'username':'paciente','password':'incorrecta'})
        self.assertContains(r,'Demasiados intentos')
        self.assertNotIn('_auth_user_id',c.session)
    def test_anonymous_has_no_data(self):
        c=Client();r=c.get('/');self.assertContains(r,'Cuidados profesionales');self.assertNotContains(r,'id="bootstrap"');self.assertEqual(c.get('/api/state/').status_code,401)
        self.assertContains(r,'Atención de enfermería')
        self.assertRedirects(c.get('/portal/paciente/'),'/login/')
        for role,client in self.clients.items():
            self.assertContains(client.get('/'),'Ir a mi portal')
    def test_other_portals_forbidden(self):
        for role,c in self.clients.items():
            self.assertContains(c.get('/portal/'+role+'/'),'id="bootstrap"')
            for other in self.clients:
                if other!=role:self.assertEqual(c.get('/portal/'+other+'/').status_code,403)
    def test_forbidden_actions(self):
        for action in ['advance','approve','slot_add','bill','review_approve']:
            self.assertEqual(self.post(action).status_code,403)
        for action in ['reserve','cancel','approve','review']:
            self.assertEqual(self.post(action,role='profesional').status_code,403)
        self.assertEqual(self.post('reserve',role='admin').status_code,403)
    def test_ownership_filter_and_foreign_id(self):
        user=get_user_model().objects.create_user('otro',password='Demo123456!')
        p=UserProfile.objects.get(user__username='paciente')
        UserProfile.objects.create(user=user,role='paciente',workspace=p.workspace)
        c=Client();c.force_login(user)
        self.assertEqual(c.get('/api/state/').json()['state']['appointments'],[])
        a=self.state()['appointments'][0]
        self.assertEqual(c.post('/api/action/',{'action':'cancel','id':a['id']},content_type='application/json').status_code,404)
    def test_professional_assignment_scope(self):
        user=get_user_model().objects.create_user('otropro',password='Demo123456!')
        p=UserProfile.objects.get(user__username='profesional')
        UserProfile.objects.create(user=user,role='profesional',workspace=p.workspace)
        c=Client();c.force_login(user)
        self.assertEqual(c.get('/api/state/').json()['state']['appointments'],[])
        a=next(a for a in self.state()['appointments'] if a['status']=='Confirmada')
        self.assertEqual(c.post('/api/action/',{'action':'advance','id':a['id'],'expected_status':'Confirmada'},content_type='application/json').status_code,404)
    def test_create_persistence_and_shared_visibility(self):
        response=self.post('reserve',**self.data());self.assertEqual(response.status_code,200)
        code=response.json()['appointment_id']
        for role in self.clients:self.assertIn(code,[a['id'] for a in self.state(role)['appointments']])
        self.client.get('/portal/paciente/')
        self.assertIn(code,[a['id'] for a in self.state()['appointments']])
    def test_price_and_idempotency(self):
        data=self.data(price=1)
        r=self.post('reserve',**data);self.assertEqual(r.status_code,200)
        again=self.post('reserve',**data);self.assertEqual(again.json()['appointment_id'],r.json()['appointment_id'])
        a=Appointment.objects.get(payment_key=data['payment_key']);self.assertEqual(a.price,a.service.price)
    def test_reservation_validation_and_conflict(self):
        self.assertEqual(self.post('reserve',**self.data(accepted=False)).status_code,400)
        self.assertEqual(self.post('reserve',**self.data(date=timezone.localdate().isoformat())).status_code,400)
        self.assertEqual(self.post('reserve',**self.data()).status_code,200)
        self.assertEqual(self.post('reserve',**self.data()).status_code,409)
    def test_advancement_and_review_moderation(self):
        a=next(a for a in self.state()['appointments'] if a['status']=='Confirmada')
        for status in ['Confirmada','En camino','En atención']:
            self.assertEqual(self.post('advance',role='profesional',id=a['id'],expected_status=status).status_code,200)
        self.assertEqual(self.post('advance',role='profesional',id=a['id'],expected_status='Confirmada').status_code,409)
        r=self.post('review',id=a['id'],rating=5,comment='La visita fue puntual y la atención muy amable.')
        self.assertEqual(r.status_code,200);review=r.json()['state']['reviews'][0]
        self.assertEqual(self.state('profesional')['reviews'],[])
        self.assertEqual(self.post('review_approve',role='admin',id=review['id']).status_code,200)
        self.assertEqual(self.state('profesional')['reviews'][0]['status'],'Aprobado')
    def test_cancellation(self):
        a=next(a for a in self.state()['appointments'] if a['status']=='Confirmada')
        self.assertEqual(self.post('cancel',id=a['id']).status_code,200)
        self.assertEqual(self.post('advance',role='profesional',id=a['id'],expected_status='Cancelada').status_code,409)
    def test_availability_and_bill(self):
        self.assertEqual(self.post('slot_add',role='profesional',weekday='Martes',**{'from':'09:00','to':'12:00'}).status_code,200)
        self.assertEqual(self.post('slot_add',role='profesional',weekday='Martes',**{'from':'10:00','to':'11:00'}).status_code,409)
        self.assertEqual(self.post('bill',role='profesional').status_code,200)
        self.assertEqual(len(self.state('admin')['bills']),1)
    def test_postulation_and_private_collections(self):
        self.assertEqual(self.state()['applicants'],[])
        self.assertEqual(self.state('profesional')['accounts'],[])
        a=self.state('admin')['applicants'][0]
        self.assertEqual(self.post('approve',role='admin',id=a['id']).status_code,200)
    def test_csrf_logout_and_admin(self):
        self.assertEqual(self.client.post('/api/action/',{'action':'reserve'},content_type='application/json').status_code,403)
        self.assertEqual(self.client.get('/logout/').status_code,405)
        self.assertEqual(self.client.get('/admin/').status_code,302)
        self.client.post('/logout/',HTTP_X_CSRFTOKEN=self.client.cookies['csrftoken'].value)
        self.assertEqual(self.client.get('/api/state/').status_code,401)
    def test_seed_repeat_does_not_reset_password(self):
        user=get_user_model().objects.get(username='paciente');user.set_password('OtraClave123!');user.save()
        count=Appointment.objects.count();call_command('preparar_demo',verbosity=0)
        user.refresh_from_db();self.assertTrue(user.check_password('OtraClave123!'));self.assertEqual(Appointment.objects.count(),count)
