"""A worker must use the UI language even before opening the project."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class WorkerLanguageTests(unittest.TestCase):
    def test_default_english_and_requested_russian_and_hebrew_startup_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / 'broken.json'
            project.write_text(json.dumps({'schema_version': 999}), encoding='utf-8')
            for language, expected in ((None, 'Unsupported SoLoData project version.'),
                                       ('en', 'Unsupported SoLoData project version.'),
                                       ('ru', 'Неподдерживаемая версия проекта SoLoData.'),
                                       ('he', 'גרסת הפרויקט של SoLoData אינה נתמכת.')):
                with self.subTest(language=language):
                    request = {'project_path': str(project), 'action': 'prepare'}
                    if language is not None:
                        request['language'] = language
                    path = root / 'request.json'
                    path.write_text(json.dumps(request), encoding='utf-8')
                    result = subprocess.run(
                        [sys.executable, '-B', '-m', 'src.desktop.worker', '--request', str(path)],
                        cwd=Path(__file__).resolve().parents[1],
                        capture_output=True, text=True, encoding='utf-8', timeout=15)
                    self.assertEqual(result.returncode, 1)
                    events = [json.loads(line) for line in result.stdout.splitlines()]
                    errors = [event for event in events if event['type'] == 'error']
                    self.assertEqual(errors[0]['message'], expected)
                    self.assertTrue(Path(str(path) + '.events.json').is_file())


if __name__ == '__main__':
    unittest.main()
