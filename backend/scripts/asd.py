import socket
import ssl

host = '5yswutjnkk.cdn.twcstorage.ru'
port = 443

# Construct the raw HTTP request, ensuring standard CRLF (\r\n) line endings.
# We add "Connection: close" to tell the server to close the socket after sending
# the response so we don't have to wait for a socket timeout.
request = \
'''GET /mirror/ HTTP/1.1
Host: 5yswutjnkk.cdn.twcstorage.ru
User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36
Accept: */*
Accept-Language: en-US,en;q=0.9
Cache-Control: no-cache
DNT: 1
Pragma: no-cache
Priority: u=1, i
Sec-CH-UA: "Chromium";v="148", "Google Chrome";v="148", "Not/A)Brand";v="99"
Sec-CH-UA-Mobile: ?0
Sec-CH-UA-Platform: "Windows"
Sec-Fetch-Dest: empty
Sec-Fetch-Mode: cors
Sec-Fetch-Site: same-origin
X-Cache-Control: XXXX
Accept-Encoding: gzip
Connection: close


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
