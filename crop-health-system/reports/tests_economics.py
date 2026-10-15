"""
Unit tests for reports.economics.estimate_decision.

Covers:
  1. Worthwhile case (TREAT)
  2. Severe / low-recovery case (ACCEPT_LOSS)
  3. Healthy — no card (returns None)
  4. Missing inputs (area=0 → None)
  5. Low-confidence preliminary flag
  6. Severity from risk_band mapping
  7. Mandi price fetch returns None when no API key
"""
from django.test import TestCase, RequestFactory, override_settings
from unittest.mock import patch

from reports.economics import (
    estimate_decision,
    severity_from_risk_band,
    fetch_mandi_price,
)


class EstimateDecisionTests(TestCase):
    """Tests for the pure function estimate_decision."""

    # 1. Worthwhile case — a treatable disease with positive net benefit
    def test_worthwhile_case(self):
        # price_per_unit in ₹/quintal (e.g. 1800 for tomato), not ₹/100g
        result = estimate_decision(
            crop="Tomato",
            disease="Early Blight",
            severity="medium",
            area_acres=2.0,
            yield_per_acre=80,
            price_per_unit=1800.0,
            confidence=0.85,
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["decision_code"], "TREAT")
        self.assertIn("worthwhile", result["decision_message"].lower())
        self.assertGreater(result["net_benefit_high"], 0)
        self.assertFalse(result["is_preliminary"])
        # Ranges present
        self.assertLess(result["expected_loss_low"], result["expected_loss_high"])
        self.assertLess(result["net_benefit_low"], result["net_benefit_high"])

    # 2. Severe damage / low recovery potential (wilt → ACCEPT_LOSS)
    def test_severe_low_recovery(self):
        result = estimate_decision(
            crop="Tomato",
            disease="Bacterial Wilt",
            severity="high",
            area_acres=1.0,
            yield_per_acre=80,
            price_per_unit=18.0,
            confidence=0.90,
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["decision_code"], "ACCEPT_LOSS")
        self.assertIn("extension officer", result["decision_message"].lower())

    # 3. Healthy → no card
    def test_healthy_no_card(self):
        result = estimate_decision(
            crop="Tomato",
            disease="Healthy",
            severity="low",
            area_acres=2.0,
            yield_per_acre=80,
            price_per_unit=18.0,
            confidence=0.95,
        )
        self.assertIsNone(result)

    def test_healthy_substring_no_card(self):
        """Disease name containing 'healthy' in any casing → no card."""
        result = estimate_decision(
            crop="Potato",
            disease="Potato___healthy",
            severity="low",
            area_acres=1.0,
            yield_per_acre=80,
            price_per_unit=12.0,
            confidence=0.92,
        )
        self.assertIsNone(result)

    # 4. Missing inputs — area=0 → None
    def test_missing_area_returns_none(self):
        result = estimate_decision(
            crop="Tomato",
            disease="Early Blight",
            severity="medium",
            area_acres=0,
            yield_per_acre=80,
            price_per_unit=18.0,
            confidence=0.80,
        )
        self.assertIsNone(result)

    def test_missing_disease_returns_none(self):
        result = estimate_decision(
            crop="Tomato",
            disease="",
            severity="medium",
            area_acres=1.0,
            yield_per_acre=80,
            price_per_unit=18.0,
            confidence=0.80,
        )
        self.assertIsNone(result)

    # 5. Low-confidence → is_preliminary=True
    def test_low_confidence_preliminary_flag(self):
        result = estimate_decision(
            crop="Tomato",
            disease="Early Blight",
            severity="medium",
            area_acres=1.0,
            yield_per_acre=80,
            price_per_unit=18.0,
            confidence=0.10,             # below 0.20 threshold
            low_confidence_threshold=0.20,
        )
        self.assertIsNotNone(result)
        self.assertTrue(result["is_preliminary"])

    def test_high_confidence_not_preliminary(self):
        result = estimate_decision(
            crop="Tomato",
            disease="Early Blight",
            severity="low",
            area_acres=1.0,
            yield_per_acre=80,
            price_per_unit=18.0,
            confidence=0.85,
        )
        self.assertIsNotNone(result)
        self.assertFalse(result["is_preliminary"])

    # 6. Severity from risk_band mapping
    def test_severity_from_risk_band(self):
        self.assertEqual(severity_from_risk_band("LOW"), "low")
        self.assertEqual(severity_from_risk_band("MEDIUM"), "medium")
        self.assertEqual(severity_from_risk_band("HIGH"), "high")
        self.assertEqual(severity_from_risk_band(""), "medium")
        self.assertEqual(severity_from_risk_band(None), "medium")

    # 7. Mandi price fetch returns None when no API key
    def test_mandi_price_no_api_key(self):
        with patch.dict("os.environ", {"DATA_GOV_API_KEY": ""}):
            price = fetch_mandi_price("Tomato")
            self.assertIsNone(price)

    # 8. Generic fallback for unknown crop / disease
    def test_unknown_crop_uses_generic(self):
        result = estimate_decision(
            crop="Dragonfruit",
            disease="Leaf Spot",
            severity="medium",
            area_acres=1.0,
            yield_per_acre=15,           # generic default
            price_per_unit=20.0,
            confidence=0.70,
        )
        self.assertIsNotNone(result)
        self.assertIn(result["decision_code"], ("TREAT", "ACCEPT_LOSS"))

    # 9. Expected value math check
    def test_expected_value_arithmetic(self):
        result = estimate_decision(
            crop="Tomato",
            disease="Early Blight",
            severity="low",
            area_acres=1.0,
            yield_per_acre=80,
            price_per_unit=18.0,
            confidence=0.90,
        )
        self.assertAlmostEqual(result["expected_value"], 80 * 18.0, places=0)

    # 10. Assumptions echoed back
    def test_assumptions_returned(self):
        result = estimate_decision(
            crop="Potato",
            disease="Late Blight",
            severity="high",
            area_acres=2.5,
            yield_per_acre=80,
            price_per_unit=12.0,
            confidence=0.75,
        )
        self.assertIsNotNone(result)
        assumptions = result["assumptions_used"]
        self.assertEqual(assumptions["crop"], "potato")
        self.assertEqual(assumptions["disease"], "late blight")
        self.assertEqual(assumptions["severity"], "high")
        self.assertAlmostEqual(assumptions["area_acres"], 2.5)


class ReportDetailViewTests(TestCase):
    """Render the report_detail page via the Django test client and check
    it returns 200 with the economic decision card present."""

    def setUp(self):
        from django.contrib.auth.models import User
        from farms.models import Farm, CropCycle
        from reports.models import DiseaseReport
        import datetime

        self.user = User.objects.create_user("testfarmer", password="pass1234")
        self.farm = Farm.objects.create(
            owner=self.user,
            name="Test Farm",
            latitude=19.0,
            longitude=73.0,
            area_acres=2.0,
            district="Pune",
        )
        self.cycle = CropCycle.objects.create(
            farm=self.farm,
            crop="Tomato",
            sowing_date=datetime.date(2026, 7, 1),
        )
        self.report = DiseaseReport.objects.create(
            farmer=self.user,
            farm=self.farm,
            crop_cycle=self.cycle,
            image="disease_reports/test.jpg",
            latitude=19.0,
            longitude=73.0,
            predicted_class="Tomato___Early_blight",
            crop_detected="Tomato",
            disease_detected="Early Blight",
            confidence=0.78,
            risk_band="MEDIUM",
            status="advisory_sent",
            econ_verdict="TREAT",
            econ_rationale="Test rationale",
            economic_estimate={
                "expected_value": 2880.0,
                "expected_loss_low": 460.8,
                "expected_loss_high": 691.2,
                "loss_avoided_low": 359.42,
                "loss_avoided_high": 539.14,
                "treatment_cost": 2800.0,
                "net_benefit_low": -2440.58,
                "net_benefit_high": -2260.86,
                "decision_code": "TREAT",
                "decision_message": "Treatment is economically worthwhile.",
                "is_preliminary": False,
                "assumptions_used": {},
            },
        )

    def test_report_detail_returns_200_with_card(self):
        self.client.login(username="testfarmer", password="pass1234")
        resp = self.client.get(f"/farmer/reports/{self.report.pk}/")
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn("econ-decision-card", content)
        self.assertIn("Treatment is economically worthwhile.", content)

    def test_report_detail_no_card_when_no_estimate(self):
        self.report.economic_estimate = None
        self.report.save()
        self.client.login(username="testfarmer", password="pass1234")
        resp = self.client.get(f"/farmer/reports/{self.report.pk}/")
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertNotIn("econ-decision-card", content)
