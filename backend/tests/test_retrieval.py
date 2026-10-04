from __future__ import annotations

from pathlib import Path

from app.config import Settings
from app import retrieval


def test_tidb_engine_enforces_certificate_and_hostname_verification(
    tmp_path: Path, monkeypatch
) -> None:
    ca_bundle = tmp_path / "ca.pem"
    ca_bundle.write_text("test certificate bundle")
    captured: dict[str, object] = {}

    def fake_create_engine(url: str, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(retrieval, "create_engine", fake_create_engine)
    settings = Settings(
        _env_file=None,
        retrieval_mode="tidb",
        tidb_database_url="mysql+pymysql://user:encoded-password@example.com:4000/littervoyage",
        tidb_ssl_ca=ca_bundle,
    )

    retrieval.TiDBEducationalRetriever(settings, embedder=object())

    assert str(captured["url"]).startswith("mysql+pymysql://")
    connect_args = captured["connect_args"]
    assert connect_args["ssl_ca"] == str(ca_bundle)
    assert connect_args["ssl_verify_cert"] is True
    assert connect_args["ssl_verify_identity"] is True
