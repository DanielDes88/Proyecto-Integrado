"""Almacenamiento de archivos como documentos BSON (sin GridFS)."""
from functools import lru_cache

from django.conf import settings
from django.utils import timezone


@lru_cache(maxsize=1)
def _collection():
    from pymongo import MongoClient

    uri = getattr(settings, "MONGODB_URI", "")
    if not uri:
        raise RuntimeError("MONGODB_URI no está configurada.")
    client = MongoClient(
        uri,
        serverSelectionTimeoutMS=5000,
        tls=getattr(settings, "MONGODB_TLS", True),
    )
    collection = client[settings.MONGODB_DATABASE]["clinical_documents"]
    collection.create_index("created_at")
    return collection


def check_connection():
    """Comprueba que MongoDB está configurado y acepta conexiones."""
    collection = _collection()
    collection.database.client.admin.command("ping")


def save_document(data, content_type):
    from bson import Binary, ObjectId

    object_id = ObjectId()
    _collection().insert_one({
        "_id": object_id,
        "content": Binary(data),
        "content_type": content_type,
        "created_at": timezone.now(),
    })
    return str(object_id)


def read_document(mongo_id):
    from bson import ObjectId

    if not ObjectId.is_valid(mongo_id):
        return None
    record = _collection().find_one({"_id": ObjectId(mongo_id)}, {"content": 1})
    return bytes(record["content"]) if record else None


def delete_document(mongo_id):
    from bson import ObjectId

    if not ObjectId.is_valid(mongo_id):
        return False
    return _collection().delete_one({"_id": ObjectId(mongo_id)}).deleted_count == 1