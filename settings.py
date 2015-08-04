
import dotenv
from unipath import Path
from os import getenv as env

dotenv.load_dotenv(Path(__file__).parent.child('.env'))

VERSION = '0.1.0'
DEFAULT_RETRIES = 10
DEFAULT_WAIT = 10

#Matterhorn credentials and http bits
MATTERHORN_HEADERS     = { 'X-REQUESTED-AUTH' : 'Digest', 'X-Opencast-Matterhorn-Authorization' : 'true' }
MATTERHORN_REALM       = 'Opencast Matterhorn'
MATTERHORN_ADMIN_SERVER_USER = env('MATTERHORN_ADMIN_SERVER_USER')
MATTERHORN_ADMIN_SERVER_PASS = env('MATTERHORN_ADMIN_SERVER_PASS')

MAX_WORKERS = 10
MIN_WORKERS = 2
MAX_QUEUED_JOBS = 0
MIN_IDLE_WORKERS = 1
MAJOR_LOAD_SERVICE_TYPES = [
    'org.opencastproject.composer',
    'org.opencastproject.inspection',
    'org.opencastproject.videoeditor',
    'org.opencastproject.videosegmenter'
]

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

LOGGLY_TOKEN = env('LOGGLY_TOKEN')
LOGGLY_URL = 'logs-01.loggly.com'
LOGGLY_TAGS = 'ec2-manager'
