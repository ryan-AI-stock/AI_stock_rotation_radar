"""Complete TWCA's server chain without disabling certificate verification."""
from functools import lru_cache
from pathlib import Path
import tempfile
import certifi


@lru_cache(maxsize=1)
def ca_bundle():
    # Public intermediates terminate at the TWCA Global Root already in certifi.
    # No leaf certificate or new root trust anchor is added.
    bundle = Path(tempfile.mkdtemp(prefix='radar-tls-')) / 'ca.pem'
    bundle.write_bytes(Path(certifi.where()).read_bytes() + b'\n' +
                      Path(__file__).with_name('twca_intermediates.pem').read_bytes())
    return str(bundle)
