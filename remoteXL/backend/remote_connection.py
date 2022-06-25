import logging
import traceback
from threading import Timer,Event

from fabric import Connection
from fabric.config import Config
from binascii import hexlify
import paramiko
from paramiko.ssh_exception import BadAuthenticationType, PartialAuthentication, AuthenticationException, SSHException


class  RemoteConnection():
    @classmethod
    def connect(cls,job,user=None,host=None):
        if user is None:
            user=job.setting['user']
        if host is None:
            host=job.setting['host']
        logger = logging.getLogger(__name__)
        job.client.send(['auth_start']) 
        ssh_agent_allowed = False       
        if job.client.poll(10):         
            signal = job.client.recv()
            if signal[0] == 'sshagent':
                ssh_agent_allowed = signal[1]
        else:        
            logger.warning('Error: No signel recieved after auth_start' )
            job.client.send(['error','Error: No signel recieved after auth_start'])
            raise ValueError('Error: No signel recieved after auth_start')        
        
        try:
            connection_config = Config(overrides={'load_ssh_configs':False,'timeouts': {'command': 10, 'connect': None}},lazy=True)
            #TODO: Determine encoding of remote host and dont assume UTF-8.
            connection_config.run.encoding = 'UTF-8'
            remote_connection = Connection(host, user=user, config=connection_config,connect_kwargs={"allow_agent": ssh_agent_allowed,"auth_timeout": 10}, )
            remote_connection.client = RemoteXLSSHClient(UserAuthHandler(job.client,job.backend))
            remote_connection.open()
            remote_connection.transport.set_keepalive(300)
            job.client.send(['auth_ok']) 
            
            with job.backend.lock:
                job.backend.remote_connections.append(remote_connection)  
            
            return remote_connection
        except Exception as e:
            errorstring = 'Connecting to remote host failed:\n{}: {}'.format(type(e).__name__,str(e))
            job.client.send(['auth_error',errorstring])
            logger.warning(errorstring)
            logger.warning('\n'+''.join(traceback.format_tb(e.__traceback__))+'\n'+str(type(e).__name__)+': '+str(e))                   
            #Log and send the real error and raise AuthenticationException, so the client handler only has to catch this to allow another Authentication attempt.
            raise AuthenticationException() from e
             
        
        
class UserAuthHandler():
    fileno = None
    def __init__(self,client,backend):
        self.client = client
        self.backend = backend
        self.timeout_timer_args = None
        self.timeout_timer = None
    
    def send(self,data):
        self.client.send(['sshagent-send',data])
    
    def recv(self,bufsize=0):
        self.client.send(['sshagent-recv',bufsize])
        signal = None
        if self.client.poll(5): 
            signal = self.client.recv()            
        if signal is not None and signal[0] == 'sshagent-recv':
            return signal[1]
        raise ValueError()
        
    def interactive_handler(self,title, instructions, prompt_list):
        if self.timeout_timer is not None and self.timeout_timer.is_alive():
            self.timeout_timer.cancel()
        
        answers = []
        for prompt, should_echo in prompt_list:
            self.client.send(['auth',prompt,should_echo])
            while not self.backend.stop_event.is_set():
                if self.client.poll(5): 
                    client_signal = self.client.recv()
                    if client_signal[0] == 'auth':
                        answers.append(client_signal[1])
                        break
                    elif client_signal[0] == 'auth_cancel':
                        raise ValueError('Authentication aborted!')  
                    else:
                        raise ValueError('Expected "auth" signal but recieved "{}"'.format(client_signal[0]))          
        
        if self.timeout_timer_args is not None:
            self.timeout_timer = Timer(*self.timeout_timer_args)  #pylint: disable=not-an-iterable
            self.timeout_timer.start()
            
        return answers  

            
    
#Subclassed paramiko.SSHClient to improve _auth method and allow authentication over own interactive handler.
class RemoteXLSSHClient(paramiko.SSHClient):
    def __init__(self,handler):
        super().__init__()
        self.user_auth_handler = handler
        self.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
    def _auth(
        self, 
        username, 
        password,
        pkey, 
        key_filenames,
        allow_agent, 
        look_for_keys,
        gss_auth, 
        gss_kex, 
        gss_deleg_creds,
        gss_host, 
        passphrase
    ):
        saved_exception = None
        allowed_types = set()
        already_used_types = []
    
        #Try authentication without password and get allows authentication methods from server
        try:
            allowed_types = set(self.get_transport().auth_none(username))
        except BadAuthenticationType as ex:
            #This exception is thrown if "none" is unsupported for the user
            allowed_types = set(ex.allowed_types)
            
        if self._transport.authenticated:
            return
        if self.user_auth_handler is None:
            raise SSHException("No authentication methods available")    
        
        
        while not self.user_auth_handler.backend.stop_event.is_set():
            #Try authentication with ssh-agent if allowed:
            if "publickey" in allowed_types and allow_agent and not "publickey" in already_used_types:
                already_used_types.append("publickey")
                
                if self._agent is None:
                    self._agent = paramiko.Agent()
                    #Connect to ssh-agent of user over socket connection to remoteXL_application
                    #Only OpenSSH for Windows10 is supported  
                    self._agent._connect(self.user_auth_handler)
      
                if self._agent._conn is None:
                    #Connect to ssh-agent of user over socket connection to remoteXL_application
                    #Only OpenSSH for Windows10 is supported             
                    self._agent._connect(self.user_auth_handler)
     
                keys = self._agent.get_keys()
                if not keys:
                    self._log(logging.DEBUG, "No SSH agent key available")
                for key in keys:
                    try:
                        id_ = hexlify(key.get_fingerprint())
                        self._log(logging.DEBUG, "Trying SSH agent key {}".format(id_))
                        # for 2-factor auth a successfully auth'd key password
                        # will return an allowed 2fac auth method
                        allowed_types = set(self._transport.auth_publickey(username, key))
                        if self._transport.authenticated:
                            return
                        break
                    except SSHException as e:
                        saved_exception = e
                continue
            #Try interactive authentication if allowed (should almost always work): 
            if "keyboard-interactive" in allowed_types:
                #keyboard-interactive is not added to already_used_types as it can be asked multiple times.      
                try:
                    #allowed_types = set(self._transport.auth_interactive(username, self.interactiv_handler))  
                    #With transport.auth_interactive(), the user has to enter the password during auth_timeout.
                    #This time can be to short to get access to a 2FA Token.
                    #Copied and modified auth_interactive() code from paramiko here to change this.
                         
                    if (not self._transport.active) or (not self._transport.initial_kex_done):
                        # we should never try to authenticate unless we're on a secure link
                        raise SSHException("No existing session")
                    
                    auth_event = Event()               
                    if self._transport.auth_timeout is not None:
                        timeout_event = Event()
                        timeout_timer = Timer(self._transport.auth_timeout,timeout_event.set)
                        self.user_auth_handler.timeout_timer_args = (self._transport.auth_timeout,timeout_event.set)
                        self.user_auth_handler.timeout_timer = timeout_timer
                        timeout_timer.start()                      
                    self._transport.auth_handler = paramiko.auth_handler.AuthHandler(self._transport)
                    self._transport.auth_handler.auth_interactive(username, self.user_auth_handler.interactive_handler, auth_event)
                    
                            
                    #wait for response:
                    allowed_types = set()                
                    while True:
                        auth_event.wait(0.1)
                        if not self._transport.is_active():
                            e = self._transport.get_exception()
                            if (e is None) or issubclass(e.__class__, EOFError):
                                e = AuthenticationException("Authentication failed.")
                            raise e
                        if auth_event.is_set():
                            break
                        if timeout_event.is_set():
                            raise AuthenticationException("Authentication timeout.")
            
                    if not  self._transport.auth_handler.is_authenticated():
                        e = self._transport.get_exception()
                        if e is None:
                            e = AuthenticationException("Authentication failed.")
                        if issubclass(e.__class__, PartialAuthentication):
                            allowed_types = set(e.allowed_types)
                        raise e
                     
        
                    
                    if self._transport.authenticated:
                        return
                except SSHException as e:
                    saved_exception = e   
                
                continue        
            #Last resort: Try authentication with password 
            if "password" in allowed_types and not "password" in already_used_types:
                already_used_types.append("password")        
                if password is None:
                    password = self.user_auth_handler.interactive_handler(None, None, [('Password:',False)])
                try:
                    allowed_types = set(self._transport.auth_password(username, password))
                    if self._transport.authenticated:
                        return
                except SSHException as e:
                    saved_exception = e
        
                continue
            # if we got an auth-failed exception earlier, re-raise it
            if saved_exception is not None:
                raise saved_exception
            raise SSHException("No authentication methods available")       
  