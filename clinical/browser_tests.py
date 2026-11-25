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
        self.patient = patient
        admin = user_model.objects.create_user(
            username="browser-admin",
            password="BrowserTest123!",
            first_name="Admin",
            last_name="Prueba",
        )
        self.workspace = DemoWorkspace.objects.create()
        UserProfile.objects.create(
            user=self.professional,
            role="profesional",
            workspace=self.workspace,
        )
        UserProfile.objects.create(
            user=admin,
            role="admin",
            admin_level="super_admin",
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
        self.cancelled_appointment = self.create_appointment(
            service, patient, today + timedelta(days=32), "Cancelada", 30_000
        )
        self.cancelled_appointment.patient_notice = (
            "Esta atención fue cancelada porque el profesional ya no está disponible. "
            "Por favor, vuelve a agendar este servicio desde el catálogo."
        )
        self.cancelled_appointment.save(update_fields=["patient_notice"])

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

    def test_application_png_selection_survives_focus_refresh(self):
        patient_context = self.browser.new_context()
        self.addCleanup(patient_context.close)
        page = patient_context.new_page()
        page.goto(f"{self.live_server_url}/login/")
        page.get_by_label("Nombre de usuario").fill(self.patient.username)
        page.get_by_label("Contraseña").fill("BrowserTest123!")
        page.get_by_role("button", name="Iniciar sesión").click()
        page.wait_for_url("**/portal/paciente/")
        page.get_by_role("link", name="Postular a profesional").click()

        credential = page.locator("#applicationCredential")
        credential.dispatch_event("click")
        credential.set_input_files({
            "name": "titulo.png",
            "mimeType": "image/png",
            "buffer": b"\x89PNG\r\n\x1a\n",
        })

        with page.expect_response("**/api/state/"):
            page.evaluate("window.dispatchEvent(new Event('focus'))")

        self.assertEqual(
            page.locator("#applicationCredential").evaluate(
                "(input) => input.files[0]?.name"
            ),
            "titulo.png",
        )

    def test_patient_home_shows_cancellation_notice_and_reschedule_link(self):
        patient_context = self.browser.new_context()
        self.addCleanup(patient_context.close)
        page = patient_context.new_page()
        page.goto(f"{self.live_server_url}/login/")
        page.get_by_label("Nombre de usuario").fill(self.patient.username)
        page.get_by_label("Contraseña").fill("BrowserTest123!")
        page.get_by_role("button", name="Iniciar sesión").click()
        page.wait_for_url("**/portal/paciente/")

        alert = page.get_by_role("status").filter(has_text=self.cancelled_appointment.code)
        self.assertTrue(alert.is_visible())
        self.assertIn(self.cancelled_appointment.patient_notice, alert.inner_text())
        self.assertEqual(
            alert.get_by_role("link", name="Volver a agendar").get_attribute("href"),
            "#servicios",
        )

    def test_evaluation_form_has_polished_star_and_comment_layout(self):
        patient_context = self.browser.new_context()
        self.addCleanup(patient_context.close)
        page = patient_context.new_page()
        page.goto(f"{self.live_server_url}/login/")
        page.get_by_label("Nombre de usuario").fill(self.patient.username)
        page.get_by_label("Contraseña").fill("BrowserTest123!")
        page.get_by_role("button", name="Iniciar sesión").click()
        page.wait_for_url("**/portal/paciente/")
        page.goto(f"{self.live_server_url}/portal/paciente/#paciente")
        page.locator('#main .tabs [data-sub="historial"]').wait_for()
        page.locator('#main .tabs [data-sub="historial"]').click()

        finished_card = page.locator("#main article.appointment").filter(
            has_text=self.finished_appointment.code
        )
        finished_card.get_by_role("button", name="Evaluar").click()
        dialog = page.get_by_role("dialog")
        self.assertEqual(dialog.locator(".review-star").count(), 5)
        self.assertEqual(dialog.locator("textarea#comment").count(), 1)
        self.assertEqual(dialog.locator("select").count(), 0)
        dialog.get_by_role("radio", name="1 de 5 estrellas").click()
        dialog.locator("textarea#comment").fill("Puntual")
        self.assertIn("1 de 5 estrellas seleccionadas", dialog.inner_text())
        self.assertIn("7/300", dialog.inner_text())
        self.assertNotIn("pendiente de aprobación", dialog.inner_text())
        star_style = dialog.get_by_role("radio", name="1 de 5 estrellas").evaluate(
            "(element) => { const style = getComputedStyle(element); return {color: style.color, background: style.backgroundColor, className: element.className}; }"
        )
        self.assertEqual(star_style["color"], "rgb(233, 166, 47)")
        self.assertEqual(star_style["background"], "rgb(255, 242, 207)")
        self.assertEqual(
            dialog.locator("textarea#comment").evaluate(
                "(element) => getComputedStyle(element).minHeight"
            ),
            "144px",
        )

    def test_super_admin_can_return_professional_to_patient_from_account_table(self):
        admin_context = self.browser.new_context()
        self.addCleanup(admin_context.close)
        page = admin_context.new_page()
        page.goto(f"{self.live_server_url}/login/")
        page.get_by_label("Nombre de usuario").fill("browser-admin")
        page.get_by_label("Contraseña").fill("BrowserTest123!")
        page.get_by_role("button", name="Iniciar sesión").click()
        page.wait_for_url("**/portal/admin/")
        page.get_by_role("link", name="Gestión de cuentas").click()
        page.wait_for_function(
            "document.querySelector('#main').textContent.includes('Postulaciones y cuentas registradas')"
        )

        professional_row = page.get_by_role("row").filter(has_text="Profesional Prueba")
        professional_row.get_by_role("button", name="Volver a paciente").click()
        page.get_by_role("dialog").get_by_role("button", name="Confirmar cambio").click()

        professional_row = page.get_by_role("row").filter(has_text="Profesional Prueba")
        professional_row.get_by_role("cell").nth(2).get_by_text("Paciente").wait_for()
        self.assertIn("Paciente", professional_row.inner_text())
        self.assertEqual(
            professional_row.get_by_role("button", name="Volver a paciente").count(),
            0,
        )
