# -*- coding: utf-8
import logging, re, time, threading,sys, config, git, jenkins, web_

try:
    from suds.client import Client
except:
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
    git_master_head_local_done = git.get_head('remotes/origin/master')
    git_remote_head_local_done = git.get_head(branch)
    git.get_status()
    git_merge_status = git.merge()
    git_branch_head_merged = git.get_head(branch)
    #sql_info, bsh_info, config_info = git.get_diff()
    git_sql_info, git_bsh_info, git_config_info = None, None, None
    dbcon.execute(
        '''update branch set git_master_head_local_done=?, git_remote_head_local_done=?, git_branch_head_merged=?, git_merge_status=?, git_sql_info=?, git_bsh_info=?, git_config_info=?, git_last_update_time=? where branch=?;'''
        ,
        (git_master_head_local_done, git_remote_head_local_done, git_branch_head_merged, git_merge_status, git_sql_info, git_bsh_info, git_config_info, int(time.time()), branch))


def git_update_remote_heads():
    git.fetch()

    remote_branch_heads = git.get_all_remote_branch_heads(branch_regexp=config.branch_name_regexp)
    dbcon.executemany("insert or ignore into branch(branch, git_remote_head_remote) values (?, ?);", remote_branch_heads)
    dbcon.executemany("update branch set git_remote_head_remote=? where branch=?;",
                      map(lambda (branch, head): (head, branch), remote_branch_heads))
    
    git_master_head_remote = git.get_head('remotes/origin/master')
    dbcon.execute('''update branch set git_master_head_remote=?;''',(git_master_head_remote,))

def git_delete_removed():
    remote_branches, local_branches = git.get_remote_and_local_branches()
    branches = set([i[0] for i in dbcon.execute('''select branch from branch;''').fetchall()])
    diff = branches.difference(set(remote_branches))
    if TRACE:
        print "DELETE BRANCHES: ", diff
    dbcon.executemany('''delete from branch where branch=?;''', map(lambda x: (x,), diff))


def git_merge_updated(limit=20):
    remote_branches, local_branches = git.get_remote_and_local_branches()
    q = dbcon.execute(
        '''select branch from branch where
        ((not git_master_head_remote is git_master_head_local_done)
        or (not git_remote_head_remote is git_remote_head_local_done))
        and jira_task_status='Need testing'
        limit %s;''' % (limit)).fetchall()
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

def jira_update_new():
    _jira_update(only_new=True)

def jira_update_obsolete():
    _jira_update(only_new=False)

def _jira_update(only_new=True, limit=60):
    if only_new:
        q = dbcon.execute('''select DISTINCT branch from branch where jira_task_id is null limit %s;''' % (limit))
    else:
        q = dbcon.execute('''select DISTINCT branch from branch where jira_last_update_time<? limit ?;''', (int(time.time()) + 300, limit) )
    branches = [i[0] for i in q.fetchall()]
    if TRACE:
        print 'LOAD JIRA TASKS:'
        print 'only_new: ' , only_new
        print branches
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


def jenkins_add_jobs(limit=5):
    current_jobs = set([i['name'] for i in jenkins.get_jobs()])
    branches_to_build = set([i[0] for i in dbcon.execute(
        '''select branch from branch where
        (git_master_head_remote is git_master_head_local_done)
        and (git_remote_head_remote is git_remote_head_local_done)
        and jira_task_status='Need testing' and git_merge_status='MERGED'
        and (jenkins_branch_head_merged is null);''').fetchall()])
    new_jobs = list(branches_to_build.difference(current_jobs))[:limit]
    if TRACE:
        print "Current jobs", current_jobs
        print "Ready to build jobs", branches_to_build
        print '[JENKINS] add jobs:' + repr(new_jobs)
    if new_jobs:
        config_template = jenkins.get_config()
        jobs_and_configs = map(
            lambda job: (job, config_template.replace('remotes/origin/master', job).replace(config.GIT_REMOTE_PATH,
                                                                                        'file://' + config.GIT_WORK_DIR + '/.git/'))
            , new_jobs)
        jenkins.create_jobs(jobs_and_configs)
        jenkins.trigger_build_jobs(new_jobs)


def jenkins_delete_jobs(limit=5):
    jobs = set([i['name'] for i in jenkins.get_jobs() if re.match(config.branch_name_regexp, i['name'])])
    branches = set([i[0] for i in dbcon.execute(
        '''select branch from branch where jira_task_status='Need testing' or jira_task_status is null;''').fetchall()])
    for branch in list(jobs.difference(branches))[:limit]:
        if TRACE:
            print '[JENKINS] delete job:' + repr(branch)
        jenkins.delete_job(branch)


def jenkins_get_jobs_result():
    def _get(result):
        l = []
        for job in result:
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

    result = jenkins.get_job_branch_sha1()
    matched_jobs = [(i['status'], i['jenkins_head'], int(time.time()), i['name'])
        for i in _get(result) if re.match(config.branch_name_regexp, i['name'])]
    if TRACE:
            print '[JENKINS] get job  results for: ' + str(len(matched_jobs)) + ' jobs'
    dbcon.executemany(
        '''update branch set jenkins_status=?, jenkins_branch_head_merged=?, jenkins_last_update_time=?
        where branch=?;''', (matched_jobs))


def jenkins_rebuild_obsolete(limit=5):
    current_jobs = set([i['name'] for i in jenkins.get_jobs() if
        (re.match(config.branch_name_regexp, i['name']) and i['color'] == 'blue')])
    obsolete_jobs = set([i[0] for i in dbcon.execute(
        '''select branch from branch where jira_task_status='Need testing'
            and git_merge_status='MERGED'
            and (git_master_head_remote is git_master_head_local_done)
            and (git_remote_head_remote is git_remote_head_local_done)
            and not (git_branch_head_merged is jenkins_branch_head_merged)
            order by jira_task_priority;''').fetchall()])
    jobs_to_rebild = list(obsolete_jobs.intersection(current_jobs))[:limit]
    if TRACE:
        print "Current_jobs", current_jobs
        print "Obsolete_jobs", obsolete_jobs
        print "[JENKINS]: Rebuild obsolete jobs: " + repr(jobs_to_rebild)
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
    dbcon = sqlite3.connect(":memory:", check_same_thread=False, isolation_level=None,  detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES)
#    dbcon = sqlite3.connect("/dev/shm/123.sqlite3", check_same_thread=False, isolation_level=None)
    dbcon.row_factory = sqlite3.Row
    dbcon.execute('''create table branch (
                        branch text PRIMARY KEY DESC,

                        git_master_head_remote text,
                        git_master_head_local_done text,
                        git_remote_head_remote text,
                        git_remote_head_local_done text,

                        git_branch_head_merged text,
                        jenkins_branch_head_merged text,
                        
                        git_merge_status text,
                        git_sql_info text,
                        git_bsh_info text,
                        git_config_info text,
                        git_last_update_time INTEGER,

                        jira_task_id text,
                        jira_task_priority text,
                        jira_task_type text,
                        jira_task_summary text,
                        jira_task_resolution text,
                        jira_task_status text,
                        jira_task_assignee text,
                        jira_task_updated text,
                        jira_last_update_time INTEGER,

                        jenkins_status text,
                        jenkins_last_update_time INTEGER,

                        selenium_status text,
                        selenium_branch_head text,
                        selenium_last_update_time text
                        );''')


tasks = {
    git_update_remote_heads: 60,
    git_merge_updated: 60,
    git_delete_removed: 60,
    jira_update_new: 60,
    jira_update_obsolete: 60,
    jira_get_statuses_resolutions_priorities: 3600,
    jenkins_add_jobs: 60,
    jenkins_get_jobs_result: 60,
    jenkins_rebuild_failed_random: 60,
    jenkins_rebuild_obsolete: 60,
    jenkins_delete_jobs: 60
}

def main_loop():
    import heapq, traceback
    h = []
    for task, timeout in tasks.iteritems():
        heapq.heappush(h, (time.time(), task))
    while True:
        exec_time, task = heapq.heappop(h)
        if exec_time < time.time():
            if TRACE:
                import utils.memory
                print "\nMemory stats:"
                print int(utils.memory.stacksize()/1024), "kB stacksize"
                print int(utils.memory.memory()/1024**2), "MB virt"
                print int(utils.memory.resident()/1024**2), "MB resident"
                print int(time.time()), " try to do task...: ", int(exec_time), task
            try:
                task()
                if TRACE:
                    print int(time.time()), "task done. "
            except Exception, err:
                if TRACE:
                    print traceback.print_exc(file=sys.stdout)
                logging.warning(traceback.format_exc())
            finally:
                heapq.heappush(h, (time.time() + tasks[task], task))
                if TRACE:
                    print int(time.time()), " add task again: ", int(time.time()) + tasks[task], task
        else:
            #if TRACE:
            #    print time.time(), " miss task: ", exec_time, task
            heapq.heappush(h, (exec_time, task))
        time.sleep(1)


if __name__ == '__main__':
    init_db()
    logging.info('Please wait: cloning %s to %s ...' % (config.GIT_REMOTE_PATH, config.GIT_WORK_DIR))
    git.clone()
    git_update_remote_heads()
    logging.info('Please wait: Initial branch merging ...')
    git_merge_updated(limit=5)
    logging.info('Please wait: Initial jira task information upload ...')
    jira_get_statuses_resolutions_priorities()
    jira_update_new()
    loop = threading.Thread(target=main_loop)
    loop.start()
    web_.init_web(dbcon, jira_priority_map)



#            import utils.memory
#            print utils.memory.stacksize()
#            print utils.memory.memory()
#            print utils.memory.resident()
#            import utils.reflect
#            utils.reflect.reflect()