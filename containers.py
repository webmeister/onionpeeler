import cachecontrol
import collections
import functools
import requests
import time


class Operator:
	def __init__(self, name, data):
		self.name = name
		self.subgroups = {}
		self.search_criteria = collections.defaultdict(frozenset)

		is_container = True
		for value in data.values():
			if not isinstance(value, dict):
				is_container = False
				break

		if is_container:
			for key, value in data.items():
				self.subgroups[key] = Operator(key, value)
			for subitem in self.subgroups.values():
				for key, value in subitem.search_criteria.items():
					self.search_criteria[key] = self.search_criteria[key] | value
		else:
			for key, value in data.items():
				self.search_criteria[key] = frozenset(value)

	def resolve(self, path):
		return self.subgroups[path[0]].resolve(path[1:]) if path else self


class Relays:
	def __init__(self, sources, ttl):
		self.sources = sources
		self.session = cachecontrol.CacheControl(requests.session())
		self.data = []
		self.ttl = ttl
		self.last_refresh = 0

	def reload(self):
		for index, source in enumerate(self.sources):
			try:
				result = self.session.get(source, timeout=1).json()['relays']
			except Exception:
				result = []
			else:
				if index != 0:
					self.sources[0], self.sources[index] = self.sources[index], self.sources[0]
				break

		if result != self.data:
			self.query_cache.cache_clear()
			self.data = result

	@functools.lru_cache()
	def query_cache(self, **fields):
		fingerprints = set()
		for relay in self.data:
			if any(relay.get(field, '') in values for field, values in fields.items()):
				fingerprints.add(relay['fingerprint'])
				for fingerprint in relay.get('effective_family', []) or relay.get('family', []):
					fingerprints.add(fingerprint[1:])
		return [relay for relay in self.data if relay['fingerprint'] in fingerprints]

	def search(self, operator=None):
		if time.time() - self.last_refresh > self.ttl:
			self.reload()
			self.last_refresh = time.time()
		return self.query_cache(**operator.search_criteria) if operator else self.data
