from io import BytesIO
import boto3, os
from dotenv import load_dotenv
import requests


load_dotenv()
# DigitalOcean credentials
ACCESS_KEY = os.environ.get("DIGITAL_OCEAN_ACCESS_KEY")
SECRET_KEY = os.environ.get("DIGITAL_OCEAN_SECRET_KEY")

SPACE_NAME = os.environ.get("DIGITAL_OCEAN_SPACE_NAME")  
REGION_NAME = os.environ.get("DIGITAL_OCEAN_REGION_NAME") 
ENDPOINT_URL = os.environ.get("DIGITAL_OCEAN_ENDPOINT_URL")


# Create a session with boto3
session = boto3.session.Session()

# Initialize the S3 client with DigitalOcean Spaces details
client = session.client('s3',
                        region_name=REGION_NAME,
                        endpoint_url=ENDPOINT_URL,
                        aws_access_key_id=ACCESS_KEY,
                        aws_secret_access_key=SECRET_KEY)

def set_file_public(bucket_name, object_name):
    try:
        client.put_object_acl(ACL='public-read', Bucket=bucket_name, Key=object_name)
        print(f"File {object_name} is now public.")
    except Exception as e:
        print(f"Error setting file public: {e}")

def upload_file_to_spaces(filePath, object_name, bucket_name=SPACE_NAME):

    try:
        client.upload_file(filePath, bucket_name, object_name)
        print(f"File uploaded successfully: {object_name}")
        set_file_public(bucket_name, object_name)

        print(f"https://{bucket_name}.{REGION_NAME}.digitaloceanspaces.com/{object_name}")

        return object_name
    
    except Exception as e:
        print(f"Error uploading file: {e}")
        return None
    

def upload_image_from_url(image_url: str, object_name: str, bucket_name=SPACE_NAME):
    try:
        # Step 1: Download image from URL
        response = requests.get(image_url)
        response.raise_for_status()  # Raise error if download fails

        # Step 2: Upload to DigitalOcean Spaces
        client.upload_fileobj(
            Fileobj=BytesIO(response.content),
            Bucket=bucket_name,
            Key=object_name,
            ExtraArgs={'ACL': 'public-read', 'ContentType': response.headers.get('Content-Type', 'image/jpeg')}
        )

        print(f"Image uploaded successfully to: {object_name}")
        set_file_public(bucket_name, object_name)
        public_url = f"https://{bucket_name}.{REGION_NAME}.digitaloceanspaces.com/{object_name}"
        print(f"Public URL: {public_url}")
        return {
            "image_url" : public_url
        }

    except Exception as e:
        print(f"Error uploading image: {e}")
        return None