"""Session auth and goals endpoints, as the Next.js frontend uses them."""

from django.contrib.auth.models import User
from django.test import Client, TestCase

from accounts.models import Profile


def _json_post(client: Client, path: str, data: dict | None = None, **headers):
    return client.post(path, data or {}, content_type="application/json", headers=headers)


class AuthApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alex", password="pw12345!")

    def test_login_sets_a_session_and_me_returns_the_user(self):
        response = _json_post(self.client, "/api/auth/login", {"username": "alex", "password": "pw12345!"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"username": "alex", "is_staff": False})
        self.assertEqual(self.client.get("/api/auth/me").json()["username"], "alex")

    def test_wrong_password_is_rejected(self):
        response = _json_post(self.client, "/api/auth/login", {"username": "alex", "password": "nope"})

        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

    def test_login_requires_the_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        credentials = {"username": "alex", "password": "pw12345!"}

        self.assertEqual(_json_post(client, "/api/auth/login", credentials).status_code, 403)

        self.assertEqual(client.get("/api/auth/csrf").status_code, 204)
        token = client.cookies["csrftoken"].value
        response = _json_post(client, "/api/auth/login", credentials, X_CSRFToken=token)
        self.assertEqual(response.status_code, 200)

    def test_authenticated_writes_require_the_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)

        self.assertEqual(_json_post(client, "/api/auth/logout").status_code, 403)

    def test_logout_ends_the_session(self):
        self.client.force_login(self.user)

        self.assertEqual(_json_post(self.client, "/api/auth/logout").status_code, 204)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)


class GoalsApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alex", password="pw12345!")
        self.client.force_login(self.user)

    def test_new_user_has_no_goals(self):
        body = self.client.get("/api/profile").json()

        self.assertEqual(set(body.values()), {None})

    def test_goals_are_saved_and_can_be_cleared(self):
        goals = {
            "daily_calorie_target": 2000,
            "protein_target_g": 120,
            "carbs_target_g": None,
            "fat_target_g": None,
            "fiber_target_g": 30,
        }

        response = self.client.put("/api/profile", goals, content_type="application/json")

        self.assertEqual(response.status_code, 200)
        profile = Profile.objects.get(user=self.user)
        self.assertEqual((profile.daily_calorie_target, profile.fiber_target_g), (2000, 30))
        self.assertTrue(profile.has_goals())

        cleared = dict.fromkeys(goals)
        self.client.put("/api/profile", cleared, content_type="application/json")
        profile.refresh_from_db()
        self.assertFalse(profile.has_goals())

    def test_negative_target_is_rejected(self):
        response = self.client.put("/api/profile", {"protein_target_g": -5}, content_type="application/json")

        self.assertEqual(response.status_code, 422)

    def test_anonymous_user_is_rejected(self):
        self.client.logout()

        self.assertEqual(self.client.get("/api/profile").status_code, 401)
