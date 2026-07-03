"""INFINITO_CA_CERT_HOST: host path of the self-signed root CA cert.

Derived from the ca_trust_paths SPOT plus SOFTWARE_NAME (group_vars); consumed
by scripts/system/tls/trust/*.sh so the path never lives in shell literals.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from plugins.filter.ca_trust_paths import ca_cert_host
from utils import PROJECT_ROOT
from utils.cache.yaml import load_yaml

if TYPE_CHECKING:
    from utils.env.builder import BuildContext, EnvBuilder

KEY = "INFINITO_CA_CERT_HOST"
COMMENT = "Host path of the self-signed root CA cert (ca_trust_paths SPOT)."


def _software_domain() -> str:
    general = load_yaml(str(PROJECT_ROOT / "group_vars/all/00_general.yml"))
    return str(general["SOFTWARE_NAME"]).lower()


def apply(eb: EnvBuilder, ctx: BuildContext) -> None:
    eb.set(KEY, ca_cert_host(_software_domain()), comment=COMMENT)
