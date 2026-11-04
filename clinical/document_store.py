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
    client = MongoClient(uri, serverSelectionTimeoutMS=5000, tls=True)
    return client[settings.MONGODB_DATABASE]["clinical_documents"]


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

    record = _collection().find_one({"_id": ObjectId(mongo_id)}, {"content": 1})
    return bytes(record["content"]) if record else None


def delete_document(mongo_id):
    from bson import ObjectId

    _collection().delete_one({"_id": ObjectId(mongo_id)})