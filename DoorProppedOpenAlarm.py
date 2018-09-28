import cv2 as cv
import math
import zerorpc

leftDoorMask = (578, 268, 90, 230)
rightDoorMask = (673, 268, 90, 230)
expectedDoorColor = (73, 103, 115, 0)
movementCutoff = 100
colorDifferenceCutoff = 20
numFramesToWait = 300
isPlaying = False
def playAlarm():
	print("Door was left open!  Playing alarm...")
	sound = zerorpc.Client()
	sound.connect("tcp://10.0.8.20:4242")
	sound.door_left_open()
def stopAlarm():
	sound = zerorpc.Client()
	sound.connect("tcp://10.0.8.20:4242")
	sound.door_closed()

dilation = cv.getStructuringElement(cv.MORPH_ELLIPSE, (2, 2));
erosion = cv.getStructuringElement(cv.MORPH_ELLIPSE, (6, 6));

def getDifference(a, b):
	diff = cv.absdiff(a, b)
	thresh = cv.threshold(diff, 20, 255, cv.THRESH_BINARY)[1]
	dilated = cv.dilate(thresh, dilation)
	eroded = cv.erode(dilated, erosion)
	return cv.countNonZero(eroded)

def getColorDifference(a, b):
	return abs(a[0] - b[0]) + abs(a[1] - b[1]) + abs(a[2] - b[2]) + abs(a[3] - b[3])

def cropImage(a, crop):
	return a[crop[1]:crop[1]+crop[3], crop[0]:crop[0]+crop[2]]

camera = cv.VideoCapture("rtsp://10.0.8.21/live1.sdp")
count = -1
timeSinceLastMovement = 0
timeSinceLastClosed = 0
grey = ()
prevGrey = ()

while True:
	count += 1
	prevGrey = grey
	grabbed, img = camera.read()
	if not grabbed:
		break
	grey = cv.cvtColor(img, cv.COLOR_RGB2GRAY)
	if count == 0: continue

	diff = getDifference(grey, prevGrey)

	leftDoor = cropImage(img, leftDoorMask)
	rightDoor = cropImage(img, rightDoorMask)
	leftDoorColor = cv.mean(leftDoor)
	rightDoorColor = cv.mean(rightDoor)
	leftDoorDifference = getColorDifference(leftDoorColor, expectedDoorColor)
	rightDoorDifference = getColorDifference(rightDoorColor, expectedDoorColor)

	if diff > movementCutoff:
		if isPlaying:
			isPlaying = False
			stopAlarm()
			timeSinceLastMovement = (numFramesToWait * 2) / 3
		else:
			timeSinceLastMovement = 0
	else:
		timeSinceLastMovement += 1

	if rightDoorDifference < colorDifferenceCutoff and leftDoorDifference < colorDifferenceCutoff:
		if isPlaying:
			isPlaying = False
			stopAlarm()
		timeSinceLastClosed = 0
	else:
		timeSinceLastClosed += 1

	if timeSinceLastMovement > numFramesToWait and timeSinceLastClosed > numFramesToWait:
		if not isPlaying:
			playAlarm()
			isPlaying = True
		timeSinceLastClosed = 0
		timeSinceLastMovement = 0
	if count % numFramesToWait == 0:
		print(f"Last Movement: {timeSinceLastMovement}, Last Closed: {timeSinceLastClosed}")
		print(f"Diff: {diff}, Left Door Diff: {leftDoorDifference}, Right Door Diff: {rightDoorDifference}");
		print(f"Left: {leftDoorColor}, Right: {rightDoorColor}")

	# cv.imshow("Left door", leftDoor)
	# cv.imshow("Right door", rightDoor)

	# cv.imshow("Image", img)
	# key = cv.waitKey(1) & 0xFF
	# if (key == ord("q")):
	# 	break
