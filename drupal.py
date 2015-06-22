
import tempfile
import filecmp
import re
import os
import glob
import subprocess
import shutil
import urllib
import urllib2
import tarfile
import zipfile

from threading import Semaphore

# Version and branch regexps for .info files
pname = re.compile(r"name\s*=\s*\"?([a-z0-9_\ ]+)\"?", re.DOTALL|re.IGNORECASE)
pproject = re.compile(r"project\s*=\s*\"?([a-z0-9_\ ]+)\"?", re.DOTALL|re.IGNORECASE)
ppackage = re.compile(r"package\s*=\s*\"?([a-z0-9_\ ]+)\"?", re.DOTALL|re.IGNORECASE)
pbranch = re.compile(r"[0-9]+\.x-[0-9]\.", re.DOTALL|re.IGNORECASE)
pversion = re.compile(r"[0-9]+\.x-[0-9]\.[0-9x]+-?[a-z0-9]*", re.DOTALL|re.IGNORECASE)
mmakepatch = re.compile(r"- (http.*)", re.DOTALL|re.IGNORECASE)
cphpcserrors = re.compile(r"FOUND ([0-9]+) ERRORS", re.DOTALL|re.IGNORECASE)
cphpcswarnings = re.compile(r"FOUND.*([0-9]+) WARNINGS", re.DOTALL|re.IGNORECASE)

options_detailed = 0x01
options_submodules = 0x10


sem_cwd = Semaphore(1)

def git(*args):
	FNULL = open(os.devnull, 'w')
	return subprocess.call(['git'] + list(args), stdout=FNULL, stderr=FNULL)

class ProjectJailer:

	# Constructor
	def __init__(self, project):
		self.project = project
		self.temp_directory = False
		self.project_directory = False

	# Destructor
	def __del__(self):
		# Delete directory if such exists
		if self.temp_directory:
			shutil.rmtree(self.temp_directory)

	# Fetch the code for the given project
	# Returns directory where the project resides.
	def fetch(self):

		try:
			self.temp_directory = tempfile.mkdtemp('ds') + "/"
			url = "http://ftp.drupal.org/files/projects/%s-%s.tar.gz" % (self.project.machine_name, self.project.version)
			file = "%sproject.tar.gz" % (self.temp_directory)
			urllib.urlretrieve(url, file)
			tfile = tarfile.open(file, 'r:gz')
			tfile.extractall(self.temp_directory)
			os.remove(file)
			self.project_directory = "%s%s/" % (self.temp_directory, self.project.machine_name)
			return self.project_directory

		except:
			return False

		# if git("clone", "http://git.drupal.org/project/%s.git" % (self.machine_name), "--branch", self.branch, directory) == 0:
		# 	git("--git-dir", directory + ".git", "--work-tree", directory, "checkout", self.version)
		# 	return True
		# else:
		# 	return False


class Project:

	def __init__(self, file):

		self.machine_name = os.path.splitext(os.path.basename(file))[0]
		self.dir = os.path.dirname(file)
		self.info_file = file
		self.machine_name = "unknown"
		self.name = "unknown"
		self.project = "unknown"
		self.package = "unknown"
		self.version = "unknown"
		self.branch = "unknown"
		self.status = "unknown"
		self.patches = []
		self.sub_projects = {}
		self.diff_files = []
		self.custom_report = None
		self.extract_information_from_info_file()

	def extract_information_from_info_file(self):

		f = open(self.info_file, 'r')
		info = f.read()

		self.machine_name = os.path.splitext(os.path.basename(self.info_file))[0]

		temp_name = pname.findall(info)
		temp_project = pproject.findall(info)
		temp_package = ppackage.findall(info)
		temp_version = pversion.findall(info)
		temp_branch = pbranch.findall(info)

		if temp_name and len(temp_name[-1]) > 0:
			self.name = temp_name[-1]

		if temp_project and len(temp_project[-1]) > 0:
			self.project = temp_project[-1]

		if temp_package and len(temp_package) > 0:
			self.package = temp_package[-1]

		if temp_branch and len(temp_branch) > 0:
			self.branch = temp_branch[-1] + "x"

		if temp_version and len(temp_version) > 0:
			self.version = temp_version[-1]

	def add_sub_project(self, project):

		#print "added %s to %s" % (project.machine_name, self.machine_name)
		self.sub_projects[project.machine_name] = project

	def parse_diffs(self, dcmp):

		for name in dcmp.diff_files:
			self.diff_files.append(("%s%s" % (dcmp.right, name)).replace(self.dir, ""))
		for sub_dcmp in dcmp.subdirs.values():
			self.parse_diffs(sub_dcmp)


	def is_core_project(self):

		return self.project == "drupal"

	def report(self, options = 0, depth = 0):

		if depth > 0:
			print "%s- %s" % (" " * depth, self.machine_name)

		else:
			if options & options_detailed:
				print "%s (%s): %s %s: %s" % (self.name, self.machine_name, self.version, self.branch, self.status)
				if len(self.patches) > 0:
					for file in self.patches:
						print "%s + %s" % (" " * depth, file)
				if self.status == "HACKED":
					for file in self.diff_files:
						print "%s * %s" % (" " * depth, file)
			else:
				if self.status == "HACKED":
					print "%s (%s) %s: %s (%s patches, %s bad files)" % (self.name, self.machine_name, self.version, self.status, len(self.patches), len(self.diff_files))
				else:
					if len(self.patches) > 0:
						print "%s (%s) %s: %s with %s patch(es)" % (self.name, self.machine_name, self.version, self.status, len(self.patches))
					else:
						print "%s (%s) %s: %s" % (self.name, self.machine_name, self.version, self.status)

			if self.custom_report:
				for key, value in self.custom_report.items():
					print "%s %s: %s" % (" " * depth, key, value)

		if options & options_submodules:
			for name, project in self.sub_projects.items():
				project.report(options, depth + 2)

	def is_sub_project(self):

		return self.machine_name != self.project


	def is_dorg_project(self):
		try:
			url = 'https://www.drupal.org/project/' + self.machine_name
			response = urllib2.urlopen(url)
			# Non existing projects get redirected to the page d.o/403 :(
			if url == response.geturl():
				# This project is in d.o
				return True
			return False
		except:
			return False


	# Apply given patch file
	def apply_patch(self, patch_file):
		FNULL = open(os.devnull, 'w')
		pipe = open(patch_file, 'r')
		p = subprocess.Popen(['patch', '-p1', '-s', '-t'], stdin=pipe)
		p.wait()

	def collect_patches(self):
		# Collect patches inside the project dir
		# TODO: Collect patches from PATCHES.txt (drush make)
		make_patch_file = self.dir + '/PATCHES.txt'

		patches = []

		if os.path.isfile(make_patch_file):

			with open(make_patch_file, 'r') as mf:
				for line in mf:
					patch_file = mmakepatch.findall(line)
					if patch_file and len(patch_file[-1]) > 0:

						response = urllib2.urlopen(patch_file[0])

						fd, filepath = tempfile.mkstemp()
						with os.fdopen(fd, 'w') as tf:
							tf.write(response.read())

						patches.append(filepath)

		for root, dirs, files in os.walk(self.dir):
			for file in files:
				if file.endswith(".patch"):
					patches.append(os.path.abspath(os.path.join(root, file)))
		return patches

	# Create a diff for this project
	def diff(self):

		if (self.branch == "" or self.version == ""):
			self.status = "UNKNOWN"
			return

		if not self.is_dorg_project():

			p = subprocess.Popen(['phpcs', '--standard=~/.drush/coder/coder_sniffer/Drupal', self.dir], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
			out, err = p.communicate()
			errors = cphpcserrors.findall(out)
			warnings = cphpcswarnings.findall(out)
			self.custom_report = {
				'phpcs errors': sum(map(int, errors)),
				'phpcs warnings': sum(map(int, warnings))
			}
			self.status = "CUSTOM"
			return

		if "dev" in self.version:
			self.status = "DEV"
			return

		jailer = ProjectJailer(self)
		project_dir = jailer.fetch()

		# Checkout the project
		if project_dir:

			# Fetch patches
			self.patches = self.collect_patches()

			# Get absolute path for the project directory
			abs_self_dir = os.path.abspath(self.dir)

			# os.chdir etc are not thread safe - so we'll use a semamphore for this section
			sem_cwd.acquire()
			cwd = os.getcwd()

			try:

				os.chdir(project_dir)
				for patch_file in self.patches:
					self.apply_patch(patch_file)
				os.chdir(abs_self_dir)
				ignore = glob.glob("*.info") + glob.glob("*.patch") + ['translations', 'LICENSE.txt', '.git']

			except:

				os.chdir(cwd)
				sem_cwd.release()
				self.status = "(internal error)"

				return

			os.chdir(cwd)

			# Compare directories
			result = filecmp.dircmp(project_dir, self.dir + "/", ignore)
			self.parse_diffs(result)

			sem_cwd.release()

			# Determine result
			if len(self.diff_files) > 0:
				self.status = "HACKED"
			else:
				self.status = "OK"

		else:
			print "Unable to fetch %s %s" % (self.machine_name, self.branch)
			self.status = "ERROR"




