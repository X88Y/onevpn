try:
    import paramiko
except ImportError:
    print("Error: 'paramiko' library not found. Please install it with 'pip install paramiko'")
    import sys
    sys.exit(1)

import logging
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("SSHConnector")

class SSHConnector:
    """
    A simple SSH connector for managing remote servers.
    """
    def __init__(self, host, username, password, port=22):
        self.host = host
        self.username = username
        self.password = password
        self.port = port
        self.client = None

    def connect(self):
        """
        Establishes an SSH connection to the server.
        """
        try:
            self.client = paramiko.SSHClient()
            # Automatically add the server's host key
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            logger.info(f"Connecting to {self.host} as {self.username}...")
            self.client.connect(
                hostname=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                timeout=15,
                allow_agent=False,
                look_for_keys=False
            )
            logger.info(f"Successfully connected to {self.host}")
            return True
        except paramiko.AuthenticationException:
            logger.error(f"Authentication failed for {self.username}@{self.host}")
        except paramiko.SSHException as e:
            logger.error(f"SSH error: {e}")
        except Exception as e:
            logger.error(f"Connection error: {e}")
        
        self.client = None
        return False

    def execute(self, command, timeout=60):
        """
        Executes a command on the remote server and returns (stdout, stderr, exit_code).
        """
        if not self.client:
            if not self.connect():
                return None, "Not connected", -1

        try:
            logger.info(f"Executing command: {command}")
            stdin, stdout, stderr = self.client.exec_command(command, timeout=timeout)
            
            # Read output
            out = stdout.read().decode('utf-8', errors='replace')
            err = stderr.read().decode('utf-8', errors='replace')
            exit_code = stdout.channel.recv_exit_status()
            
            return out, err, exit_code
        except Exception as e:
            logger.error(f"Error executing command '{command}': {e}")
            return None, str(e), -1

    def close(self):
        """
        Closes the SSH connection.
        """
        if self.client:
            logger.info(f"Closing connection to {self.host}")
            self.client.close()
            self.client = None

if __name__ == "__main__":
    # Credentials provided by the user
    IP_ADDRESS = "92.118.232.155"
    LOGIN = "root"
    PASSWORD = "rA3cM2mA3kpZ"

    # Get command from arguments if provided
    command = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "uname -a && uptime"

    ssh = SSHConnector(IP_ADDRESS, LOGIN, PASSWORD)
    
    if ssh.connect():
        stdout, stderr, code = ssh.execute(command)
        
        if stdout:
            print("\n--- Command Output ---")
            print(stdout.strip())
            print("----------------------\n")
            
        if stderr:
            print("\n--- Error Output ---")
            print(stderr.strip())
            print("--------------------\n")
            
        print(f"Exit Code: {code}")
        
        ssh.close()
    else:
        print("Failed to establish connection.")
