"""Decorateur de retry avec backoff exponentiel pour les appels API.
Utilise 3 tentatives avec délai croissant (1s, 2s, 4s).
"""

import logging
import time
from functools import wraps

logger = logging.getLogger(__name__)


def retry(tries: int = 3, delay: float = 1.0, backoff: float = 2.0, exceptions: tuple = (Exception,)):
    """Decorateur : re-tente un appel API jusqu'à `tries` fois.

    Args:
        tries: Nombre maximum de tentatives.
        delay: Délai initial en secondes entre les tentatives.
        backoff: Multiplicateur du délai à chaque tentative.
        exceptions: Tuple d'exceptions à rattraper.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            current_delay = delay
            for attempt in range(1, tries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < tries:
                        logger.warning(
                            f"[Retry] {func.__name__} tentative {attempt}/{tries} "
                            f"echouee: {e}. Nouvel essai dans {current_delay:.1f}s"
                        )
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(
                            f"[Retry] {func.__name__} a echoue apres {tries} tentatives: {e}"
                        )
            raise last_exception
        return wrapper
    return decorator