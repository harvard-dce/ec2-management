
from unipath import Path
from os import getenv as env

import warnings
warnings.filterwarnings('ignore', module='dotenv')

import dotenv
dotenv.load_dotenv(Path(__file__).parent.child('.env'))

VERSION = '2.3.3'

# Matterhorn credentials and http bits
MATTERHORN_HEADERS     = { 'X-REQUESTED-AUTH' : 'Digest', 'X-Opencast-Matterhorn-Authorization' : 'true' }
MATTERHORN_REALM       = 'Opencast Matterhorn'
MATTERHORN_ADMIN_SERVER_USER = env('MATTERHORN_ADMIN_SERVER_USER')
MATTERHORN_ADMIN_SERVER_PASS = env('MATTERHORN_ADMIN_SERVER_PASS')

NON_MH_SUFFIXES = ["-nfs", "-db", "-mysql"]
MH_SUFFIXES = ["-admin", "-worker", "-engage"]

MAJOR_LOAD_OPERATION_TYPES = ["compose", "editor", "inspect", "video-segment"]

# scaling settings
EC2M_MAX_WORKERS = int(env('EC2M_MAX_WORKERS', 10))
EC2M_MIN_WORKERS = int(env('EC2M_MIN_WORKERS', 2))
EC2M_MAX_QUEUED_JOBS = int(env('EC2M_MAX_QUEUED_JOBS', 0))
EC2M_MIN_IDLE_WORKERS = int(env('EC2M_MIN_IDLE_WORKERS', 0))
EC2M_IDLE_UPTIME_THRESHOLD = int(env('EC2M_IDLE_UPTIME_THRESHOLD', 55)) # this should be tweaked based on frequency of any autoscale cron jobs

EC2M_WAIT_RETRIES = int(env('EC2M_WAIT_RETRIES', 10))
EC2M_WAIT_TIME = int(env('EC2M_WAIT_TIME', 10))

#AWS bits
AWS_REGION = env('AWS_REGION', 'us-east-1')
AWS_ACCESS_KEY_ID = env('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = env('AWS_SECRET_ACCESS_KEY')
AWS_PROFILE = env('AWS_PROFILE')

ZADARA_TOKEN = env('ZADARA_TOKEN')
ZADARA_VPSA_ID = env('ZADARA_VPSA_ID')

LOGGLY_TOKEN = env('LOGGLY_TOKEN')
LOGGLY_URL = 'logs-01.loggly.com'
LOGGLY_TAGS = 'ec2-manager'

PYHORN_TIMEOUT = env('PYHORN_TIMEOUT', 30)
