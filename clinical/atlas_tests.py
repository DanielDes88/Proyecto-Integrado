"""Opt-in integration tests that write a disposable document to MongoDB Atlas."""
import os
from datetime import timedelta
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone

from .document_store import delete_document
from .models import Appointment, ClinicalDocument, DemoWorkspace, Service, UserProfile


ATLAS_TESTS_ENABLED = (
    os.environ.get("RUN_ATLAS_INTEGRATION_TESTS") == "1"
    and bool(os.environ.get("MONGODB_URI"))
    and os.environ.get("MONGODB_DATABASE") == "goclinical_dev"
)


@skipUnless(
    ATLAS_TESTS_ENABLED,
    "Set RUN_ATLAS_INTEGRATION_TESTS=1 and MONGODB_DATABASE=goclinical_dev to run Atlas integration tests.",
)
class AtlasDocumentIntegrationTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.patient = user_model.objects.create_user(
            username="atlas-integration-patient",
            password="AtlasTest123!",
        )
        self.workspace = DemoWorkspace.objects.create()
        UserProfile.objects.create(
            user=self.patient,
            role="paciente",
            workspace=self.workspace,
        )
        service = Service.objects.create(
            name="Servicio de integración",
            category="Enfermería",
            price=1000,
            duration=30,
            code="ATLAS-TEST",
            description="Servicio ficticio para prueba de integración.",
        )
        appointment = Appointment.objects.create(
            workspace=self.workspace,
            patient=self.patient,
            service=service,
            date=timezone.localdate() + timedelta(days=10),
            time="08:00",
            address="Domicilio de demostración",
            price=service.price,
            duration=service.duration,
        )
        self.appointment_code = appointment.code
        self.client.force_login(self.patient)

    def test_document_upload_and_download_round_trip_with_atlas(self):
        content = b"%PDF-1.7\nAtlas integration test; fictitious content.\n"
        mongo_id = None
        try:
            response = self.client.post(
                "/api/documents/upload/",
                {
                    "file": SimpleUploadedFile(
                        "atlas-test.pdf",
                        content,
                        content_type="application/pdf",
                    ),
                    "category": "Otro",
                    "appointment": self.appointment_code,
                },
            )
            document = ClinicalDocument.objects.filter(patient=self.patient).first()
            if document:
                mongo_id = document.mongo_id

            self.assertEqual(response.status_code, 200, response.content.decode())
            self.assertIsNotNone(document)
            self.assertEqual(document.content_type, "application/pdf")
            self.assertEqual(document.size, len(content))

            downloaded = self.client.get(f"/api/documents/{document.pk}/download/")
            self.assertEqual(downloaded.status_code, 200)
            self.assertEqual(downloaded.content, content)
            self.assertIn("attachment", downloaded["Content-Disposition"])
        finally:
            if mongo_id:
                delete_document(mongo_id)
