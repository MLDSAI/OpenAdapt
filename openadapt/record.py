"""Script for creating Recordings.

Usage:

    $ python openadapt/record.py "<description of task to be recorded>"

"""

from collections import namedtuple
from functools import partial
from typing import Any, Callable, Dict
import multiprocessing
import queue
import signal
import sys
import threading
import time

from loguru import logger
from pynput import keyboard, mouse
import fire
import mss.tools

from openadapt import config, crud, utils, window

import functools


EVENT_TYPES = ("screen", "action", "window")
LOG_LEVEL = "INFO"
PROC_WRITE_BY_EVENT_TYPE = {
    "screen": True,
    "action": True,
    "window": True,
}
PLOT_PERFORMANCE = False


Event = namedtuple("Event", ("timestamp", "type", "data"))

utils.configure_logging(logger, LOG_LEVEL)


def args_to_str(*args: tuple) -> str:
    """Convert positional arguments to a string representation.

    Args:
        *args: Positional arguments.

    Returns:
        str: Comma-separated string representation of positional arguments.
    """
    return ", ".join(map(str, args))


def kwargs_to_str(**kwargs: dict[str, Any]) -> str:
    """Convert keyword arguments to a string representation.

    Args:
        **kwargs: Keyword arguments.

    Returns:
        str: Comma-separated string representation of keyword arguments in form "key=value".
    """
    return ",".join([f"{k}={v}" for k, v in kwargs.items()])


def trace(logger: Any) -> Any:
    """Decorator that logs the function entry and exit using the provided logger.

    Args:
        logger: The logger object to use for logging.

    Returns:
        A decorator that can be used to wrap functions and log their entry and exit.
    """

    def decorator(func: Any) -> Any:
        @functools.wraps(func)
        def wrapper_logging(*args: tuple, **kwargs: dict[str, Any]) -> Any:
            func_name = func.__qualname__
            func_args = args_to_str(*args)
            func_kwargs = kwargs_to_str(**kwargs)

            if func_kwargs != "":
                logger.info(f" -> Enter: {func_name}({func_args}, {func_kwargs})")
            else:
                logger.info(f" -> Enter: {func_name}({func_args})")

            result = func(*args, **kwargs)

            logger.info(f" <- Leave: {func_name}({result})")
            return result

        return wrapper_logging

    return decorator


def process_event(
    event: Any, write_q: Any, write_fn: Any, recording_timestamp: int, perf_q: Any
) -> None:
    """Process an event and take appropriate action based on its type.

    Args:
        event: The event to process.
        write_q: The queue for writing the event.
        write_fn: The function for writing the event.
        recording_timestamp: The timestamp of the recording.
        perf_q: The queue for collecting performance statistics.

    Returns:
        None
    """
    if PROC_WRITE_BY_EVENT_TYPE[event.type]:
        write_q.put(event)
    else:
        write_fn(recording_timestamp, event, perf_q)


@trace(logger)
def process_events(
    event_q: queue.Queue,
    screen_write_q: multiprocessing.Queue,
    action_write_q: multiprocessing.Queue,
    window_write_q: multiprocessing.Queue,
    perf_q: multiprocessing.Queue,
    recording_timestamp: float,
    terminate_event: multiprocessing.Event,
) -> None:
    """Process events from the event queue and write them to the respective write queues.

    Args:
        event_q: A queue with events to be processed.
        screen_write_q: A queue for writing screen events.
        action_write_q: A queue for writing action events.
        window_write_q: A queue for writing window events.
        perf_q: A queue for collecting performance data.
        recording_timestamp: The timestamp of the recording.
        terminate_event: An event to signal the termination of the process.
    """
    utils.configure_logging(logger, LOG_LEVEL)
    utils.set_start_time(recording_timestamp)
    logger.info("Starting")

    prev_event = None
    prev_screen_event = None
    prev_window_event = None
    prev_saved_screen_timestamp = 0
    prev_saved_window_timestamp = 0
    while not terminate_event.is_set() or not event_q.empty():
        event = event_q.get()
        logger.trace(f"{event=}")
        assert event.type in EVENT_TYPES, event
        if prev_event is not None:
            assert event.timestamp > prev_event.timestamp, (event, prev_event)
        if event.type == "screen":
            prev_screen_event = event
        elif event.type == "window":
            prev_window_event = event
        elif event.type == "action":
            if prev_screen_event is None:
                logger.warning("Discarding action that came before screen")
                continue
            if prev_window_event is None:
                logger.warning("Discarding input that came before window")
                continue
            event.data["screenshot_timestamp"] = prev_screen_event.timestamp
            event.data["window_event_timestamp"] = prev_window_event.timestamp
            process_event(
                event,
                action_write_q,
                write_action_event,
                recording_timestamp,
                perf_q,
            )
            if prev_saved_screen_timestamp < prev_screen_event.timestamp:
                process_event(
                    prev_screen_event,
                    screen_write_q,
                    write_screen_event,
                    recording_timestamp,
                    perf_q,
                )
                prev_saved_screen_timestamp = prev_screen_event.timestamp
            if prev_saved_window_timestamp < prev_window_event.timestamp:
                process_event(
                    prev_window_event,
                    window_write_q,
                    write_window_event,
                    recording_timestamp,
                    perf_q,
                )
                prev_saved_window_timestamp = prev_window_event.timestamp
        else:
            raise Exception(f"unhandled {event.type=}")
        prev_event = event
    logger.info("Done")


def write_action_event(
    recording_timestamp: float,
    event: Event,
    perf_q: multiprocessing.Queue,
) -> None:
    """Write an action event to the database and update the performance queue.

    Args:
        recording_timestamp: The timestamp of the recording.
        event: An action event to be written.
        perf_q: A queue for collecting performance data.
    """
    assert event.type == "action", event
    crud.insert_action_event(recording_timestamp, event.timestamp, event.data)
    perf_q.put((event.type, event.timestamp, utils.get_timestamp()))


def write_screen_event(
    recording_timestamp: float,
    event: Event,
    perf_q: multiprocessing.Queue,
) -> None:
    """Write a screen event to the database and update the performance queue.

    Args:
        recording_timestamp: The timestamp of the recording.
        event: A screen event to be written.
        perf_q: A queue for collecting performance data.
    """
    assert event.type == "screen", event
    screenshot = event.data
    png_data = mss.tools.to_png(screenshot.rgb, screenshot.size)
    event_data = {"png_data": png_data}
    crud.insert_screenshot(recording_timestamp, event.timestamp, event_data)
    perf_q.put((event.type, event.timestamp, utils.get_timestamp()))


def write_window_event(
    recording_timestamp: float,
    event: Event,
    perf_q: multiprocessing.Queue,
) -> None:
    """Write a window event to the database and update the performance queue.

    Args:
        recording_timestamp: The timestamp of the recording.
        event: A window event to be written.
        perf_q: A queue for collecting performance data.
    """
    assert event.type == "window", event
    crud.insert_window_event(recording_timestamp, event.timestamp, event.data)
    perf_q.put((event.type, event.timestamp, utils.get_timestamp()))


@trace(logger)
def write_events(
    event_type: str,
    write_fn: Callable,
    write_q: multiprocessing.Queue,
    perf_q: multiprocessing.Queue,
    recording_timestamp: float,
    terminate_event: multiprocessing.Event,
) -> None:
    """Write events of a specific type to the database using the provided write function.

    Args:
        event_type: The type of events to be written.
        write_fn: A function to write events to the database.
        write_q: A queue with events to be written.
        perf_q: A queue for collecting performance data.
        recording_timestamp: The timestamp of the recording.
        terminate_event: An event to signal the termination of the process.
    """
    utils.configure_logging(logger, LOG_LEVEL)
    utils.set_start_time(recording_timestamp)
    logger.info(f"{event_type=} Starting")
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    while not terminate_event.is_set() or not write_q.empty():
        try:
            event = write_q.get_nowait()
        except queue.Empty:
            continue
        assert event.type == event_type, (event_type, event)
        write_fn(recording_timestamp, event, perf_q)
        logger.debug(f"{event_type=} written")
    logger.info(f"{event_type=} Done")


def trigger_action_event(
    event_q: queue.Queue, action_event_args: Dict[str, Any]
) -> None:
    """Triggers an action event and adds it to the event queue.

    Args:
        event_q: The event queue to add the action event to.
        action_event_args: A dictionary containing the arguments for the action event.

    Returns:
        None
    """
    x = action_event_args.get("mouse_x")
    y = action_event_args.get("mouse_y")
    if x is not None and y is not None:
        if config.RECORD_READ_ACTIVE_ELEMENT_STATE:
            element_state = window.get_active_element_state(x, y)
        else:
            element_state = {}
        action_event_args["element_state"] = element_state
    event_q.put(Event(utils.get_timestamp(), "action", action_event_args))


def on_move(event_q: queue.Queue, x: int, y: int, injected: bool) -> None:
    """Handles the 'move' event.

    Args:
        event_q: The event queue to add the 'move' event to.
        x: The x-coordinate of the mouse.
        y: The y-coordinate of the mouse.
        injected: Whether the event was injected or not.

    Returns:
        None
    """
    logger.debug(f"{x=} {y=} {injected=}")
    if not injected:
        trigger_action_event(
            event_q,
            {"name": "move", "mouse_x": x, "mouse_y": y},
        )


def on_click(
    event_q: queue.Queue,
    x: int,
    y: int,
    button: mouse.Button,
    pressed: bool,
    injected: bool,
) -> None:
    """Handles the 'click' event.

    Args:
        event_q: The event queue to add the 'click' event to.
        x: The x-coordinate of the mouse.
        y: The y-coordinate of the mouse.
        button: The mouse button.
        pressed: Whether the button is pressed or released.
        injected: Whether the event was injected or not.

    Returns:
        None
    """
    logger.debug(f"{x=} {y=} {button=} {pressed=} {injected=}")
    if not injected:
        trigger_action_event(
            event_q,
            {
                "name": "click",
                "mouse_x": x,
                "mouse_y": y,
                "mouse_button_name": button.name,
                "mouse_pressed": pressed,
            },
        )


def on_scroll(
    event_q: queue.Queue,
    x: int,
    y: int,
    dx: int,
    dy: int,
    injected: bool,
) -> None:
    """Handles the 'scroll' event.

    Args:
        event_q: The event queue to add the 'scroll' event to.
        x: The x-coordinate of the mouse.
        y: The y-coordinate of the mouse.
        dx: The horizontal scroll amount.
        dy: The vertical scroll amount.
        injected: Whether the event was injected or not.

    Returns:
        None
    """
    logger.debug(f"{x=} {y=} {dx=} {dy=} {injected=}")
    if not injected:
        trigger_action_event(
            event_q,
            {
                "name": "scroll",
                "mouse_x": x,
                "mouse_y": y,
                "mouse_dx": dx,
                "mouse_dy": dy,
            },
        )


def handle_key(
    event_q: queue.Queue,
    event_name: str,
    key: keyboard.KeyCode,
    canonical_key: keyboard.KeyCode,
) -> None:
    """Handles a key event.

    Args:
        event_q: The event queue to add the key event to.
        event_name: The name of the key event.
        key: The key code of the key event.
        canonical_key: The canonical key code of the key event.

    Returns:
        None
    """
    attr_names = [
        "name",
        "char",
        "vk",
    ]
    attrs = {
        f"key_{attr_name}": getattr(key, attr_name, None) for attr_name in attr_names
    }
    logger.debug(f"{attrs=}")
    canonical_attrs = {
        f"canonical_key_{attr_name}": getattr(canonical_key, attr_name, None)
        for attr_name in attr_names
    }
    logger.debug(f"{canonical_attrs=}")
    trigger_action_event(event_q, {"name": event_name, **attrs, **canonical_attrs})


def read_screen_events(
    event_q: queue.Queue,
    terminate_event: multiprocessing.Event,
    recording_timestamp: float,
) -> None:
    """Read screen events and add them to the event queue.

    Args:
        event_q: A queue for adding screen events.
        terminate_event: An event to signal the termination of the process.
        recording_timestamp: The timestamp of the recording.
    """
    utils.configure_logging(logger, LOG_LEVEL)
    utils.set_start_time(recording_timestamp)
    logger.info("Starting")
    while not terminate_event.is_set():
        screenshot = utils.take_screenshot()
        if screenshot is None:
            logger.warning("Screenshot was None")
            continue
        event_q.put(Event(utils.get_timestamp(), "screen", screenshot))
    logger.info("Done")


@trace(logger)
def read_window_events(
    event_q: queue.Queue,
    terminate_event: multiprocessing.Event,
    recording_timestamp: float,
) -> None:
    """Read window events and add them to the event queue.

    Args:
        event_q: A queue for adding window events.
        terminate_event: An event to signal the termination of the process.
        recording_timestamp: The timestamp of the recording.
    """
    utils.configure_logging(logger, LOG_LEVEL)
    utils.set_start_time(recording_timestamp)
    logger.info("Starting")
    prev_window_data = {}
    while not terminate_event.is_set():
        window_data = window.get_active_window_data()
        if not window_data:
            continue
        if window_data["title"] != prev_window_data.get("title") or window_data[
            "window_id"
        ] != prev_window_data.get("window_id"):
            # TODO: fix exception sometimes triggered by the next line on win32:
            #   File "\Python39\lib\threading.py" line 917, in run
            #   File "...\openadapt\record.py", line 277, in read window events
            #   File "...\env\lib\site-packages\loguru\logger.py" line 1977, in info
            #   File "...\env\lib\site-packages\loguru\_logger.py", line 1964, in _log
            #       for handler in core.handlers.values):
            #   RuntimeError: dictionary changed size during iteration
            _window_data = window_data
            _window_data.pop("state")
            logger.info(f"{_window_data=}")
        if window_data != prev_window_data:
            logger.debug("Queuing window event for writing")
            event_q.put(
                Event(
                    utils.get_timestamp(),
                    "window",
                    window_data,
                )
            )
        prev_window_data = window_data


@trace(logger)
def performance_stats_writer(
    perf_q: multiprocessing.Queue,
    recording_timestamp: float,
    terminate_event: multiprocessing.Event,
) -> None:
    """Write performance stats to the database.

    Each entry includes the event type, start time, and end time.

    Args:
        perf_q: A queue for collecting performance data.
        recording_timestamp: The timestamp of the recording.
        terminate_event: An event to signal the termination of the process.
    """
    utils.configure_logging(logger, LOG_LEVEL)
    utils.set_start_time(recording_timestamp)
    logger.info("Performance stats writer starting")
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    while not terminate_event.is_set() or not perf_q.empty():
        try:
            event_type, start_time, end_time = perf_q.get_nowait()
        except queue.Empty:
            continue

        crud.insert_perf_stat(
            recording_timestamp,
            event_type,
            start_time,
            end_time,
        )
    logger.info("Performance stats writer done")


@trace(logger)
def create_recording(
    task_description: str,
) -> Dict[str, Any]:
    """Create a new recording entry in the database.

    Args:
        task_description: A text description of the task being recorded.

    Returns:
        The newly created Recording object.
    """
    timestamp = utils.set_start_time()
    monitor_width, monitor_height = utils.get_monitor_dims()
    double_click_distance_pixels = utils.get_double_click_distance_pixels()
    double_click_interval_seconds = utils.get_double_click_interval_seconds()
    recording_data = {
        # TODO: rename
        "timestamp": timestamp,
        "monitor_width": monitor_width,
        "monitor_height": monitor_height,
        "double_click_distance_pixels": double_click_distance_pixels,
        "double_click_interval_seconds": double_click_interval_seconds,
        "platform": sys.platform,
        "task_description": task_description,
    }
    recording = crud.insert_recording(recording_data)
    logger.info(f"{recording=}")
    return recording


def read_keyboard_events(
    event_q: queue.Queue,
    terminate_event: multiprocessing.Event,
    recording_timestamp: float,
) -> None:
    """Reads keyboard events and adds them to the event queue.

    Args:
        event_q: The event queue to add the keyboard events to.
        terminate_event: The event to signal termination of event reading.
        recording_timestamp: The timestamp of the recording.

    Returns:
        None
    """

    def on_press(event_q: queue.Queue, key: Any, injected: Any) -> None:
        canonical_key = keyboard_listener.canonical(key)
        logger.debug(f"{key=} {injected=} {canonical_key=}")
        if not injected:
            handle_key(event_q, "press", key, canonical_key)

    def on_release(event_q: queue.Queue, key: Any, injected: Any) -> None:
        canonical_key = keyboard_listener.canonical(key)
        logger.debug(f"{key=} {injected=} {canonical_key=}")
        if not injected:
            handle_key(event_q, "release", key, canonical_key)

    utils.set_start_time(recording_timestamp)
    keyboard_listener = keyboard.Listener(
        on_press=partial(on_press, event_q),
        on_release=partial(on_release, event_q),
    )
    keyboard_listener.start()
    terminate_event.wait()
    keyboard_listener.stop()


def read_mouse_events(
    event_q: queue.Queue,
    terminate_event: multiprocessing.Event,
    recording_timestamp: float,
) -> None:
    """Reads mouse events and adds them to the event queue.

    Args:
        event_q: The event queue to add the mouse events to.
        terminate_event: The event to signal termination of event reading.
        recording_timestamp: The timestamp of the recording.

    Returns:
        None
    """
    utils.set_start_time(recording_timestamp)
    mouse_listener = mouse.Listener(
        on_move=partial(on_move, event_q),
        on_click=partial(on_click, event_q),
        on_scroll=partial(on_scroll, event_q),
    )
    mouse_listener.start()
    terminate_event.wait()
    mouse_listener.stop()


@trace(logger)
def record(
    task_description: str,
) -> None:
    """Record Screenshots/ActionEvents/WindowEvents.

    Args:
        task_description: A text description of the task to be recorded.
    """
    utils.configure_logging(logger, LOG_LEVEL)
    logger.info(f"{task_description=}")

    recording = create_recording(task_description)
    recording_timestamp = recording.timestamp

    event_q = queue.Queue()
    screen_write_q = multiprocessing.Queue()
    action_write_q = multiprocessing.Queue()
    window_write_q = multiprocessing.Queue()
    # TODO: save write times to DB; display performance plot in visualize.py
    perf_q = multiprocessing.Queue()
    terminate_event = multiprocessing.Event()

    window_event_reader = threading.Thread(
        target=read_window_events,
        args=(event_q, terminate_event, recording_timestamp),
    )
    window_event_reader.start()

    screen_event_reader = threading.Thread(
        target=read_screen_events,
        args=(event_q, terminate_event, recording_timestamp),
    )
    screen_event_reader.start()

    keyboard_event_reader = threading.Thread(
        target=read_keyboard_events,
        args=(event_q, terminate_event, recording_timestamp),
    )
    keyboard_event_reader.start()

    mouse_event_reader = threading.Thread(
        target=read_mouse_events,
        args=(event_q, terminate_event, recording_timestamp),
    )
    mouse_event_reader.start()

    event_processor = threading.Thread(
        target=process_events,
        args=(
            event_q,
            screen_write_q,
            action_write_q,
            window_write_q,
            perf_q,
            recording_timestamp,
            terminate_event,
        ),
    )
    event_processor.start()

    screen_event_writer = multiprocessing.Process(
        target=write_events,
        args=(
            "screen",
            write_screen_event,
            screen_write_q,
            perf_q,
            recording_timestamp,
            terminate_event,
        ),
    )
    screen_event_writer.start()

    action_event_writer = multiprocessing.Process(
        target=write_events,
        args=(
            "action",
            write_action_event,
            action_write_q,
            perf_q,
            recording_timestamp,
            terminate_event,
        ),
    )
    action_event_writer.start()

    window_event_writer = multiprocessing.Process(
        target=write_events,
        args=(
            "window",
            write_window_event,
            window_write_q,
            perf_q,
            recording_timestamp,
            terminate_event,
        ),
    )
    window_event_writer.start()

    terminate_perf_event = multiprocessing.Event()
    perf_stat_writer = multiprocessing.Process(
        target=performance_stats_writer,
        args=(
            perf_q,
            recording_timestamp,
            terminate_perf_event,
        ),
    )
    perf_stat_writer.start()

    # TODO: Discard events until everything is ready

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        terminate_event.set()

    logger.info("Joining...")
    keyboard_event_reader.join()
    mouse_event_reader.join()
    screen_event_reader.join()
    window_event_reader.join()
    event_processor.join()
    screen_event_writer.join()
    action_event_writer.join()
    window_event_writer.join()

    terminate_perf_event.set()

    if PLOT_PERFORMANCE:
        utils.plot_performance(recording_timestamp)

    logger.info(f"Saved {recording_timestamp=}")


# Entry point
def start() -> None:
    """Starts the recording process."""
    fire.Fire(record)


if __name__ == "__main__":
    fire.Fire(record)
