"""
Central path resolution for the entire project.

Why this exists:
- Tests, agents, and orchestrator all need to reference files
  (features, prompts, configs, reports). 
- Hardcoding paths breaks when running from different working directories
  (IDE vs CLI vs CI).
- This module computes everything from PROJECT_ROOT, which is derived
  from THIS file's location — making it CWD-independent.

Usage:
    from config.paths import FEATURES_DIR, REPORTS_DIR
    feature_file = FEATURES_DIR / "login.feature"
"""
from pathlib import Path

# === Anchor: this file lives at <project_root>/config/paths.py ===
# So PROJECT_ROOT = parent of "config" folder = parent of this file's parent.
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent

# === Top-level directories ===
AGENTS_DIR: Path = PROJECT_ROOT / "agents"
CONFIG_DIR: Path = PROJECT_ROOT / "config"
FEATURES_DIR: Path = PROJECT_ROOT / "features"
ORCHESTRATOR_DIR: Path = PROJECT_ROOT / "orchestrator"
PAGES_DIR: Path = PROJECT_ROOT / "pages"
PROMPTS_DIR: Path = PROJECT_ROOT / "prompts"
REPORTS_DIR: Path = PROJECT_ROOT / "reports"
SCRIPTS_DIR: Path = PROJECT_ROOT / "scripts"
TESTS_DIR: Path = PROJECT_ROOT / "tests"

# === Specific files ===
CONFIG_YAML: Path = CONFIG_DIR / "config.yaml"
ENV_FILE: Path = PROJECT_ROOT / ".env"

# === Reporting subdirectories ===
ALLURE_RESULTS_DIR: Path = REPORTS_DIR / "allure-results"
ALLURE_REPORT_DIR: Path = REPORTS_DIR / "allure-report"


def feature_path(feature_name: str) -> Path:
    """Build a path to a .feature file. Pass with or without .feature extension."""
    if not feature_name.endswith(".feature"):
        feature_name += ".feature"
    return FEATURES_DIR / feature_name


def prompt_path(prompt_name: str) -> Path:
    """Build a path to a prompt template file."""
    if not prompt_name.endswith((".txt", ".md", ".yaml")):
        prompt_name += ".md"
    return PROMPTS_DIR / prompt_name