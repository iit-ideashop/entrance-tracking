import cv2 as cv
import sys
import math
import time
import os
import argparse

## Configuration
# Box comparison options
maxDistanceDifference = 200 # Maximum movement between centers of two boxes for them to be considered as the same box moving (anything that moves more than this in one frame will be considered as two separate boxes)
maxPctAreaDifference = 0.5 # Maximum change in area between two boxes for them to be considered as the same box.  This is a percentage, if the smaller box is less than this fraction in area of the bigger box, it will be considered.
minHeight = 300 # Anyone higher than this in the video will be ignored (note that OpenCV coordinates are from the top left, so 0 is the most permissive).  This is to remove people who are close to the camera, people far from the camera will be near the center while people close to the camera will extend higher.
# Person detection options
minSize = 20000 # The minimum size of a box for it to be considered a person

parser = argparse.ArgumentParser(description="Detect people and play sounds")
parser.add_argument("camera", type=int, help="The OpenCV id of the camera to use")
parser.add_argument("--min-size", dest="minSize", type=int, default=minSize, help="The minimum size of a box for it to be considered a person")
parser.add_argument("--min-height", dest="minHeight", type=int, default=minHeight, help="The highest a box can go while still being considered (low numbers == high pixels)")
parser.add_argument("--max-distance", dest="maxDistance", type=int, default=maxDistanceDifference, help="The maximum movement between centers of two boxes for them to be considered as the same box moving")
parser.add_argument("--max-area-diff", dest="maxAreaDiff", type=float, default=maxPctAreaDifference, help="The maximum change in area between two boxes for them to be considered as the same box")
parser.add_argument("--verbose", "-v", dest="verbose", action="store_true", help="Verbose mode")
parser.add_argument("--live", "-l", dest="live", action="store_true", help="Enables live camera feed window")
args = parser.parse_args(sys.argv[1:])
verbose = args.verbose
shouldCamera = args.live

maxDistanceDifference = args.maxDistance
maxPctAreaDifference = args.maxAreaDiff
minHeight = args.minHeight
minSize = args.minSize

# Pass camera as first program argument
camera = args.camera
if verbose:
	print("Using camera " + str(camera))
video = cv.VideoCapture(camera)

import pygame
pygame.mixer.init()
outSegment = pygame.mixer.Sound("audio/out.ogg")
inSegment = pygame.mixer.Sound("audio/in.ogg")

# Person must be moving in the same direction for this amount of pixels before a notice is played
requiredTimeToActivate = 0.2
requiredDistanceToActivate = 100 # Pixels
# The same notice won't be played more than once ever this number of seconds
minTimeBetweenPlays = 6
# Function that is run if a person is detected walking in the positive direction (from left to right in camera view)
def playSoundMovingPositive():
	if verbose: print("Playing sound!")
	outSegment.play()
# Function that is run if a person is detected walking in the negative direction (from right to left in camera view)
def playSoundMovingNegative():
	inSegment.play()

videoWidth = video.get(cv.CAP_PROP_FRAME_WIDTH)
videoHeight = video.get(cv.CAP_PROP_FRAME_HEIGHT)
areaModifier = (videoWidth * videoHeight) / (1920 * 1080)
widthModifier = videoWidth / 1920
heightModifier = videoHeight / 1080

maxDistanceDifference *= widthModifier
minSize *= areaModifier
requiredDistanceToActivate *= widthModifier
minHeight *= heightModifier

_, last = video.read()
last = cv.cvtColor(last, cv.COLOR_BGR2GRAY)
lastContours = []
lastPlay = 0
class ChangeTracker:
	def __init__(self, distanceToActivate, minTimeBetweenPlays):
		self.distanceToActivate = distanceToActivate
		self.minTimeBetweenPlays = minTimeBetweenPlays
		self.OKStart = time.time()
		self.lastPlay = 0
		self.totalDist = 0

	def update(self, distance):
		if distance == 0:
			self.distance = 0
		else:
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
			self.lastPlay = time.time()
			return True
		else:
			return False
negTracker = ChangeTracker(-requiredDistanceToActivate, minTimeBetweenPlays)
posTracker = ChangeTracker(requiredDistanceToActivate, minTimeBetweenPlays)

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
	if posTracker.shouldActivate():
		playSoundMovingPositive()
		posTracker.update(0)
		negTracker.update(0)
	elif negTracker.shouldActivate():
		playSoundMovingNegative()
		posTracker.update(0)
		negTracker.update(0)
	

while True:
	grabbed, img = video.read()
	if not grabbed:
		break

	gray = cv.cvtColor(img, cv.COLOR_BGR2GRAY)
	contours = compareImages(last, gray)	

	for contour in contours:
		(x, y, w, h) = cv.boundingRect(contour)
		# Draw boxes
		cv.rectangle(img, (x, y), (x + w, y + h), (0, 255, 0), 2)

	distance = 0
	foundPos = False
	foundNeg = False
	for lastBox in lastContours:
		for curBox in contours:
			points = areSimilar(lastBox, curBox)
			if points == None:
				continue
			if (points[0][0] < points[1][0]):
				cv.arrowedLine(img, points[0], points[1], (0, 255, 255), thickness=2)
				foundPos = True
			else:
				cv.arrowedLine(img, points[0], points[1], (0, 0, 255), thickness=2)
				foundNeg = True
			distance += (points[0][0] - points[1][0])
	negTracker.update(distance)
	posTracker.update(distance)
	checkAndPlaySound()

	last = gray
	lastContours = contours

	if shouldCamera:
		cv.imshow("Final", img)
		key = cv.waitKey(1) & 0xFF
		if key == ord("q"):
			break
