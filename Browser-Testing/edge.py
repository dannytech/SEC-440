#!/usr/bin/env python3

import sys
import csv
import time
import datetime

from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from multiprocessing import Manager, Pool

urls = sys.argv[1]
col = int(sys.argv[2])
concurrency = int(sys.argv[3])

imported = 0
detected = 0

def load(queue, col):
    # load dataset
    print("Loading URLs...")
    with open(urls, "r") as f:
        reader = csv.reader(f)

        # push each line into a shared queue
        for entry in reader:
            if not entry[0].startswith("#"): # ignore comments
                queue.put(entry[col])

    # sentinel value to terminate processing
    queue.put(None)

    # wait for all URLs to be processed and terminate this thread
    queue.join()

    print("Finished reading dataset, and sent sentinel.")

def save(queue):
    # counters
    processed = 0
    detected = 0
    timeout = 0

    # save results as they come in
    print("Saving output to file...")
    with open("output.csv", "w") as f:
        writer = csv.writer(f)

        while True:
            result = queue.get()

            # wait for sentinel and then quit
            if result is None:
                print("Detected sentinel, exiting...")

                queue.task_done()

                break

            # write the results to a file
            print("Writing new result...")
            writer.writerow(result)
            processed += 1

            # flush the file to the disk every 10 lines
            if processed % 10 == 0:
                f.flush()

            # count detected items
            if result[1]:
                detected += 1
            elif result[1] is None:
                timeout += 1

            # this result was processed
            queue.task_done()

    print("Finished writing results.")

    return (processed, detected, timeout)

def instance():
    # create a new Chromium Edge configuration
    edge_options = webdriver.EdgeOptions()
    edge_options.add_argument("--user-data-dir=C:\\Selenium\\Profiles\\Edge")
    edge_options.headless = False

    # register the Chromium Edge config with any Chromium Edge instance available on the Grid
    print("Provisioning browser instance...")
    driver = webdriver.Remote(
        command_executor="http://localhost:4444/wd/hub",
        options=edge_options)

    return driver

def detect(iqueue, oqueue):
    print("Starting worker thread...")

    # obtain a new browser instance through Selenium
    browser = instance()

    while True:
        url = iqueue.get()

        # if all tasks have been marked complete, stop processing
        if url is None:
            print("Detected sentinel, passing it on and exiting...")

            iqueue.put(None) # re-add the sentinel value for other threads
            iqueue.task_done()

            break

        print("Requesting page...")
        try:
            browser.get(url)
        except WebDriverException as err:
            # ignore timed-out pages
            if "CONNECTION_TIMED_OUT" in err.msg:
                oqueue.put((url, None))
                continue

        # get information about the visited page
        print("Testing for alert...")
        origin = browser.execute_script("return window.origin")
        oqueue.put((url, origin == "null")) # write the result to be saved

        # indicate that processing completed
        iqueue.task_done()

    browser.quit()

if __name__ == "__main__":
    # thread pool for browser workers
    workers = Pool(concurrency)

    # thread pool for file I/O
    io = Pool(2)

    # create a shared queue
    manager = Manager()
    iqueue = manager.Queue()
    oqueue = manager.Queue()

    # asynchronously read the URL list
    loader = io.apply_async(load, args=(iqueue, col))

    # asynchronously write the results
    saver = io.apply_async(save, args=(oqueue,))

    # start of the actual processing
    start = time.monotonic()

    # add workers
    workers.starmap(detect, ((iqueue, oqueue),) * concurrency)
    print("Workers exited successfully.")

    end = time.monotonic()

    # consume the leftover sentinel value once all threads have exited
    iqueue.get()
    iqueue.task_done()

    # sentinel value to close the output file
    oqueue.put(None)

    # get the statistics
    imported, detected, timeout = saver.get()

    print("Processing completed successfully!")
    print(f"Processed: {imported}, Detected: {detected}, Timed Out: {timeout}")
    print(f"Completed in", datetime.timedelta(seconds=end - start))
