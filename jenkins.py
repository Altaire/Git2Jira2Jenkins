import logging, urllib, base64, config

TRACE = True

def _e(s):
    return urllib.quote(s)


def _urlopen(url, data=None):
    import urllib2
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
        raise
    return result


#[(url, data), ...]
def _urlopen_multi(urls_and_datas):
    import pycurl, cStringIO

    reqs = []
    m = pycurl.CurlMulti()
    for (url_, data) in urls_and_datas:
        url = config.JENKINS_SERVER + url_
        response = cStringIO.StringIO()
        handle = pycurl.Curl()
        handle.setopt(pycurl.URL, url)
        handle.setopt(pycurl.WRITEFUNCTION, response.write)
        handle.setopt(pycurl.CONNECTTIMEOUT, 10)
        base64string = base64.encodestring('%s:%s' % (config.JENKINS_LOGIN, config.JENKINS_PASSWORD)).replace('\n', '')
        headers = ['Authorization: ' + "Basic %s" % base64string]
        if data:
            handle.setopt(pycurl.POST, 1)
            handle.setopt(pycurl.POSTFIELDS, str(data))
            headers.append("Content-Type: text/xml")

        handle.setopt(pycurl.HTTPHEADER, headers)
        req = (url, response, handle)
        # Note that the handle must be added to the multi object
        # by reference to the req tuple.
        m.add_handle(req[2])
        reqs.append(req)
        if TRACE:
            print '[JENKINS] CURLMULTI: ' + url

    SELECT_TIMEOUT = 1.0
    num_handles = len(reqs)
    while num_handles:
        ret = m.select(SELECT_TIMEOUT)
        if ret == -1:
            continue
        while 1:
            ret, num_handles = m.perform()
            if ret != pycurl.E_CALL_MULTI_PERFORM:
                break
    for req in reqs:
        print req[1].getvalue()


def get_all(depth=0):
    return eval(_urlopen('api/python?depth={0}'.format(depth)))


def get_jobs():
    return get_all(depth=0)['jobs']


def create_job(job_name, job_config):
    _urlopen("createItem?name={0}".format(_e(job_name)), job_config)


def create_jobs(jobs_and_configs):
    urls_and_datas = map(lambda (job, config): ("createItem?name={0}".format(_e(job)), config), jobs_and_configs)
    _urlopen_multi(urls_and_datas)


def delete_job(job_name):
    return _urlopen("job/{0}/doDelete".format(_e(job_name)), "json=%7B%7D&Submit=Yes")


def get_config():
    return _urlopen(config.JENKINS_JOB_CONFIG_TEMPLATE_PATH)


def trigger_build_job(job_name):
    return _urlopen('job/{0}/build?token={1}'.format(_e(job_name), config.JENKINS_JOB_REBUILD_TOKEN))


def trigger_build_jobs(job_names):
    urls_and_datas = map(lambda job_name: ('job/{0}/build?token={1}'.format(_e(job_name), config.JENKINS_JOB_REBUILD_TOKEN), None), job_names)
    _urlopen_multi(urls_and_datas)

