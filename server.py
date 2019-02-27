#! python3
import socket 
import struct
import sys
import time
import signal 
import threading
import os
from queue import Queue

NUMBER_OF_THREADS = 2
JOB_NUMBER = [1, 2]
queue = Queue()

COMMANDS = {'help' :['Description of all commands'], #Will not be necessary when a GUI is made, but nice to have before when testing. 
			'select' :['Select a client by its index, takes index as param'],
			}
			
			
#TODO: Make a list for pinging each raspi unit to see if they're working
#Maybe when installing the program on a machine(server) install an folder with an enviroment variable(containing the number of clients), picture folder and maybe more useful stuff??
#When server disconnects TCP connection is broken (endpoint error) client throws error, but how should I reset the client TCP socket for reconnection? 
#Maybe have the server checking periodically for new clients? This way you don't have to multicast each time you want to connect a new client
#
#When the server quits and reconnects the clients don't respond properly e.g. don't connect when I connect server again '
#Handle exception transport endpoint is not connected in reset_tcp_socket and receive_commands methods
#If a client doesn't take a picture, retry a couple of times before reporting an error
#Don't think the clients are responding porperly when server disconnects
#If a client stops responding/bugs out/resets, need to update the client lists
#Add method for retrieving pictures from specific clients
#If you retrieve a picture twice either send it to the same folder, or give an option to make a new folder.
#If there is an error trying to retrieve a picture, don't make a new empty folder.    
#For updating the clients maybe start another script that updates the program when resetting
class Server(object):
	
	def __init__(self):
		self.mcast_port = 5000 #Port number that will be used for multicast communication. Maybe add a method for changing port?
		self.tcp_port = 6000 #Port number that will be used for tcp communication. Maybe add a method for changing port?
		self.mcast_grp = ('224.1.1.1', self.mcast_port) #First parameter is a ip address specifically reserved for multicast traffic. Second parameter is the port which will be used for broadcasting multicast messages. 
		self.tcp_grp = (self.get_address(), self.tcp_port)#First parameter is a method which finds the IP address of the server device running the program. 
		self.MCAST_sock = None #Multicast socket needed for communicating with several (RaspPI) devices at the same time. Taking pictures, changing server device connected to all raspPIs etc..
		self.TCP_sock = None #TCP socket needed for communication through TCP. Used for sending pictures from raspPIs to server, identifying each raspPI unit, sending messages to individual PI unites. 
		self.all_connections = [] #Store all socket objects in a list (Socket connection with each PI used for communication)
		self.all_addresses = [] #Store all the addresses of the PIs connected
		self.all_pis = [] #Store the personal ID of each pi and order them ascending
		self.pictureName = None #Name for the folder with most recent set of pictures
		self.pictureData = None #Variable to temporarily hold the picture data, set to None after finished using
		self.picturePath = 'C:/Python27/pythonpractice/pictures/' #TODO: maybe add a method for changing this location
		#self.clientPath = 'C:/Python27/pythonpractice/client/' #TODO: find a way to update the PIs with new software and restart them
		self.numberOfClients = None #feature for scaling. TODO: incorporate this feature, and make sure that at the same time all methods "scale" to it. 
		
	"""Close the connections and shut down the program"""
	def quit_program(self, signal=None, frame=None):
		print('\nQuitting the program')
		#self.mcast_message('reset')
		for i, conn in enumerate(self.all_connections):
			try:
				conn.shutdown(2)
				conn.close()
			except Exception as e:
				print('Could not close connection to PI #' + self.all_pis[i] + ': %S' % str(e)) #Figure out a way to get unique ID of each raspPI
				continue
		self_all_pis = []
		self.all_addresses = [] 
		self.TCP_sock.close()
		sys.exit(0) 
		
	"""Signal handler"""#Find out how this works
	def register_signal_handler(self):
		signal.signal(signal.SIGINT, self.quit_program)
		signal.signal(signal.SIGTERM, self.quit_program)
		return 
		
	"""Print all the help alternatives"""
	def print_help(self):
		for cmd, v in COMMANDS.items():
			print ("{0}:\t{1}".format(cmd, v[0]))
		return
		
	"""Create a socket and set it up for multicasting"""
	def create_mcast_socket(self):
		try:
			self.MCAST_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
			self.MCAST_sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 32)
		except socket.error as e:
			print ("Socket creation error: " + str(e))
			return
		return
		
	"""Send a multicast message""" #Find a way to check if the message is valid, if not give error message
	def mcast_message(self, message):
		#print(message)
		if(message == 'address'):
			self.reset_addresses() 
			message += ' ' + str(self.get_address())
		elif(message == 'picture'):
			description = input('Description> ')
			message += ' ' + description
			self.pictureName = description
		SCMD = message.encode()
		self.MCAST_sock.sendto(SCMD, self.mcast_grp)
	
	"""Create a socket for TCP connection"""
	def create_tcp_socket(self):
		try:
			self.TCP_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		except socket.error as e:
			print ('Error trying to create socket: ' + str(e))
			return
		return
	
	"""Bind tcp socket to a port and wait for connections"""
	def bind_tcp_socket(self):
		try:
			self.TCP_sock.bind(self.tcp_grp)
			self.TCP_sock.listen(5)
		except socket.error as e: 
			print ('Socket binding error: ' + str(e))
			time.sleep(5)
			self.bind_tcp_socket()
		return
		
	"""Close the TCP connection"""
	def close_tcp_socket(self):
		try:
			self.TCP_sock.shutdown(2)
			self.TCP_sock.close()
			self.TCP_sock = None
		except Exception as e:
			pass #How does pass work in this context? 
		return

	""" Accept connections from multiple clients and save to list """
	def accept_connections(self): #maybe make two methods, one try statement that handles incoming connections and one try statement that tries to add conn, addr and id to lists. If a connection is already in a list, don't add it. 
		for c in self.all_connections:
			c.close()
		self.all_connections = []
		self.all_addresses = []
		self.all_pis = []
	
		while True:
			try:
				conn, address = self.TCP_sock.accept()
				conn.setblocking(1)
				client_hostname = conn.recv(1024).decode("utf-8") #Receive the client hostname + client ID e.g. 169.254.125.215 + 1
				txt = str(client_hostname).split()
				address = address + (txt[0],) #First address is the address bound to the socket on the other end of the connection. Second address is address of the client. 
				raspID = int(txt[1]) 
				
			except Exception as e:
				print('Error accepting connections: %s' % str(e))
				continue
				# Loop indefinitely
			
			self.order_lists(raspID, address, conn)
			print('\nConnection has been established: {0} ({1})'.format(address[-1], address[0]))
		return
		
	#Not very elegant looking method at all! 	
	"""Order all lists in ascending order according to their raspberry ID"""
	def order_lists(self, raspID, address, conn):
		try:
			if not self.all_pis:
				self.all_pis.append(raspID)
				self.all_addresses.append(address)
				self.all_connections.append(conn)
			elif raspID < self.all_pis[0]:
				self.all_pis.insert(0, raspID)
				self.all_addresses.insert(0, address)
				self.all_connections.insert(0, conn)			
			elif raspID > self.all_pis[-1]:
				self.all_pis.append(raspID)
				self.all_addresses.append(address)
				self.all_connections.append(conn)
			else:
				for i, value in enumerate(self.all_pis):
					if raspID > value and raspID < self.all_pis[i+1]: #this doesn't find the next elements, just adds 1 to it. client IDs start at 1--->, lists include 0. e.g. if list = [1,3] and you want to add 2 to the list you have to .insert(i, 2) i = 1 on first iteration
						self.all_pis.insert(i+1, raspID) #what if self.all_pis[i] doesn't exist? 
						self.all_addresses.insert(i+1, address)
						self.all_connections.insert(i+1, conn)
					elif raspID == i:
						pass
		except Exception as e:
			print('Error adding pi #' + str(raspID) + 'to list')
				
	"""List all the pis currently connected"""
	def list_connections(self):
		results = ''
		for i, conn in enumerate(self.all_connections):
			try:
				conn.sendall(b'list')
				answer = conn.recv(20480).decode() #When client has disconnected, still receive answer? Client still in the list...
				print(answer)
				if(answer != 'connected'):
					print(answer)
					raise ValueError('Invalid answer from raspPI')
			except:
				del self.all_pis[i]
				del self.all_addresses[i] 
				del self.all_connections[i]
				continue
			results += str(i+1) + '   ' + str(self.all_addresses[i][0]) + '   ' + str(self.all_addresses[i][1]) + '   ' + str(self.all_addresses[i][2]) + '\n'
		
		if not results:
			print("No connections")
		else:
			print ('-----Clients-----' + '\n' + results)
		return	
	
	"""Get a target by its ID e.g. raspiPI #1, #2, #3 etc.."""#When making a GUI, display all available clients by their ID
	def get_target(self, cmd):
		target = cmd.split(' ')[-1]
		try:
			target = int(target)
		except ValueError:
			print('Client index should be an integer')
			return None, None
		try:
			conn = self.all_connections[target]
		except IndexError:
			print('Not a valid selection')
			return None, None
		print("You are now connected to PI #" + str(self.all_pis[target]) + ', PI address: ' + str(self.all_addresses[target][2])) #Find out what elements are in the address list
		return target, conn
			
	"""Connect with a remote target client(raspPI)"""
	def send_target_commands(self, target, conn): #Suggestion for commands: reset PI, get pi address, get piID, stream camera, 
		while True:
			try:
				cmd = input('Command> ')
				if cmd == 'id':
				# if len(str.encode(cmd)) > 0:
					conn.send(str.encode(cmd))
					client_response = conn.recv(80).decode()
					print(client_response)
					# cmd_output = self.read_command_output(conn)
					# client_response = str(cmd_output, "utf-8")
					# print(client_response, end="")
				elif cmd == 'get':
					conn.send(str.encode(cmd))
				elif cmd == 'shutdown':
					conn.send(str.encode(cmd))
				elif cmd == 'reboot':
					conn.send(str.encode(cmd))
				elif cmd == 'quit':
					break
				else: 
					print("Command not recognized")
			except Exception as e:
				print("Connection was lost %s" %str(e))
				break
        # del self.all_connections[target]
        # del self.all_addresses[target]
		return
		
	"""Get the LAN address of the device running the program"""
	def get_address(self): 
		IP = socket.gethostbyname(socket.gethostname())
		return IP #Not sure if this returns the IP address of the device, or the ip address given to the device by the router? 
	
	"""Reset all the raspPI addresses"""
	def reset_addresses(self):
		# self.mcast_message('reset')
		for c in self.all_connections:
			try:
				c.shutdown(2)
				c.close()
			except Exception as e:
				print('Connection has not yet been established' + str(e))
		self.all_pis = []
		self.all_connections = []
		self.all_addresses = []
		
	"""For receiving pictures the recvall method is not suited, large amounts of data is most effectively received in small packets"""
	"""Send a request to each connection asking for the most recent picture taken. Then store the picture in a new folder at a given directory"""
	def get_pictures(self): #Try to add a progress bar for the transfer of pictures
		try:
			self.create_folder()
		except Exception as e:
			print('No pictures taken so far')
			return #Add a way to get the most recent pictures taken 
		for conn in self.all_connections: #Try to get the pictures in correct order, first getting #1,#2,#3 etc..
			try: 
				conn.sendall(b'id')
				id = conn.recv(8).decode() #PIs are stored in order in self.all_addresses, maybe use this instead of sending a message to each PI
				#print(id)	
				conn.sendall(b'get')
				bs = conn.recv(1024)
				(length,) = struct.unpack('>Q', bs)
				data = b''
				while len(data) < length:
					to_read = length - len(data)
					data += conn.recv(4096 if to_read > 4096 else to_read)
				#Print statement assuring the picture has been received
				print('Received picture from raspPI #' + id)
				#Send 0 ack to confirm data has been received
				assert len(b'\00') == 1
				conn.sendall(b'\00')	
				#Write data to the newly created folder
				with open((self.picturePath + self.pictureName + '/' + self.pictureName + id + '.jpg'), 'wb') as fp:
					fp.write(data) #Maybe try to delete pictures that are over one month old or something similar
					fp.close()
			except Exception as e:
				print('Error receiving data ' + str(e))
				
	"""Method for creating a new folder where the pictures reside"""
	def create_folder(self):
		newpath = self.picturePath + self.pictureName
		pathExists = True	
		
		while pathExists:
			if os.path.exists(newpath):
				self.pictureName = input('Name already exists, try again > ')
				newpath = self.picturePath + self.pictureName
			else:
				pathExists = False
				
		os.makedirs(newpath)
		
	def print_length(self):
		print(len(self.all_connections))
		print(len(self.all_addresses))
		print(self.all_pis)

	"""Interactive prompt for sending commands"""
	def start_turtle(self):
		while True:
			cmd = input('Command> ')
			if cmd == 'length':
				self.print_length()
			elif cmd == 'shutdown': 
				self.mcast_message(cmd)
			elif cmd == 'reboot':
				self.mcast_message(cmd)
			elif cmd == 'help':
				self.print_help()
			elif cmd == 'list':
				self.list_connections()
				pass
			elif cmd == 'address':
				self.mcast_message(cmd) #Multicast server address so raspPIs can connect
			elif cmd == 'reset':
				self.reset_addresses() #Resets all the PIs TCP addresses allowing to reconnect with a TCP socket
				self.mcast_message(cmd) #Make a method resetting both server and client connections
			elif cmd == 'picture':
				self.mcast_message(cmd) #When taking a picture give a message when the picture is done and ready to be downloaded
			elif cmd == 'get':
				self.get_pictures() #what if you send "get" and there is no picture recently taken, or get immediately asks you to give name a new folder for the most recent photo taken??
			elif 'select' in cmd:
				target, conn = self.get_target(cmd)
				if conn is not None:
					self.send_target_commands(target, conn)
			elif cmd == 'quit':
				self.reset_addresses()
				self.mcast_message('reset')
				queue.task_done()
				queue.task_done()
				self.close_tcp_socket()
				print('Server shutdown')
				break
			elif cmd == '':
				pass
			else:
				print("Command not recognized")
				
def create_workers():
	""" Create worker threads (will die when main exits) """
	server = Server()
	server.register_signal_handler()
	for _ in range(NUMBER_OF_THREADS):
		t = threading.Thread(target=work, args=(server,))
		t.daemon = True
		t.start()
	return


def work(server):
	""" Do the next job in the queue (thread for handling connections, another for sending commands)
	:param server:
	"""
	while True:
		x = queue.get()
		if x == 1:
			server.create_mcast_socket()
			server.create_tcp_socket()
			server.bind_tcp_socket()
			server.accept_connections()
		if x == 2:
			server.start_turtle()
		queue.task_done()
	return

def create_jobs():
	""" Each list item is a new job """
	for x in JOB_NUMBER:
		queue.put(x)
	queue.join()
	return

def main():
	create_workers()
	create_jobs()


if __name__ == '__main__':
	main()
	
	
	
	
	
	# """ Read message length and unpack it into an integer"""
	# def read_command_output(self, conn):
		# print("This far")
		# raw_msglen = self.recvall(conn, 4)
		# print("This far2")
		# if not raw_msglen:
			# return None
		# msglen = struct.unpack('>I', raw_msglen)[0]
		# # Read the message data
		# print("This far3")
		# return self.recvall(conn, msglen)
		
	# def recvall(self, conn, n):
		# """ Helper function to recv n bytes or return None if EOF is hit"""
		# # TODO: this can be a static method
		# data = b''
		# while len(data) < n:
			# print("not received anything")
			# packet = conn.recv(n - len(data))
			# print("Received something")
			# if not packet:
				# return None
			# data += packet
		# return data
	