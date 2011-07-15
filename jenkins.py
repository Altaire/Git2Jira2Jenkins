import multiprocessing, logging, urllib, config

TRACE = True

def _e(s):
    return urllib.quote(s)


def _urlopen((url, data)):
    import urllib2, base64, config

    url = config.JENKINS_SERVER + url
    request = urllib2.Request(url, data)
    base64string = base64.encodestring('%s:%s' % (config.JENKINS_LOGIN, config.JENKINS_PASSWORD)).replace('\n', '')
    request.add_header("Authorization", "Basic %s" % base64string)
    if data:
        request.add_header("Content-Type", "text/xml")
    if TRACE:
        print '[JENKINS]: ' + request.get_full_url()
    try:
        response = urllib2.urlopen(request, timeout=10)
        result = response.read()
    except:
        logging.warning('[JENKINS]: ' + request.get_full_url())
        result = None
    return result


def get_all(depth=0):
    return eval(_urlopen(('api/python?depth={0}'.format(depth), None)))


def get_jobs():
    return get_all(depth=0)['jobs']


def create_job(job_name, job_config):
    _urlopen(("createItem?name={0}".format(_e(job_name)), job_config))


def create_jobs(jobs_and_configs):
    pool = multiprocessing.Pool(processes=5)
    params = map(lambda (job, config): ("createItem?name={0}".format(_e(job)), config), jobs_and_configs)
    pool.map(_urlopen, params)
    pool.close()
    pool.join()

    
def delete_job(job_name):
    return _urlopen("createItem?name={0}".format(_e(job_name)))


def get_config():
    return _urlopen((config.JENKINS_JOB_CONFIG_TEMPLATE_PATH, None))


def trigger_build_job(job_name):
    return _urlopen(('job/{0}/build?token={1}'.format(_e(job_name), config.JENKINS_JOB_REBUILD_TOKEN), None))


def trigger_build_jobs(job_names):
    pool = multiprocessing.Pool(processes=5)
    params = map(lambda job_name: ('job/{0}/build?token={1}'.format(_e(job_name), config.JENKINS_JOB_REBUILD_TOKEN), None), job_names)
    pool.map(_urlopen, params)
    pool.close()
    pool.join()
