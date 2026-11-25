from django.contrib import admin
from django.urls import path
from clinical import tracking, views
urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("register/", views.register_view, name="registro"),
    path("logout/", views.logout_view, name="logout"),
    path("portal/<str:role>/", views.portal, name="portal"),
    path("", views.index, name="inicio"),
    path("api/state/", views.state_view, name="estado_demo"),
    path("api/action/", views.action_view, name="accion_demo"),
    path("api/payments/flow/checkout/", views.flow_checkout_view, name="flow_checkout"),
    path("api/payments/flow/confirmation/", views.flow_confirmation_view, name="flow_confirmation"),
    path("payments/flow/return/", views.flow_return_view, name="flow_return"),
    path("api/documents/", views.documents_view, name="documentos"),
    path("api/documents/upload/", views.document_upload_view, name="documento_carga"),
    path("api/documents/<int:document_id>/download/", views.document_download_view, name="documento_descarga"),
    path("api/applications/", views.professional_application_view, name="professional_application"),
    path("api/applications/<int:applicant_id>/documents/<int:document_id>/download/", views.applicant_document_download_view, name="applicant_document_download"),
    path("api/tracking/", tracking.patient_trips, name="patient_trips"),
    path("api/tracking/<int:appointment_id>/", tracking.share_location, name="share_location"),
    path("api/tracking/<int:appointment_id>/eta/", tracking.patient_eta, name="patient_eta"),
    path("admin/", admin.site.urls),
]
