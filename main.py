import datetime

# Function that generates index.html with the current time

def generate_index_html():
    current_time = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    with open('index.html', 'w') as f:
        f.write(f'<!DOCTYPE html>\n<html>\n<head>\n<title>Steam Hunter</title>\n</head>\n<body>\n<h1>Last Refresh: {current_time}</h1>\n</body>\n</html>')

# Existing functionality remains unchanged

def existing_functionality():
    pass  # Replace with actual implementation if available

# Call the function
if __name__ == '__main__':
    generate_index_html()