"""Bounded native subprocess lifecycle, including editor/render cancellation."""
import os,signal,subprocess,sys


def _signal_group(process,kind):
    try:
        if os.name=='posix':os.killpg(process.pid,kind)
        else:process.send_signal(kind)
    except ProcessLookupError:pass


def _stop(process):
    # Node's Playwright signal handlers close its detached browser process group.
    # Allow that cleanup before escalation. A following SIGINT forces an already
    # closing Playwright browser to stop, before a last-resort Node group kill.
    _signal_group(process,signal.SIGTERM)
    try:process.wait(timeout=5);return
    except subprocess.TimeoutExpired:pass
    _signal_group(process,signal.SIGINT)
    try:process.wait(timeout=2);return
    except subprocess.TimeoutExpired:pass
    _signal_group(process,signal.SIGKILL);process.wait()


def run_native(command,*,check=False,capture_output=False,**options):
    """subprocess.run's used subset, with graceful isolated-group cancellation."""
    if capture_output:
        if 'stdout' in options or 'stderr' in options:raise ValueError('capture_output cannot be combined with stdout/stderr')
        options.update(stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    process=subprocess.Popen(command,**options,**({'start_new_session':True} if os.name=='posix' else {}))
    try:
        stdout,stderr=process.communicate()
    except BaseException:
        try:_stop(process)
        except BaseException as error:
            try:print('sbph: Native process cleanup failed for PID '+str(process.pid)+' ('+type(error).__name__+')',file=sys.stderr)
            except BaseException:pass
        raise
    finally:
        for name in ['stdin','stdout','stderr']:
            pipe=getattr(process,name,None)
            if pipe is not None:pipe.close()
    result=subprocess.CompletedProcess(command,process.returncode,stdout,stderr)
    if check:result.check_returncode()
    return result
