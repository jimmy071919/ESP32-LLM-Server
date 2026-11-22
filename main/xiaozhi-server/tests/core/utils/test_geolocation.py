"""IP geolocation is opt-in and allowlisted; nothing is sent by default."""
import unittest
from unittest.mock import MagicMock

from core.utils.geolocation import is_private_or_local_ip, lookup_ip_location


def fake_get(payload, status=200):
    response = MagicMock(status_code=status)
    response.json.return_value = payload
    return MagicMock(return_value=response)


class GeolocationTests(unittest.TestCase):
    def test_disabled_by_default(self):
        http_get = fake_get({"city": "X"})
        self.assertEqual(lookup_ip_location("8.8.8.8", {}, http_get=http_get), {})
        self.assertEqual(lookup_ip_location("8.8.8.8", {"geolocation": {"provider": "none"}}, http_get=http_get), {})
        http_get.assert_not_called()

    def test_unknown_provider_is_disabled_not_fallback(self):
        http_get = fake_get({"city": "X"})
        config = {"geolocation": {"provider": "pconline"}}
        self.assertEqual(lookup_ip_location("8.8.8.8", config, http_get=http_get), {})
        http_get.assert_not_called()

    def test_private_ip_skipped_unless_opted_in(self):
        http_get = fake_get({"city": "Taipei", "loc": "25.0,121.5"})
        config = {"geolocation": {"provider": "ipinfo", "api_key": "t"}}
        self.assertEqual(lookup_ip_location("192.168.1.5", config, http_get=http_get), {})
        http_get.assert_not_called()
        config["geolocation"]["lookup_private_ip_as_server"] = True
        info = lookup_ip_location("192.168.1.5", config, http_get=http_get)
        self.assertEqual(info["city"], "Taipei")
        self.assertEqual(http_get.call_args.args[0], "https://ipinfo.io/json")

    def test_ipinfo_and_ipwhois_parsing(self):
        http_get = fake_get({"city": "Taipei", "region": "Taipei", "country": "TW", "loc": "25.04,121.53"})
        info = lookup_ip_location("8.8.8.8", {"geolocation": {"provider": "ipinfo", "api_key": "tok"}}, http_get=http_get)
        self.assertEqual(info["latitude"], 25.04)
        self.assertEqual(http_get.call_args.kwargs["params"], {"token": "tok"})
        http_get = fake_get({"success": True, "city": "Tokyo", "country_code": "JP", "latitude": 35.6, "longitude": 139.7})
        info = lookup_ip_location("8.8.4.4", {"geolocation": {"provider": "ipwhois"}}, http_get=http_get)
        self.assertEqual((info["city"], info["country"]), ("Tokyo", "JP"))
        self.assertTrue(http_get.call_args.args[0].startswith("https://ipwho.is/"))

    def test_errors_return_empty(self):
        self.assertEqual(lookup_ip_location("8.8.8.8", {"geolocation": {"provider": "ipwhois"}}, http_get=fake_get({}, 500)), {})
        boom = MagicMock(side_effect=OSError("network"))
        self.assertEqual(lookup_ip_location("8.8.8.8", {"geolocation": {"provider": "ipwhois"}}, http_get=boom), {})

    def test_private_detection(self):
        for ip in ("10.0.0.1", "172.16.3.4", "192.168.0.1", "127.0.0.1", "::1", "fe80::1", "fd00::1", "", "bad"):
            self.assertTrue(is_private_or_local_ip(ip), ip)
        self.assertFalse(is_private_or_local_ip("8.8.8.8"))


if __name__ == "__main__":
    unittest.main()
