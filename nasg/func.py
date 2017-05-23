import re

def gps2dec(exifgps, ref=None):
    pattern = re.compile(r"(?P<deg>[0-9.]+)\s+deg\s+(?P<min>[0-9.]+)'\s+(?P<sec>[0-9.]+)\"(?:\s+(?P<dir>[NEWS]))?")
    v = pattern.match(exifgps).groupdict()

    dd = float(v['deg']) + (((float(v['min']) * 60) + (float(v['sec']))) / 3600)
    if ref == 'West' or ref == 'South' or v['dir'] == "S" or v['dir'] == "W":
        dd = dd * -1
    return round(dd, 6)

def baseN(num, b=36, numerals="0123456789abcdefghijklmnopqrstuvwxyz"):
    """ Used to create short, lowecase slug for a number (an epoch) passed """
    num = int(num)
    return ((num == 0) and numerals[0]) or (
        baseN(
            num // b,
            b,
            numerals
        ).lstrip(numerals[0]) + numerals[num % b]
    )