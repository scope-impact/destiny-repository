"""
Unit tests for the Minio blob storage client's transport configuration.

The signed URLs this client produces are handed to robots and, for full text
enhancements, validated as https by the SDK
(:class:`destiny_sdk.enhancements.FullTextEnhancement`). A client pinned to
plain HTTP therefore makes every full text unreadable, so the scheme is worth
asserting directly.
"""

import datetime

import pytest

from app.core.config import MinioConfig
from app.persistence.blob.clients.minio import MinioBlobStorageClient
from app.persistence.blob.models import (
    BlobContainer,
    BlobSignedUrlType,
    BlobStorageFile,
    BlobStorageLocation,
)


def _config(**overrides) -> MinioConfig:
    return MinioConfig(
        host=overrides.pop("host", "fs:9000"),
        access_key="localuser",
        secret_key="localpass",
        # A region is always set here so signing never triggers a
        # GetBucketLocation lookup: these tests must not touch the network.
        region=overrides.pop("region", "us-east-1"),
        containers={
            BlobContainer.OPERATIONS: "ops",
            BlobContainer.FULL_TEXTS: "full-texts",
        },
        **overrides,
    )


def _file() -> BlobStorageFile:
    return BlobStorageFile(
        location=BlobStorageLocation.MINIO,
        container="full-texts",
        path="reference/1",
        filename="paper.pdf",
    )


@pytest.mark.asyncio
async def test_signed_urls_are_https_by_default():
    """The default configuration signs https URLs, as full texts require."""
    client = MinioBlobStorageClient(_config(), presigned_url_expiry_seconds=60)

    for interaction in BlobSignedUrlType:
        url = await client.generate_signed_url(_file(), interaction)
        assert url.startswith("https://"), f"{interaction} signed a non-https URL"


@pytest.mark.asyncio
async def test_signed_urls_are_http_when_tls_is_disabled():
    """An explicit opt-out still works, for a plain-HTTP local Minio."""
    client = MinioBlobStorageClient(
        _config(secure=False), presigned_url_expiry_seconds=60
    )

    url = await client.generate_signed_url(_file(), BlobSignedUrlType.DOWNLOAD)
    assert url.startswith("http://")


@pytest.mark.asyncio
async def test_region_is_passed_to_the_signing_client():
    """A configured region is used for signing rather than being discovered."""
    client = MinioBlobStorageClient(
        _config(host="s3.eu-north-1.amazonaws.com", region="eu-north-1"),
        presigned_url_expiry_seconds=60,
    )

    assert client.region == "eu-north-1"
    url = await client.generate_signed_url(_file(), BlobSignedUrlType.DOWNLOAD)
    assert "eu-north-1" in url


def test_expiry_is_honoured():
    """Guards the expiry plumbing the signed-url helpers depend on."""
    client = MinioBlobStorageClient(_config(), presigned_url_expiry_seconds=120)

    assert client.presigned_url_expiry_seconds == 120
    assert datetime.timedelta(seconds=client.presigned_url_expiry_seconds) == (
        datetime.timedelta(minutes=2)
    )
