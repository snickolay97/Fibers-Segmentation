import copy
from dataclasses import fields
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from src.app_settings import PipelineSettings, SettingsValidationError, inspect_settings
from src.default_settings import DEFAULTS_VERSION, FACTORY_DEFAULTS, factory_defaults
from src.desktop.project import Project
from src.desktop.settings_safety import backup_project, recover_project_settings


class SettingsSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.path = self.root/'project.json'

    def tearDown(self):
        self.temporary.cleanup()

    def document(self, settings):
        return dict(path=str(self.path), name='Existing research', workspace=str(self.root),
            settings=settings, sources=[dict(id='source',path='original.tif')],
            datasets=[dict(id='dataset',status='running',path='saved_tiles',
                           settings=dict(gamma=1.3),labels_dir='annotations/version-one',
                           results_dir='measurements/one',last_csv='measurements/one/features.csv')],
            active_dataset_id='dataset', history=[dict(time='earlier',action='original_action')],
            schema_version=1, custom_extension=dict(note='Preserve unrelated metadata'))

    def write_document(self, settings):
        document = self.document(settings)
        original = (json.dumps(document,ensure_ascii=False,indent=4)+'\n').replace('\n','\r\n').encode('utf-8')
        self.path.write_bytes(original)
        return document,original,Project.load(self.path)

    def test_factory_defaults_are_immutable_complete_and_independent_copies(self):
        self.assertEqual(set(FACTORY_DEFAULTS),{field.name for field in fields(PipelineSettings)})
        self.assertEqual(factory_defaults(),PipelineSettings().to_dict())
        self.assertEqual(DEFAULTS_VERSION,1)
        self.assertEqual(FACTORY_DEFAULTS['gamma'],1.2)
        self.assertEqual(FACTORY_DEFAULTS['buffer_kernel_size'],5)
        with self.assertRaises(TypeError):FACTORY_DEFAULTS['gamma']=1.6
        editable=factory_defaults(); editable['gamma']=9
        self.assertEqual(factory_defaults()['gamma'],1.2)
        self.assertEqual(PipelineSettings().gamma,1.2)

    def test_runtime_defaults_do_not_drift_with_mutable_config(self):
        script = ('from src import config; config.GAMMA_VALUE=9.9; '
                  'config.BUFFER_KERNEL_SIZE=11; config.TARGET_SIZE=4096; '
                  'from src.app_settings import PipelineSettings; '
                  's=PipelineSettings(); assert (s.gamma,s.buffer_kernel_size,s.target_size)==(1.2,5,1500)')
        completed=subprocess.run([sys.executable,'-B','-c',script],cwd=Path(__file__).resolve().parents[1],
                                 capture_output=True,text=True,timeout=15)
        self.assertEqual(completed.returncode,0,completed.stderr)

    def test_repair_only_invalid_kernel_keeps_gamma_data_and_exact_backup(self):
        settings=factory_defaults(); settings.update(gamma=1.6,buffer_kernel_size=6)
        before,original,project=self.write_document(settings)
        report=recover_project_settings(project)
        self.assertEqual(report['status'],'recovered')
        self.assertEqual(Path(report['backup_path']).read_bytes(),original)
        self.assertIn('.recovery',Path(report['backup_path']).parts)
        self.assertEqual(project.settings['gamma'],1.6)
        self.assertEqual(project.settings['buffer_kernel_size'],5)
        self.assertEqual([change['field'] for change in report['changes']],['buffer_kernel_size'])
        saved=json.loads(self.path.read_text(encoding='utf-8'))
        for name in ('sources','datasets','active_dataset_id','custom_extension'):
            self.assertEqual(saved[name],before[name])
        self.assertEqual(saved['history'][:-1],before['history'])
        event=saved['history'][-1]
        self.assertEqual(event['action'],'recover_project_settings')
        self.assertEqual(event['defaults_version'],DEFAULTS_VERSION)
        self.assertEqual((event['changes'][0]['old'],event['changes'][0]['new']),(6,5))
        self.assertEqual(event['backup_path'],report['backup_path'])
        self.assertEqual(Project.load(self.path).settings,project.settings)

    def test_recovery_is_idempotent_and_valid_legacy_settings_are_not_rewritten(self):
        settings=dict(gamma=1.6,buffer_kernel_size=6)
        before,original,project=self.write_document(settings)
        first=recover_project_settings(project)
        recovered=self.path.read_bytes()
        second=recover_project_settings(project)
        self.assertFalse(second['changed'])
        self.assertIsNone(second['backup_path'])
        self.assertEqual(self.path.read_bytes(),recovered)
        self.assertEqual(len(list((self.root/'.recovery').iterdir())),1)
        self.assertEqual(set(project.settings),{'gamma','buffer_kernel_size'})
        self.path.write_bytes(original.replace(b'"buffer_kernel_size": 6',b'"buffer_kernel_size": 5'))
        valid_bytes=self.path.read_bytes()
        valid=Project.load(self.path)
        self.assertFalse(recover_project_settings(valid)['changed'])
        self.assertEqual(self.path.read_bytes(),valid_bytes)

    def test_malformed_settings_containers_recover_without_losing_other_data(self):
        for malformed in (None,[],42,'broken settings'):
            with self.subTest(settings=malformed):
                before,original,project=self.write_document(malformed)
                report=recover_project_settings(project)
                self.assertEqual(project.settings,factory_defaults())
                self.assertEqual(Path(report['backup_path']).read_bytes(),original)
                self.assertEqual(project.sources,before['sources'])
                self.assertEqual(project.datasets,before['datasets'])
                self.assertEqual(report['changes'][0]['action'],'replace_invalid_settings_container')

    def test_unknown_settings_are_backed_up_and_removed_with_audit_reason(self):
        settings=dict(gamma=1.6,future_option=dict(value='preserve in backup'))
        before,original,project=self.write_document(settings)
        report=recover_project_settings(project)
        self.assertEqual(project.settings,dict(gamma=1.6))
        self.assertEqual(report['changes'][0]['action'],'remove_unknown_setting')
        self.assertEqual(report['changes'][0]['old'],settings['future_option'])
        self.assertEqual(Path(report['backup_path']).read_bytes(),original)
        self.assertEqual(json.loads(self.path.read_text())['custom_extension'],before['custom_extension'])

    def test_multiple_invalid_fields_and_types_are_reported_and_repaired_together(self):
        settings=dict(target_size='bad',overview_size=0,buffer_kernel_size=6,channel=-1,
                      enable_gamma='yes',pixel_size_um=[],gamma=1.6)
        issues=inspect_settings(settings)
        expected={'target_size','overview_size','buffer_kernel_size','channel','enable_gamma','pixel_size_um'}
        self.assertEqual({issue['field'] for issue in issues},expected)
        self.write_document(settings)
        project=Project.load(self.path)
        report=recover_project_settings(project)
        self.assertEqual({change['field'] for change in report['changes']},expected)
        self.assertEqual(project.settings['gamma'],1.6)
        runtime=PipelineSettings.from_dict(project.settings)
        self.assertEqual(runtime.margins()['margin_start'],1125)
        self.assertEqual(runtime.margins()['margin_end'],1462)

    def test_backend_remains_strict_and_project_save_cannot_persist_invalid_settings(self):
        settings=dict(gamma=1.6,buffer_kernel_size=6)
        before,original,project=self.write_document(settings)
        with self.assertRaises(SettingsValidationError) as caught:PipelineSettings.from_dict(settings)
        self.assertEqual(caught.exception.issues[0]['field'],'buffer_kernel_size')
        with self.assertRaises(SettingsValidationError):project.save()
        self.assertEqual(self.path.read_bytes(),original)
        self.assertFalse((self.root/'.recovery').exists())
        invalid=PipelineSettings(); invalid.gamma='invalid'; invalid.channel=True
        self.assertEqual({issue['field'] for issue in invalid.validation_issues()},{'gamma','channel'})
        with self.assertRaises(SettingsValidationError):invalid.validate()

    def test_nonfinite_invalid_values_are_preserved_descriptively_in_history(self):
        settings=dict(gamma=float('nan'),pixel_size_um=float('inf'))
        before,original,project=self.write_document(settings)
        report=recover_project_settings(project)
        self.assertEqual(project.settings,dict(gamma=1.2,pixel_size_um=None))
        gamma_change=next(change for change in report['changes'] if change['field']=='gamma')
        self.assertEqual(gamma_change['old'],dict(type='float',representation='nan'))
        def reject_constant(value):raise AssertionError('Nonfinite literal persisted: '+value)
        json.loads(self.path.read_text(),parse_constant=reject_constant)
        self.assertEqual(Path(report['backup_path']).read_bytes(),original)

    def test_failed_final_save_rolls_back_memory_and_keeps_original_bytes(self):
        before,original,project=self.write_document(dict(gamma=1.6,buffer_kernel_size=6))
        settings_before=copy.deepcopy(project.settings); history_before=copy.deepcopy(project.history)
        with patch('src.desktop.project.atomic_json',side_effect=PermissionError('simulated write failure')):
            with self.assertRaises(PermissionError):recover_project_settings(project)
        self.assertEqual(self.path.read_bytes(),original)
        self.assertEqual(project.settings,settings_before)
        self.assertEqual(project.history,history_before)
        backups=list((self.root/'.recovery').glob('*/project.json'))
        self.assertEqual(len(backups),1)
        self.assertEqual(backups[0].read_bytes(),original)

    def test_backup_failure_prevents_any_project_save(self):
        before,original,project=self.write_document(dict(buffer_kernel_size=6))
        with patch('src.desktop.settings_safety.backup_project',side_effect=PermissionError('backup denied')):
            with self.assertRaises(PermissionError):recover_project_settings(project)
        self.assertEqual(self.path.read_bytes(),original)
        self.assertEqual(project.settings,dict(buffer_kernel_size=6))
        self.assertEqual(project.history,before['history'])

    def test_public_backup_is_unique_and_does_not_save_project(self):
        before,original,project=self.write_document(dict(gamma=1.6))
        first=Path(backup_project(project,'Manual settings reset'))
        second=Path(backup_project(project,'Manual settings reset'))
        self.assertNotEqual(first,second)
        self.assertEqual(first.read_bytes(),original)
        self.assertEqual(second.read_bytes(),original)
        self.assertEqual(self.path.read_bytes(),original)
        self.assertEqual(project.history,before['history'])


if __name__=='__main__':unittest.main()
