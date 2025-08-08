# utils/logger.py
# A simple logging utility for beautiful and standardized console output


# ANSI color codes
class Colors:
    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKCYAN = "\033[96m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"


def _log(prefix, message, color):
    """
    Internal log function.
    Note: Colors may not display on all terminals (e.g., old Windows CMD),
    but work well in most modern terminals (VSCode, PowerShell, Linux/macOS).
    """
    print(f"{color}{prefix}{Colors.ENDC} {Colors.BOLD}{message}{Colors.ENDC}")


def step(message):
    """For marking major process steps."""
    _log("🚀", message, Colors.HEADER)


def info(message):
    """For general information, search prompts, etc."""
    _log("🔍", message, Colors.OKBLUE)


def success(message):
    """For marking successful operations."""
    _log("✅", message, Colors.OKGREEN)


def warn(message):
    """For printing warnings, where the program can still continue."""
    _log("⚠️", message, Colors.WARNING)


def error(message):
    """For printing errors that might lead to failure or interruption."""
    _log("❌", message, Colors.FAIL)


def system(message):
    """For system-level messages like startup, shutdown, caching."""
    _log("🔧", message, Colors.OKCYAN)


def cache(message):
    """Specifically for cache-related messages."""
    _log("🗂️", message, Colors.OKCYAN)


def result(message):
    """For printing final results or important data points."""
    # Using a simple print for lists or multi-line results often looks cleaner.
    print(message)
