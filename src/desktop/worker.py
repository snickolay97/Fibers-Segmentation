"""JSON event protocol for a separate, cancellable scientific worker process."""
import argparse
import contextlib
import json
from pathlib import Path
import sys
import traceback

from src.desktop.project import Project, atomic_json
from src.desktop.i18n import set_language


class LogStream:
    def __init__(self, emit):
        self.emit = emit
        self.buffer = ''

    def write(self, text):
        self.buffer += text
        while '\n' in self.buffer:
            line, self.buffer = self.buffer.split('\n', 1)
            if line.strip():
                self.emit(dict(type='log', message=line.rstrip()))
        return len(text)

    def flush(self):
        if self.buffer.strip():
            self.emit(dict(type='log', message=self.buffer))
        self.buffer = ''


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--request', required=True)
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    output = sys.stdout
    events = []

    def emit(event):
        events.append(event)
        output.write(json.dumps(event, ensure_ascii=False, default=str) + '\n')
        output.flush()

    request_path = Path(args.request).resolve()
    request = json.loads(request_path.read_text(encoding='utf-8'))
    log = LogStream(emit)
    exit_code = 0
    try:
        set_language(request.get('language', 'en'))
        from src.app_settings import PipelineCancelled
        from src.desktop.service import execute_action
        project = Project.load(request['project_path'])
        cancel_path = Path(str(request_path) + '.cancel')
        with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            summary = execute_action(project, request,
                progress=lambda event: emit(dict(event, type='progress')),
                cancelled=cancel_path.exists)
        status = summary.get('status', 'completed')
        exit_code = 1 if status in ('failed', 'error') else 0
        emit(dict(type='result', action=request['action'], status=status, summary=summary))
    except Exception as error:
        from src.app_settings import PipelineCancelled
        if isinstance(error, PipelineCancelled):
            emit(dict(type='result', action=request.get('action'), status='cancelled', summary={'status': 'cancelled'}))
            exit_code = 2
        else:
            emit(dict(type='error', action=request.get('action'), message=str(error), details=traceback.format_exc()))
            exit_code = 1
    finally:
        log.flush()
        atomic_json(str(request_path) + '.events.json', events)
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
