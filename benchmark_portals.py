import time
from pubaccess import Pubaccess
import os

def time_to_str(value):
	if value == 20:
		time = 'timeout'
	elif value == 999:
		time = 'error'
	else:
		time = value
	return time

print('Starting benchmark')

f = open("2MBfile.txt", "w+")
text = ''
# generate 2MB text
for i in range(262144):
	text += 'PubLive '
f.write(text)
f.close()

portals = [
	'https://scp.techandsupply.ca',
	'https://scprime.hashpool.eu',
]
results = []

for portal in portals:
	start_time = time.time()
	opts = type('obj', (object,), {
		'portal_url': portal,
		'timeout': 20
	})
	try:
		try:
			skylink = Skynet.upload_file('2MBfile.txt', opts)
			uploadtime = round(time.time() - start_time, 2)
			current_result = [uploadtime, portal]      
		except TimeoutError as e:
			current_result = [opts.timeout, portal]
		
	except Exception as e:
		current_result = [999, portal]
	results.append(current_result)
	print('Benchmarking', str(len(results)) + '/' + str(len(portals)), 'portal. Current:', time_to_str(current_result[0]), current_result[1])

print('\nRESULTS:\n')
results.sort(key=lambda x: x[0])
for elem in results:
	time = time_to_str(elem[0])
	print(time, elem[1])

os.remove("2MBfile.txt")
