"""Permisos por rol, acceso a objetos y recorridos del prototipo."""
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from urllib.error import HTTPError
from urllib.parse import parse_qsl, urlsplit
from datetime import timedelta
from ssl import SSLError
from threading import Barrier
from unittest.mock import patch
from django.test import TestCase, Client, TransactionTestCase, override_settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from .flow import FlowError, _api_request, sign_params
from .models import Applicant, ApplicantDocument, Appointment, Availability, ClinicalDocument, DemoWorkspace, Service, UserProfile, UserRoleChange, TripLocation


class FlowSignatureTests(TestCase):
    def test_signature_sorts_names_and_uses_hmac_sha256(self):
        import hashlib
        import hmac
        params={'currency':'CLP','amount':'5000','apiKey':'key'}
        expected=hmac.new(b'secret',b'amount5000apiKeykeycurrencyCLP',hashlib.sha256).hexdigest()
        self.assertEqual(sign_params(params,'secret'),expected)

    @override_settings(FLOW_API_KEY='test-api-key',FLOW_SECRET_KEY='test-secret-key',FLOW_SITE_URL='https://goclinical.example.test')
    def test_get_request_serializes_signed_parameters_alphabetically(self):
        with patch('clinical.flow.urlopen',return_value=BytesIO(b'{}')) as request:
            _api_request('payment/getStatus',{'token':'test-flow-token'},'GET')
        query=urlsplit(request.call_args.args[0].full_url).query
        self.assertEqual([key for key,_ in parse_qsl(query)],['apiKey','s','token'])

    @override_settings(FLOW_API_KEY='test-api-key',FLOW_SECRET_KEY='test-secret-key',FLOW_SITE_URL='https://goclinical.example.test')
    def test_http_error_exposes_flow_code_and_logs_provider_message(self):
        error = HTTPError(
            'https://sandbox.flow.cl/api/payment/create',
            401,
            'Unauthorized',
            {},
            BytesIO(b'{"code": 401, "message": "Invalid signature"}'),
        )
        with patch('clinical.flow.urlopen',side_effect=error):
            with self.assertLogs('clinical.flow',level='WARNING') as captured:
                with self.assertRaisesRegex(FlowError,'código 401'):
                    _api_request('payment/create',{'amount':5000},'POST')
        self.assertIn('Invalid signature',' '.join(captured.output))
        self.assertNotIn('test-secret-key',' '.join(captured.output))


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
    def submit_application(self, role='paciente', **changes):
        data={
            'area':'Kinesiología',
            'experience':'3 años',
            'has_vehicle':'true',
            'credential':SimpleUploadedFile('titulo.pdf',b'%PDF-1.7\ntitulo',content_type='application/pdf'),
            'cv':SimpleUploadedFile('cv.pdf',b'%PDF-1.7\ncv',content_type='application/pdf'),
        }
        data.update(changes)
        client=self.clients[role]
        return client.post(
            '/api/applications/',
            data,
            HTTP_X_CSRFTOKEN=client.cookies['csrftoken'].value,
        )
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
        for action in ['advance','approve','slot_add','bill','review_approve','set_user_role']:
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
    def test_flow_return_accepts_external_post_and_verifies_token(self):
        appointment=Appointment.objects.filter(patient__username='paciente').first()
        appointment.payment_status='paid'
        client=Client(enforce_csrf_checks=True)
        with patch('clinical.views.confirm_payment',return_value=appointment) as confirm:
            response=client.post('/payments/flow/return/',{'token':'test-flow-token'},HTTP_ORIGIN='https://sandbox.flow.cl')
        self.assertEqual(response.status_code,302)
        self.assertEqual(response['Location'],'/portal/paciente/?flow_payment=paid#paciente')
        confirm.assert_called_once_with('test-flow-token')
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
    @override_settings(GOOGLE_MAPS_ROUTES_KEY='routes-test')
    def test_live_tracking_lifecycle(self):
        visit = Appointment.objects.get(status='Confirmada')
        url = f'/api/tracking/{visit.pk}/'
        pro = self.clients['profesional']
        owner = self.clients['paciente']
        share_id = str(uuid.uuid4())

        def send(client, action='position', **changes):
            data = {'action': action, 'share_id': share_id, 'latitude': -33.45, 'longitude': -70.66}
            return client.post(url, {**data, **changes}, content_type='application/json',
                               HTTP_X_CSRFTOKEN=client.cookies['csrftoken'].value)

        visit.paid = False
        visit.payment_status = 'pending'
        visit.save(update_fields=['paid', 'payment_status'])
        self.assertEqual(self.post('advance', role='profesional', id=visit.code,
                                   expected_status='Confirmada').status_code, 409)
        visit.refresh_from_db()
        self.assertEqual(visit.status, 'Confirmada')
        self.assertEqual(send(pro).status_code, 409)
        self.assertFalse(TripLocation.objects.filter(appointment=visit).exists())
        visit.paid = True
        visit.payment_status = 'paid'
        visit.save(update_fields=['paid', 'payment_status'])

        self.assertEqual(send(pro).status_code, 409)
        self.assertEqual(self.post('advance', role='profesional', id=visit.code,
                                   expected_status='Confirmada').status_code, 200)
        self.assertIsNone(owner.get('/api/tracking/').json()['trips'][0]['position'])
        self.assertEqual(send(owner).status_code, 403)
        self.assertEqual(send(pro, latitude=True).status_code, 400)
        self.assertEqual(send(pro, longitude=181).status_code, 400)
        self.assertEqual(pro.post(url, {}, content_type='application/json').status_code, 403)
        self.assertEqual(send(pro).status_code, 200)
        trip = owner.get('/api/tracking/').json()['trips'][0]
        self.assertEqual(trip['position'], {'lat': -33.45, 'lng': -70.66})
        self.assertEqual(self.clients['admin'].get('/api/tracking/').status_code, 403)
        other = get_user_model().objects.create_user('paciente-ajeno')
        UserProfile.objects.create(user=other, workspace=visit.workspace, role='paciente')
        client = Client()
        client.force_login(other)
        self.assertEqual(client.get('/api/tracking/').json()['trips'], [])
        self.assertEqual(client.post(url + 'eta/').status_code, 404)

        with patch('clinical.tracking.compute_eta', return_value=180) as route:
            headers = {'HTTP_X_CSRFTOKEN': owner.cookies['csrftoken'].value}
            self.assertEqual(owner.post(url + 'eta/', **headers).json()['eta_seconds'], 180)
            self.assertEqual(owner.post(url + 'eta/', **headers).status_code, 429)
            route.assert_called_once_with((-33.45, -70.66), (trip['destination']['lat'], trip['destination']['lng']))

        self.assertEqual(send(pro, share_id=str(uuid.uuid4())).status_code, 409)
        self.assertEqual(send(pro, action='stop').status_code, 200)
        self.assertIsNone(owner.get('/api/tracking/').json()['trips'][0]['position'])
        self.assertEqual(send(pro).status_code, 200)
        TripLocation.objects.filter(appointment=visit).update(received_at=timezone.now() - timedelta(seconds=46))
        self.assertIsNone(owner.get('/api/tracking/').json()['trips'][0]['position'])
        self.assertFalse(TripLocation.objects.filter(appointment=visit).exists())
        self.assertEqual(send(pro).status_code, 200)
        self.assertEqual(self.post('advance', role='profesional', id=visit.code,
                                   expected_status='En camino').status_code, 200)
        self.assertEqual(owner.get('/api/tracking/').json()['trips'], [])
        self.assertFalse(TripLocation.objects.filter(appointment=visit).exists())
        self.assertEqual(send(pro).status_code, 409)

    def test_advancement_updates_only_selected_appointment(self):
        appointments=self.state('profesional')['appointments']
        target=next(a for a in appointments if a['status']=='Confirmada')
        other_statuses={a['id']:a['status'] for a in appointments if a['id']!=target['id']}
        transitions=[('Confirmada','En camino'),('En camino','En atención'),('En atención','Finalizada')]

        for expected_status,next_status in transitions:
            response=self.post('advance',role='profesional',id=target['id'],expected_status=expected_status)
            self.assertEqual(response.status_code,200)
            statuses={a['id']:a['status'] for a in response.json()['state']['appointments']}
            self.assertEqual(statuses[target['id']],next_status)
            for appointment_id,status in other_statuses.items():
                self.assertEqual(statuses[appointment_id],status)

            if expected_status=='Confirmada':
                stale_response=self.post('advance',role='profesional',id=target['id'],expected_status='Confirmada')
                self.assertEqual(stale_response.status_code,409)
                statuses={a['id']:a['status'] for a in self.state('profesional')['appointments']}
                self.assertEqual(statuses[target['id']],next_status)
                for appointment_id,status in other_statuses.items():
                    self.assertEqual(statuses[appointment_id],status)

        response=self.post('advance',role='profesional',id=target['id'],expected_status='Finalizada')
        self.assertEqual(response.status_code,409)
        statuses={a['id']:a['status'] for a in self.state('profesional')['appointments']}
        self.assertEqual(statuses[target['id']],'Finalizada')
        for appointment_id,status in other_statuses.items():
            self.assertEqual(statuses[appointment_id],status)
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
        self.assertEqual(self.state('admin')['applicants'],[])

    def test_patient_application_requires_both_documents_and_vehicle_answer(self):
        missing_cv=self.submit_application(cv='')
        self.assertEqual(missing_cv.status_code,400)
        self.assertFalse(Applicant.objects.exists())

        missing_vehicle=self.submit_application(has_vehicle='')
        self.assertEqual(missing_vehicle.status_code,400)
        self.assertFalse(Applicant.objects.exists())

        self.assertEqual(
            self.submit_application('profesional').status_code,
            403,
        )

    def test_patient_can_submit_application_and_admin_can_download_documents(self):
        with patch(
            'clinical.views.save_document',
            side_effect=['0123456789abcdef01234567','0123456789abcdef01234568'],
        ) as save:
            response=self.submit_application(has_vehicle='false')
        self.assertEqual(response.status_code,201)
        self.assertEqual(save.call_count,2)

        applicant=Applicant.objects.get()
        self.assertEqual(applicant.user.username,'paciente')
        self.assertEqual((applicant.area,applicant.experience,applicant.has_vehicle),('Kinesiología','3 años',False))
        self.assertEqual(applicant.documents.count(),2)
        patient_state=self.state()
        self.assertEqual(patient_state['applicants'],[])
        self.assertEqual(patient_state['my_application']['status'],'Pendiente')
        admin_application=self.state('admin')['applicants'][0]
        self.assertEqual(admin_application['email'],applicant.user.email)
        self.assertEqual(len(admin_application['documents']),2)

        document=ApplicantDocument.objects.filter(applicant=applicant).first()
        url=f'/api/applications/{applicant.pk}/documents/{document.pk}/download/'
        self.assertEqual(self.clients['paciente'].get(url).status_code,403)
        other_admin=get_user_model().objects.create_user('other-admin')
        UserProfile.objects.create(
            user=other_admin,
            role='admin',
            workspace=DemoWorkspace.objects.create(),
        )
        other_client=Client()
        other_client.force_login(other_admin)
        self.assertEqual(other_client.get(url).status_code,404)
        with patch('clinical.views.read_document',return_value=b'%PDF-1.7\ntitulo'):
            downloaded=self.clients['admin'].get(url)
        self.assertEqual(downloaded.status_code,200)
        self.assertEqual(downloaded.content,b'%PDF-1.7\ntitulo')
        self.assertIn('private, no-store',downloaded['Cache-Control'])

    def test_approval_promotes_the_applicant_and_records_who_reviewed(self):
        with patch(
            'clinical.views.save_document',
            side_effect=['1123456789abcdef01234567','1123456789abcdef01234568'],
        ):
            self.assertEqual(self.submit_application().status_code,201)
        applicant=Applicant.objects.get()
        UserProfile.objects.filter(user__username='admin').update(admin_level='normal')

        response=self.post('approve',role='admin',id=applicant.pk)

        self.assertEqual(response.status_code,200)
        applicant.refresh_from_db()
        profile=UserProfile.objects.get(user__username='paciente')
        self.assertEqual((applicant.status,applicant.reviewed_by.username),('Aprobado','admin'))
        self.assertIsNotNone(applicant.reviewed_at)
        self.assertEqual(profile.role,'profesional')
        change=UserRoleChange.objects.get(target_user=applicant.user)
        self.assertEqual((change.previous_role,change.new_role),('paciente','profesional'))

    def test_only_one_pending_application_can_be_submitted(self):
        with patch(
            'clinical.views.save_document',
            side_effect=['3123456789abcdef01234567','3123456789abcdef01234568'],
        ) as save:
            self.assertEqual(self.submit_application().status_code,201)
            self.assertEqual(self.submit_application().status_code,409)
        self.assertEqual(save.call_count,2)
        self.assertEqual(Applicant.objects.filter(status='Pendiente').count(),1)

    def test_rejection_keeps_the_applicant_as_patient_and_cannot_be_repeated(self):
        with patch(
            'clinical.views.save_document',
            side_effect=['2123456789abcdef01234567','2123456789abcdef01234568'],
        ):
            self.assertEqual(self.submit_application().status_code,201)
        applicant=Applicant.objects.get()

        self.assertEqual(self.post('reject',role='admin',id=applicant.pk).status_code,200)
        applicant.refresh_from_db()
        self.assertEqual(applicant.status,'Rechazado')
        self.assertEqual(applicant.user.clinical_profile.role,'paciente')
        self.assertEqual(self.post('reject',role='admin',id=applicant.pk).status_code,409)
    def test_super_admin_can_promote_patient_and_audit_role_change(self):
        patient = UserProfile.objects.get(user__username='paciente')
        response = self.post(
            'set_user_role', role='admin', user_id=patient.user_id,
            target_role='admin', admin_level='normal',
        )
        self.assertEqual(response.status_code,200)
        patient.refresh_from_db()
        self.assertEqual((patient.role,patient.admin_level),('admin','normal'))
        change = UserRoleChange.objects.get(target_user_id=patient.user_id)
        self.assertEqual(change.changed_by.username,'admin')
        self.assertEqual((change.previous_role,change.new_role),('paciente','admin'))
        self.assertEqual(self.clients['paciente'].get('/portal/paciente/').status_code,403)
    def test_super_admin_can_return_professional_to_patient_and_notify_affected_patient(self):
        professional = UserProfile.objects.get(user__username='profesional')
        patient = UserProfile.objects.get(user__username='paciente')
        service = Service.objects.first()
        confirmed = Appointment.objects.create(
            workspace=professional.workspace,
            patient=patient.user,
            professional=professional.user,
            service=service,
            date=timezone.localdate()+timedelta(days=30),
            time='14:00',
            address='Domicilio de demostración',
            status='Confirmada',
            price=service.price,
            duration=service.duration,
        )
        finished = Appointment.objects.create(
            workspace=professional.workspace,
            patient=patient.user,
            professional=professional.user,
            service=service,
            date=timezone.localdate()+timedelta(days=31),
            time='14:00',
            address='Domicilio de demostración',
            status='Finalizada',
            price=service.price,
            duration=service.duration,
        )
        Availability.objects.create(
            workspace=professional.workspace,
            professional=professional.user,
            weekday='Lunes',
            start='09:00',
            end='12:00',
        )

        response = self.post(
            'set_user_role', role='admin', user_id=professional.user_id,
            target_role='paciente', admin_level='normal',
        )

        self.assertEqual(response.status_code,200)
        professional.refresh_from_db()
        confirmed.refresh_from_db()
        finished.refresh_from_db()
        self.assertEqual(professional.role,'paciente')
        self.assertEqual(
            (confirmed.status,confirmed.professional_id),
            ('Cancelada',None),
        )
        self.assertTrue(confirmed.patient_notice)
        self.assertEqual((finished.status,finished.professional_id),('Finalizada',professional.user_id))
        self.assertFalse(Availability.objects.filter(workspace=professional.workspace,professional=professional.user).exists())
        patient_appointments = self.state()['appointments']
        notified = next(item for item in patient_appointments if item['id']==confirmed.code)
        self.assertEqual(notified['patient_notice'],confirmed.patient_notice)
        self.assertEqual(notified['status'],'Cancelada')
        change = UserRoleChange.objects.get(target_user=professional.user)
        self.assertEqual((change.previous_role,change.new_role),('profesional','paciente'))
    def test_professional_cannot_be_demoted_while_visit_is_in_progress(self):
        professional = UserProfile.objects.get(user__username='profesional')
        patient = UserProfile.objects.get(user__username='paciente')
        service = Service.objects.first()
        confirmed = Appointment.objects.create(
            workspace=professional.workspace,
            patient=patient.user,
            professional=professional.user,
            service=service,
            date=timezone.localdate()+timedelta(days=30),
            time='14:00',
            address='Domicilio de demostración',
            status='Confirmada',
            price=service.price,
            duration=service.duration,
        )
        for index, status in enumerate(['En camino','En atención']):
            Appointment.objects.create(
                workspace=professional.workspace,
                patient=patient.user,
                professional=professional.user,
                service=service,
                date=timezone.localdate()+timedelta(days=31+index),
                time='14:00',
                address='Domicilio de demostración',
                status=status,
                price=service.price,
                duration=service.duration,
            )
        slot = Availability.objects.create(
            workspace=professional.workspace,
            professional=professional.user,
            weekday='Lunes',
            start='09:00',
            end='12:00',
        )

        response = self.post(
            'set_user_role', role='admin', user_id=professional.user_id,
            target_role='paciente', admin_level='normal',
        )

        self.assertEqual(response.status_code,409)
        professional.refresh_from_db()
        confirmed.refresh_from_db()
        self.assertEqual(professional.role,'profesional')
        self.assertEqual((confirmed.status,confirmed.professional_id),('Confirmada',professional.user_id))
        self.assertTrue(Availability.objects.filter(pk=slot.pk).exists())
        self.assertFalse(UserRoleChange.objects.filter(target_user=professional.user).exists())
    def test_super_admin_can_assign_another_super_admin(self):
        patient = UserProfile.objects.get(user__username='paciente')
        response = self.post(
            'set_user_role', role='admin', user_id=patient.user_id,
            target_role='admin', admin_level='super_admin',
        )
        self.assertEqual(response.status_code,200)
        patient.refresh_from_db()
        self.assertEqual((patient.role,patient.admin_level),('admin','super_admin'))
    def test_normal_admin_cannot_change_account_roles(self):
        workspace = UserProfile.objects.get(user__username='admin').workspace
        normal_admin = get_user_model().objects.create_user('normal-admin',password='Demo123456!')
        UserProfile.objects.create(user=normal_admin,role='admin',admin_level='normal',workspace=workspace)
        patient = UserProfile.objects.get(user__username='paciente')
        professional = UserProfile.objects.get(user__username='profesional')
        client = Client()
        client.force_login(normal_admin)
        patient_response = client.post(
            '/api/action/',
            {'action':'set_user_role','user_id':patient.user_id,'target_role':'admin','admin_level':'normal'},
            content_type='application/json',
        )
        professional_response = client.post(
            '/api/action/',
            {'action':'set_user_role','user_id':professional.user_id,'target_role':'paciente','admin_level':'normal'},
            content_type='application/json',
        )
        self.assertEqual(patient_response.status_code,403)
        self.assertEqual(professional_response.status_code,403)
        patient.refresh_from_db()
        professional.refresh_from_db()
        self.assertEqual(patient.role,'paciente')
        self.assertEqual(professional.role,'profesional')
    def test_super_admin_cannot_change_own_role(self):
        admin = UserProfile.objects.get(user__username='admin')
        response = self.post(
            'set_user_role', role='admin', user_id=admin.user_id,
            target_role='paciente', admin_level='normal',
        )
        self.assertEqual(response.status_code,403)
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
    def test_document_upload_accepts_supported_signatures(self):
        appointment=Appointment.objects.filter(patient__username='paciente').first()
        files=[
            ('documento.pdf',b'%PDF-1.7\nprueba','application/pdf','application/pdf','000000000000000000000001'),
            ('documento.png',b'\x89PNG\r\n\x1a\nprueba','image/png','image/png','000000000000000000000002'),
            ('documento.jpg',b'\xff\xd8\xffprueba','image/jpeg','image/jpeg','000000000000000000000003'),
        ]
        client=self.clients['paciente']
        for name,content,upload_type,expected_type,mongo_id in files:
            with self.subTest(name=name), patch('clinical.views.save_document',return_value=mongo_id) as save:
                response=client.post('/api/documents/upload/',{
                    'file':SimpleUploadedFile(name,content,content_type=upload_type),
                    'category':'Otro','appointment':appointment.code,
                },HTTP_X_CSRFTOKEN=client.cookies['csrftoken'].value)
                self.assertEqual(response.status_code,200)
                save.assert_called_once_with(content,expected_type)
                self.assertEqual(ClinicalDocument.objects.get(mongo_id=mongo_id).content_type,expected_type)
    def test_document_upload_enforces_10_mib_limit(self):
        appointment=Appointment.objects.filter(patient__username='paciente').first()
        client=self.clients['paciente']
        max_size=10*1024*1024
        prefix=b'%PDF-1.7\n'
        with patch('clinical.views.save_document') as save:
            oversized=client.post('/api/documents/upload/',{
                'file':SimpleUploadedFile('demasiado-grande.pdf',prefix+b'x'*max_size,content_type='application/pdf'),
                'category':'Otro','appointment':appointment.code,
            },HTTP_X_CSRFTOKEN=client.cookies['csrftoken'].value)
            self.assertEqual(oversized.status_code,413)
            save.assert_not_called()

        accepted_content=prefix+b'x'*(max_size-len(prefix))
        with patch('clinical.views.save_document',return_value='000000000000000000000010') as save:
            accepted=client.post('/api/documents/upload/',{
                'file':SimpleUploadedFile('limite.pdf',accepted_content,content_type='application/pdf'),
                'category':'Otro','appointment':appointment.code,
            },HTTP_X_CSRFTOKEN=client.cookies['csrftoken'].value)
        save.assert_called_once_with(accepted_content,'application/pdf')
        self.assertEqual(accepted.status_code,200)
        self.assertEqual(ClinicalDocument.objects.get().size,max_size)
    def test_document_upload_handles_tls_failure(self):
        appointment=Appointment.objects.filter(patient__username='paciente').first()
        client=self.clients['paciente']
        with self.assertLogs('clinical.views',level='ERROR'):
            with patch('clinical.views.save_document',side_effect=SSLError('TLS handshake failed')) as save:
                response=client.post('/api/documents/upload/',{
                    'file':SimpleUploadedFile('prueba.pdf',b'%PDF-1.7\nprueba',content_type='application/pdf'),
                    'category':'Otro','appointment':appointment.code,
                },HTTP_X_CSRFTOKEN=client.cookies['csrftoken'].value)
        self.assertEqual(response.status_code,503)
        self.assertIn('Revisa la conexión con MongoDB',response.json()['error'])
        save.assert_called_once()
        self.assertEqual(ClinicalDocument.objects.count(),0)
    def test_seed_repeat_does_not_reset_password(self):
        user=get_user_model().objects.get(username='paciente');user.set_password('OtraClave123!');user.save()
        count=Appointment.objects.count();call_command('preparar_demo',verbosity=0)
        user.refresh_from_db();self.assertTrue(user.check_password('OtraClave123!'));self.assertEqual(Appointment.objects.count(),count)


class LoginThrottleConcurrencyDiagnosticTests(TransactionTestCase):
    """Reproduces the current non-atomic login throttle race with local requests."""

    def setUp(self):
        cache.clear()
        get_user_model().objects.create_user(
            username='concurrent-login-test',
            password='CorrectTestPassword123!',
        )

    def tearDown(self):
        cache.clear()
        super().tearDown()

    def test_simultaneous_failures_can_exceed_the_throttle_limit(self):
        attempts=11
        remote_addr='192.0.2.42'
        rate_limit_key='gc-login-'+remote_addr
        barrier=Barrier(attempts)
        original_get=cache.get

        def read_same_count_then_wait(key,*args,**kwargs):
            value=original_get(key,*args,**kwargs)
            if key==rate_limit_key:
                barrier.wait(timeout=15)
            return value

        def submit_failed_login(_):
            return Client().post(
                '/login/',
                {'username':'concurrent-login-test','password':'wrong-password'},
                REMOTE_ADDR=remote_addr,
            )

        with patch('clinical.views.cache.get',side_effect=read_same_count_then_wait):
            with ThreadPoolExecutor(max_workers=attempts) as pool:
                responses=list(pool.map(submit_failed_login,range(attempts)))

        throttled=sum('Demasiados intentos' in response.content.decode() for response in responses)
        self.assertEqual(throttled,0)
        self.assertEqual(cache.get(rate_limit_key),1)


class PatientRegistrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('preparar_demo', verbosity=0)

    def registration_data(self, **overrides):
        data = {
            'first_name': 'Andrea',
            'last_name': 'Silva',
            'date_of_birth': '1990-02-14',
            'phone': '+56912345678',
            'email': 'andrea.silva@example.test',
            'address': 'Avenida Central 123',
            'city': 'Santiago',
            'username': 'andrea-silva',
            'password1': 'V!7mQ2#rP9zL',
            'password2': 'V!7mQ2#rP9zL',
        }
        data.update(overrides)
        return data

    def test_registration_creates_patient_in_clinic_workspace_and_logs_in(self):
        response = self.client.post('/register/', self.registration_data())

        self.assertRedirects(response, '/portal/paciente/')
        user = get_user_model().objects.get(username='andrea-silva')
        profile = user.clinical_profile
        clinic_workspace = UserProfile.objects.get(user__username='admin').workspace
        self.assertEqual(profile.role, 'paciente')
        self.assertEqual(profile.workspace, clinic_workspace)
        self.assertEqual(profile.date_of_birth.isoformat(), '1990-02-14')
        self.assertEqual(profile.phone, '+56912345678')
        self.assertEqual(profile.address, 'Avenida Central 123')
        self.assertEqual(profile.city, 'Santiago')
        self.assertTrue(user.check_password('V!7mQ2#rP9zL'))
        self.assertEqual(self.client.session['_auth_user_id'], str(user.pk))
        portal = self.client.get('/portal/paciente/')
        self.assertContains(portal, '1990-02-14')
        self.assertContains(portal, 'Avenida Central 123')

    def test_registration_rejects_duplicate_email_case_insensitively(self):
        data = self.registration_data(
            username='another-patient',
            email='EMILIOXD.7@GMAIL.COM',
        )

        response = self.client.post('/register/', data)

        self.assertEqual(response.status_code, 200)
        self.assertIn('email', response.context['form'].errors)
        self.assertFalse(get_user_model().objects.filter(username='another-patient').exists())

    def test_registration_fails_when_clinic_workspace_is_ambiguous_or_missing(self):
        UserProfile.objects.filter(role='admin', admin_level='super_admin').delete()

        response = self.client.post('/register/', self.registration_data())

        self.assertEqual(response.status_code, 503)
        self.assertIn(
            'El registro no está disponible por el momento.',
            response.context['form'].non_field_errors()[0],
        )
        self.assertFalse(get_user_model().objects.filter(username='andrea-silva').exists())

    def test_registration_is_linked_from_login_and_public_home(self):
        self.assertContains(self.client.get('/login/'), '/register/')
        self.assertContains(self.client.get('/'), '/register/')
