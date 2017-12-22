# Microsoft Comic Chat Helper for ZNC V0.02Z
#
# README:
# This script allows Microsoft Comic Chat 2.5 (4.71.2302) to be used with
# bnchub and Freenode.
#
# Freenode does not use some formatting that MSCC depends on for operation. As
# a result, MSCC will crash upon joining Freenode channels. This script
# provides a fix by creating a ``server socket'' on loclhost. Once MSCC
# connects to it, the script establishes a connection with Freenode. It begins
# forwarding MSCC's input to Freenode and sanitizing Freenode's responses
# before sending them back to MSCC.
#
# USAGE:
# Run this script, enter Freenode username and password, leave it running in background.
# Connect MSCC to the address '127.0.0.1:6660' or whatever options are set.
# If you are a terrible person, hard-code Freenode username and password into this script.
#
# CHANGES:
# 7/1/2014 - V0.01  - Initial Release. Raleigh NC to Little Rock AK
# 7/2/2014 - V0.02  - Disabled removing channel mode list (not necessary)
#				    - Added SSL support
#				    - Made passwords secure
#				    - Little Rock AK to the middle of nowhere in Oklahoma
#			 V0.02a - Made use numeral cues (as opposed to language cues) for control
#				    - Added some more exception handling
# 7/3/2014 - V0.02b - Fixed greedy sanitation bug (deleting too many chars)
#					- Made empty recv()s throw ConnectionAbortedError
#					- Restructured exception handling
#					- Fixed abort on MSCC disconnect or connection lost
# 9/3/2014 - V0.02Z - First release for ZNC. 
# KNOWN ISSUES:
# - Can't send messages containing ` JOIN #'
# - Blocking operations (connect, waitign for client connect) cause hang that can't be aborted with ^C ^X ^Z.
# - After a connection dies, sockets stay alive for a long time. Can only be 
#   'solved' by: 1) Lowering socket TCP timeout (non-fix) 
#                2) Checking for TCP pings/aknowlegements (nasty)
#                3) Sending IRC pings in paralell (ineffective)
# - Can't run headless with logging.
#------------------------------------------------------------------------------
# (c) 2014 Christian Chapman under the 1988 MIT license

import sys;
import string;
import base64;
import getpass;
import errno;

import socket;
import ssl;
import select;

# Options for IRC Server
host = 'alpha.bnchub.net';
port = 1935;

# If you choose to hardcode remember to comment out 'getCreds()' line.
#str_username = '';
#str_authident = str_username;

# Options for MSCC connection
str_localAddr = '127.0.0.1';
n_localPort = 6660;

str_msccBuf = '';
str_ircBuf = '';

# Sanitizes raw Freenode message so that it won't crash MSCC. Currently
# performs 4 manipulations, all related to joining channels:
# 1) Add `:' to initial `JOIN' message.
# 2) (DISABLED) Remove channel MODE message.
# 3) Change channel user list delimiter from `@' to `='.
# 4) Prefix channel user list with a `:'.
#
# Inputs:
# str_in: UTF-8 string of raw messages from Freenode terminated by '\r\n.'
# str_usr: String containing username
# Returns: Sanitized messages in the same format.
def sanitizeMscc(str_in, str_usr):
	# Add `:' to initial `JOIN' message.
	str_san = str_in.replace('JOIN #','JOIN :#');

	# Remove channel MODE message.
	#if ' MODE #' in str_san:
	#	idx = str_san.find(' MODE #');
	#	# We expect all input to be terminated.
	#	en  = str_san.find('\r\n', idx);
	#	st  = str_san.rfind('\r\n', idx);
	#	if st < 0:
	#		str_san = str_san[en + 4:]; # It's at the very beginning
	#	else:
	#		str_san = str_san[0:st + 4] + str_san[en + 4:];

	# Change channel user list delimiter from `@' to `='.
	# Prefix channel user list with a `:'.
	idx = str_san.find('353' + str_usr + ' @ #');
	while idx > 0:
		idx = str_san.find(' @ #', idx);
		str_end = str_san[idx + 2:];
		li = str_end.split(None, 1);
		str_san = str_san[0:idx] + ' = #' + li[0] + ' :' + li[1];
		idx = str_san.find('353' + str_usr + ' @ #');

	# Removes garbage response about MSCC's `ISIRCX' query
	idx = str_san.find('ISIRCX :No such channel');
	while idx > 0:
		# We expect all input to be terminated.
		en  = str_san.find('\r\n', idx);
		st  = str_san.rfind('\r\n', 0, idx);
		if st < 0:
			str_san = str_san[en + 2:]; # It's at the very beginning
		else:
			str_san = str_san[0:st + 2] + str_san[en + 2:];
		idx = str_san.find('ISIRCX :No such channel');

	return str_san;
	
# Get info
def getCreds():
	str_usr = input('Username: ');
	#str_auth = str_usr;
	str_auth = input('Auth: ');
	return (str_usr, str_auth);

(str_username, str_authident) = getCreds();
	
# Outer loop makes sockets. If some connection is lost, it will restart to here.
while(True):
	try:
		# Create a server for MSCC to connect.
		try:
			skt_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM);
			skt_server.bind((str_localAddr, n_localPort));
			skt_server.listen(5);
		except socket.error as msg:
			print('Failed to create socket. Error code: ' + str(msg[0]) + \
				  ' , Error message : ' + msg[1]);
			sys.exit();
		print('Created server socket. Waiting for MSCC to connect...');

		# Get MSCC's connection to skt_server.
		(skt_mscc, addr_mscc) = skt_server.accept();
		print('Client Connected.');

		# Connect to IRC.
		skt_irc = socket.socket(socket.AF_INET, socket.SOCK_STREAM);
		#skt_irc = ssl.wrap_socket(skt_irc);
		try:
			print('Resolving host...');
			remote_ip = socket.gethostbyname( host );
		except socket.gaierror:
			# Could not resolve.
			print('Hostname could not be resolved. Exiting.');
			sys.exit();

		# Connect, wait until socket is connected.
		print('Connecting to IRC...');
		skt_irc.connect((remote_ip , port));
		
		print('Connected to ' + host + ' on ip ' + remote_ip);
		
		skt_irc.setblocking(False);
		
		# Request SASL.
		# Send client info
		print('NICK ' + str_username + '\r\n');
		print('PASS ' + str_authident + '\r\n');
						   
		skt_irc.sendall(bytes('NICK ' + str_username + '\r\n','utf-8'));
		skt_irc.sendall(bytes('PASS ' + str_authident + '\r\n','utf-8'));
						   
		print('Sent client info.');
			
		# Recall that we earlier initialized our buffer with Freenode's initial messages.
		# (Freenode will (mostly) ignore MSCC's attempt to reauth)
		# In case we stopped in the middle of a message, add a delimiter.
		str_ircBuf = str_ircBuf + '\r\n';
		
		# main loop
		# Forward IRC socket received data to MSCC & vice-versa.
		while(True):
			(li_rready, _, _) = select.select([skt_mscc, skt_irc],[],[]);
			try:
				# Forward MSCC to Freenode
				if skt_mscc in li_rready:
					b_msccBuf = skt_mscc.recv(4096);
					if(len(b_msccBuf)==0):
						raise ConnectionAbortedError('No more data in socket.');
					skt_irc.sendall(b_msccBuf);
					print( ' > ' + b_msccBuf.decode(sys.stdout.encoding, errors='replace'));
					b_msccBuf = b'';

					# Forward IRC to MSCC
				if skt_irc in li_rready:
					b = skt_irc.recv(4096);
					if(len(b)==0):
						raise ConnectionAbortedError('No more data in socket.');
					str_ircBuf = str_ircBuf + b.decode('utf-8', errors='replace');
					
					# Sometimes the buffer will chop a message in the middle.
					if '\r\n' in str_ircBuf:
						li = str_ircBuf.rsplit('\r\n', 1);
						str_ircBuf = li[0];
						str_ircBuf = str_ircBuf + '\r\n';
						str_ircBufCutOff = li[1];
					# If there's no carriage return in the buffer, it's a really long message. We need to finish loading at least all of one message into str_ircBuf, so go back to beginning.
					else:
						continue;

					# Sanitize the buffer for MSCC and send
					str_ircBuf = sanitizeMscc(str_ircBuf, str_username);
					skt_mscc.sendall(str_ircBuf.encode('utf-8', errors='replace'));
					print(bytes(str_ircBuf,'utf-8').decode(sys.stdout.encoding, errors='replace'));

					# Include the beginning of the cut off message to be sent next time.
					str_ircBuf = str_ircBufCutOff;
					str_ircBufCutOff = '';
			except (ssl.SSLWantReadError, ssl.SSLWantWriteError) as e:
				# Not enough TLS packets have come in for us to read any SSL data.
				continue;
			except (ConnectionAbortedError, ConnectionResetError):
				raise;
			except socket.error as e:
				error = e.args[0];
				if e != errno.EAGAIN and e != errno.EWOULDBLOCK:
					raise e;
				else:
					# No data to read.
					continue;
			except (ssl.SSLWantReadError, ssl.SSLWantWriteError) as e:
				# Not enough TLS packets have come in for us to read any SSL data.
				continue;
		
	except (ConnectionAbortedError, ConnectionResetError) as e:
		skt_mscc.close();
		skt_irc.close();
		error = e.args[0];
		print(error);
		print('Connection aborted.');
		continue;
	except socket.error as e:
		error = e.args[0];
		if error != errno.EAGAIN and error != errno.EWOULDBLOCK:
			# a "real" error occurred
			print('Socket error: ');
			print(error);
			print(type(e));
			raise ;
		else:
			# No data to read.
			pass;
