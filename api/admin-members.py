import json
import os
import re
from http.server import BaseHTTPRequestHandler
from urllib.error import HTTPError
from uuid import UUID

from article_service import request_json


def create_member(token, body):
    url = os.environ.get('NEXT_PUBLIC_SUPABASE_URL', '').strip().rstrip('/')
    public_key = os.environ.get('NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY', '').strip()
    service = os.environ.get('SUPABASE_SERVICE_ROLE_KEY', '').strip()
    if not url or not public_key or not service:
        return 503, {'error': 'server_setup_required'}
    if not token.startswith('Bearer ') or len(token) > 10000:
        return 401, {'error': 'login_required'}
    public_headers = {'apikey': public_key, 'Authorization': token}
    try:
        user = request_json(url + '/auth/v1/user', headers=public_headers)
        allowed = request_json(url + '/rest/v1/rpc/tripfact_is_admin', {}, public_headers)
        if allowed is not True or not user.get('id'):
            return 403, {'error': 'admin_required'}
    except Exception:
        return 403, {'error': 'admin_required'}
    if not isinstance(body, dict):
        return 400, {'error': 'invalid_fields'}
    email = str(body.get('email', '')).strip().lower()
    password = body.get('password', '')
    role = body.get('role')
    name = str(body.get('name', '')).strip()
    company = str(body.get('company', '')).strip()
    try:
        request_id = str(UUID(str(body.get('request_id', ''))))
    except ValueError:
        return 400, {'error': 'invalid_fields'}
    if (not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email) or len(email) > 254
            or not isinstance(password, str) or not 12 <= len(password) <= 128
            or role not in ('consumer', 'business', 'admin') or len(name) > 40
            or (role == 'business' and not 1 <= len(company) <= 120)
            or (role == 'admin' and body.get('admin_ack') is not True)):
        return 400, {'error': 'invalid_fields'}
    service_headers = {'apikey': service}
    if service.startswith('eyJ'):
        service_headers['Authorization'] = 'Bearer ' + service
    status_data = {'p_request': request_id, 'p_actor': user['id']}
    def previous():
        return request_json(url + '/rest/v1/rpc/tripfact_admin_creation_status', status_data, service_headers)
    try:
        old = previous()
    except Exception:
        return 503, {'error': 'sql_or_server_setup_required'}
    if old:
        if old['email'].lower() != email or old['role'] != role:
            return 409, {'error': 'request_conflict'}
        return 200, {'member': old}
    payload = {
        'email': email, 'password': password, 'email_confirm': True,
        'user_metadata': {'display_name': name, 'member_type': 'business' if role == 'business' else 'consumer', 'business_name': company if role == 'business' else ''},
        'app_metadata': {'tripfact_created_by': user['id'], 'tripfact_create_request': request_id,
                         'tripfact_role': role, 'tripfact_approved': role == 'business' and body.get('approved') is True},
    }
    try:
        request_json(url + '/auth/v1/admin/users', payload, service_headers)
        created = previous()
        if not created:
            return 503, {'error': 'creation_unconfirmed'}
        return 201, {'member': created}
    except HTTPError as error:
        # A completed concurrent request may have returned an email-already-exists response.
        try:
            old = previous()
            if old and old['email'].lower() == email and old['role'] == role:
                return 200, {'member': old}
        except Exception:
            pass
        if error.code in (400, 422):
            try:
                info = json.loads(error.read(4096))
            except Exception:
                info = {}
            if info.get('code') in ('email_exists', 'user_already_exists') or info.get('error_code') in ('email_exists', 'user_already_exists'):
                return 409, {'error': 'email_exists'}
            return 400, {'error': 'create_rejected'}
        return 502, {'error': 'create_failed'}
    except Exception:
        return 502, {'error': 'retry_same_request'}


def update_member(token, body):
    url = os.environ.get('NEXT_PUBLIC_SUPABASE_URL', '').strip().rstrip('/')
    public_key = os.environ.get('NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY', '').strip()
    service = os.environ.get('SUPABASE_SERVICE_ROLE_KEY', '').strip()
    if not url or not public_key or not service:
        return 503, {'error': 'server_setup_required'}
    if not token.startswith('Bearer ') or len(token) > 10000:
        return 401, {'error': 'login_required'}
    try:
        headers = {'apikey': public_key, 'Authorization': token}
        actor = request_json(url + '/auth/v1/user', headers=headers)
        if request_json(url + '/rest/v1/rpc/tripfact_is_admin', {}, headers) is not True:
            return 403, {'error': 'admin_required'}
    except Exception:
        return 403, {'error': 'admin_required'}
    if not isinstance(body, dict) or body.get('action') not in ('info', 'password'):
        return 400, {'error': 'invalid_fields'}
    try:
        target = str(UUID(str(body.get('user_id', ''))))
        request_id = str(UUID(str(body.get('request_id', ''))))
    except ValueError:
        return 400, {'error': 'invalid_fields'}
    kind = body['action']
    if kind == 'password':
        password = body.get('password', '')
        if not isinstance(password, str) or not 12 <= len(password) <= 128:
            return 400, {'error': 'invalid_fields'}
    else:
        email = str(body.get('email', '')).strip().lower()
        name = str(body.get('name', '')).strip()
        company = str(body.get('company', '')).strip()
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email) or len(email) > 254 or len(name) > 40 or len(company) > 120:
            return 400, {'error': 'invalid_fields'}
    service_headers = {'apikey': service}
    if service.startswith('eyJ'):
        service_headers['Authorization'] = 'Bearer ' + service
    status_args = {'p_actor': actor['id'], 'p_user': target, 'p_request': request_id}
    def status():
        return request_json(url + '/rest/v1/rpc/tripfact_admin_member_edit_status', status_args, service_headers)
    try:
        previous = status()
    except Exception:
        return 503, {'error': 'edit_sql_required'}
    if not previous:
        return 404, {'error': 'member_not_found'}
    if previous['applied']:
        return 200, {'updated': True}
    if kind == 'info' and previous['member_type'] == 'business' and not company:
        return 400, {'error': 'invalid_fields'}
    try:
        old = request_json(url + '/auth/v1/admin/users/' + target, headers=service_headers)
        app_metadata = dict(old.get('app_metadata') or {})
        edit = {'actor': actor['id'], 'request_id': request_id, 'action': kind}
        payload = {}
        if kind == 'password':
            payload['password'] = password
        else:
            metadata = dict(old.get('user_metadata') or {})
            metadata['display_name'] = name
            if previous['member_type'] == 'business':
                metadata['business_name'] = company
                edit.update(company=company, approved=body.get('approved') is True)
            payload.update(email=email, email_confirm=True, user_metadata=metadata)
        app_metadata['tripfact_admin_edit'] = edit
        payload['app_metadata'] = app_metadata
        request_json(url + '/auth/v1/admin/users/' + target, payload, service_headers, method='PUT')
        final = status()
        if not final or not final['applied']:
            return 503, {'error': 'update_unconfirmed'}
        return 200, {'updated': True}
    except HTTPError as error:
        if error.code == 404:
            return 404, {'error': 'member_not_found'}
        if error.code in (400, 422):
            return 400, {'error': 'update_rejected'}
        return 502, {'error': 'update_failed'}
    except Exception:
        return 502, {'error': 'retry_same_request'}


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        self.process(create_member)

    def do_PATCH(self):
        self.process(update_member)

    def process(self, operation):
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if size <= 0 or size > 8192:
                self.reply(400, {'error': 'invalid_fields'})
                return
            body = json.loads(self.rfile.read(size))
        except (ValueError, UnicodeError):
            self.reply(400, {'error': 'invalid_fields'})
            return
        status, data = operation(self.headers.get('Authorization', ''), body)
        self.reply(status, data)

    def reply(self, status, data):
        payload = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
