"""Snowflake connection manager for local SSO and AWS-secret service users."""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Mapping

logger = logging.getLogger(__name__)

DEFAULT_SECRET_KEYS = {
    "username_key": "USER",
    "privatekey_key": "PRIVATE_KEY",
    "passphrase_key": "PASSPHRASE",
    "warehouse_key": "WAREHOUSE",
}


class SnowflakeManager:
    """
    Manage Snowflake connections for local SSO or AWS-secret service users.

    Local runs use browser SSO (``authenticator=externalbrowser``) with the
    interactive user profile. Non-local runs load a service-account private key
    from AWS Secrets Manager and connect with key-pair authentication.

    Attributes
    ----------
    account : str
        Snowflake account identifier.
    is_run_locally : bool
        Whether to use local SSO authentication.
    user : str
        Snowflake username.
    warehouse : str
        Default warehouse.
    database : str or None
        Optional default database.
    schema : str or None
        Optional default schema.
    role : str or None
        Optional default role.
    secret_name : str or None
        AWS Secrets Manager secret name for non-local auth.
    region : str
        AWS region for Secrets Manager.
    connection
        Active Snowflake connection, if opened.
    """

    def __init__(
        self,
        account: str,
        *,
        is_run_locally: bool = True,
        user: str | None = None,
        warehouse: str | None = None,
        database: str | None = None,
        schema: str | None = None,
        role: str | None = None,
        secret_name: str | None = None,
        region: str = "eu-west-1",
        username_key: str = DEFAULT_SECRET_KEYS["username_key"],
        privatekey_key: str = DEFAULT_SECRET_KEYS["privatekey_key"],
        passphrase_key: str = DEFAULT_SECRET_KEYS["passphrase_key"],
        warehouse_key: str = DEFAULT_SECRET_KEYS["warehouse_key"],
        session_parameters: Mapping[str, Any] | None = None,
    ) -> None:
        """
        Initialise connection settings and optionally load AWS secrets.

        Parameters
        ----------
        account : str
            Snowflake account identifier.
        is_run_locally : bool, default True
            Use local SSO when ``True``; AWS secret key-pair auth otherwise.
        user : str or None, optional
            Snowflake username. Defaults to ``SNOWFLAKE_USER`` locally.
        warehouse : str or None, optional
            Snowflake warehouse.
        database : str or None, optional
            Default database.
        schema : str or None, optional
            Default schema.
        role : str or None, optional
            Default role.
        secret_name : str or None, optional
            AWS secret containing non-human credentials.
        region : str, default "eu-west-1"
            AWS region for Secrets Manager.
        username_key : str, optional
            Secret JSON key for the username.
        privatekey_key : str, optional
            Secret JSON key for the private key.
        passphrase_key : str, optional
            Secret JSON key for the key passphrase.
        warehouse_key : str, optional
            Secret JSON key for the warehouse override.
        session_parameters : mapping or None, optional
            Snowflake session parameters such as ``QUERY_TAG``.

        Raises
        ------
        ValueError
            If required connection settings are missing.
        """
        self.account = account
        self.is_run_locally = bool(is_run_locally)
        self.user = user or os.environ.get("SNOWFLAKE_USER", "")
        self.warehouse = warehouse or os.environ.get("WAREHOUSE", "")
        self.database = database
        self.schema = schema
        self.role = role
        self.secret_name = secret_name
        self.region = region
        self.username_key = username_key
        self.privatekey_key = privatekey_key
        self.passphrase_key = passphrase_key
        self.warehouse_key = warehouse_key
        self.session_parameters = dict(session_parameters or {})
        self.connection = None
        self.privatekey: str | None = None
        self.passphrase: str | None = None

        if not self.account:
            raise ValueError("Snowflake account is required")

        if self.is_run_locally:
            if not self.user:
                raise ValueError(
                    "Local Snowflake connections require user or SNOWFLAKE_USER"
                )
            return

        if not self.secret_name:
            raise ValueError(
                "Non-local Snowflake connections require secret_name for the "
                "non-human user credentials"
            )
        self.get_secret(self.secret_name, self.region)

    @classmethod
    def from_settings(
        cls,
        settings: Mapping[str, Any],
        environ: Mapping[str, str] | None = None,
    ) -> SnowflakeManager:
        """
        Build a manager from the analysis YAML ``snowflake`` block.

        Parameters
        ----------
        settings : mapping
            Snowflake settings from analysis config.
        environ : mapping of str or None, optional
            Environment variables. Defaults to ``os.environ``.

        Returns
        -------
        SnowflakeManager
            Configured connection manager.
        """
        environment = os.environ if environ is None else environ
        session_parameters = _session_parameters(settings)
        return cls(
            account=str(
                settings.get("account")
                or settings.get("account_name")
                or environment.get("SNOWFLAKE_ACCOUNT", "")
            ),
            is_run_locally=_is_local(settings, environment),
            user=settings.get("user") or environment.get("SNOWFLAKE_USER"),
            warehouse=settings.get("warehouse") or environment.get("WAREHOUSE"),
            database=settings.get("database"),
            schema=settings.get("schema"),
            role=settings.get("role"),
            secret_name=settings.get("secret_name"),
            region=str(settings.get("region") or settings.get("aws_region") or "eu-west-1"),
            username_key=str(
                settings.get("username_key")
                or settings.get("secret_user_key")
                or DEFAULT_SECRET_KEYS["username_key"]
            ),
            privatekey_key=str(
                settings.get("privatekey_key")
                or settings.get("secret_privatekey_key")
                or DEFAULT_SECRET_KEYS["privatekey_key"]
            ),
            passphrase_key=str(
                settings.get("passphrase_key")
                or settings.get("secret_passphrase_key")
                or DEFAULT_SECRET_KEYS["passphrase_key"]
            ),
            warehouse_key=str(
                settings.get("warehouse_key")
                or settings.get("secret_warehouse_key")
                or DEFAULT_SECRET_KEYS["warehouse_key"]
            ),
            session_parameters=session_parameters,
        )

    def get_secret(self, secret_name: str, region_name: str) -> None:
        """
        Load non-human Snowflake credentials from AWS Secrets Manager.

        Parameters
        ----------
        secret_name : str
            AWS secret identifier.
        region_name : str
            AWS region for the Secrets Manager client.

        Raises
        ------
        Exception
            Propagates boto3 or JSON parsing failures after logging.
        """
        try:
            response = _secrets_manager_client(region_name).get_secret_value(
                SecretId=secret_name
            )
        except Exception:
            logger.exception("Failed to load Snowflake secret %s", secret_name)
            raise

        secret = json.loads(response["SecretString"])
        self.user = secret[self.username_key]
        self.privatekey = secret[self.privatekey_key]
        self.passphrase = secret[self.passphrase_key]
        self.warehouse = secret.get(self.warehouse_key, self.warehouse)

    def connect(self):
        """
        Open a Snowflake connection using the configured auth mode.

        Returns
        -------
        connection
            Active Snowflake connection object.
        """
        kwargs: dict[str, Any] = {
            "account": self.account,
            "user": self.user,
            "ocsp_fail_open": True,
        }
        for key, value in (
            ("warehouse", self.warehouse),
            ("database", self.database),
            ("schema", self.schema),
            ("role", self.role),
        ):
            if value:
                kwargs[key] = value
        if self.session_parameters:
            kwargs["session_parameters"] = self.session_parameters

        if self.is_run_locally:
            kwargs["authenticator"] = "externalbrowser"
            logger.info("Connecting to Snowflake with local user-profile SSO")
        else:
            kwargs["private_key"] = self._load_private_key()
            logger.info("Connecting to Snowflake with AWS-secret non-human user")

        self.connection = _snowflake_connect(**kwargs)
        return self.connection

    def cursor(self):
        """
        Return a cursor, opening the connection if needed.

        Returns
        -------
        cursor
            Snowflake cursor for the active connection.
        """
        if self.connection is None:
            self.connect()
        return self.connection.cursor()

    def close_connection(self) -> None:
        """Close the active Snowflake connection if one is open."""
        if self.connection is not None:
            self.connection.close()
            self.connection = None
            logger.info("Snowflake connection closed")

    def _load_private_key(self):
        """
        Deserialize the PEM private key loaded from AWS Secrets Manager.

        Returns
        -------
        cryptography private key object
            Key suitable for Snowflake key-pair authentication.

        Raises
        ------
        ValueError
            If the private key or passphrase has not been loaded.
        """
        if not self.privatekey or self.passphrase is None:
            raise ValueError("Private key and passphrase must be loaded from the AWS secret")

        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives import serialization

        return serialization.load_pem_private_key(
            self.privatekey.encode("utf-8"),
            password=self.passphrase.encode(),
            backend=default_backend(),
        )


def _snowflake_connect(**kwargs):
    """
    Create a Snowflake connector connection.

    Parameters
    ----------
    **kwargs
        Arguments forwarded to ``snowflake.connector.connect``.

    Returns
    -------
    connection
        Snowflake connection object.
    """
    import snowflake.connector

    return snowflake.connector.connect(**kwargs)


def _secrets_manager_client(region_name: str):
    """
    Build an AWS Secrets Manager client.

    Parameters
    ----------
    region_name : str
        AWS region name.

    Returns
    -------
    boto3.client
        Secrets Manager client.
    """
    import boto3

    return boto3.session.Session().client(
        service_name="secretsmanager",
        region_name=region_name,
    )


def _is_local(settings: Mapping[str, Any], environment: Mapping[str, str]) -> bool:
    """
    Determine whether to use local SSO based on config and environment.

    Parameters
    ----------
    settings : mapping
        Snowflake settings block.
    environment : mapping of str
        Process environment variables.

    Returns
    -------
    bool
        ``True`` when local SSO should be used.
    """
    if environment.get("ENVIRONMENT"):
        return False
    return bool(settings.get("is_run_locally", True))


def _session_parameters(settings: Mapping[str, Any]) -> dict[str, str]:
    """
    Build Snowflake session parameters such as ``QUERY_TAG`` from config.

    Parameters
    ----------
    settings : mapping
        Snowflake settings block.

    Returns
    -------
    dict of str
        Session parameters to pass to Snowflake connect.
    """
    raw = settings.get("session_parameters") or settings.get("query_tags") or {}
    if not isinstance(raw, Mapping):
        return {}
    project_tag = raw.get("project_tag", raw)
    if not isinstance(project_tag, Mapping):
        return {}
    if "QUERY_TAG" in project_tag:
        return {"QUERY_TAG": str(project_tag["QUERY_TAG"])}
    query_tag = "; ".join(
        f"{key}={value}" for key, value in project_tag.items() if value is not None
    )
    return {"QUERY_TAG": query_tag} if query_tag else {}
