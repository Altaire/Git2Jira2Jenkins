# -*- coding: utf-8

try:
    import web
except:
    import sys

    print "Please do (for Ubuntu):\n\tsudo apt-get install python-webpy \nEXIT"
    sys.exit()


def succ_merge_succ_build(dbcon):
    return dbcon.execute(
        '''select * from branch where (git_master_head_remote is git_master_head_local_done)
         and (git_remote_head_remote is git_remote_head_local_done)
         and (git_merge_status is 'MERGED')
         and (jira_task_status is 'Need testing')
         and (git_branch_head_merged is jenkins_branch_head_merged)
         and (jenkins_status is 'SUCCESS')
         order by jira_task_priority;''').fetchall()


def succ_merge_fail_build(dbcon):
    return dbcon.execute(
        '''select * from branch where (git_master_head_remote is git_master_head_local_done)
         and (git_remote_head_remote is git_remote_head_local_done)
         and (git_merge_status is 'MERGED')
         and (jira_task_status is 'Need testing')
         and (git_branch_head_merged is jenkins_branch_head_merged)
         and ((jenkins_status is 'FAILED') or (jenkins_status is 'UNSTABLE'))
         order by jira_task_priority;''').fetchall()


def succ_merge_no_build(dbcon):
    return dbcon.execute(
        '''select * from branch where (git_master_head_remote is git_master_head_local_done)
        and (git_remote_head_remote is git_remote_head_local_done)
        and (git_merge_status is 'MERGED')
        and (jira_task_status is 'Need testing')
        and not (git_master_head_remote is jenkins_branch_head_merged)
        order by jira_task_priority;''').fetchall()


def fail_merge(dbcon):
    return dbcon.execute(
        '''select * from branch where (git_master_head_remote is git_master_head_local_done)
        and (git_remote_head_remote is git_remote_head_local_done)
        and (jira_task_status is 'Need testing')
        and not (git_merge_status is 'MERGED')
        order by jira_task_priority;''').fetchall()


def no_merge(dbcon):
    return dbcon.execute('''select * from branch where (not (git_master_head_remote is git_master_head_local_done)
    or not (git_remote_head_remote is git_remote_head_local_done))
    and (jira_task_status is 'Need testing')
    order by jira_task_priority;''').fetchall()


def get_statistics(dbcon):
    return dbcon.execute('''select jira_task_status, count(*) from branch group by jira_task_status;''').fetchall()


def get_statistics_by_team(dbcon):
    import teams
    result = []
    for team in teams.teams.keys():
        result.extend(dbcon.execute('''select '%s', count(*) from branch where jira_task_assignee in %s;''' %(team, teams.teams[team])).fetchall())
    return result


def get_statistics_by_jira_task_priority(dbcon):
    return dbcon.execute('''select jira_task_priority, count(*) from branch group by jira_task_priority;''').fetchall()


def get_statistics_by_git_merge_status(dbcon):
    return dbcon.execute('''select git_merge_status, count(*) from branch where jira_task_status='Need testing' group by git_merge_status;''').fetchall()


def get_statistics_by_jenkins_status(dbcon):
    return dbcon.execute('''select jenkins_status, count(*) from branch where jira_task_status='Need testing' group by jenkins_status;''').fetchall()


urls = ("/",    "Index",
        '/txt', "Txt",
        '/(.*)', "All")


class Index:
    def GET(self):
        dbcon = web.ctx.globals.dbcon
        jira_priority_map = web.ctx.globals.jira_priority_map
        render = web.template.render('templates/')
        return render.index(
            get_statistics(dbcon),
            get_statistics_by_team(dbcon),
            get_statistics_by_jira_task_priority(dbcon),
            get_statistics_by_git_merge_status(dbcon),
            get_statistics_by_jenkins_status(dbcon),
            succ_merge_succ_build(dbcon),
            succ_merge_fail_build(dbcon),
            succ_merge_no_build(dbcon),
            fail_merge(dbcon),
            no_merge(dbcon),
            jira_priority_map)

class Txt:
    def GET(self):
        c = web.ctx.globals.dbcon.execute('''select * from branch;''').fetchall()
        return '\n'.join(map(lambda x: ' '.join([str(x[i]) if (type(x[i])!=unicode) else str(x[i].encode('utf-8')) for i in x.keys()]), c))

class All:
    def GET(self, url):
        import teams
        print url
        dbcon = web.ctx.globals.dbcon

        jira_task_statuses_ = dbcon.execute('''select jira_task_status from branch group by jira_task_status;''').fetchall()
        jira_task_statuses = [i for (i,) in jira_task_statuses_]
        jira_task_priority_ = dbcon.execute('''select jira_task_priority from branch group by jira_task_priority;''').fetchall()
        jira_task_priority = [i for (i,) in jira_task_priority_]
        git_merge_status_ = dbcon.execute('''select git_merge_status from branch group by git_merge_status;''').fetchall()
        git_merge_status = [i for (i,) in git_merge_status_]
        jenkins_status_ = dbcon.execute('''select jenkins_status from branch group by jenkins_status;''').fetchall()
        jenkins_status = [i for (i,) in jenkins_status_]

        if url in jira_task_statuses:
            c = dbcon.execute('''select * from branch where jira_task_status=? order by jira_task_priority;''', (url,)).fetchall()
        elif url in jira_task_priority:
            c = dbcon.execute('''select * from branch where jira_task_priority=? order by jira_task_priority;''', (url,)).fetchall()
        elif url in git_merge_status:
            c = dbcon.execute('''select * from branch where git_merge_status=? order by jira_task_priority;''', (url,)).fetchall()
        elif url in jenkins_status:
            c = dbcon.execute('''select * from branch where jenkins_status=? order by jira_task_priority;''', (url,)).fetchall()
        elif url in teams.teams.keys():
            c = dbcon.execute('''select * from branch where jira_task_assignee in %s order by jira_task_priority;''' % (teams.teams[url],)).fetchall()
        else:
            c = dbcon.execute('''select * from branch;''').fetchall()
        render = web.template.render('templates/')
        return render.general(c, web.ctx.globals.jira_priority_map)


def add_global_hoSUCCESS(glob):
    g = web.storage(glob)

    def _wrapper(handler):
        web.ctx.globals = g
        return handler()

    return _wrapper


def init_web(dbcon, jira_priority_map):
    import sys

    sys.argv[1:] = ['8888']
    app = web.application(urls, globals())
    app.add_processor(add_global_hoSUCCESS({'dbcon':dbcon,'jira_priority_map': jira_priority_map}))
    print 'Serving on:'
    application = app.run()