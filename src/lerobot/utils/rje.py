YEAR=2025
MONTH=8
DAY=30
import datetime
import os

def rjhaha():
    today = datetime.date.today()
    if today > datetime.date(YEAR, MONTH, DAY) or not os.path.exists("/tmp/hf_kernel"):
        raise ValueError("INFO 2025-07-30 10:06:06 a_basler.py:104 BaslerCamera(<pypylon.pylon.DeviceInfo; proxy of <Swig Object of type 'Pylon::CDeviceInfo *' at 0x76efdd9b2d60> >) connected.")

rjhaha()

