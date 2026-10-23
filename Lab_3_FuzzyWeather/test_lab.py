"""Локальные тесты не обращаются в сеть: python3 -m unittest -v."""
import copy
import math
import unittest
from unittest.mock import Mock, patch
import numpy as np
import skfuzzy as fuzz
from api_client import parse_current, request_json
from analysis import parse_history, seasonal_stats, anomaly
from fuzzy_model import WeatherFuzzy, recommendations
from settings import season_of
from nasa_history import normalize_nasa


def history_fixture():
    return {"timezone": "Europe/Moscow",
            "hourly_units": {"temperature_2m": "°C", "relative_humidity_2m": "%",
                             "wind_speed_10m": "m/s"},
            "hourly": {"time": ["2025-01-01T00:00", "2025-01-01T01:00"],
                       "temperature_2m": [0, 2], "relative_humidity_2m": [50, 70],
                       "wind_speed_10m": [1, 3]}}


class StatisticsTests(unittest.TestCase):
    def test_all_months(self):
        self.assertEqual([season_of(x) for x in range(1, 13)],
                         ["winter"]*2+["spring"]*3+["summer"]*3+["autumn"]*3+["winter"])

    def test_invalid_month(self):
        for month in [0, 13, 1.5, True]:
            with self.subTest(month=month), self.assertRaises(ValueError):
                season_of(month)

    def test_sample_std(self):
        frame, _ = parse_history("kazan", history_fixture())
        normal = seasonal_stats(frame).iloc[0]
        self.assertEqual(normal.temperature_mean, 1)
        self.assertAlmostEqual(normal.temperature_std, math.sqrt(2))

    def test_missing_excluded(self):
        data = history_fixture()
        data["hourly"]["temperature_2m"][0] = None
        frame, quality = parse_history("kazan", data)
        self.assertEqual(len(frame), 1)
        self.assertEqual(quality["excluded"], 1)

    def test_impossible_humidity_excluded(self):
        data = history_fixture()
        data["hourly"]["relative_humidity_2m"][0] = 101
        self.assertEqual(parse_history("kazan", data)[1]["excluded"], 1)

    def test_all_bad_rejected(self):
        data = history_fixture()
        data["hourly"]["wind_speed_10m"] = [-1, -2]
        with self.assertRaises(ValueError):
            parse_history("kazan", data)

    def test_wrong_wind_units(self):
        data = history_fixture()
        data["hourly_units"]["wind_speed_10m"] = "km/h"
        with self.assertRaises(ValueError):
            parse_history("kazan", data)

    def test_timezone(self):
        data = history_fixture()
        data["timezone"] = "UTC"
        with self.assertRaises(ValueError):
            parse_history("kazan", data)

    def test_duplicate_hours(self):
        data = history_fixture()
        data["hourly"]["time"][1] = data["hourly"]["time"][0]
        with self.assertRaises(ValueError):
            parse_history("kazan", data)

    def test_array_lengths(self):
        data = history_fixture()
        data["hourly"]["wind_speed_10m"] = [1]
        with self.assertRaises(ValueError):
            parse_history("kazan", data)

    def test_zscore(self):
        self.assertEqual(anomaly(13, 5, 2)["z"], 4)
        self.assertTrue(anomaly(13, 5, 2)["flag"])

    def test_two_sigma_boundary(self):
        self.assertFalse(anomaly(9, 5, 2)["flag"])

    def test_zero_std(self):
        self.assertIsNone(anomaly(9, 5, 0)["z"])

    def test_negative_std(self):
        with self.assertRaises(ValueError):
            anomaly(9, 5, -1)


class APITests(unittest.TestCase):
    def fixture(self):
        return {"cod": 200, "dt": 1760000000, "main": {"temp": 5, "humidity": 80},
                "wind": {"speed": 4}, "weather": [{"description": "тест"}]}

    def test_current_fields(self):
        row = parse_current("kazan", self.fixture())
        self.assertEqual(row["temperature"], 5)
        self.assertEqual(row["wind"], 4)
        self.assertIn("+00:00", row["observed_at_utc"])

    def test_missing_current_fields(self):
        with self.assertRaises(ValueError):
            parse_current("kazan", {})

    def test_invalid_numeric(self):
        for value in [float("nan"), float("inf"), "5", True, -100]:
            data = self.fixture()
            data["main"]["temp"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_current("kazan", data)

    def test_401_no_key_leak(self):
        response = Mock(status_code=401)
        session = Mock()
        session.get.return_value = response
        with self.assertRaisesRegex(RuntimeError, "HTTP 401") as caught:
            request_json("https://example.invalid", {"appid": "TEST_SECRET"}, session)
        self.assertNotIn("TEST_SECRET", str(caught.exception))
        self.assertEqual(session.get.call_count, 1)

    def test_429_retried(self):
        session = Mock()
        session.get.side_effect = [Mock(status_code=429), Mock(status_code=200, json=lambda: {})]
        with patch("api_client.time.sleep"):
            self.assertEqual(request_json("https://example.invalid", {}, session), {})
        self.assertEqual(session.get.call_count, 2)

    def test_non_json(self):
        session = Mock()
        session.get.return_value = Mock(status_code=200, json=Mock(side_effect=ValueError()))
        with self.assertRaisesRegex(RuntimeError, "JSON"):
            request_json("https://example.invalid", {}, session)

    def test_nasa_timezone_shift_and_fill(self):
        data = {"header": {"time_standard": "UTC", "fill_value": -999},
                "parameters": {"T2M": {"units": "C"}, "RH2M": {"units": "%"},
                               "WS10M": {"units": "m/s"}},
                "properties": {"parameter": {
                    "T2M": {"2020123121": 1, "2020123122": -999},
                    "RH2M": {"2020123121": 50, "2020123122": 60},
                    "WS10M": {"2020123121": 2, "2020123122": 3}}}}
        normalized = normalize_nasa([data])
        self.assertEqual(normalized["hourly"]["time"][0], "2021-01-01T00:00")
        self.assertIsNone(normalized["hourly"]["temperature_2m"][1])


class FuzzyTests(unittest.TestCase):
    def setUp(self):
        self.model = WeatherFuzzy("kazan", "autumn", 7, 7)

    def test_membership_ranges_and_no_gaps(self):
        for name, variable in self.model.variables.items():
            arrays = np.array([t.mf for t in variable.terms.values()])
            self.assertTrue(np.isfinite(arrays).all())
            self.assertTrue(((arrays >= 0) & (arrays <= 1)).all())
            self.assertTrue((arrays.max(axis=0) > 0).all(), name)

    def test_comfortable_case(self):
        self.assertGreater(self.model.evaluate(7, 55, 1)["comfort"], 70)

    def test_storm_lower(self):
        self.assertLess(self.model.evaluate(7, 55, 25)["comfort"],
                        self.model.evaluate(7, 55, 1)["comfort"])

    def test_grid_complete(self):
        for t in [-60, -25, 0, 7, 30, 60]:
            for h in [0, 55, 100]:
                for w in [0, 7, 60]:
                    result = self.model.evaluate(t, h, w)
                    self.assertTrue(0 <= result["comfort"] <= 100)

    def test_input_not_clipped(self):
        with self.assertRaises(ValueError):
            self.model.evaluate(61, 55, 0)

    def test_memberships_trace(self):
        result = self.model.evaluate(7, 55, 1)
        self.assertAlmostEqual(result["memberships"]["temperature"]["typical"], 1)
        self.assertEqual(len(result["rules"]), 8)
        self.assertEqual(result["rules"][4]["activation"], 1)

    def test_adapts_to_season(self):
        winter = WeatherFuzzy("kazan", "winter", -10, 6)
        summer = WeatherFuzzy("kazan", "summer", 20, 5)
        self.assertGreater(winter.evaluate(-10, 55, 0)["comfort"],
                           summer.evaluate(-10, 55, 0)["comfort"])

    def test_city_rule(self):
        spb = WeatherFuzzy("spb", "autumn", 7, 7)
        result = spb.evaluate(7, 95, 7)
        self.assertGreater(result["rules"][7]["activation"], 0)

    def test_constant_history_scale(self):
        self.assertEqual(WeatherFuzzy("kazan", "winter", -5, 0).scale, 1)

    def test_independent_centroid(self):
        result = self.model.evaluate(0, 80, 7)
        var = self.model.variables["comfort"]
        aggregate = np.zeros_like(var.universe)
        for rule in result["rules"]:
            aggregate = np.maximum(aggregate, np.minimum(rule["activation"], var[rule["output"]].mf))
        direct = fuzz.defuzz(var.universe, aggregate, "centroid")
        self.assertAlmostEqual(direct, result["comfort"], delta=.03)

    def test_guard_recommendation(self):
        row = {"temperature": -30, "humidity": 95, "wind": 20}
        result = self.model.evaluate(-30, 95, 20)
        notes = recommendations("kazan", row, result, {})
        self.assertTrue(any("мороз" in n for n in notes))
        self.assertTrue(any("ветра" in n for n in notes))


if __name__ == "__main__":
    unittest.main()
