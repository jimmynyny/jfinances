from server.app.config import Settings


def test_production_refuses_placeholders(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("PLAID_ENV", "production")
    monkeypatch.setenv("PLAID_SECRET", "REPLACE_ME")
    monkeypatch.setenv("CF_ACCESS_AUD", "REPLACE_ME_AFTER_ACCESS_APP")
    monkeypatch.setenv("DEV_LOGIN_EMAIL", "x@y.z")
    problems = Settings().validate_for_boot("web")
    joined = "\n".join(problems)
    assert "PLAID_SECRET" in joined
    assert "CF_ACCESS_AUD" in joined
    assert "DEV_LOGIN_EMAIL" in joined


def test_production_env_mismatch(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("PLAID_ENV", "sandbox")
    assert any("does not match" in p for p in Settings().validate_for_boot("worker"))


def test_local_is_permissive(monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    assert Settings().validate_for_boot("web") == []


def test_derived_urls():
    s = Settings()
    assert s.plaid_webhook_url == "https://hooks.example.com/plaid/webhook"
    assert s.plaid_redirect_uri == "https://fin.example.com/link/oauth"
    assert s.cf_access_audiences == ["aud-one", "aud-two"]
    assert s.allowed_user_emails == ["jimmy@example.com", "wife@example.com"]
