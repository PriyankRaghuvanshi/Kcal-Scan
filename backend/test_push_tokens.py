"""Tests for push token store and registration."""
from __future__ import annotations

import os
import tempfile
import unittest

from push_token_store import register_push_token, unregister_push_token, list_tokens_for_user


class TestPushTokenStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["PUSH_TOKEN_STORE_PATH"] = os.path.join(self.tmp.name, "push_token_store.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_register_token_success(self):
        saved = register_push_token({
            "user_id": "u123",
            "expo_push_token": "ExponentPushToken[abc123xyz]",
            "platform": "ios",
        })
        self.assertEqual(saved["user_id"], "u123")
        self.assertEqual(saved["expo_push_token"], "ExponentPushToken[abc123xyz]")
        self.assertEqual(saved["platform"], "ios")
        self.assertTrue(saved["active"])
        self.assertIn("created_at", saved)
        self.assertIn("updated_at", saved)
        self.assertIn("last_seen_at", saved)

    def test_register_requires_user_id(self):
        with self.assertRaises(ValueError):
            register_push_token({
                "expo_push_token": "ExponentPushToken[abc]",
            })

    def test_register_requires_expo_token_format(self):
        with self.assertRaises(ValueError):
            register_push_token({
                "user_id": "u1",
                "expo_push_token": "invalid_token",
            })

    def test_duplicate_token_dedupe_update(self):
        first = register_push_token({
            "user_id": "u1",
            "expo_push_token": "ExponentPushToken[abc]",
            "platform": "ios",
        })
        second = register_push_token({
            "user_id": "u1",
            "expo_push_token": "ExponentPushToken[abc]",
            "platform": "android",
            "app_version": "1.0.3",
        })
        self.assertEqual(first["created_at"], second["created_at"])
        self.assertNotEqual(first["updated_at"], second["updated_at"])
        self.assertEqual(second["platform"], "android")
        self.assertEqual(second["app_version"], "1.0.3")

    def test_unregister_success(self):
        register_push_token({
            "user_id": "u1",
            "expo_push_token": "ExponentPushToken[xyz]",
            "platform": "android",
        })
        result = unregister_push_token({
            "user_id": "u1",
            "expo_push_token": "ExponentPushToken[xyz]",
        })
        self.assertEqual(result["ok"], True)
        tokens = list_tokens_for_user("u1", active_only=True)
        self.assertEqual(len(tokens), 0)

    def test_unregister_requires_user_id(self):
        with self.assertRaises(ValueError):
            unregister_push_token({"expo_push_token": "ExponentPushToken[abc]"})

    def test_unregister_requires_token(self):
        with self.assertRaises(ValueError):
            unregister_push_token({"user_id": "u1"})
