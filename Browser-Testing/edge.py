#!/usr/bin/env python3

import sys
import csv

from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from multiprocessing import Manager, Pool

urls = sys.argv[1]
col = int(sys.argv[2])
concurrency = int(sys.argv[3])

imported = 0
detected = 0

def load(q, c):
    # load dataset
    print("Loading URLs...")
    with open(urls, "r") as f:
        reader = csv.reader(f)

        # push each line into a shared queue
        for entry in reader:
            if not entry[0].startswith("#"): # ignore comments
                q.put(entry[c])

    # sentinel value to terminate processing
    q.put(None)

    # wait for all URLs to be processed and terminate this thread
    q.join()

    print("Finished reading dataset, and sent sentinel.")

def save(q):
    # save results as they come in
    print("Saving output to file...")
    with open("output.csv", "w") as f:
        writer = csv.writer(f)

        i = 0

        while True:
            result = q.get()

            # wait for sentinel and then quit
            if result is None:
                print("Detected sentinel, exiting...")

                q.task_done()

                break

            # write the results to a file
            print("Writing new result...")
            writer.writerow(result)
            i += 1

            # flush the file to the disk every 10 lines
            if i % 10 == 0:
                f.flush()

            # this result was processed
            q.task_done()

    print("Finished writing results.")

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

def detect(q, r):
    print("Starting worker thread...")

    # obtain a new browser instance through Selenium
    browser = instance()

    while True:
        url = q.get()

        # if all tasks have been marked complete, stop processing
        if url is None:
            print("Detected sentinel, passing it on and exiting...")

            q.put(None) # re-add the sentinel value for other threads
            q.task_done()

            break

        print("Requesting page...")
        try:
            browser.get(url)
        except WebDriverException as err:
            # assume timed-out pages were not blocked
            if "CONNECTION_TIMED_OUT" in err.msg:
                continue

        # get information about the visited page
        print("Testing for alert...")
        origin = browser.execute_script("return window.origin")
        r.put((url, origin == "null")) # write the result to be saved

        # indicate that processing completed
        q.task_done()

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

    # add workers
    workers.starmap(detect, ((iqueue, oqueue),) * concurrency)
    print("Workers exited successfully.")

    # consume the leftover sentinel value once all threads have exited
    iqueue.get()
    iqueue.task_done()

    # sentinel value to close the output file
    oqueue.put(None)

    print("Processing completed successfully!")
