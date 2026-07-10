"""The compiled-in secret-path denylist (#540, #548, ADR-053 Q3a).

`select_blobs` gained a trust boundary that runs BEFORE the text/garbage
predicates and BEFORE any blob is fetched. It is:
  * compiled in (not from any in-repo file),
  * case-insensitive (a security floor over-matches on purpose), and
  * not overridable — an ignore file may narrow, never re-admit.

This also removes `.env`, `.env.example`, `.env.sample`, `.npmrc`, `.yarnrc`
from TEXT_EXTENSIONS: `.npmrc`/`.yarnrc` were a live leak #540 never named, and
the `*.example`/`*.sample` templates are preserved by NAME PATTERN, not by a
fake extension entry.
"""

import asyncio

import pytest

from llm_council.verification import file_ops
from llm_council.verification.constants import TEXT_EXTENSIONS


# (path, should_be_denied) — the ADR Q3a table, plus the accidental-protection
# cases that #542's content-sniffing would otherwise expose.
DENIED = [
    # env
    ".env",
    ".env.local",
    ".env.production",
    ".envrc",
    "config/.env",
    # keys / certs
    "server.pem",
    "private.key",
    "cert.p12",
    "bundle.pfx",
    "app.keystore",
    "release.jks",
    "vpn.ovpn",
    "signed.asc",
    # ssh / gpg
    "id_rsa",
    "id_rsa.pub",
    "id_ecdsa",
    "id_ed25519",
    ".ssh/config",
    ".gnupg/secring.gpg",
    # package registries
    ".npmrc",
    ".yarnrc",
    ".pypirc",
    ".gem/credentials",
    ".cargo/credentials.toml",
    # cloud
    ".aws/credentials",
    ".aws/config",
    "my-service-account.json",
    ".config/gcloud/foo.json",
    ".azure/accessTokens.json",
    "kubeconfig",
    "prod.kubeconfig",
    ".kube/config",
    # git / docker
    ".git-credentials",
    ".dockercfg",
    ".docker/config.json",
    # unix classics
    ".netrc",
    "_netrc",
    ".pgpass",
    ".htpasswd",
    ".s3cfg",
    ".boto",
    # iac / misc
    "terraform.tfvars",
    "prod.auto.tfvars",
    ".terraformrc",
    "secrets.yaml",
    "secrets.yml",
    ".databrickscfg",
]

# case-insensitivity: real files on case-preserving filesystems
DENIED_CASE = [".Env", "Secrets.YAML", "ID_RSA", "Server.PEM", ".NPMRC"]

# preserved: templates are conventionally secret-free
ALLOWED = [
    ".env.example",
    ".env.sample",
    ".env.template",
    "config.env.example",
    "src/app.py",
    "README.md",
    "docs/guide.md",
    "settings.yaml",  # a plain yaml is NOT secrets.yaml
]


@pytest.mark.parametrize("path", DENIED)
def test_denied_paths_are_secrets(path):
    assert file_ops._is_secret_path(path), f"{path} must be denied"


@pytest.mark.parametrize("path", DENIED_CASE)
def test_denylist_is_case_insensitive(path):
    assert file_ops._is_secret_path(path), f"{path} must be denied (case-insensitive)"


@pytest.mark.parametrize("path", ALLOWED)
def test_allowed_paths_are_not_secrets(path):
    assert not file_ops._is_secret_path(path), f"{path} must NOT be denied"


class TestSelectBlobsAppliesTheBoundary:
    def test_secret_is_omitted_with_denied_secret_reason(self):
        selected, omitted = asyncio.run(file_ops.select_blobs("0" * 40, [(".env", "explicit")]))
        assert selected == []
        assert len(omitted) == 1
        assert omitted[0].reason == "denied_secret"
        assert omitted[0].path == ".env"

    def test_boundary_runs_before_text_check(self):
        # `.env` is text; it must be denied as a SECRET, not admitted as text.
        selected, omitted = asyncio.run(file_ops.select_blobs("0" * 40, [(".env", "discovered")]))
        assert not selected
        assert omitted[0].reason == "denied_secret"

    def test_omission_records_path_only_never_a_value(self):
        # mirrors ADR-050 D3 scrub_exception — no content, just the path.
        _sel, omitted = asyncio.run(file_ops.select_blobs("0" * 40, [("private.key", "explicit")]))
        o = omitted[0]
        assert o.path == "private.key"
        assert o.reason == "denied_secret"
        # the Omission carries no field that could hold file bytes
        assert set(vars(o)) == {"path", "reason", "origin"}

    def test_template_and_source_pass(self):
        selected, omitted = asyncio.run(
            file_ops.select_blobs(
                "0" * 40, [(".env.example", "explicit"), ("src/app.py", "explicit")]
            )
        )
        assert {b.path for b in selected} == {".env.example", "src/app.py"}
        assert omitted == []


class TestTextExtensionsNoLongerCarrySecrets:
    @pytest.mark.parametrize("ext", [".env", ".env.example", ".env.sample", ".npmrc", ".yarnrc"])
    def test_secret_bearing_entries_removed(self, ext):
        assert ext not in TEXT_EXTENSIONS, (
            f"{ext} is still on TEXT_EXTENSIONS — a text file named this would be reviewed"
        )
