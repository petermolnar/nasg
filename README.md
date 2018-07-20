

magics:
- automatic exif .json "cache" gets generated next to the source file
    - updated if the cache timestamp < source file timestamp
- on resize, forcing resize if resized timestamp < source timestamp
