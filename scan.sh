#!/usr/bin/env python

import sys
import os
import glob
import getopt

from os import listdir
from os.path import isfile, join
from threading import Thread
from threading import Semaphore


import drupal

modules = []
sem_threads = Semaphore(7)

def notice(*args):
	print "\033[92m** SCAN NOTICE: \033[0m" + ' '.join(str(a) for a in args)

def check_module(project, args):
	project.diff()
	print project.name
	sem_threads.release()

check_module.percentage = 0



def fetch_path_for(path, dirtype):
	result = []
	for root, dirs, files in os.walk(path):
		for name in files:
			subDirPath = os.path.join(root, name)
			if name.endswith(dirtype):
				result.append(subDirPath)
	return result


def help():
	print 'scan.sh <options>'
	print ' -d --detailed Show detailed information'
	print ' -s --submodules Show submodules'

def main(argv):

	options = 0

	try:
		opts, args = getopt.getopt(argv, "ds", ["detailed", "submodules"])
	except getopt.GetoptError:
		help()
		return
	for opt, arg in opts:
		if opt == '-h':
			help()
			return
		elif opt in ("-d", "--detailed"):
			options = options | drupal.options_detailed
		elif opt in ("-s", "--submodules"):
			options = options | drupal.options_submodules

	try:

		notice("Scanning projects... This will take a while so grab a cup of coffee")
		threads = []

		path = "."

		modules = fetch_path_for(path, "info")
		projects = {}

		for path in modules:
			project = drupal.Project(path)
			projects[project.machine_name] = project

		for name, project in projects.items():
			if project.is_sub_project() and project.project in projects:
				projects[project.project].add_sub_project(project)

		for name, project in projects.items():
			if not project.is_sub_project() and not project.is_core_project():
				sem_threads.acquire()
				t = Thread(target=check_module, args=(project, 1))
				threads.append(t)
				t.daemon = True
				t.start()

		map(lambda t: t.join(), threads)

		level = 0

		notice("Scanning finished")

		for name, project in projects.items():
			if not project.is_sub_project() and not project.is_core_project():
				project.report(options)

	except Exception, errtxt:
		import traceback
		print(traceback.format_exc())

		print errtxt



if __name__ == "__main__":

	main(sys.argv[1:])
