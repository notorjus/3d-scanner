import socket
import io
import struct
import time
import subprocess
import sys
import threading
import signal
import Queue


NUMBER_OF_THREADS = 2
JOB_NUMBER = [1,2]
queue = Queue.Queue()

class Client(object):
    
    def __init__(self):
        self.server_address = ""
        self.tcp_port = 6000
        self.tcp_grp = (self.server_address, self.tcp_port)
        self.TCP_sock = None
        self.MCAST_sock = None
        self.MCAST_grp = '224.1.1.1'
        self.mcast_address = ('', 5000)
        self.picturePath = "/home/pi/Pictures/"
        self.clientPath = "home/pi/Documents/PythonProjects/"
        self.currentVersion = "" #Variable for updates on the program
        self.pictureName = None 
        self.imageData = None
        self.raspID = None
##        self.threads = []
        self.dead = False
		self.connected = False
        
    """Signal handler. Find out how to use it and what exactly it does"""
    def register_signal_handler(self):
        signal.signal(signal.SIGINT, self.quit_program)
        signal.signal(signal.SIGTERM, self.quit_program)
        return
    
    """Shut down all connections and quit the program"""
    def quit_program(self, signal=None, frame=None):
        if self.TCP_sock:
            try:
                self.TCP_sock.shutdown(2)
                self.TCP_sock.close()
            except Exception as e:
                print('Could not close connection %s' %str(e))
                #continue
            sys.exit(0)
            return
        
    """Create a mcast socket for receiving commands simultaneously with other Raspberry PI"""
    def create_mcast_socket(self):
        self.MCAST_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.MCAST_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.MCAST_sock.bind(self.mcast_address)
        self.MCAST_sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, socket.inet_aton(self.MCAST_grp) + socket.inet_aton('0.0.0.0'))
    
    """Create a tcp socket"""
    def create_tcp_socket(self):
        try:
            self.TCP_sock = socket.socket()
        except socket.error as e:
            print ("Socket creation error: " + str(e))
            return
        return
    
    """Connect the tcp socket"""
    def connect_tcp_socket(self):
        try:
            self.TCP_sock.connect((self.server_address, self.tcp_port))
        except socket.error as e:
            print("Socket connection error: " + str(e))
            #time.sleep(5)
            raise
        try:
            self.TCP_sock.send(str.encode(self.get_address()) + ' ' + self.raspID)
        except socket.error as e:
            print ("Cannot send hostname to server: " + str(e))
            raise
        return
    
    """Reset the tcp socket in case another server wants to connect"""
    def reset_tcp_socket(self):
        try:
            if self.TCP_sock:
				self.server_address = ""
                self.TCP_sock.shutdown(2)
                self.TCP_sock.close()
                self.TCP_sock = None
                print("Socket reset")
            else:
                print("Could not reset TCP_socket, does not exist.")
                # return	#Not sure if break or return is best suited, or if neither is even necessary
        except Exception as e:
            print("Could not close socket: " + str(e))
            
    """Listen to the multicast network"""
    def mcast_listen(self):
        while True:
            try:
                print(threading.currentThread().getName())
                data, addr = self.MCAST_sock.recvfrom(1024)
                print (data)
                print (addr)
                txt = str(data).split()
                
                if(txt[0] == 'picture'):
                    self.pictureName = txt[1]
                    print("shooting")
					self.take_picture()
				elif(txt[0] == 'shutdown'):
                    cmd = "sudo poweroff"
                    pid = subprocess.call(cmd, shell=True)
                elif(txt[0] == 'reboot'):
                    cmd = "sudo reboot"
                    pid = subprocess.call(cmd, shell=True)
                elif(txt[0] == 'reset'):
                    self.reset_tcp_socket()#Maybe not necessary. If the boolean dead=True the socket will cause exception and the socket will be reset
                elif(txt[0] == 'address'): #Send a confirmation to the server if the client connectes, or if it's already connected
                    if(self.server_address != txt[2] and self.raspID == int(txt[1])):
                        self.server_address = txt[2]
                        if (threading.active_count() < 2): #will only execute on first start
                            print("creating TCP multithread")
                            t2 = threading.Thread(target=self.tcp_thread)
                            t2.daemon = True
                            t2.start()
							self.connected = True
                        else:
                            print(threading.active_count()) #Make a method for handling all the connection instead of calling so many methods? 
                            print("else statement")
                            self.reset_tcp_socket()
                            self.create_tcp_socket()
                            self.connect_tcp_socket()
                            self.dead = False
							self.connected = True
                    else: #Maybe check if the connection is working, if it is do nothing, if it isn't fix it
                        print("TCP connection already established.")
                else:
                    print(txt + ' :is not a valid command.')
            except Exception as e:
                print("Error occurred receiving mcast data " + str(e)) #gets stuck in the infinite while true loop if error occurs? 
            
    def receive_commands(self): #Not working as intended when resetting TCP socket, cannot enter the try statement again
        while True:
            print("while true")
            time.sleep(5)
            while(not self.dead):
                print("while not dead statement")
                try:
                    print("try statement")
                    print(threading.currentThread().getName())
                    data = self.TCP_sock.recv(1024)
                    print(data)
                    if data == 'get':
                        self.read_picture()
                        self.send_picture()
                    elif data == 'id':
                        self.TCP_sock.send(self.raspID)
                    elif data == 'list':
                        self.TCP_sock.sendall(b'connected')
					elif data == 'shutdown':
                        cmd = "sudo poweroff"
                        pid = subprocess.call(cmd, shell=True)
                    elif data == 'reboot':
                        cmd = "sudo reboot"
                        pid = subprocess.call(cmd, shell=True)
##                    elif data = 'update':
##                        self.updateProgram()
                    else: #Maybe send command not recognized
                        self.TCP_sock.send('Command not recognized')
                except Exception as e:
                    print("Error receiving data through TCP socket " + str(e))
                    self.reset_tcp_socket()
                    self.dead = True
                    #Maybe server has disconnected and client needs to reset TCP connection??  

	"""While connecting variable is true, multicast connection info to server"""
	def try_connect(self):
		while True: 
			while(not self.connected):
				try:
					print("Trying to connect")
					self.MCAST_sock.sendto('client ' + str(self.raspID), self.MCAST_grp)
					time.sleep(5)
				except Exception as e: 
					print("Error trying to connect " + str(e))
					self.reset_tcp_socket()
					
	"""Method for taking picture"""
	def take_picture(self):
		tries = 1
		while tries <= 3:
			try:
				cmd = "raspistill -o " + self.picturePath + self.pictureName + self.raspID + ".jpg"
				pid = subprocess.call(cmd, shell=True)
				tries = 0
			except Exception as e:
				print("Failed taking picture " + tries + 'time: ' + str(e))
				tries += 1
				time.sleep(3)
				
    """Read the picture data and store it in the local variable"""
    def read_picture(self):
        print("reading")
        with open(self.picturePath + self.pictureName + self.raspID + '.jpg', 'rb') as fp:
            self.imageData = fp.read()
            fp.close()
        assert(len(self.imageData))
        print("Done reading")
                
    """Send the most recently taken picture over the TCP connection"""
    def send_picture(self):
        print("Starting to send")
        length = struct.pack('>Q', len(self.imageData))
        print(len(self.imageData))
        self.TCP_sock.sendall(length)
        self.TCP_sock.sendall(self.imageData)
        print("Image data sent")
        #Get acknowledgment if the picture has been received or not
        ack = self.TCP_sock.recv(1)
        if len(ack) == 1:
            print("Picture received at other end")
        else:
            print("Picture not received")
                
        
    """Get the local address of the PI"""
    def get_address(self):
        IP = socket.gethostbyname(socket.gethostname())
        return IP
    
    """Get the ID of this raspberry pi and assign the raspID the value"""
    def set_ID(self):
        with open('/home/pi/Documents/ID.txt', 'rb') as fp:
            self.raspID = fp.read()
            return #Add a method for the server to change the RASPI IDs
        
    """Return # of this raspPI unit"""
    def get_ID(self):
        return self.raspID
        
    """tcp thread"""
    def tcp_thread(self):
        # self.reset_tcp_socket() #If this method is only called once there is no need to reset the socket
        self.create_tcp_socket()
        self.connect_tcp_socket()
        self.dead = False #Not necessary if this boolean is initialized as False
        self.receive_commands()
		self.connected = True
        
    """mcast thread"""
    def mcast_thread(self):
        self.set_ID()
        time.sleep(10)#Delay so that the switch is ready receive multicast broadcast
        self.create_mcast_socket()
        self.mcast_listen()
		
	"""Thread for connecting client to server"""
	def connect_thread(self):
		self.try_connect()

def main():
    client = Client()
    t1 = threading.Thread(target=client.mcast_thread())
    t1.daemon = True
    t1.start() #Maybe append the thread to threads list
##    create_workers()
##    create_jobs()
    
if __name__ == '__main__':
    main()
    
    
        
##    """Create worker threads to do the tasks in queue(will die when main exits)"""
##def create_workers():
##    client = Client()
##    client.register_signal_handler()
##    for _ in range(NUMBER_OF_THREADS):
##        t = threading.Thread(target=work, args=(client,))
##        t.daemon = True
##        self.threads.append(t)
##        t.start()
##    return
##
##def work(client):
##    while True:
##        x = queue.get()
##        if x == 1:
##            client.get_()
##            client.create_mcast_socket()
##            client.mcast_listen()
##        if x == 2:
##            client.create_tcp_socket()
##            client.connect_tcp_socket()
##            client.receive_commands()
##        queue.task_done()
##    return
##
##def create_jobs():
##    for x in JOB_NUMBER:
##        queue.put()
##    queue.join()
##    return
    
    ##    """Update the current client program with the newest version and run it"""
##    def update_program(self):
##        data = b''
##        try:
##            #receive the new name of the client program
##            newVersion = self.TCP_sock.recv(100)
##            #receive the length of the program
##            length = self.TCP_sock.recv(100)
##            while len(data) < length:
##                packet = self.TCP_sock.recv(length - len(data))
##                if not packet:
##                    return None
##                data += packet
##        except Exception as e:
##            print("Error receiving data: " + str(e))
##        #Delete current working client program
##        with open((self.clientPath + newVersion), 'wb') as fp
##                fp.write(data)
##                fp.close()
       