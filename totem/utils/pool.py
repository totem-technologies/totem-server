import threading
from queue import Queue

from django.conf import settings
from sentry_sdk import capture_exception


class Item:
    def __init__(self, func, *args, **kwargs):
        self.func = func
        self.args = args
        self.kwargs = kwargs

    def __call__(self):
        self.func(*self.args, **self.kwargs)


class _Sentinel:
    pass


class ThreadPool:
    """A thread pool that can be used to execute tasks in the background. The threads are daemons, so they will
    automatically exit when the main thread exits. This makes it unsuitable for long-running tasks, or critical tasks.
    It's best used for shot-lived tasks that can be safely interrupted, like single emails, or API calls.
    Also, you don't get results.

    Usage:

    def send_email(to, subject, body):
        # Send email

    pool = ThreadPool()
    pool.add_task(send_email, "user@example", "Subject", "Body")
    pool.wait_completion()
    pool.stop()
    """

    def __init__(self, num_threads=10, max_queue_size=100000, error_callback=capture_exception):
        self.queue = Queue(max_queue_size)
        self.num_threads = num_threads
        self.error_callback = error_callback
        self.threads = []  # Keep track of threads so they can be joined if needed
        for _ in range(num_threads):
            t = threading.Thread(target=self.worker, daemon=True)
            t.start()
            self.threads.append(t)  # Add thread to the list

    def worker(self):
        while True:
            item = self.queue.get(block=True)
            if isinstance(item, _Sentinel):  # Sentinel value to exit the loop
                break
            try:
                item()
            except Exception as e:
                if self.error_callback is not None:
                    self.error_callback(e)  # Pass the exception to the error callback
            finally:
                self.queue.task_done()

    def add_task(self, fn, *args, **kwargs):
        self.queue.put(Item(fn, *args, **kwargs))
        if settings.TOTEM_ASYNC_WORKER_QUEUE_ENABLED is False:
            self.queue.join()

    def wait_completion(self):
        self.queue.join()

    def stop(self):
        # Ensure that all tasks have been processed before stopping the threads
        self.wait_completion()
        for _ in range(self.num_threads):
            self.queue.put(_Sentinel())
        for thread in self.threads:
            thread.join()  # Wait for threads to finish


global_pool = ThreadPool()
