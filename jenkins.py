import logging, urllib, base64, config

TRACE = True

def _e(s):
    return urllib.quote(s)

#def _urlopen(url, data=None):
#    import urllib2
#    url = config.JENKINS_SERVER + url
#    request = urllib2.Request(url, data)
#    base64string = base64.encodestring('%s:%s' % (config.JENKINS_LOGIN, config.JENKINS_PASSWORD)).replace('\n', '')
#    request.add_header("Authorization", "Basic %s" % base64string)
#    if data:
#        request.add_header("Content-Type", "text/xml")
#    if TRACE:
#        print '[JENKINS]: ' + request.get_full_url()
#    try:
#        response = urllib2.urlopen(request, timeout=10)
#        result = response.read()
#    except:
#        logging.warning('[JENKINS]: ' + request.get_full_url())
#        raise
#    return result


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
        handle.setopt(pycurl.CONNECTTIMEOUT, 2)
        handle.setopt(pycurl.TIMEOUT, 10)
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
    result = []
    for req in reqs:
        result.append(req[1].getvalue())
#    if TRACE:
#        print result
    if len(result) == 1:
        return result[0]
    else:
        return result


def get_job_branch_sha1():
    return eval(_urlopen_multi([('api/python?tree=jobs[name,lastBuild[result,actions[lastBuiltRevision[SHA1]]]]', None)]))['jobs']


def get_jobs():
    return eval(_urlopen_multi([('api/python?tree=jobs[name,color]', None)]))['jobs']



def create_job(job_name, job_config):
    _urlopen_multi([("createItem?name={0}".format(_e(job_name)), job_config)])


def create_jobs(jobs_and_configs):
    urls_and_datas = map(lambda (job, config): ("createItem?name={0}".format(_e(job)), config), jobs_and_configs)
    _urlopen_multi(urls_and_datas)


def delete_job(job_name):
    return _urlopen_multi([("job/{0}/doDelete".format(_e(job_name)), "json=%7B%7D&Submit=Yes")])


def get_config():
    return _urlopen_multi([(config.JENKINS_JOB_CONFIG_TEMPLATE_PATH, None)])


def trigger_build_job(job_name):
    return _urlopen_multi([('job/{0}/build?token={1}'.format(_e(job_name), config.JENKINS_JOB_REBUILD_TOKEN), None)])


def trigger_build_jobs(job_names):
    urls_and_datas = map(lambda job_name: ('job/{0}/build?token={1}'.format(_e(job_name), config.JENKINS_JOB_REBUILD_TOKEN), None), job_names)
    _urlopen_multi(urls_and_datas)

