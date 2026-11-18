"""Local HTTP load test for authenticated GoClinical sessions."""
import os
from urllib.parse import urlparse

from locust import HttpUser, between, task
from locust.exception import StopUser


class GoClinicalSessionUser(HttpUser):
    host = "http://127.0.0.1:8000"
    wait_time = between(3, 6)

    def on_start(self):
        if urlparse(self.host).hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise StopUser("This load test is restricted to the local machine.")

        username = os.environ.get("LOCUST_USERNAME", "paciente")
        password = os.environ.get("LOCUST_PASSWORD")
        if not password:
            raise StopUser("Set LOCUST_PASSWORD before starting Locust.")

        with self.client.get("/login/", name="/login/", catch_response=True) as response:
            csrf_token = self.client.cookies.get("csrftoken")
            if response.status_code != 200 or not csrf_token:
                response.failure("Could not load the login form or its CSRF cookie.")
                raise StopUser()

        with self.client.post(
            "/login/",
            data={
                "username": username,
                "password": password,
                "csrfmiddlewaretoken": csrf_token,
            },
            headers={"Referer": f"{self.host.rstrip('/')}/login/"},
            name="/login/",
            allow_redirects=False,
            catch_response=True,
        ) as response:
            if response.status_code != 302 or response.headers.get("Location") != "/portal/paciente/":
                response.failure("Login did not redirect to the patient portal.")
                raise StopUser()

        self.logged_in = True
        self._get_portal()

    def on_stop(self):
        if not getattr(self, "logged_in", False):
            return

        csrf_token = self.client.cookies.get("csrftoken")
        with self.client.post(
            "/logout/",
            data={"csrfmiddlewaretoken": csrf_token},
            headers={"Referer": f"{self.host.rstrip('/')}/portal/paciente/"},
            name="/logout/",
            allow_redirects=False,
            catch_response=True,
        ) as response:
            if response.status_code != 302 or response.headers.get("Location") != "/":
                response.failure("Logout did not redirect to the public page.")
            else:
                self.logged_in = False

    def _get_json(self, path, expected_key):
        with self.client.get(path, name=path, catch_response=True) as response:
            if response.status_code != 200:
                response.failure(f"Expected HTTP 200, received {response.status_code}.")
                return
            try:
                payload = response.json()
            except ValueError:
                response.failure("Response was not valid JSON.")
                return
            if expected_key not in payload:
                response.failure(f"Response did not contain {expected_key!r}.")

    def _get_portal(self):
        with self.client.get(
            "/portal/paciente/",
            name="/portal/paciente/",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"Expected HTTP 200, received {response.status_code}.")

    @task(3)
    def read_state(self):
        self._get_json("/api/state/", "state")

    @task(2)
    def open_portal(self):
        self._get_portal()

    @task(1)
    def list_documents(self):
        self._get_json("/api/documents/", "documents")

    @task(1)
    def view_tracking(self):
        self._get_json("/api/tracking/", "trips")
