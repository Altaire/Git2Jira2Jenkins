import logging, urllib2, urllib, base64, simplejson, config

def _e(s):
    return urllib.quote(s)

def _urlopen(url, data=None):
    url = config.JENKINS_SERVER + url
    request = urllib2.Request(url, data)
    base64string = base64.encodestring('%s:%s' % (config.JENKINS_LOGIN, config.JENKINS_PASSWORD)).replace('\n', '')
    request.add_header("Authorization", "Basic %s" % base64string)
    if data:
        request.add_header("Content-Type", "text/xml")
    try:
        response = urllib2.urlopen(request, timeout=10)
    except urllib2.HTTPError as e:
        logging.warning('[JENKINS] 404: ' + request.get_full_url())
        raise
    return response.read()


def get_all():
    return simplejson.loads(_urlopen('api/json'))


def get_jobs():
    return simplejson.loads(_urlopen('api/json'))['jobs']


def create_job(job_name, job_config):
    return _urlopen("createItem?name={0}".format(_e(job_name)), data=job_config)


def build_job(job_name):
    _urlopen("job/{0}/build?delay=0sec".format(_e(job_name)))


def delete_job(job_name):
    return _urlopen("createItem?name={0}".format(_e(name)))


def get_config():
    return _urlopen(config.JENKINS_JOB_CONFIG_TEMPLATE_PATH)


def get_job_result(job_name):
    return _urlopen('job/{0}/lastBuild/consoleText'.format(_e(job_name)))


def trigger_build(job_name):
    return _urlopen('job/{0}/build?token={1}'.format(_e(job_name), config.JENKINS_JOB_REBUILD_TOKEN))