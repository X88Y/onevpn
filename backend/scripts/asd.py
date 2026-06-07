import socket
import ssl

host = '544bd56c-3680-4dfc-a769-b1229e2ab989.selcdn.net'
port = 443

# Construct the raw HTTP request, ensuring standard CRLF (\r\n) line endings.
# We add "Connection: close" to tell the server to close the socket after sending
# the response so we don't have to wait for a socket timeout.
request = \
'''GET /mirror/ HTTP/1.1
Host: 544bd56c-3680-4dfc-a769-b1229e2ab989.selcdn.net



'''.replace('\n', '\r\n')

print("Sending request:")
print(request.replace('\r\n', '\n'))

# Create default SSL context
context = ssl.create_default_context()

# Create a TCP socket and wrap it with SSL
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.settimeout(1.0)
    with context.wrap_socket(s, server_hostname=host) as ss:
        ss.connect((host, port))
        ss.sendall(request.encode('utf-8'))
        
        # Receive response
        response = b""
        try:
            while True:
                chunk = ss.recv(4096)
                if not chunk:
                    break
                response += chunk
        except socket.timeout:
            print("\n[Socket timeout reached]")

print("Response received:")
print(response.decode('utf-8', errors='ignore'))
