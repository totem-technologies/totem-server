import threading
from queue import Queue

# ParamSpec requires Python 3.10+
# If using older Python, you might need typing_extensions
# from typing_extensions import ParamSpec
from typing import Any, Callable, Generic, Optional, ParamSpec, TypeVar, Union

from django.conf import settings
from sentry_sdk import capture_exception

# Define ParamSpec for capturing the parameters of the function passed to add_task
P = ParamSpec("P")
# Define TypeVar for the (ignored) return type of the function
R = TypeVar("R")


# Make Item generic using P and R
class Item(Generic[P, R]):
    def __init__(self, func: Callable[P, R], *args: P.args, **kwargs: P.kwargs):
        self.func: Callable[P, R] = func
        self.args: tuple[Any, ...] = args
        self.kwargs: dict[str, Any] = kwargs

    # __call__ itself doesn't return the result of self.func directly
    def __call__(self) -> None:
        # The return value of self.func (type R) is ignored here
        self.func(*self.args, **self.kwargs)


class _Sentinel:
    pass


# Type hint for the items that can be put in the queue
# Using Item[Any, Any] because the queue holds Items created
# with various different function signatures (different P and R types)
QueueItem = Union[Item[Any, Any], _Sentinel]


class ThreadPool:
    """A thread pool that can be used to execute tasks in the background. The threads are daemons, so they will
    automatically exit when the main thread exits. This makes it unsuitable for long-running tasks, or critical tasks.
    It's best used for shot-lived tasks that can be safely interrupted, like single emails, or API calls.
    Also, you don't get results.

    Usage:

    def send_email(to: str, subject: str, body: str) -> None:
        # Send email
        print(f"Sending email to {to} with subject '{subject}'")

    pool = ThreadPool()
    pool.add_task(send_email, "user@example", "Subject", "Body")
    # Example with keyword args
    pool.add_task(send_email, to="another@example.com", subject="Kwargs Subject", body="Kwargs Body")
    pool.wait_completion()
    pool.stop()
    """

    def __init__(
        self,
        num_threads: int = 10,
        max_queue_size: int = 100000,
        error_callback: Optional[Callable[[Exception], Any]] = capture_exception,
    ):
        # The queue holds generic Items or Sentinels
        self.queue: Queue[QueueItem] = Queue(max_queue_size)
        self.num_threads: int = num_threads
        self.error_callback: Optional[Callable[[Exception], Any]] = error_callback
        # Keep track of threads so they can be joined if needed
        self.threads: list[threading.Thread] = []
        for _ in range(num_threads):
            t = threading.Thread(target=self.worker, daemon=True)
            t.start()
            self.threads.append(t)  # Add thread to the list

    def worker(self) -> None:
        while True:
            # item will be inferred as QueueItem
            item = self.queue.get(block=True)
            if isinstance(item, _Sentinel):  # Sentinel value to exit the loop
                # Put the sentinel back in case other threads need to stop,
                # although the stop() method puts one for each thread.
                # self.queue.put(item) # Optional: depends on desired shutdown logic nuances
                break
            try:
                # We know item must be an Item instance here due to the check above
                # Type checkers might need an assertion or cast if strict,
                # but isinstance check is usually sufficient hint.
                item()  # Calls Item.__call__
            except Exception as e:
                if self.error_callback is not None:
                    # Pass the exception to the error callback
                    self.error_callback(e)
            finally:
                # Signal that the task pulled from the queue is done
                self.queue.task_done()

    # Use P and R defined earlier for the function signature
    def add_task(self, fn: Callable[P, R], *args: P.args, **kwargs: P.kwargs) -> None:
        """Adds a function call (task) to the queue for execution."""
        # Create a type-specific Item instance
        item_instance: Item[P, R] = Item(fn, *args, **kwargs)
        # Put it onto the queue (type compatibility checked by Queue[QueueItem])
        self.queue.put(item_instance)

        # This setting check remains as is
        if settings.TOTEM_ASYNC_WORKER_QUEUE_ENABLED is False:
            self.queue.join()

    def wait_completion(self) -> None:
        """Blocks until all items in the queue have been gotten and processed."""
        self.queue.join()

    def stop(self) -> None:
        """Stops the worker threads after completing queued tasks.

        Waits for the queue to be empty, then sends a sentinel object
        to each thread and waits for them to finish.
        """
        # Ensure that all tasks have been processed before stopping the threads
        self.wait_completion()
        # Send a sentinel for each thread to ensure they all receive the signal
        for _ in range(self.num_threads):
            self.queue.put(_Sentinel())
        # Wait for all worker threads to terminate
        for thread in self.threads:
            thread.join()


# Type hint the global instance
global_pool: ThreadPool = ThreadPool()

# # Example Usage (demonstrates type checking benefits)
# def sample_task(name: str, count: int) -> None:
#     print(f"Task '{name}' running with count {count}.")

# def another_task(value: float) -> str:
#     print(f"Another task with value {value}")
#     return f"Processed {value}"

# # This is type-correct
# global_pool.add_task(sample_task, "My Task", 5)
# global_pool.add_task(sample_task, name="Keyword Task", count=10)
# global_pool.add_task(another_task, 3.14)

# Example of what a type checker would flag (if run):
# global_pool.add_task(sample_task, "Wrong type", "not an int") # Error: Argument 2 to "sample_task" has incompatible type "str"; expected "int
