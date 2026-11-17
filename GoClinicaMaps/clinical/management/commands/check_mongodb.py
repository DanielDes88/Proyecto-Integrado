from django.core.management.base import BaseCommand, CommandError
from pymongo.errors import PyMongoError

from clinical.document_store import check_connection


class Command(BaseCommand):
    help = "Comprueba la conexión y la configuración de MongoDB para documentos."

    def handle(self, *args, **options):
        try:
            check_connection()
        except (PyMongoError, RuntimeError) as exc:
            raise CommandError(
                "MongoDB no está disponible: "
                f"{type(exc).__name__}: {exc}. "
                "Revisa MONGODB_URI, MONGODB_TLS y la red."
            ) from exc
        self.stdout.write(self.style.SUCCESS("Conexión a MongoDB verificada."))
