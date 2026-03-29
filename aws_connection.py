import logging
import os
import boto3
from botocore.exceptions import NoCredentialsError, PartialCredentialsError, ClientError
from config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


class AWSConnection:
    """
    AWS S3 utility class.

    Credential priority (boto3 default chain — no hardcoding needed):
      1. Environment variables: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION
      2. ~/.aws/credentials file (after running `aws configure`)
      3. IAM role attached to EC2 / SageMaker / Lambda (best for production)
    """

    def __init__(self, region_name: str = None) -> None:
        self.region_name = region_name or settings.AWS_REGION
        self.s3_client = None
        self._connect()

    def _connect(self) -> None:
        """Initialise the S3 client and verify credentials with a real API call."""
        try:
            self.s3_client = boto3.client("s3", region_name=self.region_name)
            # Verify credentials immediately — list_buckets is the lightest real call
            self.s3_client.list_buckets()
            logger.info("Successfully connected to AWS S3 (region: %s).", self.region_name)
        except NoCredentialsError:
            logger.error(
                "No AWS credentials found. Set environment variables or run `aws configure`."
            )
            raise
        except PartialCredentialsError:
            logger.error("Incomplete AWS credentials. Check your environment variables.")
            raise
        except ClientError as e:
            logger.error("AWS client error during connection: %s", e)
            raise

    # ------------------------------------------------------------------ #
    #  Upload                                                              #
    # ------------------------------------------------------------------ #

    def upload_file(self, local_path: str, bucket: str, s3_key: str) -> bool:
        """
        Upload a local file to S3.

        Args:
            local_path: Path to the local file, e.g. "data/model.pkl"
            bucket:     S3 bucket name, e.g. "my-ml-bucket"
            s3_key:     Destination key in S3, e.g. "models/v1/model.pkl"

        Returns:
            True on success, False on failure.
        """
        if not os.path.exists(local_path):
            logger.error("Local file not found: %s", local_path)
            return False
        try:
            self.s3_client.upload_file(local_path, bucket, s3_key)
            logger.info("Uploaded '%s' → s3://%s/%s", local_path, bucket, s3_key)
            return True
        except ClientError as e:
            logger.error("Upload failed: %s", e)
            return False

    # ------------------------------------------------------------------ #
    #  Download                                                            #
    # ------------------------------------------------------------------ #

    def download_file(self, bucket: str, s3_key: str, local_path: str) -> bool:
        """
        Download a file from S3 to a local path.

        Args:
            bucket:     S3 bucket name
            s3_key:     Key of the file in S3
            local_path: Where to save the file locally

        Returns:
            True on success, False on failure.
        """
        try:
            os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)
            self.s3_client.download_file(bucket, s3_key, local_path)
            logger.info("Downloaded s3://%s/%s → '%s'", bucket, s3_key, local_path)
            return True
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "404":
                logger.error("File not found in S3: s3://%s/%s", bucket, s3_key)
            else:
                logger.error("Download failed: %s", e)
            return False

    # ------------------------------------------------------------------ #
    #  List                                                                #
    # ------------------------------------------------------------------ #

    def list_files(self, bucket: str, prefix: str = "") -> list[str]:
        """
        List all file keys in a bucket (or under a prefix).

        Args:
            bucket: S3 bucket name
            prefix: Optional folder prefix, e.g. "models/v1/"

        Returns:
            List of S3 keys, or empty list on failure.
        """
        try:
            paginator = self.s3_client.get_paginator("list_objects_v2")
            keys = []
            for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
                for obj in page.get("Contents", []):
                    keys.append(obj["Key"])
            logger.info("Found %d file(s) in s3://%s/%s", len(keys), bucket, prefix)
            return keys
        except ClientError as e:
            logger.error("List failed: %s", e)
            return []

    # ------------------------------------------------------------------ #
    #  Delete                                                              #
    # ------------------------------------------------------------------ #

    def delete_file(self, bucket: str, s3_key: str) -> bool:
        """Delete a single file from S3."""
        try:
            self.s3_client.delete_object(Bucket=bucket, Key=s3_key)
            logger.info("Deleted s3://%s/%s", bucket, s3_key)
            return True
        except ClientError as e:
            logger.error("Delete failed: %s", e)
            return False

    # ------------------------------------------------------------------ #
    #  Check existence                                                     #
    # ------------------------------------------------------------------ #

    def file_exists(self, bucket: str, s3_key: str) -> bool:
        """Return True if a key exists in S3, False otherwise."""
        try:
            self.s3_client.head_object(Bucket=bucket, Key=s3_key)
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            logger.error("head_object error: %s", e)
            return False


# ------------------------------------------------------------------ #
#  Quick demo — runs only when this file is executed directly         #
# ------------------------------------------------------------------ #

if __name__ == "__main__":
    BUCKET = settings.AWS_S3_BUCKET_NAME

    # 1. Connect (credentials come from env vars or ~/.aws/credentials)
    aws = AWSConnection()

    # 2. List existing files
    files = aws.list_files(BUCKET, prefix="")
    print("\nFiles in bucket:")
    for f in files:
        print(" ", f)

    # 3. Upload a test file
    with open("test_upload.txt", "w") as fp:
        fp.write("Hello from AWS connection test!")

    success = aws.upload_file("test_upload.txt", BUCKET, "test/test_upload.txt")
    print("\nUpload success:", success)

    # 4. Check it exists
    exists = aws.file_exists(BUCKET, "test/test_upload.txt")
    print("File exists in S3:", exists)

    # 5. Download it back
    aws.download_file(BUCKET, "test/test_upload.txt", "downloaded/test_upload.txt")

    # 6. Delete from S3
    aws.delete_file(BUCKET, "test/test_upload.txt")