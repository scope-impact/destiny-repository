"""Tests for the ESConfig model."""

import pytest
from pydantic import ValidationError

from app.core.config import AzureBlobConfig, ESConfig, MinioConfig
from app.persistence.blob.models import BlobContainer


def test_es_config_api_key_auth():
    """Test ESConfig with API key authentication."""
    config = ESConfig(cloud_id="test-cloud-id", api_key="test-api-key")
    assert config.uses_api_key is True
    assert config.cloud_id == "test-cloud-id"
    assert config.api_key == "test-api-key"


def test_es_config_insecure_url():
    """Test ESConfig with insecure URL."""
    config = ESConfig(es_insecure_url="http://localhost:9200/")
    assert str(config.es_insecure_url) == "http://localhost:9200/"
    assert config.uses_api_key is False


def test_es_config_traditional_auth():
    """Test ESConfig with traditional authentication."""
    config = ESConfig(es_url="https://localhost:9200/", es_user="user", es_pass="pass")
    assert config.es_user == "user"
    assert config.es_pass == "pass"
    assert config.es_hosts == ["https://localhost:9200/"]


def test_es_config_invalid_auth():
    """Test ESConfig with invalid authentication setup."""
    with pytest.raises(ValidationError):
        ESConfig()


def test_es_config_multiple_auth_methods_invalid():
    """Test ESConfig with multiple conflicting authentication methods."""
    with pytest.raises(ValidationError):
        ESConfig(
            cloud_id="test-cloud-id",
            api_key="test-api-key",
            es_insecure_url="http://localhost:9200/",
            es_user="user",
            es_pass="pass",
        )


def test_blob_backend_config_requires_all_containers():
    """Backend configs must include a container for every BlobContainer value."""
    with pytest.raises(ValidationError, match="operations"):
        AzureBlobConfig(
            storage_account_name="acct",
            containers={BlobContainer.FULL_TEXTS: "full-texts"},
        )
    with pytest.raises(ValidationError, match="full_texts"):
        MinioConfig(
            host="h",
            access_key="a",
            secret_key="s",
            containers={BlobContainer.OPERATIONS: "ops"},
        )


def test_minio_config_defaults_to_tls_without_region():
    """TLS is on by default; region is optional and unset for Minio."""
    config = MinioConfig(
        host="s3.eu-north-1.amazonaws.com",
        access_key="a",
        secret_key="s",
        containers={
            BlobContainer.OPERATIONS: "ops",
            BlobContainer.FULL_TEXTS: "full-texts",
        },
    )
    assert config.secure is True
    assert config.region is None


def test_minio_config_accepts_plain_http_and_region():
    """A local Minio opts out of TLS explicitly; S3 can pin its region."""
    config = MinioConfig(
        host="fs:9000",
        access_key="a",
        secret_key="s",
        secure=False,
        region="eu-north-1",
        containers={
            BlobContainer.OPERATIONS: "ops",
            BlobContainer.FULL_TEXTS: "full-texts",
        },
    )
    assert config.secure is False
    assert config.region == "eu-north-1"
