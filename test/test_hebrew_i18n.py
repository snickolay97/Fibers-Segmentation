"""Hebrew coverage, formatting and stable scientific identifiers."""
import ast
from pathlib import Path
import re
import string
import unittest
from unittest.mock import patch

from src.desktop import i18n
from src.desktop.hebrew import HEBREW_TRANSLATIONS, HELP_HEBREW
from src.object_classes import OBJECT_CLASS_CATALOG


ROOT = Path(__file__).resolve().parents[1]
HEBREW = re.compile(r'[\u0590-\u05ff]')


class HebrewTranslationTests(unittest.TestCase):
    def setUp(self):
        self.original_language = i18n.get_language()

    def tearDown(self):
        i18n.set_language(self.original_language)

    def test_supported_languages_and_english_default_behavior(self):
        self.assertEqual(i18n.supported_languages(),('en','ru','he'))
        i18n.set_language('en')
        self.assertEqual(i18n.tr('Sources'),'Sources')
        i18n.set_language('he')
        self.assertEqual(i18n.tr('Sources'),'תמונות מקור')
        self.assertEqual(i18n.tr('Исходники'),'תמונות מקור')
        with self.assertRaises(ValueError): i18n.set_language('xx')

    def test_dynamic_registration_normalizes_legacy_russian_for_hebrew(self):
        with patch.dict(i18n._EN), patch.dict(i18n._RU), patch.dict(HEBREW_TRANSLATIONS):
            i18n.register_translations({'Test recovery page':'Тестовая страница восстановления'},
                                       hebrew={'Test recovery page':'עמוד שחזור לבדיקה'})
            self.assertEqual(i18n.tr('Тестовая страница восстановления',language='he'),'עמוד שחזור לבדיקה')
            self.assertEqual(i18n.tr('Test recovery page',language='ru'),'Тестовая страница восстановления')
            self.assertEqual(i18n.tr('Тестовая страница восстановления',language='en'),'Test recovery page')

    def test_all_existing_ui_catalogs_have_hebrew_translations(self):
        required=set()
        for path in (ROOT/'src/desktop').glob('*.py'):
            if path.stem in ('hebrew','help_center','parameter_reference'):
                continue
            tree=ast.parse(path.read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                if path.stem=='i18n' and isinstance(node,ast.Assign) and any(
                    isinstance(target,ast.Name) and target.id=='_EN' for target in node.targets):
                    required.update(ast.literal_eval(node.value).values())
                if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='register_translations' and node.args:
                    try:
                        required.update(ast.literal_eval(node.args[0]))
                    except (ValueError,TypeError):
                        pass
        missing=sorted(key for key in required if key not in HEBREW_TRANSLATIONS)
        self.assertFalse(missing,'Missing Hebrew UI text: '+repr(missing))
        self.assertGreaterEqual(len(required),389)
        for key in required:
            self.assertRegex(HEBREW_TRANSLATIONS[key],HEBREW,key)

    def test_format_fields_and_numeric_precision_are_preserved(self):
        formatter=string.Formatter()
        def fields(text):
            return sorted((name,spec,conversion) for _literal,name,spec,conversion in formatter.parse(text) if name is not None)
        for english,hebrew in HEBREW_TRANSLATIONS.items():
            self.assertEqual(fields(english),fields(hebrew),english)
        text=i18n.tr('Tile {v0} · {v1} · Native: {v2} px · Source px / model px: {v3:.4f} · Owned pixels: {v4}',
                     language='he',v0=5,v1='sample',v2='80 × 40',v3=2.5,v4=3200)
        self.assertIn('2.5000',text)
        self.assertIn('3200',text)

    def test_hebrew_class_names_keep_all_six_ids_and_csv_keys(self):
        expected={'particle':0,'fiber':1,'self_crossed_tube':2,'crossed_tubes':3,
                  'agglomeration':4,'adhered_objects':5}
        i18n.set_language('he')
        self.assertEqual({item['key']:item['id'] for item in OBJECT_CLASS_CATALOG},expected)
        for item in OBJECT_CLASS_CATALOG:
            self.assertRegex(i18n.tr(item['label_en']),HEBREW)
            self.assertEqual(i18n.tr(item['key']),item['key'])

    def test_all_existing_parameter_tooltips_have_full_hebrew_explanations(self):
        from src.desktop.help import _HELP, help_text
        self.assertEqual(set(_HELP),set(HELP_HEBREW))
        for key in _HELP:
            text=help_text(key,language='he')
            self.assertRegex(text,HEBREW,key)
            self.assertGreater(len(text),35,key)
            self.assertNotEqual(text,_HELP[key][0])
        self.assertIn('>> 8',help_text('save_raw_tiles',language='he'))
        self.assertIn('gamma=1',help_text('gamma',language='he'))
        self.assertIn('Manual_Class_ID',help_text('manual_export',language='he'))

    def test_hebrew_recovery_messages_explain_preservation_of_saved_values(self):
        text=i18n.tr('Invalid settings were not saved. The previous saved values were kept.',language='he')
        self.assertRegex(text,HEBREW)
        self.assertIn('לא נשמרו',text)
        message=i18n.tr('Invalid setting: {name}. Allowed: {allowed}. Factory default: {default}.',
                        language='he',name='bridge_kernel_size',allowed='odd',default=17)
        self.assertIn('bridge_kernel_size',message)
        self.assertIn('17',message)

    def test_known_worker_diagnostics_preserve_paths_and_technical_values(self):
        path='C:/source/FL01_G3_RGB_Red.tif'
        translated=i18n.tr('Processing '+path,language='he')
        self.assertRegex(translated,HEBREW)
        self.assertTrue(translated.endswith(path))
        error=i18n.tr('Ambiguous TIFF axes: QYX. Export with explicit spatial/channel/plane axes.',language='he')
        self.assertRegex(error,HEBREW)
        self.assertIn('QYX',error)
        self.assertEqual(i18n.tr(path,language='he'),path)
        self.assertEqual(i18n.tr(17,language='he'),17)

    def test_full_application_manual_and_parameter_catalog_include_hebrew(self):
        from src.desktop import parameter_reference, help_center
        for module in (parameter_reference,help_center):
            self.assertTrue(module._RU)
            self.assertEqual(set(module._RU),set(module._HE))
            for english,hebrew in module._HE.items():
                self.assertRegex(hebrew,HEBREW,english)
                self.assertEqual(i18n.tr(english,language='he'),hebrew)


if __name__=='__main__': unittest.main()
