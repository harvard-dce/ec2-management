import sys
import pprint
import urllib
import urllib2
import logging
from unipath import Path

import settings

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

def init_logging(cluster, verbose, level=logging.INFO):

    log_dir = Path(__file__).parent.child('logs')
    if not log_dir.exists():
        raise RuntimeError("Missing log path: {}".format(log_dir))

    log_file = "ec2-manager_{}.log".format(cluster)
    log_path = log_dir.child(log_file)

    log = logging.getLogger()
    log.setLevel(level)

    format=logging.Formatter(
        '%(asctime)-15s - %(name)s:%(lineno)s - %(levelname)s - %(message)s')

    fh = logging.handlers.TimedRotatingFileHandler(log_path, when='D', interval=1)
    fh.setLevel(level)
    fh.setFormatter(format)
    log.addHandler(fh)

    if verbose:
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(format)
        sh.setLevel(level)
        log.addHandler(sh)
        log.debug("logging to stdout")

    log.debug("logging to %s", log_path)
    return log



def ensureList(thing):
    if not isinstance(thing, list):
        return [thing]
    else:
        return thing


def pretty_print(stuff):
    pp = pprint.PrettyPrinter(indent=0)
    pp.pprint(stuff)
