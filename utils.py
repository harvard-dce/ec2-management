from functools import wraps
import sys
import json
import urllib
import urllib2
import logging
from pyloggly import LogglyHandler
from unipath import Path
from controllers.exceptions import ClusterException

import settings

log = logging.getLogger('ec2-manager')

def http_request(server, endpoint, post_data=None, special_request=None, content_type=None):

# I'm going to leave these here since the urllib2 docs suck even more than the pycurl docs
# Uncomment the lines below to setup debugging on the connection itself.  It's not byte-for-byte, nor formatted well
# but it works, and is clear about what's being sent
#    hh = urllib2.HTTPHandler()
#    hsh = urllib2.HTTPSHandler()
#    hh.set_http_debuglevel(1)
#    hsh.set_http_debuglevel(1)
#    opener = urllib2.build_opener(hh, hsh)
#    urllib2.install_opener(opener)

    url = '%s%s' % (server, endpoint)

    headers = {}
    if content_type:
        headers['Content-Type'] = content_type

    if special_request is not None and "MATTERHORN" in special_request:
      cookie_handler = urllib2.HTTPCookieProcessor()
      opener = urllib2.build_opener(cookie_handler)
      urllib2.install_opener(opener)
      auth_handler = urllib2.HTTPDigestAuthHandler()
      auth_handler.add_password(realm=settings.MATTERHORN_REALM,
                        uri=url,
                        user=settings.MATTERHORN_ADMIN_SERVER_USER,
                        passwd=settings.MATTERHORN_ADMIN_SERVER_PASS)
      opener = urllib2.build_opener(auth_handler)
      urllib2.install_opener(opener)
      headers = dict(headers.items() + settings.MATTERHORN_HEADERS.items())
    elif special_request is not None and "ZADARA_POST" in special_request:
      #Ensure we're posting...
      #Some Zadara endpoints require an empty POST, which turns out to be difficult to do without this trick
      if post_data == None:
        post_data=""

    if post_data == None:
      req = urllib2.Request(url, headers=headers)
    else:
      req = urllib2.Request(url, data=urllib.urlencode(post_data), headers=headers)
    response = urllib2.urlopen(req, timeout=2)
    if response.getcode() / 100 != 2:
        raise Exception('ERROR: Request to %s failed (HTTP status code %i)' %
                        (endpoint, status))
    return response.read()

def init_logging(cluster, verbose, stdout_level=logging.INFO):

    log_dir = Path(__file__).parent.child('logs')
    if not log_dir.exists():
        raise RuntimeError("Missing log path: {}".format(log_dir))

    log_file = "ec2-manager_{}.log".format(cluster)
    log_path = log_dir.child(log_file)

    log.setLevel(logging.DEBUG)

    format = '%(asctime)-15s - ' + cluster + ' - ' \
             + '%(levelname)s - %(name)s - ' \
             + '%(module)s:%(funcName)s:%(lineno)s - %(message)s'
    format=logging.Formatter(format)

    fh = logging.handlers.TimedRotatingFileHandler(log_path, when='D', interval=1)
#    fh.setLevel(logging.DEBUG)
    fh.setFormatter(format)
    log.addHandler(fh)

    if verbose:
        sh = logging.StreamHandler(sys.stdout)
        if stdout_level == logging.DEBUG:
            sh.setFormatter(format)
        else:
            sh.setFormatter(logging.Formatter(
                '%(asctime)-15s - %(levelname)s - ' + cluster + ' - %(message)s'
            ))
        sh.setLevel(stdout_level)
        log.addHandler(sh)
        log.debug("logging to stdout")

    log.debug("logging to %s", log_path)

    if hasattr(settings, 'LOGGLY_TOKEN'):
        loggly_handler = LogglyHandler(
            settings.LOGGLY_TOKEN,
            settings.LOGGLY_URL,
            tags=cluster + ',' + settings.LOGGLY_TAGS
        )
        log.addHandler(loggly_handler)
        log.debug("Logging to loggly")

def log_status_summary(stats, msg_prefix=None):

    msg = 'status summary: '
    if msg_prefix is not None:
        msg = msg_prefix + ' ' + msg

    msg += "instances: {}, instances online: {}, workers: {}, workers online: {}".format(
        len(stats['instances']),
        stats['instances_online'],
        stats['workers'],
        stats['workers_online'])

    if 'queued_jobs' in stats:
        msg += ", queued_jobs: {}, queued_high_load_jobs: {}, running_jobs: {}".format(
            stats['queued_jobs'],
            stats['queued_high_load_jobs'],
            stats['running_jobs'])

    log.info(msg, extra=stats)

def format_status(stats, format):
    if format == 'json':
        return json.dumps(stats, indent=True)
    elif format == 'table':
        raise NotImplementedError('Ooops! Not implemented yet!')

def log_before_after_stats(cmd):
    @wraps(cmd)
    def wrapped(ec2, *args, **kwargs):
        log_status_summary(ec2.status_summary(), 'Before')
        result = cmd(ec2, *args, **kwargs)
        log_status_summary(ec2.status_summary(), 'After')
        return result
    return wrapped

def handle_exit(cmd):
    """
    execute the command and catch any cluster exceptions. The return value
    will be used as the arg for sys.exit().
    """
    @wraps(cmd)
    def wrapped(ec2, *args, **kwargs):
        try:
            cmd(ec2, *args, **kwargs)
            return 0
        except ClusterException, e:
            log.info(str(e))
            return str(e)
    return wrapped

def admin_is_up(cmd):
    """
    confirm that the Matterhorn admin instance is running
    """
    @wraps(cmd)
    def wrapped(ec2, *args, **kwargs):
        if not ec2.admin_is_up():
            raise ClusterException(
                "This command requires the Matterhorn admin instance to be running"
            )
        return cmd(ec2, *args, **kwargs)
    return wrapped
