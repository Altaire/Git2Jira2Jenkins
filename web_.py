# -*- coding: utf-8

try:
    import web
except:
    import sys

    print "Please do (for Ubuntu):\n\tsudo apt-get install python-webpy \nEXIT"
    sys.exit()


def succ_merge_succ_build(dbcon):
    return dbcon.execute(
        '''select * from branch where (git_remote_branch_head is git_branch_head)
         and (git_merge_status is 'MERGED')
         and (git_remote_branch_head is jenkins_branch_head)
         and (jenkins_status is 'SUCCESS');''').fetchall()


def succ_merge_fail_build(dbcon):
    return dbcon.execute(
        '''select * from branch where (git_remote_branch_head is git_branch_head)
         and (git_merge_status is 'MERGED')
         and (git_remote_branch_head is jenkins_branch_head)
         and not (jenkins_status is 'SUCCESS');''').fetchall()


def succ_merge_no_build(dbcon):
    return dbcon.execute(
        '''select * from branch where (git_remote_branch_head is git_branch_head)
        and (git_merge_status is 'MERGED')
        and not (git_remote_branch_head is jenkins_branch_head);''').fetchall()


def fail_merge(dbcon):
    return dbcon.execute(
        '''select * from branch where (git_remote_branch_head is git_branch_head)
         and not git_merge_status is 'MERGED';''').fetchall()


def no_merge(dbcon):
    return dbcon.execute('''select * from branch where not (git_remote_branch_head is git_branch_head);''').fetchall()


urls = ("/",    "Index",
        '/txt', "Txt")

class Index:
    def GET(self):
        dbcon = web.ctx.globals.dbcon
        render = web.template.render('templates/')
        return render.index(
            succ_merge_succ_build(dbcon),
            succ_merge_fail_build(dbcon),
            succ_merge_no_build(dbcon),
            fail_merge(dbcon),
            no_merge(dbcon))

class Txt:
    def GET(self):
        c = web.ctx.globals.dbcon.execute('''select * from branch;''').fetchall()
        return '\n'.join(map(lambda x: ' '.join(['None' if (x[i]==None) else str(x[i].encode('utf-8')) for i in x.keys()]), c))


def add_global_hoSUCCESS(dbcon):
    g = web.storage({"dbcon": dbcon})

    def _wrapper(handler):
        web.ctx.globals = g
        return handler()

    return _wrapper


def init_web(dbcon):
    import sys

    sys.argv[1:] = ['8888']
    app = web.application(urls, globals())
    app.add_processor(add_global_hoSUCCESS(dbcon))
    print 'Serving on:'
    application = app.run()