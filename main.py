import logging, re, inspect, time, config, git, jenkins, web_

try:
    import SOAPpy
except:
    print "Please do (for Ubuntu):\n\tsudo apt-get install python-soappy \nEXIT"
    sys.exit()

TRACE = False
FORMAT = '%(asctime)-15s %(message)s'
logging.basicConfig(filename=config.LOG_FILENAME, level=logging.INFO, format=FORMAT)

global dbcon
jira_resolution_map = {}
jira_status_map = {}
jira_priority_map = {}


def _git_merge(branch, local_branches):
    if branch in local_branches:
        git.remove_branch(branch)
    git.checkout(branch)
    git_branch_head = git.get_head(branch)
    git_merge_status = git.merge()
    #sql_info, bsh_info, config_info = git.get_diff()
    git_sql_info, git_bsh_info, git_config_info = None, None, None
    dbcon.cursor().execute(
        '''update branch set git_branch_head=?, git_merge_status=?, git_sql_info=?, git_bsh_info=?, git_config_info=?, git_last_update_time=? where branch=?;'''
        ,
        (git_branch_head, git_merge_status, git_sql_info, git_bsh_info, git_config_info, int(time.time()), branch))
    dbcon.commit()


def git_update_heads():
    git.fetch()
    remote_branch_heads = git.get_all_remote_branch_heads(branch_regexp=config.branch_name_regexp)
    ##TODO: use insert or update
    dbcon.executemany("insert or ignore into branch(branch, git_remote_branch_head) values (?, ?);",
                      remote_branch_heads)
    dbcon.executemany("update branch set git_remote_branch_head=? where branch=?;",
                      map(lambda (branch, head): (head, branch), remote_branch_heads))


def git_delete_removed():
    remote_branches, local_branches = git.get_remote_and_local_branches()
    branches = set([i['branch'] for i in dbcon.cursor().execute('''select branch from branch;''').fetchall()])
    dbcon.executemany('''delete branch where branch=?;''', branches.difference(set(remote_branches)))


def git_merge_updated():
    remote_branches, local_branches = git.get_remote_and_local_branches()
    q = dbcon.cursor().execute('''select branch from branch where not git_remote_branch_head is git_branch_head;''')
    for (branch,) in q.fetchall():
        _git_merge(branch, local_branches)


def _jira_update_task(soap, auth, jira_task_id):
    task = soap.getIssue(auth, jira_task_id)
    dbcon.cursor().execute('''update branch set
						jira_task_priority=?,
						jira_task_status=?,
						jira_task_resolution=?,
						jira_task_type=?,
						jira_task_summary=?,
						jira_task_assignee=?,
						jira_last_update_time=? where jira_task_id=?;''', (
    jira_priority_map[task['priority']],
    jira_status_map.get(task['status']),
    jira_resolution_map.get(task['resolution']),
    task['type'],
    re.escape(task['summary']),
    task['assignee'],
    int(time.time()),
    jira_task_id
    ))
    #logging.debug("****_jira_update_task exception: %s" % (str(sys.exc_info())))

def jira_update(all=False):
    soap = SOAPpy.WSDL.Proxy(config.JIRA_SOAP_SERVER)
    auth = soap.login(config.JIRA_USER, config.JIRA_PASSWORD)
    if all:
        q = dbcon.cursor().execute('''select DISTINCT branch from branch;''')
    else:
        q = dbcon.cursor().execute('''select DISTINCT branch from branch where jira_task_id is null;''')
    branches = [i[0] for i in q.fetchall()]
    tasks_and_branches = [(re.match(config.jira_task_regexp, branch).group(), branch) for branch in branches]
    dbcon.executemany("update branch set jira_task_id=? where branch=?;", tasks_and_branches)

    ##TODO: update jira to 4.x. Jira 3.x does not support soap.getIssuesFromJqlSearch(), sorry. Cannot update by jira task 'updated' jql field
    tasks = set([task for (task, branch) in tasks_and_branches])
    for jira_task_id in tasks:
        _jira_update_task(soap, auth, jira_task_id)
    soap.logout()


def jira_get_statuses_resolutions_priorities():
    soap = SOAPpy.WSDL.Proxy(config.JIRA_SOAP_SERVER)
    auth = soap.login(config.JIRA_USER, config.JIRA_PASSWORD)
    for i in soap.getStatuses(auth):
        jira_status_map[i['id']] = i['name']
    for i in soap.getResolutions(auth):
        jira_resolution_map[i['id']] = i['name']
    for i in soap.getPriorities(auth):
        jira_priority_map[i['id']] = i['name']
    soap.logout()


def jenkins_add_jobs(limit=2):
    current_jobs = set([i['name'] for i in jenkins.get_jobs()])
    branches_to_build = set([i[0] for i in dbcon.cursor().execute(
        '''select branch from branch where jira_task_status='Need testing' and git_merge_status='MERGED'
        and not git_branch_head is jenkins_branch_head;''').fetchall()])
    config_template = jenkins.get_config()
    
    new_jobs = list(branches_to_build.difference(current_jobs))[:limit]
    for branch in new_jobs:
        job_config = config_template.replace('remotes/origin/master', branch).replace(config.GIT_REMOTE_PATH,
                                                                                      'file://' + config.GIT_WORK_DIR + '/.git/')
        jenkins.create_job(branch, job_config)
        jenkins.build_job(branch)


def jenkins_delete_jobs():
    jobs = set([i['name'] for i in jenkins.get_jobs() if re.match(config.branch_name_regexp, i['name'])])
    branches = set([i[0] for i in dbcon.cursor().execute(
        '''select branch from branch;''').fetchall()])
    for branch in jobs.difference(branches):
        jenkins.delete_job(branch)


def jenkins_get_jobs_result():
    current_jobs = set([i['name'] for i in jenkins.get_jobs()])
    matched_jobs = filter(lambda job: re.match(config.branch_name_regexp, job), current_jobs)
    for branch in matched_jobs:
        result = jenkins.get_job_result(branch).splitlines()
        ##TODO fix this bad code
        if len(result)>8 and result[-1].find('Finished:') >=0:
            jenkins_status = result[-1].split(':')[1]
            jenkins_branch_head = result[7].split()[3]
            print branch, jenkins_status, jenkins_branch_head
            if jenkins_status and jenkins_branch_head:
                dbcon.cursor().execute(
                    '''update branch set jenkins_status=?, jenkins_branch_head=?, jenkins_last_update_time=? where branch=?;'''
                    , (jenkins_status, jenkins_branch_head, int(time.time()), branch))
                dbcon.commit()





def init_db():
    import sqlite3

    global dbcon
    dbcon = sqlite3.connect(":memory:", check_same_thread=False); #~ con.isolation_level = None
    dbcon.cursor().execute('''create table branch (
                        branch text PRIMARY KEY DESC,

                        git_branch_head text,
                        git_remote_branch_head text,
                        git_merge_status text,
                        git_sql_info text,
                        git_bsh_info text,
                        git_config_info text,
                        git_last_update_time text,

                        jira_task_id text,
                        jira_task_priority text,
                        jira_task_type text,
                        jira_task_summary text,
                        jira_task_resolution text,
                        jira_task_status text,
                        jira_task_assignee text,
                        jira_task_updated text,
                        jira_last_update_time text,

                        jenkins_status text,
                        jenkins_branch_head text,
                        jenkins_last_update_time text,

                        selenium_status text,
                        selenium_branch_head text,
                        selenium_last_update_time text
                        );''')
    dbcon.commit()


def init_scheduler():
    import sys

    try:
        from apscheduler.scheduler import Scheduler
    except:
        print "Please do:\n\tsudo easy_install apscheduler \nEXIT"
        sys.exit()
    sched = Scheduler()
    sched.configure({'daemonic':'True'})

    @sched.interval_schedule(seconds=30)
    def sched_git_update_heads():
        if TRACE: print inspect.stack()[0][3]
        git_update_heads()

    @sched.interval_schedule(seconds=30)
    def sched_git_merge_updated():
        if TRACE: print inspect.stack()[0][3]
        git_merge_updated()

    @sched.interval_schedule(seconds=300)
    def sched_git_delete_removed():
        if TRACE: print inspect.stack()[0][3]
        git_delete_removed()

    @sched.interval_schedule(seconds=300)
    def sched_jira_update_all():
        if TRACE: print inspect.stack()[0][3]
        jira_update(all=True)

    @sched.interval_schedule(seconds=30)
    def sched_jira_update():
        if TRACE: print inspect.stack()[0][3]
        jira_update()

    @sched.interval_schedule(seconds=3600)
    def sched_jira_get_statuses_resolutions_priorities():
        if TRACE: print inspect.stack()[0][3]
        jira_get_statuses_resolutions_priorities()

    @sched.interval_schedule(seconds=60)
    def sched_jenkins_add_jobs():
        if TRACE: print inspect.stack()[0][3]
        jenkins_add_jobs()

    @sched.interval_schedule(seconds=300)
    def sched_jenkins_get_jobs_result():
        if TRACE: print inspect.stack()[0][3]
        jenkins_add_jobs()

    sched.start()


if __name__ == '__main__':
    init_db()
    git.clone()
    git_update_heads()
    git_merge_updated()
    jira_get_statuses_resolutions_priorities()
    jira_update(all=True)
    init_scheduler()
    web_.init_web(dbcon)