import json
from unittest.mock import MagicMock, patch

import pytest

from capacity_impact.snowflake_manager import SnowflakeManager


def test_from_settings_local_uses_user_profile(monkeypatch):
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.setenv("SNOWFLAKE_USER", "godfrey.leung")

    manager = SnowflakeManager.from_settings(
        {
            "is_run_locally": True,
            "account": "acct.privatelink",
            "warehouse": "WH_TEST",
            "database": "STAGING_QUALITY",
            "query_tags": {
                "project_tag": {
                    "name": "capacity_intervention_impact",
                    "stage": "analysis",
                }
            },
        }
    )

    assert manager.is_run_locally is True
    assert manager.user == "godfrey.leung"
    assert manager.warehouse == "WH_TEST"
    assert manager.session_parameters == {
        "QUERY_TAG": "name=capacity_intervention_impact; stage=analysis"
    }


def test_local_connect_uses_externalbrowser(monkeypatch):
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    connection = object()

    with patch(
        "capacity_impact.snowflake_manager._snowflake_connect",
        return_value=connection,
    ) as connect:
        manager = SnowflakeManager(
            account="acct.privatelink",
            is_run_locally=True,
            user="local.user",
            warehouse="WH_TEST",
            database="STAGING_QUALITY",
        )
        assert manager.connect() is connection

    connect.assert_called_once_with(
        account="acct.privatelink",
        user="local.user",
        ocsp_fail_open=True,
        warehouse="WH_TEST",
        database="STAGING_QUALITY",
        authenticator="externalbrowser",
    )


def test_non_local_requires_secret_name():
    with pytest.raises(ValueError, match="secret_name"):
        SnowflakeManager(
            account="acct.privatelink",
            is_run_locally=False,
            user="svc",
        )


def test_environment_variable_forces_non_local(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "prod")
    with pytest.raises(ValueError, match="secret_name"):
        SnowflakeManager.from_settings(
            {
                "is_run_locally": True,
                "account": "acct.privatelink",
                "user": "local.user",
            }
        )


def test_get_secret_maps_non_human_credentials():
    client = MagicMock()
    client.get_secret_value.return_value = {
        "SecretString": json.dumps(
            {
                "USER": "NH_USER",
                "PRIVATE_KEY": "-----BEGIN PRIVATE KEY-----",
                "PASSPHRASE": "phrase",
                "WAREHOUSE": "WH_NH",
            }
        )
    }
    with patch(
        "capacity_impact.snowflake_manager._secrets_manager_client",
        return_value=client,
    ):
        manager = SnowflakeManager(
            account="acct.privatelink",
            is_run_locally=False,
            secret_name="prod-snowflake-nh-ml-platform",
        )

    assert manager.user == "NH_USER"
    assert manager.warehouse == "WH_NH"
    assert manager.privatekey == "-----BEGIN PRIVATE KEY-----"
    assert manager.passphrase == "phrase"


def test_non_local_connect_uses_private_key():
    private_key = object()
    connection = object()
    manager = SnowflakeManager(
        account="acct.privatelink",
        is_run_locally=True,
        user="placeholder",
    )
    manager.is_run_locally = False
    manager.user = "NH_USER"
    manager.warehouse = "WH_NH"
    manager.privatekey = "key"
    manager.passphrase = "phrase"

    with (
        patch.object(manager, "_load_private_key", return_value=private_key),
        patch(
            "capacity_impact.snowflake_manager._snowflake_connect",
            return_value=connection,
        ) as connect,
    ):
        assert manager.connect() is connection

    connect.assert_called_once_with(
        account="acct.privatelink",
        user="NH_USER",
        ocsp_fail_open=True,
        warehouse="WH_NH",
        private_key=private_key,
    )
