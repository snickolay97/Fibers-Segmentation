import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np
import tifffile

from src.app_settings import PipelineSettings
from src.desktop.project import Project
from src.desktop import service


class WorkerProtocolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.project = Project.create(self.root/'project.json')
        settings = PipelineSettings(target_size=128, overview_size=180, bilateral_d=3,
                                    tophat_radius=8, bridge_kernel_size=3, buffer_kernel_size=3)
        self.project.settings = settings.to_dict()
        image = np.zeros((150, 200), np.uint8)
        image[50:58,20:120] = 160
        tifffile.imwrite(self.root/'input.tif', image)
        service.add_sources(self.project, [self.root/'input.tif'])

    def tearDown(self):
        self.temp.cleanup()

    def run_worker(self, request, cancelled=False):
        path = self.root/'request.json'
        path.write_text(json.dumps(dict(project_path=self.project.path, **request)), encoding='utf-8')
        if cancelled:
            Path(str(path)+'.cancel').touch()
        process = subprocess.run([sys.executable, '-B', '-u', '-m', 'src.desktop.worker', '--request', str(path)],
                                 cwd=Path(__file__).resolve().parents[1], capture_output=True,
                                 encoding='utf-8', timeout=40)
        events = [json.loads(line) for line in process.stdout.splitlines() if line.strip()]
        self.assertTrue(Path(str(path)+'.events.json').is_file())
        return process, events

    def test_fresh_prepare_and_extract_processes(self):
        process, events = self.run_worker({'action':'prepare'})
        self.assertEqual(process.returncode, 0, process.stderr + process.stdout)
        self.assertTrue(any(e['type']=='progress' for e in events))
        result = next(e for e in events if e['type']=='result')
        self.assertEqual(result['status'], 'completed')
        project = Project.load(self.project.path)
        dataset = project.get_dataset(result['summary']['datasets'][0])
        process, events = self.run_worker({'action':'extract','dataset_id':dataset['id'],'labels_mode':'auto'})
        self.assertEqual(process.returncode, 0, process.stderr + process.stdout)
        result = next(e for e in events if e['type']=='result')
        self.assertGreater(result['summary']['objects'], 0)
        self.assertEqual(Project.load(project.path).get_dataset(dataset['id'])['status'], 'completed')

    def test_cancelled_has_terminal_result_and_no_published_dataset(self):
        process, events = self.run_worker({'action':'prepare'}, cancelled=True)
        self.assertEqual(process.returncode, 2)
        self.assertEqual(events[-1]['status'], 'cancelled')
        self.assertEqual(Project.load(self.project.path).datasets, [])

    def test_invalid_request_reports_error(self):
        process, events = self.run_worker({'action':'unknown'})
        self.assertEqual(process.returncode, 1)
        self.assertEqual(events[-1]['type'], 'error')
        self.assertIn('Unknown action', events[-1]['message'])


if __name__ == '__main__':
    unittest.main()
