
import dotenv
from unipath import Path
from os import getenv as env

dotenv.load_dotenv(Path(__file__).parent.child('.env'))

#Matterhorn credentials and http bits
MATTERHORN_HEADERS     = { 'X-REQUESTED-AUTH' : 'Digest', 'X-Opencast-Matterhorn-Authorization' : 'true' }
MATTERHORN_REALM       = 'Opencast Matterhorn'
MATTERHORN_ADMIN_SERVER_USER = env('MATTERHORN_ADMIN_SERVER_USER')
MATTERHORN_ADMIN_SERVER_PASS = env('MATTERHORN_ADMIN_SERVER_PASS')

#AWS bits
AWS_REGION = 'us-east-1'
AWS_ACCESS_KEY_ID = env('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = env('AWS_SECRET_ACCESS_KEY')

AWS_PROD_PREFIX="prdAWS"
AWS_STG_PREFIX="stgAWS"
AWS_DEV_PREFIX="devAWS"

AWS_NON_MH_SUFFIXES = ["-nfs", "-db", "-mysql"]
AWS_MH_SUFFIXES = ["-admin", "-worker", "-engage"]
AWS_PUBLIC_SUFFIXES = ["-pub", "-public"]
AWS_SUFFIXES = AWS_NON_MH_SUFFIXES + AWS_MH_SUFFIXES

#Zadara bits
ZADARA_ACCOUNT_TOKEN = env('ZADARA_ACCOUNT_TOKEN')
ZADARA_VPSA_PROD_ID = '4834'
ZADARA_VPSA_STG_ID = '4727'
ZADARA_VPSA_DEV_ID = '4667'
