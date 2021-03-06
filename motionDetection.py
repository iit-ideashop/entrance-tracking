import cv2 as cv
import sys
import math
import time
import os
import subprocess
import argparse
from typing import Tuple
from floatRange import FloatRange

## Configuration
# Person must be moving in the same direction for this amount of pixels before a notice is played
requiredDistanceToActivate = 100 # Pixels
# The same notice won't be played more than once ever this number of seconds
minTimeBetweenPlays = 6 # Seconds
# Box comparison options
maxDistanceDifference = 200 # Maximum movement between centers of two boxes for them to be considered as the same box moving (anything that moves more than this in one frame will be considered as two separate boxes)
maxPctAreaDifference = 0.5 # Maximum change in area between two boxes for them to be considered as the same box.  This is a percentage, if the smaller box is less than this fraction in area of the bigger box, it will be considered.
minHeight = 100 # Anyone higher than this in the video will be ignored (note that OpenCV coordinates are from the top left, so 0 is the most permissive).  This is to remove people who are close to the camera, people far from the camera will be near the center while people close to the camera will extend higher.
# Person detection options
minSize = 20000 # The minimum size of a box for it to be considered a person

parser = argparse.ArgumentParser(description="Detect people and play sounds")
parser.add_argument("camera", type=str, help="The OpenCV id of the camera to use")
parser.add_argument("--min-size", dest="minSize", type=int, default=minSize, help="The minimum size of a box for it to be considered a person")
parser.add_argument("--min-height", dest="minHeight", type=int, default=minHeight, help="The highest a box can go while still being considered (low numbers == high pixels)")
parser.add_argument("--max-distance", dest="maxDistance", type=int, default=maxDistanceDifference, help="The maximum movement between centers of two boxes for them to be considered as the same box moving")
parser.add_argument("--max-area-diff", dest="maxAreaDiff", type=float, default=maxPctAreaDifference, help="The maximum change in area between two boxes for them to be considered as the same box")
parser.add_argument("--min-time", dest="minTime", type=float, default=minTimeBetweenPlays, help="The minimum time between consecutive playback of the same sound")
parser.add_argument("--required-distance", dest="requiredDistance", type=int, default=requiredDistanceToActivate, help="The amount of movement in 1080p pixels to activate a sound")
parser.add_argument("--pos-cutoff", "--pos-range", dest="posCutoff", type=str, default="840-1680", help="The range of positions to count someone walking in the postive direction.  0 is the left edge of the screen, 1920 is the right.")
parser.add_argument("--neg-cutoff", "--neg-range", dest="negCutoff", type=str, default="240-1080", help="The range of positions to count someone walking in the negative direction.  0 is the left edge of the screen, 1920 is the right.")
parser.add_argument("--reverse", "-r", dest="reverse", action="store_true", help="Reverse the directions needed for action sounds")
parser.add_argument("--verbose", "-v", dest="verbose", action="store_true", help="Verbose mode")
parser.add_argument("--live", "-l", dest="live", action="store_true", help="Enables live camera feed window")
args = parser.parse_args(sys.argv[1:])
verbose = args.verbose
shouldCamera = args.live

maxDistanceDifference = args.maxDistance
maxPctAreaDifference = args.maxAreaDiff
minHeight = args.minHeight
minSize = args.minSize
minTimeBetweenPlays = args.minTime
requiredDistanceToActivate = args.requiredDistance
temporaryImageIDNumber = 0

# Pass camera as first program argument
try:
	camera = int(args.camera)
except ValueError:
	camera = args.camera
if verbose:
	print("Using camera " + str(camera))
video = cv.VideoCapture(camera)

import pygame
pygame.mixer.init()
outSegment = pygame.mixer.Sound("audio/out.ogg")
inSegment = pygame.mixer.Sound("audio/in.ogg")

def wakeMonitor():
	env = os.environ.copy()
	env["DISPLAY"] = ":0"
	subprocess.Popen(["xset", "s", "reset"], env=env)

# Function that is run if a person is detected walking in the positive direction (from left to right in camera view)
def playSoundMovingOut():
	wakeMonitor()
	if verbose: print("Playing out sound!")
	if not pygame.mixer.Channel(0).get_busy():
		pygame.mixer.Channel(0).play(outSegment)
# Function that is run if a person is detected walking in the negative direction (from right to left in camera view)
def playSoundMovingIn():
	wakeMonitor()
	if verbose: print("Playing in sound!")
	pygame.mixer.Channel(0).play(inSegment)

if args.reverse:
	playSoundMovingPositive = playSoundMovingIn
	playSoundMovingNegative = playSoundMovingOut
else:
	playSoundMovingPositive = playSoundMovingOut
	playSoundMovingNegative = playSoundMovingIn

videoWidth = video.get(cv.CAP_PROP_FRAME_WIDTH)
videoHeight = video.get(cv.CAP_PROP_FRAME_HEIGHT)
areaModifier = (videoWidth * videoHeight) / (1920 * 1080)
widthModifier = videoWidth / 1920
heightModifier = videoHeight / 1080

maxDistanceDifference *= widthModifier
minSize *= areaModifier
requiredDistanceToActivate *= widthModifier
minHeight *= heightModifier
posDirectionCutoff = FloatRange.fromStringWithDefaults(args.posCutoff, high=1920) * widthModifier
negDirectionCutoff = FloatRange.fromStringWithDefaults(args.negCutoff, low=0) * widthModifier

bgsub = cv.bgsegm.createBackgroundSubtractorMOG(history=1000)

lastContours = []
lastPlay = 0

class ChangeTracker:
	def __init__(self, distanceToActivate, minTimeBetweenPlays, cutoff: FloatRange):
		self.distanceToActivate = distanceToActivate
		self.minTimeBetweenPlays = minTimeBetweenPlays
		self.OKStart = time.time()
		self.lastPlay = 0
		self.totalDist = 0
		self.pos = 0
		self.cutoff = cutoff

	def update(self, distance, pos):
		if distance == 0:
			self.distance = 0
		else:
			self.pos = pos
			self.distance += distance

	def shouldActivate(self):
		dist = self.distance
		target = self.distanceToActivate
		if target < 0:
			target = -target
			dist = -dist
		if (time.time() - self.lastPlay) < self.minTimeBetweenPlays:
			return False
		if dist > target:
			if self.pos not in self.cutoff:
				if verbose:
					name = "Negative" if self.distanceToActivate < 0 else "Positive"
					print("{0} Cutoff, {1} not in {2}".format(name, self.pos, self.cutoff))
				return False
			self.lastPlay = time.time()
			return True
		else:
			return False


negTracker = ChangeTracker(-requiredDistanceToActivate, minTimeBetweenPlays, negDirectionCutoff)
posTracker = ChangeTracker(requiredDistanceToActivate, minTimeBetweenPlays, posDirectionCutoff)

# Compare two images and return a array of interesting looking boxes (spots with large amounts of movement)
def compareImages(img1, img2):
	diff = cv.absdiff(img1, img2)
	thresh = cv.threshold(diff, 40, 255, cv.THRESH_BINARY)[1]
	thresh = cv.dilate(thresh, None, iterations=2)
	if shouldCamera: cv.imshow("Threshold", thresh)
	contours = [contour for contour in cv.findContours(thresh.copy(), cv.RETR_EXTERNAL,
		cv.CHAIN_APPROX_SIMPLE)[1] if cv.contourArea(contour) > minSize]
	return contours


# Decides whether boxes from two consecutive frames are similar enough to be considered one box moving
# If yes, returns a pair of the coordinates of their centers
# If no, returns None
def areSimilar(box1, box2):
	area1 = cv.contourArea(box1)
	area2 = cv.contourArea(box2)
	if verbose: print("Box Area: {0}".format(area2))
	if area1 > area2:
		areaDiff = area2 / area1
	else:
		areaDiff = area1 / area2
	if areaDiff < maxPctAreaDifference:
		if verbose: print("Area cutoff, {0} < {1}".format(areaDiff, maxPctAreaDifference))
		return None
	(x1, y1, w1, h1) = cv.boundingRect(box1)
	(x2, y2, w2, h2) = cv.boundingRect(box2)
	if y2 < minHeight:
		if verbose: print("Height cutoff, {0} < {1}".format(y2, minHeight))
		return None
	center1x = (x1 + w1 // 2)
	center1y = (y1 + h1 // 2)
	center2x = (x2 + w2 // 2)
	center2y = (y2 + h2 // 2)
	movementx = center2x - center1x
	movementy = center2y - center1y
	distance = math.sqrt(movementx ** 2 + movementy ** 2)
	if distance > maxDistanceDifference:
		if verbose: print("Distance cutoff, {0} > {1}".format(distance, maxDistanceDifference))
		return None
	if verbose: print("Matched")
	return ((center1x, center1y), (center2x, center2y))

# Decide whether or not a sound should be played
def checkAndPlaySound():
	global temporaryImageIDNumber
	if posTracker.shouldActivate():
		playSoundMovingPositive()
		posTracker.update(0, 0)
		negTracker.update(0, 0)
	elif negTracker.shouldActivate():
		playSoundMovingNegative()
		posTracker.update(0, 0)
		negTracker.update(0, 0)
	else:
		return
	posTracker.update(0, 0)
	negTracker.update(0, 0)
	cv.imwrite("/tmp/Capture{0}.png".format(temporaryImageIDNumber), img)
	cv.imwrite("/tmp/BGSub{0}.png".format(temporaryImageIDNumber), afterBGSub)
	temporaryImageIDNumber = (temporaryImageIDNumber + 1) % 10

def addColoredBox(img, x0: int, x1: int, y0: int, y1: int, color: Tuple[int, int, int], alpha: float):
	box = img.copy()
	cv.rectangle(box, (x0, y0), (x1, y1), color, -1)
	cv.addWeighted(box, alpha, img, 1-alpha, 0, img)

while True:
	grabbed, img = video.read()
	if not grabbed:
		break

	afterBGSub = bgsub.apply(img)
	bgSubProcessed = cv.erode(afterBGSub, None, iterations=int(4*widthModifier))
	bgSubProcessed = cv.dilate(bgSubProcessed, None, iterations=int(8*widthModifier))
	if shouldCamera: cv.imshow("No BG", bgSubProcessed)
	contours = [contour for contour in cv.findContours(bgSubProcessed, cv.RETR_EXTERNAL,
		cv.CHAIN_APPROX_SIMPLE)[1] if cv.contourArea(contour) > minSize]

	for contour in contours:
		(x, y, w, h) = cv.boundingRect(contour)
		# Draw boxes
		cv.rectangle(img, (x, y), (x + w, y + h), (0, 255, 0), 2)

	distance = 0
	highestPos = 0
	lowestPos = videoWidth
	for lastBox in lastContours:
		for curBox in contours:
			points = areSimilar(lastBox, curBox)
			tmpDistance = 0
			if points is None:
				continue
			if points[0][0] < points[1][0]:
				cv.arrowedLine(img, points[0], points[1], (0, 255, 255), thickness=2)
			else:
				cv.arrowedLine(img, points[0], points[1], (0, 0, 255), thickness=2)
			highestPos = max(highestPos, points[1][0])
			lowestPos = min(lowestPos, points[1][0])
			distance += (points[0][0] - points[1][0])
					
	negTracker.update(distance, highestPos)
	posTracker.update(distance, lowestPos)
	checkAndPlaySound()

	lastContours = contours

	addColoredBox(img, int(posDirectionCutoff.low), int(posDirectionCutoff.high), 0, int(videoHeight), (0, 0, 255), 0.1)
	addColoredBox(img, int(negDirectionCutoff.low), int(negDirectionCutoff.high), 0, int(videoHeight), (0, 255, 255), 0.1)
	if shouldCamera:
		cv.imshow("Final", img)
		key = cv.waitKey(1) & 0xFF
		if key == ord("q"):
			break
