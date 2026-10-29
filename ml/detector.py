# ml/detector.py
"""
Isolation Forest anomaly detector for CyberSentinel.

Architecture
------------
A single daemon thread runs the detection loop:

  1. Wake up every SCRAPE_INTERVAL seconds.
  2. Ask MetricsScraper for a fresh feature vector.
  3. Append the vector to a rolling history window.
  4. Train (or retrain) the Isolation Forest when thresholds are reached.
  5. Score the latest vector and update Prometheus gauges.
  6. Also run the rule-based baseline check independently.

ML vs. rule-based — key distinction
-------------------------------------
- RULE-BASED: Fixed thresholds on individual metrics (e.g., >0.5 failed
  logins/sec). Simple, interpretable, always active. Fast to trigger.
  Metric: cybersentinel_rule_based_anomaly_detected

- ML (Isolation Forest): Learns the *joint distribution* of all 7 features
  on real observed data, then flags samples that are far from that learned
  normal region. It can catch unusual *combinations* of metrics that no
  single threshold would catch.
  Metrics: cybersentinel_ml_anomaly_score
           cybersentinel_ml_anomaly_detected

Isolation Forest scoring
------------------------
  score_samples() returns a value in roughly (-0.5, 0.5):
    - Values near +0.5  → very normal
    - Values near -0.5  → very anomalous
  We negate it so that a higher gauge value always means "more suspicious",
  which is more natural in a Grafana dashboard.

  predict() returns +1 (normal) or -1 (anomaly).  The built-in threshold
  corresponds to the 'contamination' parameter (fraction of training data
  expected to be anomalous).

Limitations (important for the project evaluation)
---------------------------------------------------
- The model is trained on whatever traffic it sees during startup.
  If training data is itself anomalous, detection quality degrades.
- Isolation Forest is unsupervised — it has no labeled attack examples.
- The model cannot reliably distinguish *all* attack types; it only detects
  deviations from observed normal behaviour.
- This is a demo/academic implementation; not a production SIEM.
"""

import logging
import os
import threading
import time
from collections import deque
from typing import Optional

import numpy as np
from sklearn.ensemble import IsolationForest

from ml.features import MetricsScraper, FEATURE_NAMES
from app.metrics import (
    ML_ANOMALY_SCORE,
    ML_ANOMALY_DETECTED,
    RULE_BASED_ANOMALY_DETECTED,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration constants
# (can be overridden via environment variables for easy experimentation)
# ---------------------------------------------------------------------------

SCRAPE_INTERVAL   = int(os.environ.get("CS_SCRAPE_INTERVAL",  "10"))   # seconds
MIN_TRAIN_SAMPLES = int(os.environ.get("CS_MIN_TRAIN_SAMPLES", "20"))  # need ≥ N before first fit
MAX_HISTORY       = int(os.environ.get("CS_MAX_HISTORY",       "200")) # rolling window size
RETRAIN_EVERY     = int(os.environ.get("CS_RETRAIN_EVERY",     "25"))  # retrain after N new samples
CONTAMINATION     = float(os.environ.get("CS_CONTAMINATION",   "0.1")) # expected anomaly fraction
STARTUP_DELAY     = int(os.environ.get("CS_STARTUP_DELAY",     "12"))  # wait for Flask to be ready

# ---------------------------------------------------------------------------
# Rule-based thresholds  (baseline detector — distinct from ML)
# ---------------------------------------------------------------------------

RULE_THRESHOLDS: dict[str, float] = {
    "failed_login_rate":   0.5,    # > 0.5 failed logins per second
    "unauthorized_rate":   0.5,    # > 0.5 unauthorised requests per second
    "error_rate":          0.3,    # > 0.3 errors per second
    "error_ratio":         0.3,    # > 30% of requests are errors
    "avg_latency_ms":    500.0,    # > 500 ms average response time
}


# ---------------------------------------------------------------------------
# Detector class
# ---------------------------------------------------------------------------

class AnomalyDetector:
    """
    Isolation Forest anomaly detector running in a background daemon thread.

    Usage:
        detector = AnomalyDetector()
        detector.start()   # call once after Flask is created
    """

    def __init__(self) -> None:
        self._scraper   = MetricsScraper()
        self._history: deque[list[float]] = deque(maxlen=MAX_HISTORY)
        self._model: Optional[IsolationForest] = None
        self._samples_since_retrain: int = 0
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # Private — model management
    # ------------------------------------------------------------------

    def _fit(self) -> None:
        """
        Fit (or refit) the Isolation Forest on all samples in _history.

        Called when:
        - The history reaches MIN_TRAIN_SAMPLES for the first time.
        - RETRAIN_EVERY new samples have been collected since the last fit.
        """
        X = np.array(self._history, dtype=float)
        self._model = IsolationForest(
            n_estimators=100,
            contamination=CONTAMINATION,
            random_state=42,    # reproducible results
        )
        self._model.fit(X)
        self._samples_since_retrain = 0
        logger.info(
            "[ML] Isolation Forest (re)trained on %d samples, %d features.",
            len(X), X.shape[1],
        )

    # ------------------------------------------------------------------
    # Private — scoring
    # ------------------------------------------------------------------

    def _score_and_update(self, vector: list[float]) -> None:
        """
        Score one feature vector with the trained model and update gauges.

        Skips silently if the model is not trained yet.
        """
        if self._model is None:
            return

        X = np.array([vector], dtype=float)

        # Negated score: higher = more anomalous (intuitive for dashboards)
        raw_score     = float(self._model.score_samples(X)[0])
        anomaly_score = -raw_score

        # predict(): -1 = anomaly, +1 = normal
        prediction = int(self._model.predict(X)[0])
        is_anomaly = 1 if prediction == -1 else 0

        ML_ANOMALY_SCORE.set(anomaly_score)
        ML_ANOMALY_DETECTED.set(is_anomaly)

        if is_anomaly:
            feature_summary = ", ".join(
                f"{n}={v:.4f}" for n, v in zip(FEATURE_NAMES, vector)
            )
            logger.warning(
                "[ML] ANOMALY DETECTED | score=%.4f | %s",
                anomaly_score, feature_summary,
            )
        else:
            logger.debug("[ML] Normal | score=%.4f", anomaly_score)

    # ------------------------------------------------------------------
    # Private — rule-based baseline
    # ------------------------------------------------------------------

    def _rule_check(self, rates: dict[str, float]) -> None:
        """
        Threshold-based detection — completely separate from the ML model.

        Updates cybersentinel_rule_based_anomaly_detected (0 or 1).
        Always logs at WARNING when triggered so the two detectors can be
        compared in the console output.
        """
        triggered = []
        for metric, threshold in RULE_THRESHOLDS.items():
            value = rates.get(metric, 0.0)
            if value > threshold:
                triggered.append(f"{metric}={value:.4f} (threshold={threshold})")

        if triggered:
            RULE_BASED_ANOMALY_DETECTED.set(1)
            logger.warning("[RULE] Anomaly | %s", " | ".join(triggered))
        else:
            RULE_BASED_ANOMALY_DETECTED.set(0)
            logger.debug("[RULE] Normal")

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self) -> None:
        """
        Detection loop — runs forever in a daemon thread.

        Start-up delay gives Flask time to bind its port and serve /metrics
        before the first scrape attempt.
        """
        logger.info(
            "[ML] Detector starting. Waiting %d s for Flask to initialise...",
            STARTUP_DELAY,
        )
        time.sleep(STARTUP_DELAY)
        logger.info(
            "[ML] Detector active. Scraping every %d s. "
            "Training starts after %d samples.",
            SCRAPE_INTERVAL, MIN_TRAIN_SAMPLES,
        )

        while True:
            try:
                result = self._scraper.compute_features()

                if result is not None:
                    rates, vector = result

                    # Collect sample
                    self._history.append(vector)
                    self._samples_since_retrain += 1
                    n = len(self._history)

                    logger.info(
                        "[ML] Sample #%d collected | %s",
                        n,
                        " ".join(f"{k}={v:.3f}" for k, v in zip(FEATURE_NAMES, vector)),
                    )

                    # Decide whether to (re)train
                    need_first_train = (self._model is None and n >= MIN_TRAIN_SAMPLES)
                    need_retrain     = (self._model is not None and
                                        self._samples_since_retrain >= RETRAIN_EVERY)
                    if need_first_train or need_retrain:
                        self._fit()

                    # Score with ML model (if trained)
                    self._score_and_update(vector)

                    # Rule-based baseline (always runs, independent of ML)
                    self._rule_check(rates)

                else:
                    logger.debug(
                        "[ML] No feature vector yet "
                        "(waiting for 2nd scrape or Flask not ready)."
                    )

            except Exception:
                # Never crash the thread — log and continue
                logger.exception("[ML] Unexpected error in detection loop.")

            time.sleep(SCRAPE_INTERVAL)

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def start(self) -> None:
        """
        Launch the detection loop as a background daemon thread.

        Daemon threads are killed automatically when the main process exits,
        so we don't need any explicit cleanup logic.
        """
        self._thread = threading.Thread(
            target=self.run,
            name="cybersentinel-anomaly-detector",
            daemon=True,
        )
        self._thread.start()
        logger.info("[ML] Anomaly detector thread launched.")
