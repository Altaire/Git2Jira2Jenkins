import os, re, shutil, threading, logging, config

try:
    import pexpect
except:
    import sys

    print "Please do (for Ubuntu):\n\tsudo apt-get install python-pexpect \nEXIT"
    sys.exit()


TRACE = False
lock = threading.Lock()

#TODO: non-blocking io with timeout
def __subprocess(args, timeout):
    out, status = pexpect.run('git ' + ' '.join(args), cwd=config.GIT_WORK_DIR, timeout=timeout, withexitstatus=1)
    if status is not 0:
        return True, out, ''
    return False, out, ''

def cmd(args, print_err=True, timeout=5):
    logging.debug('[GIT] Action: ' + str(args))
    status, out, err = __subprocess(args, timeout)
    if status and print_err:
        logging.warning('[GIT] Cannot do action: ' + str(args))
        logging.warning("%s" % (out))
        logging.warning("%s" % (err))
    if TRACE:
        print('[GIT] Action done: ' + str(args))
        print(status, out, err)
    return status, out, err

def clone():
    if os.path.exists(config.GIT_WORK_DIR):
        shutil.rmtree(config.GIT_WORK_DIR)
    os.makedirs(config.GIT_WORK_DIR)
    with lock:
        status, out, err = cmd(['clone', config.GIT_REMOTE_PATH, config.GIT_WORK_DIR], timeout=300)
    if status:
        import sys
        logging.error('[GIT] Cannot do action: clone' + "\n EXIT")
        sys.exit()

def fetch():
    with lock:
        cmd(['fetch'], timeout=20)

def get_all_remote_branch_heads(branch_regexp=None):
    with lock:
        status, out, err = cmd(['branch', '-r', '-v', '--no-abbrev'])
    branch_head = [(i.split()[0].lstrip('origin/'), i.split()[1]) for i in out.splitlines()]
    return filter(lambda (branch, head): re.match(branch_regexp, branch), branch_head)

def get_remote_and_local_branches():
    with lock:
        status, out, err = cmd(['branch', '-r'])
        remote_branches = [x.strip().lstrip("origin/") for x in out.splitlines() if re.match(config.branch_name_regexp, x.strip().lstrip("origin/"))]
        status, out, err = cmd(['branch'])
        local_branches = [x.strip() for x in out.replace('*', '').splitlines() if (re.match(config.branch_name_regexp, x.strip()) and x.strip() != 'master')]
        return remote_branches, local_branches

def remove_branch(branch):
    with lock:
        cmd(['checkout', '-f', 'remotes/origin/master'])
        cmd(['branch', '-D', branch])

def checkout(branch):
    with lock:
        #cmd(['git', 'reset', '--hard'])
        #cmd(['git', 'checkout-index', '-a', '-f']
        cmd(['reset'])
        cmd(['checkout', '-f', '--no-track', '-b', branch, 'remotes/origin/' + branch])
        cmd(['reset'])
        cmd(['clean', '-fdxq'])


def merge(branch='remotes/origin/master'):
    with lock:
        status, out, err = cmd(['merge', '-q', branch], print_err=False)
        merge_status = 'MERGED'
        if status:
            merge_status = 'CONFLICT'
        return merge_status

def get_diff():
    raise
    with lock:
        status, out, err = cmd(['diff', '--name-status', '--exit-code', 'remotes/origin/master'],print_err=False)
    sql_status = "NO SQL"
    bsh_status = "NO BSH"
    config_status = "CONFIG UNKNOWN"
    if out.find(".sql") >= 0:
        sql_status = "SQL"
    if out.find(".bsh") >= 0:
        bsh_status = "BSH"
    return sql_status, bsh_status, config_status

def get_head(branch):
    with lock:
        status, out, err = cmd(['log', '-1','--color=never', '--pretty=format:%H', branch])
        return out.replace('\x1b[?1h\x1b=\r','').replace('\x1b[m\r\n\r\x1b[K\x1b[?1l\x1b>','')

def get_status():
    with lock:
        cmd(['status'])
