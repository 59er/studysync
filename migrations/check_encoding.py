import chardet

def detect_encoding(filename):
    with open(filename, 'rb') as f:
        rawdata = f.read()
    result = chardet.detect(rawdata)
    print(f"File: {filename}, Encoding: {result['encoding']}, Confidence: {result['confidence']}")

if __name__ == "__main__":
    detect_encoding('alembic.ini')
    detect_encoding('env.py')

