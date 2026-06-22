import re
import unittest
from pathlib import Path

from flask import request, url_for
from werkzeug.security import generate_password_hash

from app import create_app, db
from app.models import Professor
from config import TestingConfig


class SecureProxyTestingConfig(TestingConfig):
    SECRET_KEY = "test-secret-key"
    DEFAULT_ADMIN_ENABLED = False
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True
    SESSION_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_SAMESITE = "Lax"
    FORCE_HTTPS = True
    TRUST_PROXY_HEADERS = True
    PROXY_FIX_X_FOR = 1
    PROXY_FIX_X_PROTO = 1
    PROXY_FIX_X_HOST = 1
    PROXY_FIX_X_PORT = 1
    TRUSTED_HOSTS = ["agenda.example.edu.br"]
    HSTS_MAX_AGE = 31536000


class AuthSecurityTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(SecureProxyTestingConfig)
        self.app.add_url_rule(
            "/_test/request-info",
            endpoint="_test_request_info",
            view_func=lambda: "|".join(
                (
                    request.scheme,
                    request.host,
                    url_for("main.login", _external=True),
                )
            ),
        )
        self.client = self.app.test_client()
        self.proxy_headers = {
            "Host": "127.0.0.1:5000",
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Host": "agenda.example.edu.br",
            "X-Forwarded-Port": "443",
            "X-Forwarded-For": "203.0.113.10",
        }

    def get_login(self):
        return self.client.get("/login", headers=self.proxy_headers)

    def extract_csrf(self, response):
        match = re.search(
            r'name="_csrf_token" value="([^"]+)"',
            response.get_data(as_text=True),
        )
        self.assertIsNotNone(match)
        return match.group(1)

    def test_proxy_headers_define_public_https_url(self):
        response = self.client.get("/_test/request-info", headers=self.proxy_headers)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_data(as_text=True),
            "https|agenda.example.edu.br|https://agenda.example.edu.br/login",
        )

    def test_plain_http_is_redirected_to_https(self):
        response = self.client.get(
            "/login",
            base_url="http://agenda.example.edu.br",
        )

        self.assertEqual(response.status_code, 308)
        self.assertEqual(
            response.headers["Location"],
            "https://agenda.example.edu.br/login",
        )

    def test_login_cookie_and_security_headers_are_hardened(self):
        response = self.get_login()
        cookie = response.headers.get("Set-Cookie", "")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('action="/login"', html)
        self.assertNotIn('action="http:', html)
        self.assertIn("Secure", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Lax", cookie)
        self.assertEqual(
            response.headers["Strict-Transport-Security"],
            "max-age=31536000",
        )
        self.assertIn(
            "upgrade-insecure-requests",
            response.headers["Content-Security-Policy"],
        )
        self.assertIn("no-store", response.headers["Cache-Control"])

    def test_valid_login_csrf_reaches_login_handler(self):
        page = self.get_login()
        token = self.extract_csrf(page)

        response = self.client.post(
            "/login",
            headers=self.proxy_headers,
            data={"_csrf_token": token, "matricula": "nao-existe"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Matrícula não encontrada", response.get_data(as_text=True))

    def test_successful_login_sets_secure_session_and_remember_cookies(self):
        with self.app.app_context():
            db.session.add(
                Professor(
                    nome="Professora Teste",
                    matricula="12345678901",
                    senha=generate_password_hash("nao-utilizada"),
                    is_admin=False,
                )
            )
            db.session.commit()

        page = self.get_login()
        token = self.extract_csrf(page)
        response = self.client.post(
            "/login",
            headers=self.proxy_headers,
            data={"_csrf_token": token, "matricula": "123.456.789-01"},
        )
        cookies = response.headers.getlist("Set-Cookie")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/")
        self.assertTrue(any(cookie.startswith("session_eesjv=") for cookie in cookies))
        self.assertTrue(any(cookie.startswith("remember_token=") for cookie in cookies))
        for cookie in cookies:
            if cookie.startswith(("session_eesjv=", "remember_token=")):
                self.assertIn("Secure", cookie)
                self.assertIn("HttpOnly", cookie)
                self.assertIn("SameSite=Lax", cookie)

    def test_stale_login_csrf_gets_safe_retry_instead_of_bad_request_page(self):
        first_client = self.app.test_client()
        page = first_client.get("/login", headers=self.proxy_headers)
        stale_token = self.extract_csrf(page)

        response = self.client.post(
            "/login",
            headers=self.proxy_headers,
            data={"_csrf_token": stale_token, "matricula": "nao-existe"},
        )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["Location"], "/login")

        retry_page = self.client.get(
            response.headers["Location"],
            headers=self.proxy_headers,
        )
        self.assertEqual(retry_page.status_code, 200)
        self.assertIn(
            "formulário foi renovado",
            retry_page.get_data(as_text=True),
        )

    def test_untrusted_host_is_rejected(self):
        response = self.client.get(
            "/login",
            base_url="https://host-invalido.example",
        )

        self.assertEqual(response.status_code, 400)

    def test_service_worker_never_caches_navigation_or_unsafe_requests(self):
        service_worker = (
            Path(__file__).resolve().parents[1] / "app" / "static" / "sw.js"
        ).read_text(encoding="utf-8")
        login_template = (
            Path(__file__).resolve().parents[1] / "app" / "templates" / "login.html"
        ).read_text(encoding="utf-8")

        self.assertNotIn("  '/',", service_worker)
        self.assertNotIn("caches.match('/')", service_worker)
        self.assertIn("event.request.method !== 'GET'", service_worker)
        self.assertIn("event.request.mode === 'navigate'", service_worker)
        self.assertIn('scope: "/static/"', login_template)


if __name__ == "__main__":
    unittest.main()
