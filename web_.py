import sys

try:
    import web
except:
    print "Please do (for Ubuntu):\n\tsudo apt-get install python-webpy \nEXIT"
    sys.exit()


def web_get_ready():
    branches = set([i[0] for i in main.dbcon.execute(
        '''select branch from branch where (remote_branch_head is branch_head) and (remote_branch_head is jenkins_branch_head) and jenkins_status='OK';''').fetchall()])
    return branches


def web_get_failed():
    branches = set([i[0] for i in main.dbcon.execute(
        '''select branch from branch where (remote_branch_head is branch_head) and (remote_branch_head is jenkins_branch_head) and jenkins_status!='OK';''').fetchall()])
    return branches


def web_get_conflicted():
    branches = set([i[0] for i in main.dbcon.execute(
        '''select branch from branch where (remote_branch_head is branch_head) and (remote_branch_head is jenkins_branch_head) and jenkins_status='OK';''').fetchall()])
    return branches


def web_get_conflicted_for_user():
    branches = set([i[0] for i in main.dbcon.execute(
        '''select branch from branch where (remote_branch_head is branch_head) and (remote_branch_head is jenkins_branch_head) and jenkins_status='OK';''').fetchall()])
    return branches


urls = ("/", "Index")
class Index:
    def GET(self):
        c = web.ctx.globals.dbcon.execute('''select * from branch;''').fetchall()
        return '\n'.join(map(lambda x: str(x), c))

def add_global_hook(dbcon):
    g = web.storage({"dbcon": dbcon})

    def _wrapper(handler):
        web.ctx.globals = g
        return handler()

    return _wrapper


def init_web(dbcon):
    sys.argv[1:] = ['8888']
    app = web.application(urls, globals())
    app.add_processor(add_global_hook(dbcon))
    print 'Serving on:'
    application = app.run()