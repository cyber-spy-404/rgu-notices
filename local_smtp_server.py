import asyncio
import threading
import email
from email import policy
from aiosmtpd.controller import Controller
import database as db

class LocalSMTPHandler:
    async def handle_DATA(self, server, session, envelope):
        mail_from = envelope.mail_from
        rcpt_tos = envelope.rcpt_tos
        content = envelope.content

        # Parse MIME message
        try:
            msg = email.message_from_bytes(content, policy=policy.default)
            subject = msg.get('Subject', '(No Subject)')
            
            body_text = ''
            body_html = ''

            if msg.is_multipart():
                for part in msg.walk():
                    ctype = part.get_content_type()
                    cdispo = str(part.get('Content-Disposition'))
                    if 'attachment' not in cdispo:
                        if ctype == 'text/plain' and not body_text:
                            body_text = part.get_payload(decode=True).decode(part.get_content_charset() or 'utf-8', errors='ignore')
                        elif ctype == 'text/html' and not body_html:
                            body_html = part.get_payload(decode=True).decode(part.get_content_charset() or 'utf-8', errors='ignore')
            else:
                ctype = msg.get_content_type()
                payload = msg.get_payload(decode=True)
                charset = msg.get_content_charset() or 'utf-8'
                text = payload.decode(charset, errors='ignore') if payload else ''
                if ctype == 'text/html':
                    body_html = text
                else:
                    body_text = text

            db.add_inbox_email(mail_from, rcpt_tos, subject, body_text, body_html)
            db.log_event('INFO', 'SMTP', f'Local SMTP captured email: "{subject}" to {len(rcpt_tos)} recipient(s)')
        except Exception as e:
            db.log_event('ERROR', 'SMTP', f'Failed parsing inbound email: {str(e)}')

        return '250 Message accepted for delivery by RGU Local SMTP Server'

_controller = None
_server_thread = None
_is_running = False

def start_local_smtp_server(host='127.0.0.1', port=2525):
    global _controller, _is_running
    if _is_running and _controller:
        return True, f'Local SMTP Server already running on {host}:{port}'
    
    try:
        handler = LocalSMTPHandler()
        _controller = Controller(handler, hostname=host, port=port)
        _controller.start()
        _is_running = True
        db.log_event('SUCCESS', 'SMTP', f'Built-in Local SMTP Server running on {host}:{port}')
        return True, f'Local SMTP Server active on {host}:{port}'
    except Exception as e:
        _is_running = False
        db.log_event('ERROR', 'SMTP', f'Failed to start Local SMTP Server on {host}:{port}: {str(e)}')
        return False, str(e)

def stop_local_smtp_server():
    global _controller, _is_running
    if _controller and _is_running:
        try:
            _controller.stop()
            _is_running = False
            db.log_event('INFO', 'SMTP', 'Local SMTP Server stopped.')
            return True, 'Local SMTP Server stopped'
        except Exception as e:
            return False, str(e)
    return True, 'Server was not running'

def get_smtp_status():
    global _is_running, _controller
    return {
        'running': _is_running,
        'host': _controller.hostname if _controller else '127.0.0.1',
        'port': _controller.port if _controller else 2525
    }
