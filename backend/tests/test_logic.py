"""Pure-logic tests: run with  python -m unittest discover -s tests -v   (no database, torch or FastAPI needed)."""
import sys
import types
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.modules.setdefault("asyncpg", types.ModuleType("asyncpg"))   # routing/reports import app.db, which imports asyncpg

from app.model.base import FORECAST_HORIZONS                      # noqa: E402
from app.model.mock_provider import MockProvider                  # noqa: E402
from app.services import config_store, nodes as nodes_mod, reports, risk, routing  # noqa: E402

TH = dict(risk.DEFAULT_THRESHOLDS)


class RiskTests(unittest.TestCase):
    def test_levels_at_boundaries(self):
        self.assertEqual(risk.level_for_depth(0.0, TH), "SAFE")
        self.assertEqual(risk.level_for_depth(0.029, TH), "SAFE")
        self.assertEqual(risk.level_for_depth(0.03, TH), "LOW")
        self.assertEqual(risk.level_for_depth(0.15, TH), "MODERATE")
        self.assertEqual(risk.level_for_depth(0.30, TH), "HIGH")
        self.assertEqual(risk.level_for_depth(0.60, TH), "CRITICAL")

    def test_states_and_frontend_status(self):
        self.assertEqual(risk.node_state(0.0, 0.1, 3.0, TH), "NORMAL")
        self.assertEqual(risk.node_state(0.0, 1.6, 3.0, TH), "INCREASED_LEVEL")
        self.assertEqual(risk.node_state(0.0, 2.9, 3.0, TH), "SURCHARGE")
        self.assertEqual(risk.node_state(0.05, 0.1, 3.0, TH), "SURCHARGE")
        self.assertEqual(risk.node_state(0.2, 0.1, 3.0, TH), "SURFACE_FLOODING")
        self.assertEqual(risk.node_state(0.9, 0.1, 3.0, TH), "SEVERE")
        self.assertEqual(risk.frontend_status("SEVERE"), "FLOODED")
        self.assertEqual(risk.frontend_status("SURCHARGE"), "SURCHARGE")
        self.assertEqual(risk.frontend_status("INCREASED_LEVEL"), "PASSABLE")

    def test_zero_max_depth_is_safe(self):
        self.assertEqual(risk.node_state(0.0, 5.0, 0.0, TH), "NORMAL")

    def test_threshold_validation(self):
        self.assertEqual(risk.validate_thresholds(TH), TH)
        bad = dict(TH, high_m=0.1)
        with self.assertRaises(ValueError):
            risk.validate_thresholds(bad)
        with self.assertRaises(ValueError):
            risk.validate_thresholds({k: v for k, v in TH.items() if k != "low_m"})
        with self.assertRaises(ValueError):
            risk.validate_thresholds(dict(TH, critical_m=50))


class DotenvTests(unittest.TestCase):
    def test_parse(self):
        import os, tempfile
        from app.config import load_dotenv
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / ".env"
            f.write_text("A_TEST_X=hello   # comment\nA_TEST_Y=\"q # not comment\"\nA_TEST_Z=    # empty\n# c\nbad line\n")
            for k in ("A_TEST_X", "A_TEST_Y", "A_TEST_Z"):
                os.environ.pop(k, None)
            os.environ["A_TEST_X"] = "from-real-env"
            load_dotenv(f)
            self.assertEqual(os.environ["A_TEST_X"], "from-real-env")      # real env wins
            self.assertEqual(os.environ["A_TEST_Y"], "q # not comment")
            self.assertEqual(os.environ["A_TEST_Z"], "")


class ConfigTests(unittest.TestCase):
    def test_validate(self):
        self.assertEqual(config_store.validate_value("alert_min_level", "HIGH"), "HIGH")
        with self.assertRaises(ValueError):
            config_store.validate_value("alert_min_level", "SAFE")      # would alert on every node
        with self.assertRaises(ValueError):
            config_store.validate_value("prediction_retention_days", 0)  # unbounded growth
        self.assertEqual(config_store.validate_value("log_retention_days", 0), 0)
        with self.assertRaises(ValueError):
            config_store.validate_value("nonsense", 1)


class ReportTests(unittest.TestCase):
    def test_phone(self):
        self.assertEqual(reports.validate_phone("98765 43210"), "98765 43210")
        self.assertEqual(reports.validate_phone("+91 98765-43210"), "+91 98765-43210")
        for bad in ("abc", "123", "9876543210; DROP TABLE", "1" * 25):
            with self.assertRaises(ValueError):
                reports.validate_phone(bad)

    def test_clean_text(self):
        self.assertEqual(reports.clean_text("  hi\x00there\x07  ", 50), "hithere")
        self.assertEqual(len(reports.clean_text("x" * 500, 10)), 10)

    def test_match_node_from_text(self):
        idx = {"N104": 0, "N231": 1}
        self.assertEqual(reports.match_node_from_text("T. Nagar, near Node n104", idx), "N104")
        self.assertIsNone(reports.match_node_from_text("opposite the bus stand", idx))
        self.assertIsNone(reports.match_node_from_text("N1040", idx))        # exact token only, no prefix matching


class RoutingTests(unittest.TestCase):
    A, B, C, D = [0, 0], [1, 0], [2, 0], [3, 0]

    def test_join_orients_segments(self):
        A, B, C, D = self.A, self.B, self.C, self.D
        self.assertEqual(routing.join_segments([[A, B], [B, C], [C, D]]), [A, B, C, D])
        self.assertEqual(routing.join_segments([[A, B], [C, B], [D, C]]), [A, B, C, D])
        self.assertEqual(routing.join_segments([[B, A], [B, C], [C, D]]), [A, B, C, D])

    def test_assemble_flags_flooded_segments(self):
        import json
        rows = [{"edge": 1, "cost": 100.0, "length_m": 100.0, "geom_json": json.dumps({"coordinates": [[80.2, 13.0], [80.21, 13.0]]})},
                {"edge": 2, "cost": 1_000_000.0, "length_m": 100.0, "geom_json": json.dumps({"coordinates": [[80.21, 13.0], [80.22, 13.0]]})},
                {"edge": -1, "cost": 0.0, "length_m": None, "geom_json": None}]
        r = routing.assemble(rows)
        self.assertEqual(r["lengthM"], 200.0)
        self.assertEqual(r["floodedLengthM"], 100.0)
        self.assertEqual(r["penalizedSegments"], 1)
        self.assertEqual(r["path"][0], [13.0, 80.2])                 # [lat, lng]

    def test_eta(self):
        self.assertEqual(routing.eta_minutes(1000, 20), 3.0)


class FakeEngine:
    """Just enough of Engine for the node view builder."""
    def __init__(self, n=6):
        self.node_ids = [f"N{i}" for i in range(n)]
        self.lat, self.lon = np.linspace(13.04, 13.05, n), np.linspace(80.23, 80.24, n)
        self.max_depth = np.full(n, 3.0, dtype=np.float32)
        self.meta = [{"location": None, "elevation_m": None, "imperviousness_pct": None} for _ in range(n)]
        self.blocks = {"N0": {"source": "report"}, "N1": {"source": "manual"}}
        self.cfg = types.SimpleNamespace(thresholds=TH)
        flood = np.array([0.0, 0.0, 0.05, 0.2, 0.4, 0.9], dtype=np.float32)
        fc = {h["steps"]: flood * (1 + i) for i, h in enumerate(FORECAST_HORIZONS)}
        self.snapshot = types.SimpleNamespace(flood_m=flood, depth_m=np.full(n, 0.1, dtype=np.float32), forecasts=fc,
                                              route_blocking_count=3, penalized_streets=10, forecast_ms=5)


class NodeViewTests(unittest.TestCase):
    def test_public_view_hides_official_fields(self):
        out = nodes_mod.build_nodes(FakeEngine(), 0.0, admin=False)
        self.assertEqual(len(out), 6)
        self.assertEqual(out[0]["suggestedAction"], "")
        self.assertNotIn("predicted", out[0])
        self.assertNotIn("blockSource", out[0])
        self.assertTrue(out[0]["blocked"])

    def test_blocked_node_shows_as_flooded_and_source(self):
        out = nodes_mod.build_nodes(FakeEngine(), 0.0, admin=True)
        self.assertEqual(out[0]["status"], "FLOODED")
        self.assertEqual(out[0]["blockSource"], "report")
        self.assertEqual(out[1]["blockSource"], "manual")
        self.assertEqual(out[2]["status"], "SURCHARGE")
        self.assertEqual(out[5]["risk"], "Critical")
        self.assertEqual(set(out[5]["predicted"]), {"0.5", "1.0", "2.0", "3.0"})

    def test_forecast_hours_select_the_right_array(self):
        e = FakeEngine()
        self.assertAlmostEqual(nodes_mod.build_nodes(e, 1.0)[5]["depth"], 0.9 * 2, places=3)
        with self.assertRaises(ValueError):
            nodes_mod.build_nodes(e, 4.0)

    def test_overview_counts(self):
        o = nodes_mod.overview(FakeEngine())
        self.assertEqual(o["levelCounts"]["CRITICAL"], 1)
        self.assertEqual(o["blockedByReport"], 1)
        self.assertEqual(len(o["forecast"]), 4)


class MockProviderTests(unittest.TestCase):
    def test_dry_stays_dry_and_rain_floods(self):
        m = MockProvider(100)
        for _ in range(10):
            self.assertEqual(float(m.step(0, None).flood_m.max()), 0.0)
        for _ in range(10):
            s = m.step(100, None)
        self.assertGreater(float(s.flood_m.max()), 0.3)

    def test_forecast_does_not_change_live_state(self):
        m = MockProvider(50)
        for _ in range(5):
            m.step(80, None)
        before = m._flood.copy()
        m.forecast(80, None, [6, 36])
        np.testing.assert_array_equal(before, m._flood)

    def test_reset(self):
        m = MockProvider(50)
        for _ in range(8):
            m.step(100, None)
        m.reset()
        self.assertEqual(float(m.step(0, None).flood_m.max()), 0.0)


if __name__ == "__main__":
    unittest.main()
