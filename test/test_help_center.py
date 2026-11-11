"""Application help is complete, localized and independent of saved settings."""

from dataclasses import fields
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from src.app_settings import PipelineSettings
from src.default_settings import FACTORY_DEFAULTS, DEFAULTS_VERSION, factory_defaults
from src.desktop.parameter_reference import PARAMETER_REFERENCE, parameter_entry

try:
    from src.desktop.qt import QtCore, QtWidgets, configure_font
    from src.desktop.help_center import HelpCenter, TOPICS
    QT_AVAILABLE = True
except ImportError:
    QT_AVAILABLE = False


class ParameterReferenceTests(unittest.TestCase):
    def test_reference_covers_every_setting_with_fixed_defaults_and_explanations(self):
        keys = {field.name for field in fields(PipelineSettings)}
        self.assertEqual(set(PARAMETER_REFERENCE), keys)
        self.assertEqual(set(FACTORY_DEFAULTS), keys)
        self.assertGreaterEqual(DEFAULTS_VERSION, 1)
        for key in keys:
            entry = parameter_entry(key, 'en')
            self.assertEqual(entry['factory_default'], FACTORY_DEFAULTS[key])
            for name in ('purpose', 'unit', 'valid_range', 'increase', 'decrease', 'example', 'safety'):
                self.assertTrue(entry[name], (key, name))
        from src import config
        with patch.object(config, 'GAMMA_VALUE', 7.9):
            self.assertEqual(parameter_entry('gamma')['factory_default'], 1.2)
        changed = factory_defaults()
        changed['gamma'] = 2.5
        self.assertEqual(parameter_entry('gamma')['factory_default'], 1.2)
        with self.assertRaises(TypeError):
            FACTORY_DEFAULTS['gamma'] = 3.5

    def test_parameter_rules_and_scientific_limitations_are_explicit(self):
        for key in ('bridge_kernel_size', 'buffer_kernel_size'):
            self.assertIn('odd', parameter_entry(key, 'en')['valid_range'])
            with self.assertRaises(ValueError):
                PipelineSettings.from_dict({key: 4})
        gamma = parameter_entry('gamma', 'en')
        self.assertIn('background', gamma['increase'])
        self.assertIn('identity', gamma['decrease'])
        self.assertIn('Native', parameter_entry('min_sub_object_area', 'en')['unit'])
        self.assertIn('not a physical diameter', parameter_entry('buffer_kernel_size', 'en')['safety'])
        self.assertIsNone(parameter_entry('unknown_key'))

    def test_full_parameter_reference_is_authored_in_three_languages(self):
        for key, record in PARAMETER_REFERENCE.items():
            for name in ('title', 'purpose', 'increase', 'decrease', 'example', 'safety'):
                canonical = getattr(record, name)
                for language in ('ru', 'he'):
                    translated = parameter_entry(key, language)[name]
                    self.assertTrue(translated)
                    if canonical not in ('White top-hat',):
                        self.assertNotEqual(translated, canonical, (key, name, language))


@unittest.skipUnless(QT_AVAILABLE, 'Qt binding is not installed')
class HelpCenterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        configure_font()

    def setUp(self):
        self.help = HelpCenter(current_settings={'gamma': 2.4}, language='en')

    def tearDown(self):
        self.help.close()
        self.help.deleteLater()
        self.app.processEvents()

    def nav_payloads(self):
        return list(self.help._nav_items)

    def test_factory_and_current_are_separate_and_refresh_is_read_only(self):
        self.help.open_topic('parameters')
        table = self.help.parameter_table
        self.assertEqual(table.rowCount(), len(FACTORY_DEFAULTS))
        row = next(row for row in range(table.rowCount())
                   if table.item(row, 0).data(QtCore.Qt.ItemDataRole.UserRole) == 'gamma')
        self.assertEqual([table.item(row, column).text() for column in (1, 2)], ['1.2', '2.4'])
        table.selectRow(row)
        self.assertEqual(self.help._current_parameter, 'gamma')
        self.assertIn('Factory default\nCurrent value\n1.2\n2.4', self.help.details.toPlainText())
        self.assertIn('Try it and check the result', self.help.details.toPlainText())
        self.assertFalse(self.help.isModal())
        supplied = {'gamma': 3.5, 'metadata': {'nested': 4}}
        self.help.refresh_settings(supplied)
        self.help.current_settings['metadata']['nested'] = 99
        self.assertEqual(supplied['metadata']['nested'], 4)
        self.assertEqual([table.item(row, column).text() for column in (1, 2)], ['1.2', '3.5'])
        self.assertTrue(table.item(row, 0).isSelected())
        self.assertIn('Factory default\nCurrent value\n1.2\n3.5', self.help.details.toPlainText())
        self.assertEqual(FACTORY_DEFAULTS['gamma'], 1.2)

    def test_parameter_index_links_every_article_in_each_language(self):
        for language, heading in (
            ('en', 'Try it and check the result'),
            ('ru', 'Что попробовать и как проверить результат'),
            ('he', 'מה לנסות ואיך לבדוק את התוצאה'),
        ):
            self.help.retranslate(language)
            self.help.open_topic('parameters')
            self.assertIsNone(self.help._current_parameter)
            index = self.help.details.toHtml()
            for key in PARAMETER_REFERENCE:
                with self.subTest(language=language, key=key):
                    self.assertIn(f'href="parameter:{key}"', index)
                    self.help._follow_link(QtCore.QUrl(f'parameter:{key}'))
                    self.assertIn(heading, self.help.details.toPlainText())
                    self.assertIn('href="topic:parameters"', self.help.details.toHtml())
            self.help._follow_link(QtCore.QUrl('topic:parameters'))
            self.assertIsNone(self.help._current_parameter)

    def test_browsing_and_close_never_modify_project(self):
        from src.desktop.project import Project
        with tempfile.TemporaryDirectory(prefix='help_readonly_') as directory:
            project = Project.create(Path(directory) / 'project.json', 'Help test')
            original = Path(project.path).read_bytes()
            self.help.refresh_settings(project.settings)
            for topic in TOPICS:
                self.help.open_topic(topic)
            self.help.open_parameter('bridge_kernel_size')
            self.help.close()
            self.assertEqual(Path(project.path).read_bytes(), original)
            self.help.show()
            self.assertTrue(self.help.isVisible())

    def test_search_covers_application_topics_and_parameter_keys(self):
        self.help.search.setText('uint16')
        self.assertIn(('topic', 'sources'), self.nav_payloads())
        self.assertIn(('parameter', 'save_raw_tiles'), self.nav_payloads())
        self.help.search.setText('gamma')
        self.assertIn(('topic', 'preparation'), self.nav_payloads())
        self.assertIn(('parameter', 'gamma'), self.nav_payloads())
        self.help.search.setText('no_such_help_term_123456789')
        self.assertEqual(self.help.navigation.topLevelItemCount(), 0)
        self.assertIn('No matching help', self.help.browser.toPlainText())

    def test_model_chart_help_links_search_and_matrix_example_in_all_languages(self):
        for language, query, precision, example in (
            ('en', 'confusion matrix', '0.553', 'Fiber row and Particle column'),
            ('ru', 'матрицу ошибок', '0,553', 'строку «Волокно» и столбец «Частица»'),
            ('he', 'מטריצת הבלבול', '0.553', 'לשורת סיב ולעמודת חלקיק'),
        ):
            with self.subTest(language=language):
                self.help.retranslate(language)
                self.help.open_topic('training_charts')
                html = self.help.browser.toHtml()
                for topic in ('tree_impurity', 'confusion_matrix', 'permutation_importance'):
                    self.assertIn(f'href="topic:{topic}"', html)
                self.help._follow_link(QtCore.QUrl('topic:confusion_matrix'))
                self.assertIn('<table', self.help.browser.toHtml())
                text = self.help.browser.toPlainText()
                self.assertIn('26/47', text)
                self.assertIn(precision, text)
                self.help.search.setText(query)
                self.assertIn(('topic', 'confusion_matrix'), self.nav_payloads())
                self.help.open_topic('model_fit')
                self.assertIn('max_depth', self.help.browser.toPlainText())
                self.help.open_topic('model_evaluation')
                for topic in ('evaluation_gallery', 'object_prediction_review'):
                    self.assertIn(f'href="topic:{topic}"', self.help.browser.toHtml())
                self.help.open_topic('object_prediction_review')
                plain = self.help.browser.toPlainText().replace('\u2066', '').replace('\u2069', '')
                self.assertIn(example, plain)
                self.help.open_parameter('enable_animations')
                for axis in ('right', 'bottom'):
                    self.assertIn(f'search_0033_{axis}', self.help.details.toPlainText())

    def test_search_and_context_for_tile_editing_and_window_shifts(self):
        for language, editor_queries, automatic in (
            ('en', ('freehand erase', 'smaller side', 'brightness gamma', 'draw rectangle', 'pipette'), 'Automatic'),
            ('ru', ('стереть от руки', 'меньшая сторона', 'яркость гамма', 'выделить прямоугольник', 'пипетка'), 'Автоматически'),
            ('he', ('מחיקה ביד חופשית', 'הצד הקטן יותר', 'בהירות גאמה', 'בחירת מלבן', 'טפטפת'), 'אוטומטי'),
        ):
            with self.subTest(language=language):
                self.help.retranslate(language)
                for query in editor_queries:
                    self.help.search.setText(query)
                    self.assertIn(('topic', 'tile_editor'), self.nav_payloads(), query)
                self.help.open_parameter('tile_editor')
                self.assertEqual(self.help._current_topic, 'tile_editor')
                from src.default_settings import EDITOR_DEFAULTS
                self.assertIn(str(EDITOR_DEFAULTS['erase_radius']), self.help.browser.toPlainText())
                self.assertIn('valid_mask.png', self.help.browser.toPlainText())
                self.help.refresh_settings({'straight_shift_left': 0})
                self.help.open_parameter('straight_shift_left')
                table = self.help.parameter_table
                row = table.selectedItems()[0].row()
                self.assertEqual(table.item(row, 1).text(), automatic)
                self.assertEqual(table.item(row, 2).text(), '0')
                self.help.refresh_settings({'search_window_end': 1400})
                self.help.open_parameter('search_window_end')
                row = table.selectedItems()[0].row()
                self.assertEqual(table.item(row, 1).text(), automatic)
                self.assertEqual(table.item(row, 2).text(), '1400')
                interval = '\u2066[1125, 1400)\u2069' if language == 'he' else '[1125, 1400)'
                self.assertIn(interval, self.help.details.toPlainText())

    def test_first_run_navigation_and_troubleshooting_search_in_each_language(self):
        for language, heading, query in (
            ('en', 'First run, step by step', 'empty dataset list'),
            ('ru', 'Первый запуск по шагам', 'наборов пуст'),
            ('he', 'הפעלה ראשונה, צעד אחר צעד', 'המערכים ריקה'),
        ):
            with self.subTest(language=language):
                self.help.retranslate(language)
                self.help.home_button.click()
                self.assertIn(heading, self.help.browser.toPlainText())
                self.assertIn('topic:segmentation', self.help.browser.toHtml())
                self.help._follow_link(QtCore.QUrl('topic:segmentation'))
                self.assertEqual(self.help._current_topic, 'segmentation')
                self.help.search.setText(query)
                self.assertIn(('topic', 'recovery'), self.nav_payloads())

    def test_open_parameter_routes_topics_and_local_links(self):
        self.help.search.setText('gamma')
        self.help.open_parameter('buffer_kernel_size')
        self.assertEqual(self.help.search.text(), '')
        self.assertEqual(self.help._current_parameter, 'buffer_kernel_size')
        self.assertIn('Positive odd', self.help.details.toPlainText())
        self.help.open_parameter('tile_ids')
        self.assertEqual(self.help._current_topic, 'tiles')
        self.help._follow_link(QtCore.QUrl('parameter:gamma'))
        self.assertEqual(self.help._current_parameter, 'gamma')
        selected = self.help.parameter_table.selectedItems()
        self.assertTrue(selected)
        self.assertEqual(selected[0].data(QtCore.Qt.ItemDataRole.UserRole), 'gamma')
        self.help.open_topic('unknown_badge')
        self.assertEqual(self.help._current_topic, 'getting_started')

    def test_locale_switch_keeps_parameter_context_and_rtl_formula_direction(self):
        self.help.open_parameter('gamma')
        self.help.retranslate('he')
        self.assertEqual(self.help.pages.currentIndex(), 1)
        self.assertEqual(self.help._current_parameter, 'gamma')
        self.assertEqual(self.help.layoutDirection(), QtCore.Qt.LayoutDirection.RightToLeft)
        self.assertIn('גאמה', self.help.details.toPlainText())
        self.assertIn('gamma', self.help.details.toPlainText())
        self.assertIn('\u2066', self.help.details.toPlainText())
        self.help.retranslate('ru')
        self.assertEqual(self.help.layoutDirection(), QtCore.Qt.LayoutDirection.LeftToRight)
        self.assertIn('Гамма', self.help.details.toPlainText())

    def test_narrative_covers_complete_workflow_and_all_languages(self):
        expected = {'getting_started', 'sources', 'preparation', 'tiles', 'segmentation',
                    'manual_types', 'results', 'export', 'workspace', 'settings', 'recovery', 'shortcuts'}
        self.assertTrue(expected <= set(TOPICS))
        for topic_id in expected:
            self.help.open_topic(topic_id)
            self.assertGreater(len(self.help.browser.toPlainText()), 150)
        self.help.open_topic('results')
        self.assertIn('AR=1.0', self.help.browser.toPlainText())
        self.help.open_topic('export')
        self.assertIn('Class_ID/Class_Name', self.help.browser.toPlainText())
        self.help.open_topic('recovery')
        self.assertIn('NaN/infinity', self.help.browser.toPlainText())
        for language, term in (('ru', 'Восстановление'), ('he', 'NaN')):
            self.help.retranslate(language)
            self.help.open_topic('recovery')
            self.assertNotIn('Saved settings are checked', self.help.browser.toPlainText())


if __name__ == '__main__':
    unittest.main()
