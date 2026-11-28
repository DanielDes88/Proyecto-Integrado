"""Edición del catálogo, permisos y conservación de los importes de las reservas."""
import uuid
from datetime import timedelta
from io import BytesIO

from PIL import Image
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.utils import timezone

from .demo import catalog, create_reservation
from .models import Appointment, DemoWorkspace, Service, Transaction, UserProfile


class ServiceEditingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.workspace = DemoWorkspace.objects.create()
        cls.users = {}
        for name, role, level in [
            ("catalog-admin", "admin", "normal"),
            ("catalog-superadmin", "admin", "super_admin"),
            ("catalog-patient", "paciente", "normal"),
            ("catalog-professional", "profesional", "normal"),
        ]:
            user = get_user_model().objects.create_user(name, first_name=name)
            UserProfile.objects.create(
                user=user, role=role, admin_level=level, workspace=cls.workspace,
            )
            cls.users[name] = user
        cls.service = Service.objects.create(
            name="Atención de enfermería", code="CAT-01", category="Enfermería",
            price=15000, description="Servicio para probar la edición del catálogo.",
        )

    def setUp(self):
        self.clients = {}
        for name, user in self.users.items():
            client = Client(enforce_csrf_checks=True)
            client.force_login(user)
            client.get("/")
            self.clients[name] = client
        self.client = self.clients["catalog-admin"]
        self.url = f"/api/services/{self.service.pk}/"

    def image(self, image_format="PNG"):
        output = BytesIO()
        Image.new("RGB", (100, 60), "#309dad").save(output, image_format)
        return SimpleUploadedFile("servicio." + image_format.lower(), output.getvalue())

    def update(self, client=None, **changes):
        self.service.refresh_from_db()
        data = {"price": 18000, "revision": str(self.service.revision)}
        data.update(changes)
        client = client or self.client
        return client.post(
            self.url, data, HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
        )

    def test_admin_upload_is_visible_in_public_catalog_and_all_portals(self):
        response = self.update(image=self.image())
        self.assertEqual(response.status_code, 200)
        service = response.json()["services"][0]
        self.assertEqual(service["price"], 18000)
        self.assertTrue(service["image_url"])
        public = Client()
        self.assertContains(public.get("/"), service["image_url"])
        self.assertContains(public.get("/"), "$18.000 CLP")
        image_response = public.get(service["image_url"])
        self.assertEqual(image_response.status_code, 200)
        self.assertEqual(image_response["Content-Type"], "image/jpeg")
        self.assertEqual(image_response["X-Content-Type-Options"], "nosniff")
        with Image.open(BytesIO(image_response.content)) as image:
            image.load()
            self.assertEqual(image.size, (100, 60))
        for client in self.clients.values():
            item = client.get("/api/state/").json()["services"][0]
            self.assertEqual(item["price"], 18000)
            self.assertEqual(item["image_url"], service["image_url"])

    def test_roles_and_csrf_are_enforced(self):
        for name in ("catalog-patient", "catalog-professional"):
            self.assertEqual(self.update(client=self.clients[name]).status_code, 403)
        anonymous = Client(enforce_csrf_checks=True)
        anonymous.get("/")
        self.assertEqual(self.update(client=anonymous).status_code, 401)
        self.assertEqual(self.client.post(self.url, {"price": 1}).status_code, 403)
        self.assertEqual(self.update(client=self.clients["catalog-superadmin"]).status_code, 200)

    def test_price_only_keeps_image_and_removal_returns_to_icon(self):
        first = self.update(image=self.image()).json()["services"][0]
        self.service.refresh_from_db()
        image_bytes = bytes(self.service.image_data)
        changed = self.update(price=21000).json()["services"][0]
        self.service.refresh_from_db()
        self.assertEqual(bytes(self.service.image_data), image_bytes)
        self.assertNotEqual(first["image_url"], changed["image_url"])
        self.assertEqual(self.client.get(changed["image_url"]).status_code, 200)
        removed = self.update(remove_image="on").json()["services"][0]
        self.assertEqual(removed["image_url"], "")
        self.service.refresh_from_db()
        self.assertEqual(bytes(self.service.image_data), b"")
        self.assertEqual(self.client.get(changed["image_url"]).status_code, 404)

    def test_invalid_input_cannot_partially_change_price_or_image(self):
        for price in ("", "-1", "0", "1.5", "2147483648", "abc"):
            with self.subTest(price=price):
                self.assertEqual(self.update(price=price, image=self.image()).status_code, 400)
        self.assertEqual(self.update(image=SimpleUploadedFile(
            "aparenta-ser-foto.jpg", b"<svg onload='alert(1)'></svg>",
        )).status_code, 400)
        self.assertEqual(self.update(image=SimpleUploadedFile(
            "rota.png", b"\x89PNG\r\n\x1a\n",
        )).status_code, 400)
        self.assertEqual(self.update(image=SimpleUploadedFile(
            "grande.png", b"x" * (5 * 1024 * 1024 + 1),
        )).status_code, 400)
        self.assertEqual(self.update(image=self.image(), remove_image="on").status_code, 400)
        self.service.refresh_from_db()
        self.assertEqual(self.service.price, 15000)
        self.assertEqual(bytes(self.service.image_data), b"")

    def test_supported_images_are_normalized_and_large_dimensions_are_rejected(self):
        for image_format in ("PNG", "JPEG", "WEBP"):
            with self.subTest(image_format=image_format):
                self.assertEqual(self.update(image=self.image(image_format)).status_code, 200)
        output = BytesIO()
        Image.new("RGB", (4001, 4000)).save(output, "PNG")
        self.assertEqual(self.update(image=SimpleUploadedFile(
            "demasiados-pixeles.png", output.getvalue(),
        )).status_code, 400)

    def test_stale_editor_cannot_overwrite_another_admin(self):
        revision = str(self.service.revision)
        self.assertEqual(self.update(price=20000).status_code, 200)
        response = self.update(price=22000, revision=revision, image=self.image())
        self.assertEqual(response.status_code, 409)
        self.service.refresh_from_db()
        self.assertEqual(self.service.price, 20000)
        self.assertEqual(bytes(self.service.image_data), b"")

    def test_new_price_is_used_for_future_reservations_and_history_keeps_original(self):
        old = Appointment.objects.create(
            workspace=self.workspace, service=self.service,
            patient=self.users["catalog-patient"],
            professional=self.users["catalog-professional"],
            date=timezone.localdate() + timedelta(days=2), time="09:00",
            address="Domicilio de demostración", price=15000, duration=30,
        )
        payment = Transaction.objects.create(appointment=old, amount=15000)
        self.assertEqual(self.update(price=25000).status_code, 200)
        new = create_reservation(self.workspace, {
            "service": self.service.pk,
            "date": (timezone.localdate() + timedelta(days=4)).isoformat(),
            "time": "09:00", "address": "Domicilio de demostración",
            "accepted": True, "payment_key": str(uuid.uuid4()),
        }, self.users["catalog-patient"])
        self.assertEqual(new.price, 25000)
        old.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(old.price, 15000)
        self.assertEqual(payment.amount, 15000)

    def test_catalog_does_not_fetch_image_bytes_and_seed_keeps_edits(self):
        from django.core.management import call_command

        self.update(image=self.image())
        with CaptureQueriesContext(connection) as captured:
            entries = catalog()
        self.assertEqual(len(entries), 1)
        self.assertNotIn('"image_data"', captured[0]["sql"])
        self.service.refresh_from_db()
        revision = self.service.revision
        call_command("seed_demo", verbosity=0)
        self.service.refresh_from_db()
        self.assertEqual(self.service.price, 18000)
        self.assertEqual(self.service.revision, revision)

    def create(self, client=None, **changes):
        data = {
            "name": "Cuidado de heridas",
            "category": "Curaciones avanzadas",
            "description": "Atención de heridas y control de la evolución.",
            "price": 32000,
            "duration": 45,
            "creation_key": str(uuid.uuid4()),
        }
        data.update(changes)
        client = client or self.client
        return client.post(
            "/api/services/", data,
            HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
        )

    def delete(self, service=None, client=None, **changes):
        service = service or self.service
        service.refresh_from_db()
        client = client or self.client
        data = {"revision": str(service.revision), **changes}
        return client.post(
            f"/api/services/{service.pk}/delete/", data,
            HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
        )

    def test_admin_creates_complete_service_with_image_and_new_category(self):
        response = self.create(image=self.image())
        self.assertEqual(response.status_code, 201)
        created = Service.objects.get(pk=response.json()["service_id"])
        self.assertEqual(created.name, "Cuidado de heridas")
        self.assertEqual(created.category, "Curaciones avanzadas")
        self.assertEqual(created.duration, 45)
        self.assertEqual(created.price, 32000)
        self.assertTrue(created.image_data)
        self.assertTrue(created.is_active)
        public_services = self.client.get("/").context["services"]
        self.assertIn(created.pk, [service["id"] for service in public_services])
        self.assertEqual(self.client.get(created.image_url).status_code, 200)

    def test_create_retry_does_not_duplicate_service(self):
        key = str(uuid.uuid4())
        first = self.create(creation_key=key)
        second = self.create(creation_key=key)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()["service_id"], second.json()["service_id"])
        self.assertEqual(Service.objects.count(), 2)

    def test_admin_edits_name_and_invalid_names_are_rejected(self):
        self.assertEqual(self.update(name="Control cardiológico <especial>").status_code, 200)
        self.service.refresh_from_db()
        self.assertEqual(self.service.name, "Control cardiológico <especial>")
        self.assertContains(self.client.get("/"), "Control cardiológico &lt;especial&gt;")
        for name in ("", "   ", "a" * 101):
            with self.subTest(name=name):
                self.assertEqual(self.update(name=name, price=50000).status_code, 400)
        self.service.refresh_from_db()
        self.assertEqual(self.service.price, 18000)
        self.assertEqual(self.service.name, "Control cardiológico <especial>")

    def test_create_and_delete_require_admin_and_csrf(self):
        for name in ("catalog-patient", "catalog-professional"):
            self.assertEqual(self.create(client=self.clients[name]).status_code, 403)
            self.assertEqual(self.delete(client=self.clients[name]).status_code, 403)
        anonymous = Client(enforce_csrf_checks=True)
        anonymous.get("/")
        self.assertEqual(self.create(client=anonymous).status_code, 401)
        self.assertEqual(self.delete(client=anonymous).status_code, 401)
        self.assertEqual(self.client.post("/api/services/", {}).status_code, 403)
        self.assertEqual(self.client.post(self.url + "delete/", {}).status_code, 403)
        self.assertEqual(self.delete(client=self.clients["catalog-superadmin"]).status_code, 200)

    def test_create_rejects_missing_invalid_or_oversized_fields(self):
        for changes in (
            {"name": ""}, {"name": "a" * 101}, {"category": ""},
            {"category": "x" * 51}, {"description": "x" * 251},
            {"duration": 0}, {"duration": "30.5"}, {"price": -1},
            {"creation_key": "incorrecta"},
        ):
            with self.subTest(changes=changes):
                self.assertEqual(self.create(**changes).status_code, 400)
        self.assertEqual(Service.objects.count(), 1)

    def test_delete_retires_service_but_preserves_visits_payments_and_payment_retries(self):
        from .demo import DemoError

        visit = Appointment.objects.create(
            workspace=self.workspace, service=self.service,
            patient=self.users["catalog-patient"],
            professional=self.users["catalog-professional"],
            date=timezone.localdate() + timedelta(days=2), time="09:00",
            address="Domicilio de demostración", price=15000, duration=30,
        )
        payment = Transaction.objects.create(appointment=visit, amount=15000)
        self.assertEqual(self.delete().status_code, 200)
        self.service.refresh_from_db()
        self.assertFalse(self.service.is_active)
        self.assertTrue(Appointment.objects.filter(pk=visit.pk).exists())
        self.assertTrue(Transaction.objects.filter(pk=payment.pk, amount=15000).exists())
        self.assertEqual(catalog(), [])
        self.assertEqual(
            self.clients["catalog-patient"].get("/api/state/").json()["services"][0]["is_active"],
            False,
        )
        with self.assertRaisesRegex(DemoError, "Servicio no disponible"):
            create_reservation(self.workspace, {
                "service": self.service.pk, "accepted": True,
                "payment_key": str(uuid.uuid4()),
            }, self.users["catalog-patient"])
        retried = create_reservation(self.workspace, {
            "payment_key": str(visit.payment_key),
        }, self.users["catalog-patient"])
        self.assertEqual(retried.pk, visit.pk)
        self.assertEqual(self.update(name="Cambio tardío").status_code, 404)

    def test_stale_delete_requires_review_and_repeated_delete_is_safe(self):
        revision = str(self.service.revision)
        self.update(name="Nombre actualizado")
        self.assertEqual(self.delete(revision=revision).status_code, 409)
        self.service.refresh_from_db()
        self.assertTrue(self.service.is_active)
        revision = str(self.service.revision)
        self.assertEqual(self.delete(revision=revision).status_code, 200)
        self.assertEqual(self.delete(revision=revision).status_code, 200)

    def test_seed_does_not_restore_retired_catalog_entries(self):
        from django.core.management import call_command

        call_command("seed_demo", verbosity=0)
        seeded = Service.objects.exclude(pk=self.service.pk).first()
        self.assertEqual(self.delete(service=seeded).status_code, 200)
        call_command("seed_demo", verbosity=0)
        seeded.refresh_from_db()
        self.assertFalse(seeded.is_active)
        self.assertNotIn(seeded.pk, [service["id"] for service in catalog()])

    def test_demo_workspace_can_start_with_empty_catalog(self):
        from .demo import seed_workspace
        from .models import Availability

        Service.objects.update(is_active=False)
        other_workspace = DemoWorkspace.objects.create()
        seed_workspace(other_workspace)
        self.assertFalse(Appointment.objects.filter(workspace=other_workspace).exists())
        self.assertEqual(Availability.objects.filter(workspace=other_workspace).count(), 2)
