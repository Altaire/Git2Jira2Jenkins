import os, re, shutil, threading, logging, config
TRACE = False
lock = threading.Lock()

#TODO: non-blocking io with timeout
def __subprocess(args):
    import subprocess
    with lock:
        pipe = subprocess.Popen(args, cwd=config.GIT_WORK_DIR, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
        out, err = pipe.communicate()
        status =  pipe.returncode
        if status is not 0:
            return True, out, err
        return False, out, err

def cmd(args, print_err=True, timeout=1):
    logging.debug('[GIT] Action: ' + str(args))
    status, out, err = __subprocess(args)
    if status and print_err:
        logging.warning('[GIT] Cannot do action: ' + str(args))
        logging.warning("%s" % (out))
        logging.warning("%s" % (err))
    if TRACE:
        print('[GIT] Action: ' + str(args))
        print(status, out, err)
    return status, out, err

def clone():
    if os.path.exists(config.GIT_WORK_DIR):
        shutil.rmtree(config.GIT_WORK_DIR)
    os.makedirs(config.GIT_WORK_DIR)
    status, out, err = cmd(['git', 'clone', config.GIT_REMOTE_PATH, config.GIT_WORK_DIR])
    if status:
        import sys
        logging.error('[GIT] Cannot do action: clone' + "\n EXIT")
        sys.exit()

def fetch():
    cmd(['git', 'fetch'], timeout=20)

def get_all_remote_branch_heads(branch_regexp=None):
    status, out, err = cmd(['git', 'branch', '-r', '-v', '--no-abbrev'])
    branch_head = [(i.split()[0].lstrip('origin/'), i.split()[1]) for i in out.splitlines()]
    return filter(lambda (branch, head): re.match(branch_regexp, branch), branch_head)

def get_remote_and_local_branches():
    status, out, err = cmd(['git', 'branch', '-r'])
    remote_branches = [x.strip().lstrip("origin/") for x in out.splitlines() if re.match("origin/" + config.branch_name_regexp, x.strip())]
    status, out, err = cmd(['git', 'branch'])
    local_branches = [x.strip() for x in out.replace('*', '').splitlines() if (re.match(config.branch_name_regexp, x.strip()) and x.strip() != 'master')]
    return remote_branches, local_branches

def remove_branch(branch):
    cmd(['git', 'checkout', '-f', 'remotes/origin/master'])
    cmd(['git', 'branch', '-D', branch])


def checkout(branch):
    #cmd(['git', 'reset', '--hard'])
    #cmd(['git', 'checkout-index', '-a', '-f']
    cmd(['git', 'reset'])
    cmd(['git', 'checkout', '-f', '--no-track', '-b', branch, 'remotes/origin/' + branch])
    cmd(['git', 'reset'])
    cmd(['git', 'clean', '-fdxq'])


def merge(branch='remotes/origin/master'):
    status, out, err = cmd(['git', 'merge', '-q', branch], print_err=False)
    merge_status = 'MERGED'
    if status:
        merge_status = 'CONFLICT'
    return merge_status

def get_diff():
    raise
    status, out, err = cmd(['git', 'diff', '--name-status', '--exit-code', 'remotes/origin/master'],print_err=False)
    sql_status = "NO SQL"
    bsh_status = "NO BSH"
    config_status = "CONFIG UNKNOWN"
    if out.find(".sql") >= 0:
        sql_status = "SQL"
    if out.find(".bsh") >= 0:
        bsh_status = "BSH"
    return sql_status, bsh_status, config_status

def get_head(branch):
    status, out1, err = cmd(['git', 'log', '-1', '--pretty=format:%H', branch])
    return out1
