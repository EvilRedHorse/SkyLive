import argparse
import config
import logging
import os
import cv2
import requests
import shutil
from pubaccess import Pubaccess
import subprocess
from tabulate import tabulate
from threading import Thread
import time


def runBash(command):
	os.system(command)

def touchDir(dir, strict = False):
	if (strict == True and os.path.isdir(dir)):
		raise Exception('Folder already exists: ' + dir)
	if not os.path.isdir(dir):
		os.mkdir(dir)

def folderIsEmpty(folder):
	if not os.path.isdir(folder):
		return True
	if os.listdir(folder):
		return False
	else:    
		return True

def rmdir(dir):
	if os.path.isdir(dir):
		shutil.rmtree(dir)

def pubaccess_push(filePath, portal):
	logging.debug('Uploading ' + str(filePath) + ' with ' + str(portal))

	opts = type('obj', (object,), {
		'portal_url': portal,
		'timeout': 60
	})

	try:
		try:
			return Pubaccess.upload_file(filePath, opts)            
		except TimeoutError:
			logging.error('Uploading timeout with ' + str(portal))
			return False
	except:
		logging.error('Uploading failed with ' + str(portal))
		return False

def upload(filePath, fileId, length):
	global concurrent_uploads, filearr
	start_time = time.time()
	concurrent_uploads += 1
	filearr[fileId].status = 'uploading'

	# upload file until success
	while True:
		# upload and retry if fails with backup portals
		for upload_portal in config.upload_portals:
			publink = pubaccess_push(filePath, upload_portal)
			if publink != False:
				break
			else:
				filearr[fileId].status = 'uploading with backup portal'

		if (publink != False and len(publink) == 52):
			publink = publink.replace("scp://", "")
			filearr[fileId].publink = publink
			if filearr[fileId].status != 'share failed':
				filearr[fileId].status = 'share queued'
			filearr[fileId].uploadTime = round(time.time() - start_time)
			concurrent_uploads -= 1
			return True
		else:
			logging.error('Upload failed with all portals for ' + str(filePath))
			filearr[fileId].status = 'queued for re-uploading'
			time.sleep(10)
			filearr[fileId].status = 're-uploading'


def get_length(filename):
	cap = cv2.VideoCapture(filename)
	fps = cap.get(cv2.CAP_PROP_FPS)      # OpenCV2 version 2 used "CV_CAP_PROP_FPS"
	frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
	duration = frame_count/fps
	return duration

def chech_m3u8(recordFolder):
	for file in os.listdir(recordFolder):
		if file.endswith(".m3u8"):
			return True
	return False

def chech_ts(recordFolder):
	for file in os.listdir(recordFolder):
		if file.endswith(".ts"):
			return True
	return False

def isPlaylistFinished(recordFolder):
	playlistFile = os.path.join(recordFolder, "live.m3u8")
	with open(playlistFile, 'r') as f:
		lines = f.read().splitlines()
		last_line = lines[-1]
		if last_line == '#EXT-X-ENDLIST':
			return True
		else:
			return False

def updateDisplay(filearr, symbols):
	print('\n\n\n\n\n\n\n\n\n')
	print('Status symbols:\n')
	symbarray = []
	idx = 0
	
	for key, value in symbols.items():
		symbarray.append([value, key])
		idx += 1
	table = (tabulate(symbarray, headers=['symbol', 'status'], tablefmt='orgtbl'))
	print(table + '\n\n\n')

	file = ['File']
	status = ['Status']
	length = ['Length']
	uptime = ['Upload time']
	terminalColumns, terminalRows = shutil.get_terminal_size()
	showRows = int(terminalColumns/7) - 3
	ran = len(filearr) if (len(filearr) < showRows) else showRows
	for i in range(ran):
		ind = -ran+i
		symbolCode = filearr[ind].status
		file.append(filearr[ind].fileId)
		status.append(symbols[symbolCode])
		videoLength = round(filearr[ind].length)
		if (videoLength == -1):
			length.append('')
		else:
			length.append(str(videoLength) + 's')
		uploadTime = filearr[ind].uploadTime
		if (uploadTime == -1):
			uptime.append('')
		else:
			uptime.append(str(uploadTime) + 's')

	table = (tabulate([file, status, length, uptime], tablefmt='orgtbl'))
	print(table)

def share(fileId, filearr):
	global m3u8_list_upload_token, is_first_chunk
	filearr[fileId].status = 'sharing'
	post = {
		'token': m3u8_list_upload_token,
		'url': filearr[fileId].publink,
		'length': filearr[fileId].length,
		'is_first_chunk': is_first_chunk
		}
	try:
		x = requests.post(config.m3u8_list_upload_path, data = post)
		if (x.text != 'ok'):
			logging.error('Error: posting failed ' + str(x.text))
			filearr[fileId].status = 'share failed'
			return False
		else:
			filearr[fileId].status = 'shared'
			is_first_chunk = 0
			return True
	except Exception as e:
		logging.error('Error: posting failed ' + str(e))
		filearr[fileId].status = 'share failed'
		return False


def share_thread():
	global filearr
	lastSharedFileId = -1
	# check_share_queue(check_share_queue, filearr)
	while True:
		nextToShare = lastSharedFileId + 1
		if filearr[nextToShare].status == 'share queued' or filearr[nextToShare].status == 'share failed':
			if share(nextToShare, filearr) == True:
				lastSharedFileId += 1
			else:
				time.sleep(10)
		time.sleep(0.2)


class VideoFile:
	def __init__(self, fileId):
		self.fileId = fileId
		self.status = 'waiting for file'
		self.uploadTime = -1
		self.length = -1
		self.publink = 'publink'
	def __str__(self):
		return str(self.__dict__)

nextStreamFilename = 0
filearr = [
	# file, status, upload time, length, publink
	VideoFile(nextStreamFilename)
]

def worker():
	global concurrent_uploads, projectPath, recordFolder, filearr, nextStreamFilename

	symbols = {
		'waiting for file':				' ',
		'upload queued':				'.',
		'uploading':					'↑',
		'uploading with backup portal':	'↕',
		'queued for re-uploading':		'↔',
		're-uploading':					'↨',
		'share queued':					'▒',
		'sharing':						'▓',
		'shared':						'█',
		'share failed':					'x'
	}
	touchDir(recordFolder)

	cntr = 0
	while True:
		if not chech_m3u8(recordFolder):
			if args.record_folder:
				record_folder_name = args.record_folder
			else:
				record_folder_name = 'record_here'
			if not (chech_ts(recordFolder)):
				print('Waiting for recording, no .m3u8 or .ts file found in ' + record_folder_name + ' folder (%ds)' %(cntr))
			else:
				print('Starting uploading... Waiting for first chunk and for .m3u8 file in ' + record_folder_name + ' folder (%ds)' %(cntr))
			cntr += 1
			time.sleep(1)
		else:
			break


	Thread(target=share_thread).start()
	while True:
		nextFile = os.path.join(recordFolder, "live" + str(nextStreamFilename) + ".ts")
		nextAfterFile = os.path.join(recordFolder, "live" + str(nextStreamFilename + 1) + ".ts")
		updateDisplay(filearr, symbols)
		if concurrent_uploads < 10 and ( os.path.isfile(nextAfterFile) or ( isPlaylistFinished(recordFolder) and os.path.isfile(nextFile) ) ):
			filearr.append(VideoFile(nextStreamFilename + 1))
			filearr[nextStreamFilename].status = 'upload queued'
			nextLen = get_length(nextFile)
			filearr[nextStreamFilename].length = nextLen
			Thread(target=upload, args=(nextFile, nextStreamFilename, nextLen)).start()
			nextStreamFilename += 1
		else:
			time.sleep(1)
	

concurrent_uploads = 0
projectPath = os.path.dirname(os.path.abspath(__file__))
is_first_chunk = 1

logFile = os.path.join(projectPath, "error.log")
logging.basicConfig(filename=logFile,
	filemode='a',
	format='%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s',
	datefmt='%H:%M:%S',
	level=logging.DEBUG)
logging.info('LOGGING STARTED')

parser = argparse.ArgumentParser('Upload HLS (m3u8) live stream to Public Portals')
parser.add_argument('--record_folder', help='Record folder, where m3u8 and ts files are (will be) located (default: record_here)')
parser.add_argument('--token', help='Stream token generated by scp.techandsupply.ca')
args = parser.parse_args()


# get recordFolder
if (args.record_folder):
	if (os.path.isabs(args.record_folder)):
		recordFolder = args.record_folder
	else:
		recordFolder = os.path.join(projectPath, args.record_folder)
else:
	recordFolder = os.path.join(projectPath, "record_here")

if not folderIsEmpty(recordFolder):
	print('Record folder is not empty: ' + recordFolder)
	input('Are you sure, you want to continue? Press Enter to continue...')

if (args.token):
	m3u8_list_upload_token = args.token
else:
	while True:
		m3u8_list_upload_token = input("Enter stream token: ")
		if (m3u8_list_upload_token):
			break
	
worker()
