from django.contrib import admin
from django.urls import path
from clinical import views
urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("portal/<str:role>/", views.portal, name="portal"),
    path("", views.index, name="inicio"),
    path("api/state/", views.state_view, name="estado_demo"),
    path("api/action/", views.action_view, name="accion_demo"),
    path("api/documents/", views.documents_view, name="documentos"),
    path("api/documents/upload/", views.document_upload_view, name="documento_carga"),
    path("api/documents/<int:document_id>/download/", views.document_download_view, name="documento_descarga"),
    path("admin/", admin.site.urls),
]
