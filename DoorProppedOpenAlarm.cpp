// TODO: Convert to python and add sounds

#include <opencv2/opencv.hpp>
#include <iostream>

const static cv::Mat dilation = cv::getStructuringElement(cv::MORPH_ELLIPSE, { 2, 2 });
const static cv::Mat erosion = cv::getStructuringElement(cv::MORPH_ELLIPSE, { 6, 6 });
const static cv::Rect leftDoorMask(440, 270, 90, 230);
const static cv::Rect rightDoorMask(540, 270, 90, 230);
const static cv::Scalar_<double> expectedDoorColor(73, 113, 115, 0);
const static int movementCutoff = 100;
const static double colorDifferenceCutoff = 50;

int getDifference(cv::Mat a, cv::Mat b) {
	cv::Mat diff;
	cv::absdiff(a, b, diff);
	cv::Mat thresh;
	cv::threshold(diff, thresh, 20, 255, cv::THRESH_BINARY);
	cv::Mat dilated;
	cv::dilate(thresh, dilated, dilation);
	cv::Mat eroded;
	cv::erode(dilated, eroded, erosion);
	return cv::countNonZero(eroded);
}

double getDifference(cv::Scalar_<double> a, cv::Scalar_<double> b) {
	return abs(a(0) - b(0)) + abs(a(1) - b(1)) + abs(a(2) - b(2)) + abs(a(3) - b(3));
}

int main(int argc, const char * argv[]) {
	cv::VideoCapture camera = cv::VideoCapture("rtsp://10.0.8.21/live1.sdp");
	int count = 0;
	cv::Mat img;
	cv::Mat grey;
	cv::Mat prevGrey;
	
	int timeSinceLastMovement = 0;
	int timeSinceLastClosed = 0;
	
	while (1) {
		count++;
		std::swap(grey, prevGrey);
		if (!camera.grab()) { break; }
		if (!camera.retrieve(img)) { break; }

		cv::cvtColor(img, grey, cv::COLOR_RGB2GRAY);
		if (count == 1) {
			continue;
		}
		
		int diff = getDifference(grey, prevGrey);
		
		cv::Mat leftDoor = img(leftDoorMask);
		cv::Mat rightDoor = img(rightDoorMask);
		auto leftDoorColor = cv::mean(leftDoor);
		auto rightDoorColor = cv::mean(rightDoor);
		auto leftDoorDifference = getDifference(leftDoorColor, expectedDoorColor);
		auto rightDoorDifference = getDifference(rightDoorColor, expectedDoorColor);
		if (diff > movementCutoff) {
			timeSinceLastMovement = 0;
		}
		else {
			timeSinceLastMovement += 1;
		}
		if (rightDoorDifference < colorDifferenceCutoff && leftDoorDifference < colorDifferenceCutoff) {
			timeSinceLastClosed = 0;
		}
		else {
			timeSinceLastClosed += 1;
		}
		
		std::cout << "Last movement: " << timeSinceLastMovement << ", Last closed: " << timeSinceLastClosed << std::endl;
		
//		std::cout << "Left door: " << leftDoorDifference << ", Right door: " << rightDoorDifference << std::endl;
//		cv::imshow("Left Door", leftDoor);
//		cv::imshow("Right Door", rightDoor);
//		int key = cv::waitKey(1);
//		if (key == 'q') {
//			break;
//		}
	}
	return 0;
}
