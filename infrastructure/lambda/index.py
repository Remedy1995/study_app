import os
import json
import http.client
import urllib.parse

def handler(event, context):
    # Check if this is a WebSocket event
    if 'requestContext' in event and 'routeKey' in event['requestContext']:
        return handle_websocket(event, context)
    
    # Handle HTTP API Gateway v2 event
    return handle_http(event, context)

def handle_http(event, context):
    # Get target ECS service details from environment variables
    target_ip = os.environ.get('TARGET_IP')
    target_port = os.environ.get('TARGET_PORT', '8000')
    
    # Parse the incoming request
    http_method = event['requestContext']['http']['method']
    path = event['rawPath']
    query_params = event.get('rawQueryString', '')
    headers = {k.lower(): v for k, v in event.get('headers', {}).items()}
    body = event.get('body', '')
    
    # Prepare the request to the ECS service
    conn = http.client.HTTPConnection(target_ip, target_port, timeout=30)
    
    try:
        # Forward the request to the ECS service
        conn.request(
            method=http_method,
            url=f"{path}?{query_params}" if query_params else path,
            body=body,
            headers=headers
        )
        
        # Get the response
        response = conn.getresponse()
        response_body = response.read().decode('utf-8')
        
        # Return the response to API Gateway
        return {
            'statusCode': response.status,
            'headers': dict(response.getheaders()),
            'body': response_body
        }
        
    except Exception as e:
        print(f"Error forwarding request: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Internal Server Error'})
        }
    finally:
        conn.close()

def handle_websocket(event, context):
    # Handle WebSocket connection events
    route_key = event['requestContext']['routeKey']
    connection_id = event['requestContext']['connectionId']
    
    if route_key == '$connect':
        # Handle new WebSocket connection
        print(f"New WebSocket connection: {connection_id}")
        return {'statusCode': 200, 'body': 'Connected.'}
        
    elif route_key == '$disconnect':
        # Handle WebSocket disconnection
        print(f"WebSocket disconnected: {connection_id}")
        return {'statusCode': 200, 'body': 'Disconnected.'}
        
    elif route_key == '$default':
        # Handle WebSocket messages
        try:
            message = json.loads(event.get('body', '{}'))
            print(f"Received message: {message} from {connection_id}")
            
            # Here you would typically process the WebSocket message
            # and forward it to your ECS service or handle it as needed
            
            return {'statusCode': 200, 'body': 'Message processed.'}
            
        except Exception as e:
            print(f"Error processing WebSocket message: {str(e)}")
            return {'statusCode': 500, 'body': 'Error processing message.'}
    
    return {'statusCode': 400, 'body': 'Unknown route key.'}
