from typing import Union, Optional


class FloatRange:
	def __init__(self, low: float, high: float):
		if low > high:
			raise ValueError("Tried to create a FloatRange with low {0} greater than high {0}".format(low, high))
		self.low = low
		self.high = high

	@staticmethod
	def fromStringWithDefaults(string: str, low: Optional[float] = None, high: Optional[float] = None) -> "FloatRange":
		pieces = string.split("-")
		if str == "":
			if low is not None and high is not None:
				return FloatRange(low, high)
			else:
				raise ValueError("String was empty and at least one default was missing")
		if len(pieces) == 1:
			if low is None and high is not None:
				return FloatRange(float(pieces[0]), high)
			elif high is None and low is not None:
				return FloatRange(low, float(pieces[0]))
			else:
				raise ValueError("FromStringWithDefaults called with no defaults")
		else:
			a = float(pieces[0])
			b = float(pieces[1])
			if a > b:
				return FloatRange(b, a)
			else:
				return FloatRange(a, b)

	def __contains__(self, item: Union[float, "FloatRange"]) -> bool:
		if item is FloatRange:
			return self.low <= item.low and self.high >= item.high
		else:
			return self.low <= item <= self.high

	def __mul__(self, other: float) -> "FloatRange":
		return FloatRange(self.low * other, self.high * other)

	def __add__(self, other: float) -> "FloatRange":
		return FloatRange(self.low + other, self.high + other)

	def __str__(self):
		return "({0} ... {1})".format(self.low, self.high)
