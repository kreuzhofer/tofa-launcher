"""Synthetic Responses for runtime calibration with the production launcher.

Native launch control stays with the registered adapter. Model requests never
reach it; this boundary cannot qualify adapter inference or model capability.
"""
import json

from capability_observer import Observer


class SyntheticObserver(Observer):
    def __init__(self, *args, respond, **kwargs):
        self.respond = respond
        super().__init__(*args, **kwargs)

    def forward(self, handler, body, record):
        if record is None:
            return super().forward(handler, body, record)
        record.update(forwarded=False, transport='synthetic_observer')
        if record['role'] not in ('main', 'auxiliary_title'):
            self.reject(handler, 'synthetic_guardian_unsupported', 400, body,
                known_role=record['role'])
            return
        try:
            # Naming keeps its independent routed identity. Approval decisions
            # are never synthesized, and the live evaluator uses Observer.
            response = self.respond(dict(body, model=record['routed_model']))
            for frame in response.split(b'\n\n'):
                for line in frame.splitlines():
                    if line.startswith(b'data: ') and line[6:] != b'[DONE]':
                        self.event(record, json.loads(line[6:]))
            if not record.get('completed'): raise ValueError('synthetic_response_incomplete')
            record['status'] = 200
            handler.send_response(200)
            handler.send_header('Content-Type', 'text/event-stream')
            handler.end_headers()
            handler.wfile.write(response); handler.wfile.flush()
        except (OSError, ValueError, TypeError, KeyError):
            record['failure'] = 'synthetic_response_failed'
            raise
        finally:
            with self.lock:
                record['ended_ms'] = self.elapsed()
                self.persist()
