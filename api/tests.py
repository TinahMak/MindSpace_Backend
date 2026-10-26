"""Email validation: one set of rules for the app, the website and new accounts."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.forms import SignupForm
from api.validators import InputError, clean_email

User = get_user_model()

MISTYPED = {
    "name@g.com": "Did you mean name@gmail.com?",
    "name@gm.com": "Did you mean name@gmail.com?",
    "name@gmial.com": "Did you mean name@gmail.com?",
    "name@gmal.com": "Did you mean name@gmail.com?",
    "name@gmail.con": "Did you mean name@gmail.com?",
    "name@gmail.co": "Did you mean name@gmail.com?",
    "name@yaho.co.za": "Did you mean name@yahoo.co.za?",
    "name@hotmial.com": "Did you mean name@hotmail.com?",
    "name@outlok.com": "Did you mean name@outlook.com?",
    "name@icoud.com": "Did you mean name@icloud.com?",
    "name@example.con": "Did you mean name@example.com?",
}

VALID = [
    "name@gmail.com",
    "name@yahoo.co.za",
    "name@hotmail.co.za",
    "name@outlook.com",
    "name@mail.com",
    "name@email.com",
    "name@gmx.com",
    "name@ymail.com",
    "name@googlemail.com",
    "name@live.com",
    "name@webmail.co.za",
    "name@mweb.co.za",
    "student@myuct.ac.za",
    "name@company.co.za",
    "a.b+tag@sub.domain.org",
]


class CleanEmailTests(TestCase):
    def test_mistyped_domains_are_rejected_with_a_suggestion(self):
        for email, message in MISTYPED.items():
            with self.subTest(email=email), self.assertRaisesMessage(InputError, message):
                clean_email(email)

    def test_real_domains_are_accepted(self):
        for email in VALID:
            with self.subTest(email=email):
                self.assertEqual(clean_email(email), email)

    def test_one_letter_domain_is_rejected(self):
        with self.assertRaisesMessage(InputError, "doesn't look right"):
            clean_email("name@x.com")

    def test_bad_shape_is_rejected(self):
        for email in ["name", "name@gmail", "name@@gmail.com", "na..me@gmail.com"]:
            with self.subTest(email=email), self.assertRaises(InputError):
                clean_email(email)

    def test_case_and_spaces_are_normalised(self):
        self.assertEqual(clean_email("  Name@Gmail.COM "), "name@gmail.com")


class SignupRejectsMistypedEmailTests(TestCase):
    def test_app_signup(self):
        r = APIClient().post("/api/v1/auth/signup/", {"email": "name@g.com"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("Did you mean name@gmail.com?", str(r.data["email"]))

    def test_website_signup(self):
        form = SignupForm(data={"email": "name@g.com"})
        self.assertFalse(form.is_valid())
        self.assertIn("Did you mean name@gmail.com?", form.errors["email"][0])


class ExistingAccountsStillLogInTests(TestCase):
    def test_login_is_not_blocked_by_the_stricter_signup_rules(self):
        User.objects.create_user(username="old@g.com", email="old@g.com", password="Str0ng!pass123")
        r = APIClient().post("/api/v1/auth/login/", {"email": "old@g.com", "password": "Str0ng!pass123"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertIn("token", r.data)
