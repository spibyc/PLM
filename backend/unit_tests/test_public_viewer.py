"""Authorization tests with mocked storage; no PostgreSQL service required."""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault("PLM_DATABASE_URL", "postgresql+psycopg://unused/unused")

from fastapi.testclient import TestClient
from starlette.requests import Request

from app.api.deps import current_actor
from app.context import Actor
from app.core.errors import Forbidden
from app.db import get_db
from app.main import create_app


class PublicViewerTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.db = MagicMock()
        self.app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()

    def test_identity_needs_no_user_or_session_record(self):
        r = self.client.get("/api/auth/me")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["anonymous"])
        self.assertIsNone(r.json()["id"])
        self.assertEqual(set(r.json()["permissions"]), {"item:read", "inventory:read", "location:read"})
        self.db.get.assert_not_called()
        self.db.commit.assert_not_called()

    def test_parts_and_stock_reads(self):
        with patch("app.api.routes.items.items.list_items", return_value={"items": [], "total": 0}):
            self.assertEqual(self.client.get("/api/items").status_code, 200)
        self.assertEqual(self.client.get("/api/items/meta").status_code, 200)

    def test_location_and_lot_qr_targets_show_contents(self):
        ident = "00000000-0000-0000-0000-000000000001"
        location = {"id": ident, "code": "STORE.BIN", "contents": [{"lot_no": "LOT-1", "qty_on_hand": 5}]}
        with patch("app.api.routes.inventory.locations.location_detail", return_value=location):
            for path in ("/api/locations/by-code/STORE.BIN", f"/api/locations/{ident}"):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["contents"], location["contents"])
        self.db.execute.return_value.scalar_one_or_none.return_value = SimpleNamespace(id=ident)
        with patch("app.api.routes.inventory.inventory.lot_detail", return_value={"id": ident, "lot_no": "LOT-1"}):
            for path in ("/api/lots/by-number/LOT-1", f"/api/lots/{ident}"):
                self.assertEqual(self.client.get(path).status_code, 200)

    def test_qr_is_available_without_login(self):
        r = self.client.get("/api/qr/item/00000000-0000-0000-0000-000000000001.svg")
        self.assertEqual(r.status_code, 200)
        self.assertIn("image/svg+xml", r.headers["content-type"])

    def test_restricted_reads(self):
        for path in ("/api/audit", "/api/users", "/api/dashboard"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 403)

    def test_all_authenticated_write_routes_reject_anonymous(self):
        # Includes signing/inspection endpoints that require only a read permission
        # at the route layer and enforce signing rights deeper in the service.
        import re
        checked = 0
        for path, operations in self.app.openapi()["paths"].items():
            if path == "/api/auth/login":
                continue
            concrete = re.sub(r"\{[^}]+\}", "00000000-0000-0000-0000-000000000001", path)
            for method in operations:
                if method.upper() not in {"POST", "PUT", "PATCH", "DELETE"}:
                    continue
                with self.subTest(path=path, method=method):
                    response = self.client.request(method, concrete, json={})
                    self.assertEqual(response.status_code, 401, response.text)
                    checked += 1
        self.assertGreater(checked, 20)
        self.db.commit.assert_not_called()

    def test_expired_cookie_falls_back_to_viewer(self):
        self.client.cookies.set("plm_session", "expired")
        with patch("app.api.deps.auth.resolve_session", return_value=None):
            self.assertTrue(self.client.get("/api/auth/me").json()["anonymous"])
            self.assertEqual(self.client.post("/api/auth/change-password", json={}).status_code, 401)

    def test_staff_still_need_csrf_and_retain_identity(self):
        actor = Actor(user_id=None, username="staff", full_name="Staff")
        session = SimpleNamespace(id="session", csrf_token="valid")
        with patch("app.api.deps.auth.resolve_session", return_value=(session, object())), patch("app.api.deps.auth.actor_for", return_value=actor):
            request = Request({"type": "http", "method": "POST", "headers": [(b"cookie", b"plm_session=token")]})
            with self.assertRaises(Forbidden):
                current_actor(request, self.db)
            request = Request({"type": "http", "method": "POST", "headers": [(b"cookie", b"plm_session=token"), (b"x-csrf-token", b"valid")]})
            self.assertIs(current_actor(request, self.db), actor)


if __name__ == "__main__":
    unittest.main()
