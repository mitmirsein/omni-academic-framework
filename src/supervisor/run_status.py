"""Canonical run status vocabulary.

RunStore persists these values to `manifest.json` and `runs/index.db`.
Keep this list deliberately small: each status should imply a distinct
operational outcome, not just a different log message.
"""

RUNNING = "running"
COMPLETED = "completed"
FAILED = "failed"
NO_PAPERS_FOUND = "no_papers_found"
CANCELLED_BY_USER = "cancelled_by_user"
INVALID_CHOICE = "invalid_choice"
SCRAPER_DETECTION_FAILED = "scraper_detection_failed"
SCRAPING_FAILED = "scraping_failed"
ANALYSIS_FAILED = "analysis_failed"
UNKNOWN = "unknown"

RUN_STATUS_VALUES = (
    RUNNING,
    COMPLETED,
    FAILED,
    NO_PAPERS_FOUND,
    CANCELLED_BY_USER,
    INVALID_CHOICE,
    SCRAPER_DETECTION_FAILED,
    SCRAPING_FAILED,
    ANALYSIS_FAILED,
    UNKNOWN,
)

TERMINAL_RUN_STATUS_VALUES = (
    COMPLETED,
    FAILED,
    NO_PAPERS_FOUND,
    CANCELLED_BY_USER,
    INVALID_CHOICE,
    SCRAPER_DETECTION_FAILED,
    SCRAPING_FAILED,
    ANALYSIS_FAILED,
)
