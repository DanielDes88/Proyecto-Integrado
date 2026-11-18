"""Permisos por rol, acceso a objetos y recorridos del prototipo."""
import json
import uuid
from datetime import timedelta
from unittest.mock import patch
from django.test import TestCase, Client, override_settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from .flow import sign_params
from .models import Appointment, ClinicalDocument, Service, UserProfile


class FlowSignatureTests(TestCase):
    def test_signature_sorts_names_and_uses_hmac_sha256(self):
        import hashlib
        import hmac
        params={'currency':'CLP','amount':'5000','apiKey':'key'}
        expected=hmac.new(b'secret',b'amount5000apiKeykeycurrencyCLP',hashlib.sha256).hexdigest()
        self.assertEqual(sign_params(params,'secret'),expected)


class RoleTests(TestCase):
    @classmethod
    def setUpTestData(cls): call_command('preparar_demo', verbosity=0)
    def setUp(self):
        self.flow_settings=override_settings(FLOW_API_KEY='test-api-key',FLOW_SECRET_KEY='test-secret-key',FLOW_SITE_URL='https://goclinical.example.test')
        self.flow_settings.enable()
        cache.clear()
        self.clients={}
        for role in ['paciente','profesional','admin']:
            c=Client(enforce_csrf_checks=True);c.force_login(get_user_model().objects.get(username=role));c.get('/portal/'+role+'/');self.clients[role]=c
        self.client=self.clients['paciente']
    def tearDown(self):
        self.flow_settings.disable()
        super().tearDown()
    def post(self, action, role='paciente', **data):
        c=self.clients[role]
        return c.post('/api/action/',{'action':action,**data},content_type='application/json',HTTP_X_CSRFTOKEN=c.cookies['csrftoken'].value)
    def checkout(self, **data):
        c=self.clients['paciente']
        return c.post('/api/payments/flow/checkout/',json.dumps(data),content_type='application/json',HTTP_X_CSRFTOKEN=c.cookies['csrftoken'].value)
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
        payment={'token':'test-flow-token','flowOrder':123,'payment_url':'https://sandbox.flow.cl/?token=test-flow-token'}
        with patch('clinical.views.create_payment',return_value=payment):
            response=self.checkout(**self.data())
        self.assertEqual(response.status_code,200)
        code=response.json()['appointment_id']
        appointment=Appointment.objects.get(pk=int(code[3:]))
        self.assertFalse(appointment.paid)
        self.assertEqual(appointment.payment_status,'pending')
        for role in self.clients:self.assertIn(code,[a['id'] for a in self.state(role)['appointments']])
        self.client.get('/portal/paciente/')
        self.assertIn(code,[a['id'] for a in self.state()['appointments']])
        status={'commerceOrder':str(appointment.payment_key),'amount':appointment.price,'status':2,'flowOrder':123}
        with patch('clinical.flow.get_payment_status',return_value=status):
            confirmation=self.clients['paciente'].post('/api/payments/flow/confirmation/',{'token':appointment.flow_token})
        self.assertEqual(confirmation.status_code,200)
        appointment.refresh_from_db()
        self.assertTrue(appointment.paid)
        self.assertEqual(appointment.payment_status,'paid')
    def test_price_and_idempotency(self):
        data=self.data(price=1)
        payment={'token':'test-flow-token','flowOrder':123,'payment_url':'https://sandbox.flow.cl/?token=test-flow-token'}
        with patch('clinical.views.create_payment',return_value=payment) as create:
            r=self.checkout(**data);self.assertEqual(r.status_code,200)
            again=self.checkout(**data)
            self.assertEqual(again.json()['appointment_id'],r.json()['appointment_id'])
            create.assert_called_once()
        a=Appointment.objects.get(payment_key=data['payment_key']);self.assertEqual(a.price,a.service.price)
    def test_reservation_validation_and_conflict(self):
        payment={'token':'test-flow-token','flowOrder':123,'payment_url':'https://sandbox.flow.cl/?token=test-flow-token'}
        with patch('clinical.views.create_payment',return_value=payment):
            self.assertEqual(self.checkout(**self.data(accepted=False)).status_code,400)
            self.assertEqual(self.checkout(**self.data(date=timezone.localdate().isoformat())).status_code,400)
            self.assertEqual(self.checkout(**self.data()).status_code,200)
            self.assertEqual(self.checkout(**self.data()).status_code,409)
    def test_checkout_requires_flow_configuration_before_reserving(self):
        data=self.data()
        with override_settings(FLOW_API_KEY=''):
            response=self.checkout(**data)
        self.assertEqual(response.status_code,503)
        self.assertFalse(Appointment.objects.filter(payment_key=data['payment_key']).exists())
    def test_flow_confirmation_rejects_mismatched_amount(self):
        payment={'token':'test-flow-token','flowOrder':123,'payment_url':'https://sandbox.flow.cl/?token=test-flow-token'}
        with patch('clinical.views.create_payment',return_value=payment):
            self.checkout(**self.data())
        appointment=Appointment.objects.get(flow_token='test-flow-token')
        status={'commerceOrder':str(appointment.payment_key),'amount':appointment.price+1,'status':2,'flowOrder':123}
        with patch('clinical.flow.get_payment_status',return_value=status):
            response=self.clients['paciente'].post('/api/payments/flow/confirmation/',{'token':appointment.flow_token})
        self.assertEqual(response.status_code,503)
        appointment.refresh_from_db()
        self.assertFalse(appointment.paid)
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
    def test_document_upload_metadata_access_and_download(self):
        appointment=Appointment.objects.filter(patient__username='paciente').first()
        content=b'%PDF-1.7\nclinical test document'
        upload=SimpleUploadedFile('receta.pdf',content,content_type='application/pdf')
        client=self.clients['paciente']
        with patch('clinical.views.save_document',return_value='0123456789abcdef01234567') as save:
            response=client.post('/api/documents/upload/',{
                'file':upload,'category':'Receta médica','appointment':appointment.code,
            },HTTP_X_CSRFTOKEN=client.cookies['csrftoken'].value)
        self.assertEqual(response.status_code,200)
        save.assert_called_once_with(content,'application/pdf')
        document=ClinicalDocument.objects.get()
        self.assertEqual(document.patient.username,'paciente')
        self.assertEqual(document.uploaded_by.username,'paciente')
        self.assertEqual(document.mongo_id,'0123456789abcdef01234567')
        self.assertEqual(len(client.get('/api/documents/').json()['documents']),1)
        self.assertEqual(len(self.clients['profesional'].get('/api/documents/').json()['documents']),1)
        self.assertEqual(self.clients['admin'].get('/api/documents/').json()['documents'],[])
        with patch('clinical.views.read_document',return_value=content):
            downloaded=self.clients['profesional'].get(f'/api/documents/{document.pk}/download/')
        self.assertEqual(downloaded.status_code,200)
        self.assertEqual(downloaded.content,content)
        self.assertIn('attachment',downloaded['Content-Disposition'])
        self.assertEqual(self.clients['admin'].get(f'/api/documents/{document.pk}/download/').status_code,404)
    def test_document_upload_rejects_unrelated_user_and_unsupported_content(self):
        appointment=Appointment.objects.filter(patient__username='paciente').first()
        other=get_user_model().objects.create_user('otro_doc',password='Demo123456!')
        UserProfile.objects.create(user=other,role='paciente',workspace=UserProfile.objects.get(user__username='paciente').workspace)
        other_client=Client()
        other_client.force_login(other)
        unrelated=other_client.post('/api/documents/upload/',{
            'file':SimpleUploadedFile('orden.pdf',b'%PDF-1.7\nprueba'),
            'category':'Orden médica','appointment':appointment.code,
        })
        self.assertEqual(unrelated.status_code,404)
        client=self.clients['paciente']
        unsupported=client.post('/api/documents/upload/',{
            'file':SimpleUploadedFile('archivo.pdf',b'not a PDF'),
            'category':'Diagnóstico','appointment':appointment.code,
        },HTTP_X_CSRFTOKEN=client.cookies['csrftoken'].value)
        self.assertEqual(unsupported.status_code,400)
        self.assertEqual(ClinicalDocument.objects.count(),0)
    def test_seed_repeat_does_not_reset_password(self):
        user=get_user_model().objects.get(username='paciente');user.set_password('OtraClave123!');user.save()
        count=Appointment.objects.count();call_command('preparar_demo',verbosity=0)
        user.refresh_from_db();self.assertTrue(user.check_password('OtraClave123!'));self.assertEqual(Appointment.objects.count(),count)
