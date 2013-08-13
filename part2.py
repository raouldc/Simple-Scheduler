
import sys, os, signal, time, threading


# These functions are to be scheduled and run in separate real processes.
def low_func(proc):
    pid = os.getpid() # who am I?
    print('Low priority:', pid, '- just about to request resource')
    controller_write.write('{0}:request\n'.format(pid))
    response = proc.read.readline()
    print('Low priority:', pid, '- got resource')

    sum = 0
    for i in range(100000000):
        sum += i

    controller_write.write('{0}:release\n'.format(pid))
    print('Low priority:', pid, '- released resource')

    for i in range(100000000):
        sum += i

    print('Low priority:', pid, '- finished')


def mid_func(proc):
    for i in range(1, 11):
        print('Mid priority:', i)
        time.sleep(0.5)

def high_func(proc):
    pid = os.getpid() # who am I?
    print('High priority:', pid, '- just about to request resource')
    controller_write.write('{0}:request\n'.format(pid))
    response = proc.read.readline()
    print('High priority:', pid, '- got resource')
    controller_write.write('{0}:release\n'.format(pid))
    print('High priority:', pid, '- released resource')


#===============================================================================
class SimpleProcess():
    def __init__(self, priority, function):
        self.pid = None
        self.priority = priority
        self.func = function
        # Set up the pipe which will later be used to send replies to the process
        # from the controller.
        r, w = os.pipe()
        self.read = os.fdopen(r)
        self.write = os.fdopen(w, mode='w', buffering=1)

    # Creates the new process for this to run in when 'run' is first called.
    def run(self):
        self.pid = os.fork() # the child is the process

        if self.pid: # in the parent
            self.read.close()
            processes[self.pid] = self

        else: # in the child
            self.write.close()
            self.func(self)
            os._exit(0) # what would happen if this wasn't here?

#===============================================================================
# This is in control of the single resource.
# Only one process at a time is allowed access to the resource.
r, w = os.pipe()
controller_read = os.fdopen(r)
controller_write = os.fdopen(w, mode='w', buffering=1)

class Controller():

    def run(self):
        owner = None
        queue = []

        while True:
            input_string = controller_read.readline()
            if input_string.strip() == 'terminate':
                return
            pid, message = input_string.strip().split(':')
            pid = int(pid)
            # possible race condition on line below
            requesting_process = processes[pid]

            #pseudocode to prevent priority inversion
            """
            if process is blocked:
                find pid of process holding lock on resources
                elevate priority to of lock holding process to blocked process
                when lock is released or lock holding process quits:
                    restore priority back
            """

            if message == 'request':
                if not owner: # no current owner
                    owner = requesting_process
                    owner.write.write('reply\n')
                else: # currently owned
                    scheduler.remove_process(requesting_process)
                    queue.append(requesting_process)
            elif message == 'release' and owner == requesting_process:
                # the first in the queue gets it
                if len(queue) < 1:
                    owner = None
                else:
                    owner = queue.pop(0)
                    scheduler.add_process(owner)
                    owner.write.write('reply\n')
            print('owner pid:', owner.pid if owner else None)

#===============================================================================
# The dummy scheduler.
# Every second it selects the next process to run.
class Scheduler():

    def __init__(self):
        self.ready_list = []

    # Add a process to the run list
    def add_process(self, process):
        self.ready_list.append(process)
        self.ready_list= sorted(self.ready_list, key=lambda process:process.priority,reverse=True)

    def remove_process(self, process):
        self.ready_list.remove(process)

    # Selects the process with the best priority.
    # If more than one have the same priority these are selected in round-robin fashion.
    def select_process(self):
        if len(self.ready_list) is 0:
            return

        currentProcess = self.ready_list[0]
        pri = currentProcess.priority
        ind = 0

        #find index of process with lower priority
        for i in range(1,len(self.ready_list)):
            if pri > self.ready_list[i].priority:
                ind = i - 1
                break
            else:
                pri = self.ready_list[i].priority

        #swap processes
        self.ready_list.remove(currentProcess)
        self.ready_list.insert(ind, currentProcess)

        return currentProcess

    # Suspends the currently running process by sending it a STOP signal.
    @staticmethod
    def suspend(process):
        os.kill(process.pid, signal.SIGSTOP)

    # Resumes a process by sending it a CONT signal.
    @staticmethod
    def resume(process):
        if process.pid: # if the process has a pid it has started
            os.kill(process.pid, signal.SIGCONT)
        else:
            process.run()

    def run(self):
        current_process = None
        while True:
            #print('length of ready_list:', len(self.ready_list))
            next_process = self.select_process()
            if next_process == None: # no more processes
                controller_write.write('terminate\n')
                sys.exit()
            if next_process != current_process:
                if current_process:
                    self.suspend(current_process)
                current_process = next_process
                self.resume(current_process)
            time.sleep(1)
            # need to remove dead processes from the list
            try:
                current_process_finished = (
                    os.waitpid(current_process.pid, os.WNOHANG) != (0, 0)
                )
            except ChildProcessError:
                current_process_finished = True
            if current_process_finished:
                print('remove process', current_process.pid, 'from ready list')
                self.remove_process(current_process)
                current_process = None

#===============================================================================

controller = Controller()
scheduler = Scheduler()
processes = {}

# Priorities range from 1 to 10
low_process = SimpleProcess(1, low_func)
scheduler.add_process(low_process)

threading.Thread(target=scheduler.run).start()

time.sleep(0.5) # give low_process a chance to get going

mid_process = SimpleProcess(5, mid_func)
scheduler.add_process(mid_process)

high_process = SimpleProcess(10, high_func)
scheduler.add_process(high_process)

controller.run()

print('finished')

