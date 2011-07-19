# -*- coding: utf-8
import logging, re, time, config, git, jenkins, web_

try:
    from suds.client import Client
except:
    import sys

    print "Please do (for Ubuntu):\n\tsudo pip install SUDS \nEXIT"
    sys.exit()

TRACE = True
FORMAT = '%(asctime)-15s  %(levelname)s %(message)s  %(funcName)s %(lineno)s %(exc_info)s'
logging.basicConfig(filename=config.LOG_FILENAME, level=logging.INFO, format=FORMAT)

global dbcon
jira_resolution_map = {}
jira_status_map = {}
jira_priority_map = {}


def _git_merge(branch, local_branches):
    if branch in local_branches:
        git.remove_branch(branch)
    git.checkout(branch)
    git_master_branch_head = git.get_head('remotes/origin/master')
    git_branch_head = git.get_head(branch)
    git_merge_status = git.merge()
    git_merged_branch_head = git.get_head(branch)
    #sql_info, bsh_info, config_info = git.get_diff()
    git_sql_info, git_bsh_info, git_config_info = None, None, None
    dbcon.execute(
        '''update branch set git_master_branch_head=?, git_branch_head=?, git_merged_branch_head=?, git_merge_status=?, git_sql_info=?, git_bsh_info=?, git_config_info=?, git_last_update_time=? where branch=?;'''
        ,
        (git_master_branch_head, git_branch_head, git_merged_branch_head, git_merge_status, git_sql_info, git_bsh_info, git_config_info, int(time.time()), branch))


def git_update_remote_heads():
    git.fetch()
    remote_branch_heads = git.get_all_remote_branch_heads(branch_regexp=config.branch_name_regexp)
    dbcon.executemany("insert or ignore into branch(branch, git_remote_branch_head) values (?, ?);",
                      remote_branch_heads)
    dbcon.executemany("update branch set git_remote_branch_head=? where branch=?;",
                      map(lambda (branch, head): (head, branch), remote_branch_heads))


def git_delete_removed():
    remote_branches, local_branches = git.get_remote_and_local_branches()
    branches = set([i[0] for i in dbcon.execute('''select branch from branch;''').fetchall()])
    diff = branches.difference(set(remote_branches))
    dbcon.executemany('''delete from branch where branch=?;''', map(lambda x: (x,), diff))


def git_merge_updated(limit=10):
    remote_branches, local_branches = git.get_remote_and_local_branches()
    git_master_branch_head = git.get_head('remotes/origin/master')
    q = dbcon.execute(
        '''select branch from branch where not (git_remote_branch_head is git_branch_head) or
         not (git_master_branch_head is '%s') limit %s;''' % (git_master_branch_head, limit)).fetchall()
    for (branch,) in q:
        _git_merge(branch, local_branches)


def _jira_update_task(soap, auth, jira_task_id):
    task = soap.service.getIssue(auth, jira_task_id)
    dbcon.execute('''update branch set
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
        task['summary'],
        task['assignee'],
        int(time.time()),
        jira_task_id
        ))

def jira_update(all=False, limit=30):
    if all:
        q = dbcon.execute('''select DISTINCT branch from branch;''')
    else:
        q = dbcon.execute('''select DISTINCT branch from branch where jira_task_id is null limit %s;''' % (limit))
    branches = [i[0] for i in q.fetchall()]
    tasks_and_branches = [(re.match(config.jira_task_regexp, branch).group(), branch) for branch in branches]
    dbcon.executemany("update branch set jira_task_id=? where branch=?;", tasks_and_branches)

    ##TODO: update jira to 4.x. Jira 3.x does not support soap.getIssuesFromJqlSearch(), sorry. Cannot update by jira task 'updated' jql field
    tasks = set([task for (task, branch) in tasks_and_branches])
    if tasks:
        soap = Client(config.JIRA_SOAP_SERVER)
        auth = soap.service.login(config.JIRA_USER, config.JIRA_PASSWORD)
        for jira_task_id in tasks:
            _jira_update_task(soap, auth, jira_task_id)
        soap.service.logout()


def jira_get_statuses_resolutions_priorities():
    soap = Client(config.JIRA_SOAP_SERVER)
    auth = soap.service.login(config.JIRA_USER, config.JIRA_PASSWORD)
    for i in soap.service.getStatuses(auth):
        if i['id'] != None and i['name'] != None:
            jira_status_map[i['id']] = i['name']
            jira_status_map[i['name'] + '_icon'] = i['icon']
    for i in soap.service.getResolutions(auth):
        if i['id'] != None and i['name'] != None:
            jira_resolution_map[i['id']] = i['name']
            jira_resolution_map[i['name'] + '_icon'] = i['icon']
    for i in soap.service.getPriorities(auth):
        if i['id'] != None and i['name'] != None:
            jira_priority_map[i['id']] = i['name']
            jira_priority_map[i['name'] + '_icon'] = i['icon']
    soap.service.logout()


def jenkins_add_jobs(limit=10):
    current_jobs = set([i['name'] for i in jenkins.get_jobs()])
    branches_to_build = set([i[0] for i in dbcon.execute(
        '''select branch from branch where jira_task_status='Need testing' and git_merge_status='MERGED'
        and not git_branch_head is jenkins_branch_head;''').fetchall()])
    new_jobs = list(branches_to_build.difference(current_jobs))[:limit]
    if TRACE:
      print '[JENKINS] add jobs:' + repr(new_jobs)
    if new_jobs:
        config_template = jenkins.get_config()
        jobs_and_configs = map(
            lambda job: (job, config_template.replace('remotes/origin/master', job).replace(config.GIT_REMOTE_PATH,
                                                                                        'file://' + config.GIT_WORK_DIR + '/.git/'))
            , new_jobs)
        jenkins.create_jobs(jobs_and_configs)
        jenkins.trigger_build_jobs(new_jobs)


def jenkins_delete_jobs():
    jobs = set([i['name'] for i in jenkins.get_jobs() if re.match(config.branch_name_regexp, i['name'])])
    branches = set([i[0] for i in dbcon.execute(
        '''select branch from branch where jira_task_status='Need testing';''').fetchall()])
    for branch in jobs.difference(branches):
        if TRACE:
            print '[JENKINS] delete job:' + repr(branch)
        jenkins.delete_job(branch)


def jenkins_get_jobs_result():
    import time

    def _get(result):
        l = []
        for job in result['jobs']:
            try:
                name = job['name']
            except:
                name = None
            try:
                status = job['lastBuild']['result']
            except:
                status = None
            try:
                jenkins_head = job['lastBuild']['actions'][1]['lastBuiltRevision']['SHA1']
            except:
                jenkins_head = None
            l.append({'name': name, 'status': status, 'jenkins_head': jenkins_head})
        return l

    result = jenkins.get_all(depth=2)
    matched_jobs = [(i['status'], i['jenkins_head'], int(time.time()), i['name'])
        for i in _get(result) if re.match(config.branch_name_regexp, i['name'])]
    if TRACE:
            print '[JENKINS] get job  results for: ' + str(len(matched_jobs)) + ' jobs'
    dbcon.executemany(
        '''update branch set jenkins_status=?, jenkins_branch_head=?, jenkins_last_update_time=?
        where branch=?;''', (matched_jobs))


def jenkins_rebuild_obsolete(limit=5):
    current_jobs = set([i['name'] for i in jenkins.get_jobs() if
        (re.match(config.branch_name_regexp, i['name']) and i['color'] == 'blue')])
    obsolete_jobs = set([i[0] for i in dbcon.execute(
        '''select branch from branch where jira_task_status='Need testing' and 
            not (git_merged_branch_head is jenkins_branch_head)
            order by jira_task_priority;''').fetchall()])
    jobs_to_rebild = list(obsolete_jobs.intersection(current_jobs))[:limit]
    if TRACE:
        print "[JENKINS]: Rebuild obsolete jobs: " + repr(len(jobs_to_rebild))
    jenkins.trigger_build_jobs(jobs_to_rebild)


def jenkins_rebuild_failed_all():
    failed_jobs = [i['name'] for i in jenkins.get_jobs() if
        (re.match(config.branch_name_regexp, i['name']) and i['color'] != 'blue')]
    if TRACE:
        print "[JENKINS]: Rebuild failed jobs: " + repr(failed_jobs)
    jenkins.trigger_build_jobs(failed_jobs)


def jenkins_rebuild_failed_random():
    import random

    failed_jobs = [i['name'] for i in jenkins.get_jobs() if
        (re.match(config.branch_name_regexp, i['name']) and i['color'] != 'blue')]
    if len(failed_jobs) > 0:
        random_job = failed_jobs[random.randint(0, len(failed_jobs) - 1)]
        if TRACE:
            print "[JENKINS]: Rebuild random failed job: " + repr(random_job)
        jenkins.trigger_build_job(random_job)


def init_db():
    import sqlite3

    global dbcon
    dbcon = sqlite3.connect(":memory:", check_same_thread=False, isolation_level=None)
#    dbcon = sqlite3.connect("/dev/shm/123.sqlite3", check_same_thread=False, isolation_level=None)
    dbcon.row_factory = sqlite3.Row
    dbcon.execute('''create table branch (
                        branch text PRIMARY KEY DESC,

                        git_master_branch_head text,
                        git_remote_branch_head text,
                        git_branch_head text,
                        git_merged_branch_head text,
                        jenkins_branch_head text,
                        
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
                        jenkins_last_update_time text,

                        selenium_status text,
                        selenium_branch_head text,
                        selenium_last_update_time text
                        );''')


def init_scheduler():
    import inspect

    try:
        from apscheduler.scheduler import Scheduler
    except:
        import sys

        print "Please do:\n\tsudo easy_install apscheduler \nEXIT"
        sys.exit()
    sched = Scheduler()
    sched.configure({'daemonic': 'True'})

    @sched.interval_schedule(seconds=30)
    def sched_git_update_remote_heads():
        if TRACE: print inspect.stack()[0][3]
        git_update_remote_heads()


    @sched.interval_schedule(seconds=30)
    def sched_git_merge_updated():
        if TRACE: print inspect.stack()[0][3]
        git_merge_updated()

#    @sched.interval_schedule(seconds=300)
#    def sched_git_delete_removed():
#        if TRACE: print inspect.stack()[0][3]
#        git_delete_removed()

    @sched.interval_schedule(seconds=300)
    def sched_jira_update_all():
        if TRACE: print inspect.stack()[0][3]
        jira_update(all=True)

    @sched.interval_schedule(seconds=10)
    def sched_jira_update():
        if TRACE:
            print inspect.stack()[0][3]
#            import utils.memory
#            print utils.memory.stacksize()
#            print utils.memory.memory()
#            print utils.memory.resident()
#            import utils.reflect
#            utils.reflect.reflect()
        jira_update()

    @sched.interval_schedule(seconds=3600)
    def sched_jira_get_statuses_resolutions_priorities():
        if TRACE: print inspect.stack()[0][3]
        jira_get_statuses_resolutions_priorities()

    @sched.interval_schedule(seconds=60)
    def sched_jenkins_add_jobs():
        if TRACE: print inspect.stack()[0][3]
        jenkins_add_jobs()

    @sched.interval_schedule(seconds=60)
    def sched_jenkins_get_jobs_result():
        if TRACE: print inspect.stack()[0][3]
        jenkins_get_jobs_result()

    @sched.interval_schedule(seconds=180)
    def sched_jenkins_rebuild_failed_random():
        if TRACE: print inspect.stack()[0][3]
        jenkins_rebuild_failed_random()
        
    @sched.interval_schedule(seconds=60)
    def sched_jenkins_rebuild_obsolete():
        if TRACE: print inspect.stack()[0][3]
        jenkins_rebuild_obsolete()

    @sched.interval_schedule(seconds=120)
    def sched_jenkins_delete_jobs():
        if TRACE: print inspect.stack()[0][3]
        jenkins_delete_jobs()

    sched.start()


if __name__ == '__main__':
    init_db()
    print('Please wait: cloning %s ...' % (config.GIT_REMOTE_PATH))
    git.clone()
    git_update_remote_heads()
    print('Please wait: Initial branch merging ...')
    git_merge_updated(limit=10)
    print('Please wait: Initial jira task information upload ...')
    jira_get_statuses_resolutions_priorities()
    jira_update(limit=10)
    init_scheduler()
    web_.init_web(dbcon, jira_priority_map)