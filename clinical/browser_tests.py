"""Browser-level tests for client-side behavior that Django tests cannot execute."""
import re
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.utils import timezone
from playwright.sync_api import sync_playwright

from .models import Appointment, DemoWorkspace, Service, UserProfile


class ProfessionalFeesBrowserTests(StaticLiveServerTestCase):
    def setUp(self):
        super().setUp()
        user_model = get_user_model()
        self.professional = user_model.objects.create_user(
            username="browser-professional",
            password="BrowserTest123!",
            first_name="Profesional",
            last_name="Prueba",
        )
        patient = user_model.objects.create_user(
            username="browser-patient",
            password="BrowserTest123!",
        )
        self.workspace = DemoWorkspace.objects.create()
        UserProfile.objects.create(
            user=self.professional,
            role="profesional",
            workspace=self.workspace,
        )
        UserProfile.objects.create(
            user=patient,
            role="paciente",
            workspace=self.workspace,
        )
        service = Service.objects.create(
            name="Servicio de prueba",
            category="Enfermería",
            price=10_000,
            duration=30,
            code="BROWSER-TEST",
            description="Servicio creado para la prueba automatizada.",
        )
        today = timezone.localdate()
        self.finished_appointment = self.create_appointment(
            service, patient, today + timedelta(days=30), "Finalizada", 10_000
        )
        self.pending_appointment = self.create_appointment(
            service, patient, today + timedelta(days=31), "Confirmada", 20_000
        )

        self.playwright = sync_playwright().start()
        self.addCleanup(self.playwright.stop)
        self.browser = self.playwright.chromium.launch()
        self.addCleanup(self.browser.close)
        self.context = self.browser.new_context()
        self.addCleanup(self.context.close)
        self.page = self.context.new_page()
        self.page.goto(f"{self.live_server_url}/login/")
        self.page.get_by_label("Nombre de usuario").fill(self.professional.username)
        self.page.get_by_label("Contraseña").fill("BrowserTest123!")
        self.page.get_by_role("button", name="Iniciar sesión").click()
        self.page.wait_for_url("**/portal/profesional/")

    def create_appointment(self, service, patient, date, status, price):
        return Appointment.objects.create(
            workspace=self.workspace,
            patient=patient,
            professional=self.professional,
            service=service,
            date=date,
            time="08:00",
            address="Domicilio de demostración",
            status=status,
            price=price,
            duration=service.duration,
            paid=True,
            payment_status="paid",
        )

    def displayed_amount(self, locator):
        return re.sub(r"\D", "", locator.inner_text())

    def test_only_finalized_appointments_are_counted_in_professional_fees(self):
        home_fees = self.page.locator("#main .stat").filter(
            has_text="Honorarios ilustrativos"
        ).locator("strong")
        self.assertEqual(self.displayed_amount(home_fees), "7000")

        self.page.get_by_role("link", name="Facturación").click()
        self.page.wait_for_function(
            "document.querySelector('#breadcrumb').textContent.includes('Facturación')"
        )
        self.assertEqual(
            self.displayed_amount(self.page.locator("#main .card h1")),
            "7000",
        )

        self.page.get_by_role("link", name="Agendamiento").click()
        self.page.wait_for_function(
            "document.querySelector('#breadcrumb').textContent.includes('Agendamiento')"
        )
        pending_card = self.page.locator("#main article.appointment").filter(
            has_text=self.pending_appointment.code
        )
        for button_name in ("En camino", "Iniciar atención", "Finalizar"):
            pending_card.get_by_role("button", name=button_name).click()
        self.page.get_by_role("link", name="Facturación").click()
        self.page.wait_for_function(
            "document.querySelector('#breadcrumb').textContent.includes('Facturación')"
        )
        self.assertEqual(
            self.displayed_amount(self.page.locator("#main .card h1")),
            "21000",
        )

        self.page.get_by_role("link", name="Inicio").click()
        updated_home_fees = self.page.locator("#main .stat").filter(
            has_text="Honorarios ilustrativos"
        ).locator("strong")
        self.assertEqual(self.displayed_amount(updated_home_fees), "21000")
