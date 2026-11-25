"""Cuentas locales de demostración: nunca se usan con datos clínicos reales."""
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.db import transaction
from clinical.models import DemoWorkspace, UserProfile, Appointment, Availability
from clinical.demo import seed_workspace
from django.core.management import call_command
class Command(BaseCommand):
    help='Prepara tres cuentas locales de demostración. No cambia contraseñas ni borra registros existentes.'
    @transaction.atomic
    def handle(self,*args,**options):
        call_command('seed_demo')
        existing=UserProfile.objects.filter(user__username='paciente').first()
        w=existing.workspace if existing else DemoWorkspace.objects.create()
        users={}
        for username,first,last in [('paciente','Teresa','Cortés'),('profesional','Catalina','Hadad'),('admin','Equipo','GoClinical')]:
            user,created=get_user_model().objects.get_or_create(username=username)
            if created:
                user.first_name=first;user.last_name=last;user.email=f'{username}@example.invalid';user.set_password('GoClinical2026!');user.save()
            elif not hasattr(user,'clinical_profile'):
                raise CommandError(f'El usuario {username} ya existe sin perfil. No se modificó: utiliza una copia limpia del proyecto o asigna su perfil de forma explícita.')
            p,_=UserProfile.objects.get_or_create(user=user,defaults={'workspace':w,'role':username})
            if p.workspace_id != w.pk or p.role != username:
                raise CommandError('Las cuentas existentes tienen una configuración distinta. Revisa sus perfiles antes de continuar.')
            if username == 'admin' and p.admin_level != 'super_admin':
                p.admin_level='super_admin';p.save(update_fields=['admin_level'])
            users[username]=user
        if not Appointment.objects.filter(workspace=w).exists(): seed_workspace(w)
        Appointment.objects.filter(workspace=w,patient__isnull=True).update(patient=users['paciente'],professional=users['profesional'])
        Availability.objects.filter(workspace=w,professional__isnull=True).update(professional=users['profesional'])
        self.stdout.write(self.style.SUCCESS('Cuentas listas: paciente / profesional / admin. Contraseña inicial: GoClinical2026! (solo cuentas nuevas).'))
