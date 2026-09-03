#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

from django.core.management.base import BaseCommand
from django.apps import apps

from ...services import upsert_kb_entity

class Command(BaseCommand):
    help = 'Translate all KB entities zh -> en/ja/fr/de using translator module'

    def add_arguments(self, parser):
        parser.add_argument('--entity_id', type=int, default=None, help='Translate a single entity by id')
        parser.add_argument('--langs', nargs='*', default=["en", "ja", "fr", "de"], help='Target languages')

    def handle(self, *args, **options):
        KBEntity = apps.get_model('kb', 'KBEntity')
        if options['entity_id'] is not None:
            ents = [KBEntity.objects.get(id=options['entity_id'])]
        else:
            ents = KBEntity.objects.all()

        translated_any = 0
        from ...translator import translate_kb_entity
        for ent in ents:
            langs = ent.langs or {}
            zh_block = langs.get('zh', {})
            if not zh_block:
                continue
            new_langs = translate_kb_entity(zh_block, target_langs=options['langs'])
            upsert_kb_entity(
                {
                    "entity_key": ent.entity_key,
                    "canonical_key": ent.canonical_key,
                    "category": ent.category,
                    "source": ent.source,
                    "langs": new_langs,
                }
            )
            translated_any += 1
        self.stdout.write(self.style.SUCCESS(f"Translated {translated_any} entities"))
