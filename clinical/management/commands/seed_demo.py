import json
from pathlib import Path
from django.core.management.base import BaseCommand
from clinical.models import Service
class Command(BaseCommand):
    help = 'Crea el catálogo de ejemplo sin borrar reservas ni modificar servicios existentes.'
    def handle(self,*args,**options):
        data=json.loads((Path(__file__).resolve().parents[2]/'catalog.json').read_text(encoding='utf-8'))
        count=0
        for s in data:
            _,created=Service.objects.get_or_create(code=s['code'],defaults={
                'name':s['name'],'category':s['category'],'icon':s['icon'],'price':s['price'],
                'duration':int(s['time'].split()[0]),'description':s['desc']})
            count+=created
        self.stdout.write(self.style.SUCCESS(f'Catálogo preparado: {count} servicios nuevos.'))
